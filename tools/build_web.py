"""Build dist/dao-den-long.html: one self-contained file (game/sim.py + the modules it imports, inlined).
Used for the GitHub Release and the claude.ai Artifact. python3 tools/build_web.py

game/sim.py goes into <script id="sim-src">; every other game module that sim.py imports (maps.py, found by following the
imports) goes into <script type="text/x-python" data-module="NAME"> so the page can write them into Pyodide's FS.
Server-side modules (leaderboard.py, benchstats.py, procmem.py) are not needed by the page and are left out.

The single file has no web/vendor/ folder, so the vendor-first loader is switched off (DDL_VENDOR = false): three.js and
Pyodide come from the CDN (or from window.PYODIDE_INDEX when the Artifact host provides it). Without /api the leaderboard
falls back to localStorage."""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "game")
html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
tag = '<script type="text/x-python" id="sim-src"></script>'
vendor_flag = "window.DDL_VENDOR = true;"
assert tag in html, "sim-src tag missing in web/index.html"
assert html.count(vendor_flag) == 1, "DDL_VENDOR flag missing in web/index.html"


def read(path):
    src = open(path, encoding="utf-8").read()
    assert "</script" not in src, path
    return src


def local_imports(src):
    """Names of game/*.py modules imported by `src` (import maps / from . import maps / from game.maps import x)."""
    have = {os.path.splitext(f)[0] for f in os.listdir(GAME) if f.endswith(".py") and f != "__init__.py"}
    out = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                parts = a.name.split(".")
                n = parts[1] if parts[0] == "game" and len(parts) > 1 else parts[0]
                if n in have:
                    out.add(n)
        elif isinstance(node, ast.ImportFrom):
            parts = node.module.split(".") if node.module else []
            if parts and parts[0] == "game":
                parts = parts[1:]
            if parts and parts[0] in have:
                out.add(parts[0])
            elif not parts and (node.level > 0 or node.module == "game"):
                out.update(a.name for a in node.names if a.name in have)
    return out


mods = {"sim"}
todo = ["sim"]
while todo:
    name = todo.pop()
    for dep in sorted(local_imports(read(os.path.join(GAME, name + ".py")))):
        if dep not in mods:
            mods.add(dep)
            todo.append(dep)

blocks = ['<script type="text/x-python" id="sim-src">\n' + read(os.path.join(GAME, "sim.py")) + "</script>"]
for name in sorted(mods - {"sim"}):
    blocks.append(f'<script type="text/x-python" id="{name}-src" data-module="{name}">\n' + read(os.path.join(GAME, name + ".py")) + "</script>")
out_html = html.replace(tag, "\n".join(blocks)).replace(vendor_flag, "window.DDL_VENDOR = false;")
os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
out = os.path.join(ROOT, "dist", "dao-den-long.html")
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(out_html)
print("wrote", out, "modules:", ["sim"] + sorted(mods - {"sim"}), "vendor loader: off (CDN)")
