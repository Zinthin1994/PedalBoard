"""PedalBoard self-update from GitHub releases (same approach as PlayVault).

PedalBoard checks once when it opens - never in the background or on a timer. Only
published releases count (not drafts, pre-releases or plain pushes). Installing:
  1. download PedalBoard.zip from the latest release and verify it against the
     SHA-256 digest GitHub publishes for the asset,
  2. unpack it into update/extract and check it really is that version,
  3. back up every file it will replace into backup/<old version>/,
  4. copy the new files over the app (your settings, presets and recordings are
     never touched) and install any new Python requirements,
  5. write update/pending.json and restart through launch.py.
If the new version fails to start, launch.py restores the backup (rollback()).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile

from version import REPO, VERSION

HERE = os.path.dirname(os.path.abspath(__file__))
API = (os.environ.get("PEDALBOARD_UPDATE_API") or "https://api.github.com").rstrip("/")
ASSET = "PedalBoard.zip"
MAX_SIZE = 50 * 1024 * 1024
UPDATE_DIR = os.path.join(HERE, "update")
BACKUP_DIR = os.path.join(HERE, "backup")
PENDING = os.path.join(UPDATE_DIR, "pending.json")
USER_AGENT = f"PedalBoard/{VERSION}"
# never overwritten by an update
PROTECTED = re.compile(r"^(settings_.*\.json|presets_.*\.json|old/.*|backup/.*|update/.*|tests/out.*)$")


def parse_version(v):
    m = re.match(r"^v?(\d+(?:\.\d+)*)$", (v or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def newer(a, b):
    """True if version string a is newer than b."""
    pa, pb = parse_version(a), parse_version(b)
    return bool(pa and pb and pa > pb)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _python_console():
    """python.exe next to the running interpreter (pythonw has no console for pip)."""
    d = os.path.dirname(sys.executable)
    p = os.path.join(d, "python.exe")
    return p if os.path.isfile(p) else sys.executable


def _pythonw():
    d = os.path.dirname(sys.executable)
    p = os.path.join(d, "pythonw.exe")
    return p if os.path.isfile(p) else sys.executable


class Updater:
    """status: idle checking uptodate available downloading installing ready error"""

    def __init__(self):
        self.status = "idle"
        self.latest = None
        self.notes = ""
        self.url = f"https://github.com/{REPO}/releases"
        self.error = None
        self.progress = 0
        self._asset = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- check
    def check_async(self):
        threading.Thread(target=self.check, daemon=True).start()

    def check(self):
        with self._lock:
            try:
                self.status, self.error = "checking", None
                req = urllib.request.Request(f"{API}/repos/{REPO}/releases/latest",
                                             headers={"User-Agent": USER_AGENT,
                                                      "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    rel = json.loads(r.read())
                tag = rel.get("tag_name")
                if not parse_version(tag):
                    raise RuntimeError(f"Unexpected release tag {tag!r}")
                self.latest = tag.lstrip("v")
                self.notes = (rel.get("body") or "").strip()[:2000]
                self.url = rel.get("html_url") or self.url
                self._asset = next((a for a in rel.get("assets") or [] if a.get("name") == ASSET), None)
                self.status = "available" if newer(self.latest, VERSION) and self._asset else "uptodate"
            except Exception as e:   # noqa: BLE001 - offline etc. is not fatal
                self.status, self.error = "error", str(e)
        return self.status

    # ---------------------------------------------------------------- install
    def install_async(self):
        threading.Thread(target=self.install, daemon=True).start()

    def install(self):
        with self._lock:
            try:
                self._install()
                self.status = "ready"
            except Exception as e:   # noqa: BLE001
                self.status, self.error = "error", str(e)
        return self.status

    def _install(self):
        asset = self._asset
        if not asset:
            raise RuntimeError("No update to install")
        digest = asset.get("digest") or ""
        if not digest.startswith("sha256:"):
            raise RuntimeError("The release file has no SHA-256 checksum - not installing it")
        if int(asset.get("size") or 0) > MAX_SIZE:
            raise RuntimeError("The release file is unexpectedly large - not installing it")

        os.makedirs(UPDATE_DIR, exist_ok=True)
        zpath = os.path.join(UPDATE_DIR, ASSET + ".part")
        extract = os.path.join(UPDATE_DIR, "extract")
        self.status, self.progress = "downloading", 0
        h, got, size = hashlib.sha256(), 0, int(asset.get("size") or 0)
        req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r, open(zpath, "wb") as f:
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_SIZE:
                    raise RuntimeError("Download is larger than expected")
                h.update(chunk)
                f.write(chunk)
                if size:
                    self.progress = min(99, int(got * 100 / size))
        if h.hexdigest() != digest.split(":", 1)[1].lower():
            os.remove(zpath)
            raise RuntimeError("Downloaded update does not match its checksum - discarded")

        self.status = "installing"
        shutil.rmtree(extract, ignore_errors=True)
        with zipfile.ZipFile(zpath) as z:
            _safe_extract(z, extract)
        os.remove(zpath)
        root = os.path.join(extract, "PedalBoard")
        m = re.search(r'VERSION = "([^"]+)"', _read(os.path.join(root, "version.py")))
        if not m or m.group(1) != self.latest or not os.path.isfile(os.path.join(root, "app_v3.py")):
            shutil.rmtree(extract, ignore_errors=True)
            raise RuntimeError("The downloaded update is not a valid PedalBoard release")

        new_files = []
        for dp, _, files in os.walk(root):
            for name in files:
                rel = os.path.relpath(os.path.join(dp, name), root).replace("\\", "/")
                if not PROTECTED.match(rel):
                    new_files.append(rel)

        old_req = _read(os.path.join(HERE, "requirements.txt"))
        backup = os.path.join(BACKUP_DIR, VERSION)
        shutil.rmtree(backup, ignore_errors=True)
        added = []
        for rel in new_files:                      # back up what we replace, remember what's new
            cur = os.path.join(HERE, rel)
            if os.path.isfile(cur):
                os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
                shutil.copy2(cur, os.path.join(backup, rel))
            else:
                added.append(rel)
        with open(PENDING, "w", encoding="utf-8") as f:   # written before copying: rollback info
            json.dump({"from": VERSION, "to": self.latest, "backup": backup, "added": added,
                       "notes": self.notes}, f)
        for rel in new_files:
            dst = os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(root, rel), dst)
        shutil.rmtree(extract, ignore_errors=True)

        if _read(os.path.join(HERE, "requirements.txt")) != old_req:
            subprocess.run([_python_console(), "-m", "pip", "install", "--quiet", "-r",
                            os.path.join(HERE, "requirements.txt")],
                           cwd=HERE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)


def restart():
    """Start a fresh PedalBoard through the launcher (call after the old one shut down)."""
    subprocess.Popen([_pythonw(), os.path.join(HERE, "launch.py")], cwd=HERE)


def pending():
    return _read_json(PENDING)


def confirm():
    """The new version started fine: drop the rollback info. Returns the update info or None."""
    info = pending()
    if info:
        try:
            os.remove(PENDING)
        except OSError:
            pass
    return info


def rollback():
    """Restore the files backed up before the last update."""
    info = pending()
    if not info:
        return None
    backup = info.get("backup")
    if backup and os.path.isdir(backup):
        for dp, _, files in os.walk(backup):
            for name in files:
                src = os.path.join(dp, name)
                rel = os.path.relpath(src, backup)
                shutil.copy2(src, os.path.join(HERE, rel))
    for rel in info.get("added", []):
        try:
            os.remove(os.path.join(HERE, rel))
        except OSError:
            pass
    os.remove(PENDING)
    return info


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _safe_extract(z, dest):
    base = os.path.realpath(dest)
    for name in z.namelist():
        target = os.path.realpath(os.path.join(dest, name))
        if not target.startswith(base + os.sep):
            raise RuntimeError(f"Unsafe path in update archive: {name}")
    z.extractall(dest)
