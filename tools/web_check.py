"""Drive the real web build in headless Chromium and save proof screenshots.

Needs: pip install playwright && python -m playwright install chromium
Run:   python tools/web_check.py            -> docs/proof/phase-1/web/
Checks: page loads with no JS errors; browser (Pyodide) and headless Python give
identical state for the same seed+inputs; start -> play -> light lantern -> game over -> replay.
"""
import functools
import http.server
import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from game.sim import Game  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = os.path.join(ROOT, "docs", "proof", os.environ.get("PHASE", "phase-1"), "web")
PORT = 8765
FRAMES = [{"move": [0.4, 1.0], "cam_yaw_deg": 30.0, "jump": False, "interact": False, "pulse": False}] * 300 + \
         [{"move": [-1.0, 0.0], "cam_yaw_deg": 30.0, "jump": True, "interact": False, "pulse": True}] * 600


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    h = functools.partial(_Quiet, directory=ROOT)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def tap(pg, key):
    pg.keyboard.down(key)
    pg.wait_for_timeout(120)   # hold across a few frames like a real key press
    pg.keyboard.up(key)


def main():
    os.makedirs(OUT, exist_ok=True)
    httpd = serve()
    results = {}
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.goto(f"http://127.0.0.1:{PORT}/web/")
        pg.wait_for_function("window.__ready === true", timeout=120000)
        pg.screenshot(path=os.path.join(OUT, "01_start.png"))

        # parity: same seed + same frames in browser vs. python
        web = pg.evaluate("""(frames) => { simNew(42); let s;
            for (const f of frames) s = JSON.parse(simStep(JSON.stringify(f))).snap; return s; }""", FRAMES)
        g = Game(42)
        for f in FRAMES:
            g.step(dict(f))
        results["parity_browser_vs_python"] = web == g.snapshot()

        # play: start, walk, pulse
        pg.keyboard.press("Enter")
        pg.keyboard.down("KeyW")
        pg.wait_for_timeout(1500)
        pg.keyboard.up("KeyW")
        tap(pg, "Space")
        pg.wait_for_timeout(100)
        pg.screenshot(path=os.path.join(OUT, "02_playing_hud.png"))
        s = pg.evaluate("snap")
        results["moved_after_W"] = s["player"]["pos"] != [0.0, 0.0, 0.0]

        # light a lantern: put Mây next to L1 with 5 motes, press E
        pg.evaluate("""py.runPython("g=sim._web_game; g.player['pos']=[0.0,0.0,16.5]; g.player['carried']=5; g.shades.clear()")""")
        pg.wait_for_timeout(200)
        tap(pg, "KeyE")
        pg.wait_for_timeout(600)
        s = pg.evaluate("snap")
        results["lantern_L1_lit_in_browser"] = s["lanterns"][0]["lit"]
        pg.screenshot(path=os.path.join(OUT, "03_lantern_lit.png"))

        # game over by dawn, then replay
        pg.evaluate("""py.runPython("sim._web_game.time_left_ticks=3")""")
        pg.wait_for_timeout(1200)
        s = pg.evaluate("snap")
        results["game_over_dawn"] = s["state"] == "lost"
        pg.screenshot(path=os.path.join(OUT, "04_game_over.png"))
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        s = pg.evaluate("snap")
        results["replay_resets"] = s["state"] == "playing" and s["score"] == 0 and s["time_left_s"] > 299
        b.close()
    httpd.shutdown()
    results["js_errors"] = errors
    ok = all(v is True for k, v in results.items() if k != "js_errors") and not errors
    results["ok"] = ok
    with open(os.path.join(OUT, "web_check.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
