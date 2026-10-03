# zip-portability

Find common ZIP filename problems before sending an archive to someone on
another operating system. Inspect metadata locally without extracting files,
opening entry payloads, modifying the archive, or making network requests.

Python 3.10+, zero runtime dependencies.

## Quick start

~~~sh
python -m pip install .
zip-portability release.zip
zip-portability release.zip --format json
~~~

Run without installing using `python -m zip_portability`.

Create a synthetic demonstration archive without extracting it:

~~~sh
python examples/create_demo.py demo.zip
zip-portability demo.zip
~~~

The demo deliberately contains problematic names; use it for inspection only.

## Checks

- Exact duplicate names and collisions after NFC normalization, trailing
  space/period removal, and Unicode case folding.
- File/directory conflicts and files also used as parent directories.
- Absolute/UNC paths, Windows drive names, parent traversal, backslashes, and
  redundant path components.
- Windows-reserved characters and device names such as CON, NUL, COM1, LPT9,
  including reserved superscript forms.
- Path and component lengths measured in UTF-16 units.
- Unix symlinks and encrypted-entry flags requiring extractor-specific support.
- Declared uncompressed size and compression ratios above configured limits.

The filename rules follow
[Microsoft's naming guidance](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).
Collision matching is intentionally conservative; it does not exactly simulate
every filesystem's case or normalization rules.

## Limits and automation

~~~sh
zip-portability release.zip --max-path-units 240 --max-total-bytes 1073741824 --max-ratio 1000 --max-issues 100
~~~

These are also the defaults. The path limit applies to the archive-relative path;
an extraction destination prefix can make the final path longer. Components
over 255 UTF-16 units are reported separately.

JSON contains entry/size counts, total findings, and a capped issue list.
Every issue includes its entry number, decoded name, code, and an earlier entry
number when relevant. Filenames remain visible; text output escapes control
characters. Counts cover the whole archive even when the issue list is capped.

Exit codes: `0` no findings, `1` findings, `2` unreadable/invalid ZIP or arguments.

## Scope

The tool reads central-directory metadata through Python's zipfile module.
It never decompresses data or writes extracted paths. Declared sizes and ratios
are estimates from metadata, not measured expanded content.

This is a portability review aid, not an extraction sandbox or a complete
malicious-archive detector. It does not verify CRCs, payload integrity, matching
local headers, overlapping compressed data, nested archives, or extractor
behavior. A report with no findings does not certify extraction safety.
Memory use grows with the central directory and distinct filenames.

Legacy filename encoding is handled by Python's standard ZIP decoding rules.
The tool does not auto-detect every locale-specific encoding or rename entries.

## Development

~~~sh
python -m unittest discover -s tests -v
~~~

Tests cover actual synthetic ZIPs, Unicode collisions, Windows names, path
conflicts, metadata flags, report limits, and the absence of payload reads.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Related projects

[zip-porter](https://github.com/nlink-jp/zip-porter) creates and extracts
Windows-compatible archives on macOS.
[ronomon/pure](https://github.com/ronomon/pure) performs deeper archive analysis.
zip-portability focuses on a small cross-platform metadata inspection CLI.
This is an independent implementation with no copied source code.

Licensed under [MIT](LICENSE).
