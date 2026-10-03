import contextlib
import io
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile
from zip_portability.cli import main
from zip_portability.core import inspect_archive


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.zip"

    def create(self, names):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in names:
                    archive.writestr(name, "Synthetic data\n")

    def codes(self, **options):
        return {issue["code"] for issue in inspect_archive(self.path, **options)["issues"]}

    def test_nonfinite_limit_is_rejected(self):
        self.create([])
        with self.assertRaises(ValueError):
            inspect_archive(self.path, max_ratio=float("nan"))

    def test_normal_archive_and_empty_archive(self):
        self.create(["docs/", "docs/README.md", "assets/資料.txt"])
        self.assertTrue(inspect_archive(self.path)["ok"])
        self.create([])
        self.assertTrue(inspect_archive(self.path)["ok"])

    def test_case_and_unicode_normalization_collisions(self):
        self.create(["Readme.md", "README.md", "café.txt", "cafe\u0301.txt"])
        report = inspect_archive(self.path)
        self.assertEqual(2, report["issues_total"])
        self.assertEqual({"portable_collision"}, self.codes())

    def test_trailing_name_alias_and_exact_duplicate(self):
        self.create(["file.txt", "file.txt.", "duplicate", "duplicate"])
        self.assertEqual({"trailing_character", "portable_collision", "duplicate_name"}, self.codes())

    def test_reserved_names_include_extensions_and_superscripts(self):
        self.create(["CON.txt", "nested/aux.log", "COM¹.txt", "LPT9", "console.txt"])
        report = inspect_archive(self.path)
        self.assertEqual(4, len([item for item in report["issues"] if item["code"] == "reserved_name"]))

    def test_windows_characters_and_backslashes(self):
        self.create(["file:name", "bad?.txt", "folder/item.txt", "line\nbreak"])
        data = self.path.read_bytes().replace(b"folder/item.txt", b"folder\\item.txt")
        self.path.write_bytes(data)
        self.assertEqual({"windows_character", "backslash"}, self.codes())

    def test_absolute_drive_and_parent_paths(self):
        self.create(["/absolute", "C:/drive.txt", "../outside", r"..\outside"])
        self.assertTrue({"absolute_path", "drive_path", "parent_traversal"}.issubset(self.codes()))

    def test_file_directory_and_parent_conflicts(self):
        self.create(["a", "a/child.txt", "b/", "b"])
        self.assertEqual({"file_as_directory", "path_conflict"}, self.codes())

    def test_conflicting_parent_is_found_regardless_of_entry_order(self):
        self.create(["a/child.txt", "a"])
        self.assertIn("file_as_directory", self.codes())

    def test_redundant_components(self):
        self.create(["./file.txt", "nested//file.txt"])
        self.assertIn("noncanonical_path", self.codes())

    def test_utf16_length_and_configurable_total_size(self):
        self.create(["😀" * 121 + ".txt"])
        self.assertIn("long_path", self.codes())
        self.assertNotIn("long_path", self.codes(max_path_units=1000))
        self.assertIn("total_size", self.codes(max_total_bytes=1))

    def test_long_component(self):
        self.create(["a" * 256])
        self.assertIn("long_component", self.codes(max_path_units=1000))

    def test_symlink(self):
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.create([info])
        self.assertIn("symlink", self.codes())

    def test_encrypted_central_directory_flag(self):
        self.create(["private.txt"])
        data = bytearray(self.path.read_bytes())
        central = data.index(b"PK\x01\x02")
        flags = struct.unpack_from("<H", data, central + 8)[0]
        struct.pack_into("<H", data, central + 8, flags | 1)
        self.path.write_bytes(data)
        self.assertIn("encrypted", self.codes())

    def test_nul_original_name_is_not_hidden_by_zipinfo_truncation(self):
        self.create(["badXname"])
        data = self.path.read_bytes().replace(b"badXname", b"bad\x00name")
        self.path.write_bytes(data)
        self.assertIn("windows_character", self.codes())

    def test_declared_ratio_threshold(self):
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("large.txt", "x" * 100000)
        self.assertIn("compression_ratio", self.codes(max_ratio=10))

    def test_issue_cap_keeps_full_counts(self):
        self.create([f"CON.{index}" for index in range(25)])
        report = inspect_archive(self.path, max_issues=2)
        self.assertEqual(25, report["issues_total"])
        self.assertEqual(2, len(report["issues"]))
        self.assertTrue(report["issues_truncated"])

    def test_payload_is_never_opened_and_archive_is_unchanged(self):
        self.create(["normal.txt"])
        before = self.path.read_bytes()
        with mock.patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("No payload reads")):
            self.assertTrue(inspect_archive(self.path)["ok"])
        self.assertEqual(before, self.path.read_bytes())

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main([str(self.path), *args])
        return code, output.getvalue(), errors.getvalue()

    def test_json_and_validation_exit_code(self):
        self.create(["CON.txt"])
        code, output, _ = self.invoke("--format", "json")
        self.assertEqual(1, code)
        self.assertFalse(json.loads(output)["ok"])

    def test_bad_archive_and_missing_file_exit_code(self):
        self.path.write_text("not a zip")
        self.assertEqual(2, self.invoke()[0])
        self.path.unlink()
        self.assertEqual(2, self.invoke()[0])

    def test_module_subprocess(self):
        self.create(["README.md"])
        result = subprocess.run([sys.executable, "-m", "zip_portability", str(self.path)],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
