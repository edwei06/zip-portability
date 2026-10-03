"""Inspect archive metadata for common filename portability problems."""
from pathlib import Path
import math
import re
import stat
import unicodedata
import zipfile

RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
}
INVALID = re.compile(r'[<>:"|?*\x00-\x1f]')


def units(text):
    return len(text.encode("utf-16-le")) // 2


def inspect_archive(path: Path, *, max_path_units=240, max_total_bytes=1024 ** 3,
                    max_ratio=1000, max_issues=100):
    """Never extract or decompress entries; use central-directory metadata only."""
    if not math.isfinite(max_ratio) or min(max_path_units, max_total_bytes, max_ratio, max_issues) <= 0:
        raise ValueError("Limits must be positive")
    issues, entries, names = [], {}, {}
    issue_count = total_bytes = compressed_bytes = 0

    def add(index, name, code, message, other_entry=None):
        nonlocal issue_count
        issue_count += 1
        if len(issues) < max_issues:
            issues.append({"entry": index, "name": name, "code": code,
                           "message": message, "other_entry": other_entry})

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        for index, info in enumerate(infos, 1):
            # CPython retains the original decoded name before NUL truncation.
            name = getattr(info, "orig_filename", info.filename)
            normalized = name.replace("\\", "/")
            parts = [part for part in normalized.split("/") if part]
            is_directory = info.is_dir() or normalized.endswith("/")
            total_bytes += info.file_size
            compressed_bytes += info.compress_size
            if not parts:
                add(index, name, "empty_name", "Entry has no usable filename")
            if normalized.startswith("/"):
                add(index, name, "absolute_path", "Entry uses an absolute or UNC path")
            if re.match(r"^[A-Za-z]:", normalized):
                add(index, name, "drive_path", "Entry uses a Windows drive designator")
            if ".." in parts:
                add(index, name, "parent_traversal", "Entry contains a parent-directory component")
            if "\\" in name:
                add(index, name, "backslash", "ZIP paths should use forward slashes")
            if "." in parts or "//" in normalized:
                add(index, name, "noncanonical_path", "Entry contains redundant path components")
            if any(INVALID.search(part) for part in parts):
                add(index, name, "windows_character", "Entry contains Windows-reserved characters")
            if any(part.endswith((" ", ".")) and part not in (".", "..") for part in parts):
                add(index, name, "trailing_character", "A component ends with a space or period")
            if any(part.split(".", 1)[0].rstrip(" ").upper() in RESERVED for part in parts):
                add(index, name, "reserved_name", "A component uses a Windows device name")
            if units(normalized) > max_path_units:
                add(index, name, "long_path", "Relative path exceeds the configured UTF-16 length")
            if any(units(part) > 255 for part in parts):
                add(index, name, "long_component", "A component exceeds 255 UTF-16 units")
            mode = (info.external_attr >> 16) & 0xFFFF
            if info.create_system == 3 and stat.S_ISLNK(mode):
                add(index, name, "symlink", "Symlink behavior varies between extractors")
            if info.flag_bits & 1:
                add(index, name, "encrypted", "Encrypted entry requires compatible extractor support")
            if info.file_size / max(info.compress_size, 1) > max_ratio:
                add(index, name, "compression_ratio", "Declared compression ratio exceeds the limit")
            canonical = "/".join(unicodedata.normalize("NFC", part).rstrip(" .").casefold()
                                 for part in parts if part != ".")
            if name in names:
                add(index, name, "duplicate_name", "Archive repeats an exact entry name", names[name])
            elif canonical in entries:
                previous = entries[canonical]
                code = "path_conflict" if is_directory != previous["directory"] else "portable_collision"
                add(index, name, code, "Names collide after conservative normalization", previous["index"])
            names.setdefault(name, index)
            entries.setdefault(canonical, {"index": index, "name": name,
                                          "directory": is_directory})
        for canonical, entry in entries.items():
            components = canonical.split("/")
            for depth in range(1, len(components)):
                parent = entries.get("/".join(components[:depth]))
                if parent and not parent["directory"]:
                    add(entry["index"], entry["name"], "file_as_directory",
                        "A file entry is also used as a parent directory", parent["index"])
        if total_bytes > max_total_bytes:
            add(0, None, "total_size", "Declared uncompressed size exceeds the configured limit")
    return {"ok": issue_count == 0, "entries": len(infos), "declared_bytes": total_bytes,
            "compressed_bytes": compressed_bytes, "issues_total": issue_count,
            "issues_truncated": issue_count > len(issues), "issues": issues}
