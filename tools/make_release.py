"""Build the offline release zip (Ticket-04 part 5): dist/dao-den-long-v1.0.0.zip

python3 tools/make_release.py [--version 1.0.0] [--no-vendor]

Contents (inside one top folder dao-den-long-v<version>/):
  web/ (with web/vendor/: three.js + Pyodide, so it runs without internet), game/, serve.py, headless.py,
  bench.py, soak.py, game.contract.json, README.md, LICENSE, CREDITS.md, CHANGELOG.md, START-HERE.txt,
  plus any local image the README shows.
Unzip, run `python3 serve.py`, open http://127.0.0.1:8000/web/ . Python 3.8+ only, nothing to install.
web/vendor is fetched first (tools/fetch_vendor.py) when it is missing; --no-vendor builds a zip that needs
the CDN instead. Exit 0 = zip written and verified, 1 = failure. Pure stdlib.
"""
import argparse
import hashlib
import os
import re
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch_vendor  # noqa: E402

TOP_FILES = ["serve.py", "headless.py", "bench.py", "soak.py", "game.contract.json",
             "README.md", "LICENSE", "CREDITS.md", "CHANGELOG.md"]
TOP_DIRS = ["web", "game"]
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIX = (".pyc", ".pyo", ".part", ".tmp")

START_HERE = """Dao Den Long v{version} - offline release

1. Install Python 3.8 or newer (https://www.python.org/downloads/). Nothing else to install.
2. In this folder run:   python3 serve.py        (Windows: python serve.py)
3. The browser opens http://127.0.0.1:8000/web/   (Chrome, Edge, Firefox or Safari). No internet needed.

Other commands (see README.md):
  python3 headless.py --seed 1 --night 1 --ticks 600 --out out.jsonl
  python3 soak.py --seed 7 --nights 10 --out soak.json
  python3 bench.py --seed 42 --duration 30 --out bench.json      (needs Chrome, Chromium or Edge)
  python3 serve.py --export-leaderboard leaderboard.json
"""


def walk(rel_dir):
    """Yield (relative posix path, absolute path) for every file under rel_dir, sorted."""
    base = os.path.join(ROOT, rel_dir)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(SKIP_SUFFIX):
                continue
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, ROOT).replace(os.sep, "/"), full


def readme_images():
    """Local images the README embeds (markdown ![..](path) and <img src=...>)."""
    try:
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    refs = re.findall(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)", text) + re.findall(r"<img[^>]+src=[\"']([^\"']+)", text)
    out = []
    for ref in refs:
        ref = ref.split("#")[0].split("?")[0]
        if not ref or re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I) or ref.startswith("/"):
            continue
        full = os.path.normpath(os.path.join(ROOT, ref))
        if full.startswith(ROOT + os.sep) and os.path.isfile(full):
            out.append((os.path.relpath(full, ROOT).replace(os.sep, "/"), full))
    return out


def collect(include_vendor):
    files = {}
    for d in TOP_DIRS:
        for rel, full in walk(d):
            if not include_vendor and rel.startswith("web/vendor/"):
                continue
            files[rel] = full
    for name in TOP_FILES:
        full = os.path.join(ROOT, name)
        if os.path.isfile(full):
            files[name] = full
        else:
            print(f"warning: {name} not found, left out", file=sys.stderr)
    for rel, full in readme_images():
        files[rel] = full
    return files


def add(z, arcname, data=None, path=None):
    st_time = (2026, 1, 1, 0, 0, 0)
    if path is not None:
        t = time.localtime(os.path.getmtime(path))[:6]
        st_time = t if t[0] >= 1980 else st_time
        with open(path, "rb") as f:
            data = f.read()
    info = zipfile.ZipInfo(arcname, date_time=st_time)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o644 << 16)
    z.writestr(info, data)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build dist/dao-den-long-v<version>.zip")
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--no-vendor", action="store_true", help="do not bundle web/vendor (zip then needs the CDN)")
    a = ap.parse_args(argv)

    if not a.no_vendor:
        if fetch_vendor.main(["--check"]) != 0:
            print("web/vendor incomplete: fetching ...")
            if fetch_vendor.main([]) != 0:
                print("error: cannot bundle web/vendor (offline?). Retry online, or use --no-vendor.",
                      file=sys.stderr)
                return 1
    files = collect(include_vendor=not a.no_vendor)
    top = f"dao-den-long-v{a.version}"
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{top}.zip")
    tmp = out + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in sorted(files):
                add(z, f"{top}/{rel}", path=files[rel])
            add(z, f"{top}/START-HERE.txt", data=START_HERE.format(version=a.version).encode("utf-8"))
        with zipfile.ZipFile(tmp) as z:       # verify before publishing the file
            bad = z.testzip()
            names = set(z.namelist())
        if bad:
            raise OSError(f"corrupt entry {bad}")
        need = [f"{top}/serve.py", f"{top}/web/index.html", f"{top}/game/sim.py", f"{top}/game.contract.json"]
        if not a.no_vendor:
            need += [f"{top}/web/vendor/three.min.js", f"{top}/web/vendor/pyodide/pyodide.asm.wasm"]
        missing = [n for n in need if n not in names]
        if missing:
            raise OSError(f"zip is missing {missing}")
        os.replace(tmp, out)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    with open(out, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(f"wrote {out}\n  {len(files) + 1} files, {os.path.getsize(out) / 1e6:.1f} MB, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
