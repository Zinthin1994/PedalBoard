"""Build dist/PedalBoard.zip from the files tracked in git (personal files are never tracked)."""
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    version = re.search(r'VERSION = "([^"]+)"', open(os.path.join(ROOT, "version.py")).read()).group(1)
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "PedalBoard.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(ROOT, f), "PedalBoard/" + f)
    print(f"PedalBoard {version}: {len(files)} files -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
