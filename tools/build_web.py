"""Build dist/dao-den-long.html: one self-contained file (game/sim.py + its helper modules inlined).
Used for the GitHub Release and the claude.ai Artifact. python3 tools/build_web.py

game/sim.py goes into <script id="sim-src">; every other game/*.py (e.g. maps.py) goes into
<script type="text/x-python" data-module="NAME"> so the page can write them into Pyodide's FS."""
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
tag = '<script type="text/x-python" id="sim-src"></script>'
assert tag in html


def read(path):
    src = open(path, encoding="utf-8").read()
    assert "</script" not in src, path
    return src


blocks = ['<script type="text/x-python" id="sim-src">\n' + read(os.path.join(ROOT, "game", "sim.py")) + "</script>"]
for path in sorted(glob.glob(os.path.join(ROOT, "game", "*.py"))):
    name = os.path.splitext(os.path.basename(path))[0]
    if name in ("sim", "__init__"):
        continue
    blocks.append(f'<script type="text/x-python" id="{name}-src" data-module="{name}">\n' + read(path) + "</script>")
os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
out = os.path.join(ROOT, "dist", "dao-den-long.html")
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(html.replace(tag, "\n".join(blocks)))
print("wrote", out, "modules:", ["sim"] + [b.split('data-module="')[1].split('"')[0] for b in blocks[1:]])
