"""Create a synthetic ZIP with portability problems; never extract it."""
import argparse
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("output", help="New synthetic ZIP path")
args = parser.parse_args()
with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in ("Readme.md", "README.md", "assets/CON.txt", "assets/trailing. ",
                 "docs/file.txt", "../outside.txt"):
        archive.writestr(name, "Synthetic demo content only.\n")
print("Created a synthetic test archive. Inspect it; do not extract it.")
