"""Drive the real web build in headless Chromium and save proof screenshots.

Needs: pip install playwright && python -m playwright install chromium
Run:   PHASE=phase-2 python tools/web_check.py      -> docs/proof/$PHASE/web/  (PHASE default phase-2)
Checks:
  - page loads with no JS errors; main menu -> night intro -> play (WASD moves Mây)
  - browser (Pyodide) and CPython give identical snapshots + events for the same seed+frames (night 1 AND night 3)
  - pause (Esc) stops web_step entirely (tick frozen), resume continues
  - settings (volume, mouse sensitivity) persist after a reload (localStorage)
  - nights 2 and 3 load their maps via the page's own functions (screenshots), night-3 wind warning shows
  - lantern lit in the browser; game over -> replay resets the night
  - win chain night 1 -> 2 -> 3 -> Dawn screen with total = sum of won nights
  - average FPS over 5 s at 1280x720 (headless Chromium = software GL, so this is a lower bound)
"""
import functools
import http.server
import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from game import sim  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PHASE = os.environ.get("PHASE", "phase-2")
OUT = os.path.join(ROOT, "docs", "proof", PHASE, "web")
PORT = 8765


def _frame(move=(0.0, 0.0), yaw=0.0, **btn):
    f = {"move": list(move), "cam_yaw_deg": yaw, "jump": False, "interact": False, "pulse": False, "dash": False}
    f.update(btn)
    return f


def parity_frames(night):
    """Deterministic input script that exercises move, camera yaw, jump, dash, pulse and interact."""
    fr = []
    for t in range(900):
        yaw = 30.0 if t < 450 else -45.0
        move = (0.4, 1.0) if t < 300 else (-1.0, 0.0) if t < 600 else (0.0, -1.0)
        fr.append(_frame(move, yaw, jump=(t % 50) < 3, dash=(t % 97) < 2, pulse=(t % 130) < 2,
                         interact=(t % 70) < 2))
    if night == 3:  # head up the ramp side and toward the bell tower too
        fr += [_frame((0.0, 1.0), 0.0, dash=(t % 40) < 2) for t in range(400)]
    return fr


def python_run(seed, night, frames):
    r = json.loads(sim.web_new(seed, night))
    events = list(r["events"])
    for f in frames:
        r = json.loads(sim.web_step(json.dumps(f)))
        events += r["events"]
    return {"snap": r["snap"], "extra": r["extra"], "events": events}


BROWSER_RUN = """([seed, night, frames]) => {
  let r = JSON.parse(simNew(seed, night)); const events = r.events.slice();
  for (const f of frames) { r = JSON.parse(simStep(JSON.stringify(f))); events.push(...r.events); }
  return { snap: r.snap, extra: r.extra, events };
}"""


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


def shot(pg, name):
    pg.screenshot(path=os.path.join(OUT, name))


def visible(pg, el_id):
    return pg.evaluate(f"!document.getElementById('{el_id}').classList.contains('hidden')")


def pyrun(pg, code):
    """Run Python inside the page's Pyodide (test setup only: teleport, force timers)."""
    pg.evaluate("(c) => py.runPython(c)", "g = sim._web_game\n" + code)


def enter_night(pg, n):
    """Use the page's own functions: start night n, then click the intro button."""
    pg.evaluate(f"game.startRun({n})")
    pg.wait_for_timeout(150)
    pg.click("#btn-intro-go")
    pg.wait_for_function("game.ui === 'play'")


def force_win(pg):
    pyrun(pg, "for l in g.lanterns:\n    l['lit'] = True\n    l['deposited'] = 10")
    pg.wait_for_function("game.ui === 'result' || game.ui === 'dawn'", timeout=10000)


def measure_fps(pg, seconds=5.0):
    pg.keyboard.down("KeyW")
    pg.keyboard.down("ArrowLeft")
    f0, t0 = pg.evaluate("[window.__frames, performance.now()]")
    pg.wait_for_timeout(int(seconds * 1000))
    f1, t1 = pg.evaluate("[window.__frames, performance.now()]")
    pg.keyboard.up("ArrowLeft")
    pg.keyboard.up("KeyW")
    return round((f1 - f0) / ((t1 - t0) / 1000.0), 1)


