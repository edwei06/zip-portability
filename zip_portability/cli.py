"""Read-only ZIP portability reporting."""
import argparse
import json
import math
from pathlib import Path
import sys
import zipfile
from . import __version__
from .core import inspect_archive


def positive(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return result


def ratio(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("Expected a positive finite ratio")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ZIP filename portability without extracting entries.")
    parser.add_argument("archive")
    parser.add_argument("--max-path-units", type=positive, default=240)
    parser.add_argument("--max-total-bytes", type=positive, default=1024 ** 3)
    parser.add_argument("--max-ratio", type=ratio, default=1000)
    parser.add_argument("--max-issues", type=positive, default=100)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        report = inspect_archive(Path(args.archive), max_path_units=args.max_path_units,
                                 max_total_bytes=args.max_total_bytes, max_ratio=args.max_ratio,
                                 max_issues=args.max_issues)
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        print("zip-portability: unable to inspect a readable ZIP archive", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    else:
        for issue in report["issues"]:
            name = json.dumps(issue["name"], ensure_ascii=True)
            other = f" (entry {issue['other_entry']})" if issue["other_entry"] else ""
            print(f"{issue['code']} {name}: {issue['message']}{other}")
        print(f"{report['entries']} entries; {report['declared_bytes']} declared bytes; "
              f"{report['issues_total']} issue(s)")
        if report["issues_truncated"]:
            print("Issue list capped; counts cover all entries")
    return 0 if report["ok"] else 1
