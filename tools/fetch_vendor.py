"""Download the web build's third-party files into web/vendor/ so the game runs offline (Ticket-04 part 5).

python3 tools/fetch_vendor.py [--force] [--check]

  web/vendor/three.min.js                        three.js r128
  web/vendor/pyodide/{pyodide.js, pyodide.asm.js, pyodide.asm.wasm, python_stdlib.zip, pyodide-lock.json}
                                                 Pyodide 0.27.2 core (enough for sim.py: json, math, random)
The page uses vendor/ when it is there and falls back to the CDN otherwise. web/vendor/ is gitignored.
Files already present with the right SHA-256 are kept (--force downloads again, --check only verifies).
Exit 0 = all files present and verified, 1 = a download or check failed. Pure stdlib.
"""
import argparse
import hashlib
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "web", "vendor")

PYODIDE = "pyodide@0.27.2"
# SHA-256 of each file (identical on cdnjs/jsDelivr/unpkg when pinned)
SHA256 = {
    "three.min.js": "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2",
    "pyodide/pyodide.js": "ee1ce9d20fd7d5fc6df64f77751bf635e7a929665f2c33bfdaf84c175a525d52",
    "pyodide/pyodide.asm.js": "c5bc43242dbdd922b03fd9f9ca22480d37451238686e84cb38499143f81ec75b",
    "pyodide/pyodide.asm.wasm": "7936ef6019d80723adce4bd86666b84534d071362839f1cf9b2b80bed917c812",
    "pyodide/python_stdlib.zip": "7a4edf94cc3d937ba29078adb857d1646d9ce064ad93e795645d124e212eb5a1",
    "pyodide/pyodide-lock.json": "3a3cfb1c0bc02917a1792c1ecdf2b9b484ca406f5d03cb8af4083e97ec7d706a",
}
# (path under web/vendor, [mirrors], sha256)
FILES = [
    ("three.min.js",
     ["https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
      "https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js",
      "https://unpkg.com/three@0.128.0/build/three.min.js"],
     SHA256["three.min.js"]),
] + [
    (f"pyodide/{name}",
     [f"https://cdn.jsdelivr.net/npm/{PYODIDE}/{name}", f"https://unpkg.com/{PYODIDE}/{name}"],
     SHA256[f"pyodide/{name}"])
    for name in ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "dao-den-long-fetch-vendor"})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if os.path.getsize(tmp) == 0:
            raise OSError("empty download")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch three.js r128 and Pyodide 0.27.2 into web/vendor/")
    ap.add_argument("--force", action="store_true", help="download again even if the file is present")
    ap.add_argument("--check", action="store_true", help="only verify what is there, download nothing")
    a = ap.parse_args(argv)
    failed = 0
    for rel, urls, want in FILES:
        dest = os.path.join(VENDOR, *rel.split("/"))
        if os.path.isfile(dest) and not a.force and (want is None or sha256_of(dest) == want):
            print(f"ok       {rel} ({os.path.getsize(dest):,} bytes)")
            continue
        if a.check:
            print(f"MISSING  {rel}" if not os.path.isfile(dest) else f"BAD HASH {rel}")
            failed += 1
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        last = None
        for url in urls:
            try:
                download(url, dest)
                got = sha256_of(dest)
                if want is not None and got != want:
                    os.unlink(dest)
                    raise OSError(f"SHA-256 mismatch ({got})")
                print(f"fetched  {rel} ({os.path.getsize(dest):,} bytes) sha256={got[:12]} <- {url}")
                break
            except (OSError, ValueError) as e:     # URLError / HTTPError are OSErrors
                last = f"{url}: {e}"
                print(f"  failed {last}", file=sys.stderr)
        else:
            print(f"ERROR    {rel}: all mirrors failed ({last})", file=sys.stderr)
            failed += 1
    if failed:
        print(f"{failed} file(s) missing; the page will use the CDN for them (internet required).", file=sys.stderr)
        return 1
    print(f"web/vendor ready: {VENDOR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