def main():
    os.makedirs(OUT, exist_ok=True)
    httpd = serve()
    R = {}
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                     "--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1280, "height": 720})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.goto(f"http://127.0.0.1:{PORT}/web/")
        pg.wait_for_function("window.__ready === true", timeout=180000)
        pg.wait_for_timeout(300)
        R["menu_shown"] = visible(pg, "menu")
        shot(pg, "01_menu.png")

        # ---- parity: same seed + frames in browser (Pyodide) vs CPython, nights 1 and 3
        for n in (1, 3):
            frames = parity_frames(n)
            web = pg.evaluate(BROWSER_RUN, [42, n, frames])
            ref = python_run(42, n, frames)
            R[f"parity_night{n}_browser_vs_python"] = web == ref
            R[f"parity_night{n}_ticks"] = ref["snap"]["tick"]

        # ---- menu -> intro -> play (buttons, since keyboard focus may be missing in an iframe)
        pg.click("#btn-start")
        pg.wait_for_timeout(200)
        R["intro_after_start"] = visible(pg, "intro") and "Đảo Bến" in pg.inner_text("#intro-name")
        shot(pg, "02_intro_night1.png")
        pg.keyboard.press("Enter")                      # Enter confirms the intro
        pg.wait_for_function("game.ui === 'play'")
        pg.keyboard.down("KeyW")
        pg.wait_for_timeout(1500)
        pg.keyboard.up("KeyW")
        tap(pg, "Space")
        pg.wait_for_timeout(100)
        s = pg.evaluate("snap")
        R["moved_after_W"] = s["player"]["pos"] != [0.0, 0.0, 0.0]
        R["hud_visible"] = visible(pg, "hud") and pg.inner_text("#timer").count(":") == 1
        shot(pg, "03_play_hud.png")

        # ---- pause freezes the sim (web_step not called), resume continues
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(100)
        t0 = pg.evaluate("[snap.tick, py.runPython('sim._web_game.tick')]")
        pg.keyboard.down("KeyW")
        pg.wait_for_timeout(1000)
        pg.keyboard.up("KeyW")
        t1 = pg.evaluate("[snap.tick, py.runPython('sim._web_game.tick')]")
        R["pause_menu_shown"] = visible(pg, "pause")
        R["pause_freezes_sim"] = t0 == t1 and pg.evaluate("game.ui") == "paused"
        shot(pg, "04_pause.png")
        pg.click("#btn-resume")
        pg.wait_for_timeout(500)
        t2 = pg.evaluate("snap.tick")
        R["resume_continues"] = t2 > t1[0] and pg.evaluate("game.ui") == "play"

        # ---- settings: change from the pause menu, reload, values persist
        pg.keyboard.press("KeyP")
        pg.click("#btn-settings-pause")
        pg.evaluate("""() => { for (const [id, v] of [['set-volume', 37], ['set-sens', 155]]) {
            const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event('input')); } }""")
        shot(pg, "05_settings.png")
        pg.click("#btn-settings-done")
        R["settings_back_to_pause"] = visible(pg, "pause")
        pg.reload()
        pg.wait_for_function("window.__ready === true", timeout=180000)
        st = pg.evaluate("[game.settings.volume, game.settings.sens, +document.getElementById('set-volume').value, +document.getElementById('set-sens').value]")
        R["settings_persist_after_reload"] = st == [37, 155, 37, 155]

        # ---- lantern lit in the browser (teleport next to L1 with 10 motes, press E)
        enter_night(pg, 1)
        pyrun(pg, "g.player['pos'] = [0.0, 0.0, 23.5]\ng.player['carried'] = 10\ng.shades.clear()")
        pg.wait_for_timeout(250)
        R["interact_prompt_shown"] = visible(pg, "prompt") and "Nạp ánh sáng" in pg.inner_text("#prompt")
        tap(pg, "KeyE")
        pg.wait_for_timeout(700)
        s = pg.evaluate("snap")
        R["lantern_L1_lit_in_browser"] = s["lanterns"][0]["lit"]
        amb = pg.evaluate("ambient.intensity")
        R["ambient_follows_progress"] = abs(amb - (0.15 + 0.55 * 1 / 5)) < 1e-6
        shot(pg, "06_lantern_lit.png")

        # ---- game over by dawn -> result -> replay this night
        pyrun(pg, "g.time_left_ticks = 3")
        pg.wait_for_function("game.ui === 'result'", timeout=10000)
        s = pg.evaluate("snap")
        R["game_over_dawn"] = s["state"] == "lost" and visible(pg, "btn-retry")
        shot(pg, "07_game_over.png")
        pg.click("#btn-retry")
        pg.wait_for_timeout(200)
        s = pg.evaluate("snap")
        R["replay_resets"] = (pg.evaluate("game.ui") == "intro" and pg.evaluate("game.night") == 1
                              and s["state"] == "playing" and s["score"] == 0 and s["time_left_s"] > 299)
        pg.click("#btn-intro-go")
        pg.wait_for_function("game.ui === 'play'")

        # ---- FPS at 1280x720 on night 1 (software GL -> lower bound)
        R["fps_night1_avg_5s"] = measure_fps(pg)

        # ---- nights 2 and 3 via the page's own functions: map screenshots
        enter_night(pg, 2)
        s = pg.evaluate("snap")
        R["night2_loaded"] = s["night"] == 2 and len(s["lanterns"]) == 6 and pg.evaluate("mapData.bridges.length") == 1
        pyrun(pg, "g.player['pos'] = [35.0, 0.0, 0.0]; g.shades.clear()")   # overview from the bridge
        pg.evaluate("game.setCam(48, 62); yaw = 0")
        pg.wait_for_timeout(800)
        shot(pg, "08_night2_map.png")
        pyrun(pg, "g.player['pos'] = [24.0, 0.0, 6.0]")
        pg.evaluate("game.setCam(14, 30); yaw = 90")
        pg.wait_for_timeout(500)
        shot(pg, "09_night2_bridge.png")

        enter_night(pg, 3)
        s = pg.evaluate("snap")
        R["night3_loaded"] = (s["night"] == 3 and len(s["lanterns"]) == 7 and pg.evaluate("mapData.tower !== null")
                              and pg.evaluate("mapData.ramps.length") == 2)
        pg.evaluate("game.setCam(42, 48); yaw = 0")
        pg.wait_for_timeout(800)
        shot(pg, "10_night3_map.png")
        pyrun(pg, "g.player['pos'] = [16.0, 3.0, 20.0]")      # on tier 1 near the ramp and the jump pad
        pg.evaluate("game.setCam(16, 30); yaw = -150")
        pg.wait_for_timeout(600)
        shot(pg, "10b_night3_tiers.png")
        pyrun(pg, "g.player['pos'] = [0.0, 0.0, -30.0]")
        R["fps_night3_avg_5s"] = measure_fps(pg)
        # jump to just before the first wind (tick 1800, warned from 1680)
        pg.keyboard.press("Escape")
        pyrun(pg, "f = {'move': [0, 0], 'cam_yaw_deg': 0, 'jump': False, 'interact': False, 'pulse': False, 'dash': False}\n"
                  "g.shades.clear()\nwhile g.sim_tick < 1690:\n    g.step(f)\n    g.shades.clear()\n"
                  "    g.player['flames'] = 3")
        pg.click("#btn-resume")
        pg.wait_for_timeout(300)
        R["wind_warning_shown"] = pg.evaluate("extra.wind_warning !== null") and visible(pg, "wind")
        pg.evaluate("game.setCam(12, 25)")
        pg.wait_for_timeout(300)
        shot(pg, "11_night3_wind_warning.png")

        # ---- win chain: night 1 -> 2 -> 3 -> Dawn, total = sum of won nights
        enter_night(pg, 1)
        won = []
        for n in (1, 2, 3):
            force_win(pg)
            won.append(pg.evaluate("snap.score"))
            if n == 1:
                pg.wait_for_function("game.ui === 'result'")
                shot(pg, "12_result_won_night1.png")
            if n < 3:
                pg.wait_for_function("game.ui === 'result'")
                pg.click("#btn-next")
                pg.wait_for_timeout(150)
                R[f"next_goes_to_night{n + 1}"] = pg.evaluate("game.night") == n + 1 and visible(pg, "intro")
                pg.click("#btn-intro-go")
                pg.wait_for_function("game.ui === 'play'")
        pg.wait_for_function("game.ui === 'dawn'", timeout=10000)
        total = int(pg.inner_text("#dawn-total"))
        R["dawn_total_is_sum_of_won_nights"] = total == sum(won) and total > 0
        R["won_scores"] = won
        shot(pg, "13_dawn.png")
        b.close()
    httpd.shutdown()
    R["fps_note"] = ("headless Chromium uses SwiftShader software GL; real GPUs render much faster, "
                     "so these FPS numbers are a lower bound")
    R["js_errors"] = errors
    info = {"js_errors", "fps_note", "won_scores", "parity_night1_ticks", "parity_night3_ticks",
            "fps_night1_avg_5s", "fps_night3_avg_5s"}
    ok = all(v is True for k, v in R.items() if k not in info) and not errors
    R["ok"] = ok
    with open(os.path.join(OUT, "web_check.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(json.dumps(R, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
