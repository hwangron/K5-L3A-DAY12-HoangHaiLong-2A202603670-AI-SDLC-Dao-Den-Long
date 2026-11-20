"""Build dist/dao-den-long.html: one self-contained file (game/sim.py inlined).
Used for the GitHub Release and the claude.ai Artifact. python3 tools/build_web.py"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
src = open(os.path.join(ROOT, "game", "sim.py"), encoding="utf-8").read()
assert "</script" not in src
tag = '<script type="text/x-python" id="sim-src"></script>'
assert tag in html
os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
out = os.path.join(ROOT, "dist", "dao-den-long.html")
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(html.replace(tag, '<script type="text/x-python" id="sim-src">\n' + src + "</script>"))
print("wrote", out)
