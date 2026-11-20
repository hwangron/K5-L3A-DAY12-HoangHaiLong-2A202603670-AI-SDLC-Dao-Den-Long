"""Drive the real web build in headless Chromium and save proof screenshots.

Needs: pip install playwright && python -m playwright install chromium
Run:   PHASE=phase-3 python tools/web_check.py      -> docs/proof/$PHASE/web/  (PHASE default phase-3)
Checks:
  - page loads with no JS errors; main menu -> night intro -> play (WASD moves Mây)
  - browser (Pyodide) and CPython give identical snapshots + events for the same seed+frames (night 1 AND night 3)
    plus a Ticket-03 scenario run (refuel, lantern_out, fuel_drain, a draining shade)
  - pause (Esc) stops web_step entirely (tick frozen), resume continues
  - settings (volume, mouse sensitivity, "Bang mau de phan biet") persist after a reload (localStorage);
    the colour-blind palette changes the shade rim to #00B3FF and the UI warning colour to #FFFFFF with a warning icon
  - Ticket-03: HUD lanterns "k/n (can m)" and carried/capacity, fuel bar + "Châm dầu" prompt on a lit lantern,
    refuel, low-fuel 1 Hz blink, lantern_out (squashed + torn paper, ambient drops), relight for 5 motes,
    draining shade tendril, no early win when every lantern is lit, result texts dawn_survived / dawn / no_flames
  - nights 2 and 3 load their maps via the page's own functions (screenshots), night-3 wind warning shows
  - game over -> replay resets the night
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

PHASE = os.environ.get("PHASE", "phase-3")
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


def fuel_scenario():
    """Ticket-03 parity scenario: refuel L1 (Mây standing next to it), L2 runs dry, a shade drains L3, L4 is relit."""
    L = sim.maps.lanterns(1)
    l1, l3 = L[0], L[2]
    return {"random_motes": False, "random_shades": False, "random_drifters": False,
            "player": {"pos": [l1[0], l1[1], l1[2] - 1.5], "carried": 6, "flames": 3},
            "lanterns": [{"id": "L1", "lit": True, "fuel": 50},
                         {"id": "L2", "lit": True, "fuel": 0.05},
                         {"id": "L3", "lit": True, "fuel": 25},
                         {"id": "L4", "lit": False, "ever_lit": True}],
            "shades": [{"id": "S1", "pos": [l3[0], l3[1], l3[2] + 1.5], "state": "drain", "target_lantern_id": "L3"}]}


def fuel_frames():
    return [_frame(interact=(t < 2)) for t in range(700)]


def python_run(seed, night, frames, scenario=None):
    r = json.loads(sim.web_new(seed, night))
    events = list(r["events"])
    if scenario is not None:
        sim._web_game = sim.Game(seed, scenario, night)
        events = list(sim._web_game.initial_events())
    for f in frames:
        r = json.loads(sim.web_step(json.dumps(f)))
        events += r["events"]
    return {"snap": r["snap"], "extra": r["extra"], "events": events}


BROWSER_RUN = """([seed, night, frames, sc]) => {
  let r = JSON.parse(simNew(seed, night)); let events = r.events.slice();
  if (sc) {
    py.runPython("sim._web_game = sim.Game(" + seed + ", json.loads(" + JSON.stringify(JSON.stringify(sc)) + "), " + night + ")");
    events = JSON.parse(py.runPython("json.dumps(sim._web_game.initial_events())"));
  }
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


def calm(pg):
    """No random shades / motes while a check runs, and nothing already roaming."""
    pyrun(pg, "g.random_shades = False\ng.random_motes = False\ng.shades.clear()")


def set_fuel(pg, idx, fuel):
    pyrun(pg, f"l = g.lanterns[{idx}]\nl['lit'] = True\nl['deposited'] = 10\nl['ever_lit'] = True\nl['units'] = {int(round(fuel * 60))}")


def force_win(pg):
    """Enough lit lanterns (ceil(0.6 n)) with fuel, then the last two ticks before dawn."""
    pyrun(pg, "n = len(g.lanterns)\nneed = -(-n * 6 // 10)\nfor l in g.lanterns[:need]:\n"
              "    l['lit'] = True\n    l['deposited'] = 10\n    l['units'] = 6000\n    l['ever_lit'] = True\n"
              "g.shades.clear()\ng.time_left_ticks = 2")
    pg.wait_for_function("game.ui === 'result' || game.ui === 'dawn'", timeout=10000)


def drain_scene(pg, fuel=29):
    """Replace the running game by a scenario: L1 lit at `fuel`, shade S1 draining it, Mây far away."""
    L1 = sim.maps.lanterns(1)[0]
    sc = {"random_motes": False, "random_shades": False, "random_drifters": False,
          "player": {"pos": [L1[0], L1[1], L1[2] - 8.0], "carried": 0, "flames": 3},   # 8 m: > 6 m, so the shade keeps draining
          "lanterns": [{"id": "L1", "lit": True, "fuel": fuel}],
          "shades": [{"id": "S1", "pos": [L1[0] + 1.8, L1[1], L1[2]], "state": "drain", "target_lantern_id": "L1"}]}
    pg.evaluate("(c) => py.runPython(c)", f"import json as _j\nsim._web_game = sim.Game(7, _j.loads({json.dumps(json.dumps(sc))}), 1)")
    pg.evaluate("game.setCam(10, 20)")
    pg.wait_for_function("snap.shades.length > 0 && snap.shades[0].state === 'drain'", timeout=5000)
    pg.wait_for_timeout(500)


def sample_blink(pg, seconds=3.0, every_ms=25, lid="L1"):
    return pg.evaluate("""async ([sec, every, lid]) => {
        const out = []; const t0 = performance.now();
        while (performance.now() - t0 < sec * 1000) {
          const u = lanternObjs[lid].userData;
          out.push([u.blinkOn, u.low, u.bar.visible, Math.round(u.barFill.material.opacity * 100)]);
          await new Promise((r) => setTimeout(r, every));
        }
        return out; }""", [seconds, every_ms, lid])


def transitions(seq):
    return sum(1 for a, b in zip(seq, seq[1:]) if a != b)


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
            web = pg.evaluate(BROWSER_RUN, [42, n, frames, None])
            ref = python_run(42, n, frames)
            R[f"parity_night{n}_browser_vs_python"] = web == ref
            R[f"parity_night{n}_ticks"] = ref["snap"]["tick"]
        # ---- parity on a Ticket-03 scenario (fuel, refuel, lantern_out, drain, relight state)
        sc, frames = fuel_scenario(), fuel_frames()
        web = pg.evaluate(BROWSER_RUN, [5, 1, frames, sc])
        ref = python_run(5, 1, frames, sc)
        R["parity_fuel_scenario_browser_vs_python"] = web == ref
        names = {e["name"] for e in ref["events"]}
        R["parity_fuel_scenario_has_fuel_events"] = {"refuel", "lantern_out", "fuel_drain"} <= names
        R["parity_fuel_scenario_snapshot_has_fuel"] = all("fuel" in l and "ever_lit" in l and "relit_count" in l
                                                          for l in ref["snap"]["lanterns"]) and "capacity" in ref["snap"]["player"]

        # ---- menu -> intro -> play (buttons, since keyboard focus may be missing in an iframe)
        pg.click("#btn-start")
        pg.wait_for_timeout(200)
        R["intro_after_start"] = visible(pg, "intro") and "Đảo Bến" in pg.inner_text("#intro-name")
        goals = pg.evaluate("[GOALS, ONG_DANG]")
        text = " ".join(list(goals[0].values()) + list(goals[1].values()))
        R["no_all_lit_win_wording"] = (all(w not in text for w in ("Thắp đủ", "thắp lại năm", "Thắp 5 đèn", "Thắp 6 đèn", "Thắp 7 đèn"))
                                       and "đủ" not in pg.inner_text("#intro-goal").lower().split("sáng tới")[0])
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
        R["hud_lanterns_k_of_n_need_m"] = (pg.inner_text("#lanterns") == "0/5" and pg.inner_text("#need") == "(cần 3)"
                                           and "đang sáng" in pg.inner_text("#topright"))
        R["hud_carried_over_capacity_10"] = (pg.inner_text("#motecount").endswith("/10")
                                             and pg.evaluate("document.querySelectorAll('#motebar .slot').length") == 10)
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

        # ---- settings: change from the pause menu (incl. the colour-blind palette), reload, values persist
        pg.keyboard.press("KeyP")
        pg.click("#btn-settings-pause")
        R["colorblind_toggle_default_off"] = (not pg.evaluate("document.getElementById('set-cb').checked")
                                              and not pg.evaluate("document.body.classList.contains('cb')"))
        pg.evaluate("""() => { for (const [id, v] of [['set-volume', 37], ['set-sens', 155]]) {
            const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event('input')); } }""")
        pg.click("#set-cb")
        shot(pg, "05_settings.png")
        pg.click("#btn-settings-done")
        R["settings_back_to_pause"] = visible(pg, "pause")
        pg.reload()
        pg.wait_for_function("window.__ready === true", timeout=180000)
        st = pg.evaluate("[game.settings.volume, game.settings.sens, +document.getElementById('set-volume').value, +document.getElementById('set-sens').value]")
        R["settings_persist_after_reload"] = st == [37, 155, 37, 155]
        R["colorblind_persists_after_reload"] = pg.evaluate(
            "game.settings.cb === true && document.body.classList.contains('cb') && document.getElementById('set-cb').checked")

        # ---- colour-blind palette in play: shade rim #00B3FF, warning colour #FFFFFF + warning icon, drain tendril
        enter_night(pg, 1)
        drain_scene(pg)
        R["cb_shade_rim_is_00B3FF"] = pg.evaluate("shadeObjs.S1.userData.rimMat.color.getHex()") == 0x00B3FF
        R["cb_shade_eyes_are_00B3FF"] = pg.evaluate("shadeObjs.S1.userData.eyeMat.color.getHex()") == 0x00B3FF
        R["cb_warning_colour_is_white"] = pg.evaluate(
            "getComputedStyle(document.body).getPropertyValue('--danger').trim().toLowerCase()") == "#ffffff"
        R["cb_warning_icon_shown"] = ("⚠" in pg.evaluate("getComputedStyle(document.getElementById('need'), '::before').content")
                                      and "warn" in pg.evaluate("document.getElementById('need').className"))
        R["cb_unlit_lantern_squashed_and_torn"] = pg.evaluate(
            "(() => { const u = lanternObjs.L2.userData; return Math.abs(u.shell.scale.y - 0.8) < 1e-6 && u.tear.visible; })()")
        shot(pg, "05b_colorblind_drain.png")
        # turn it off again through the real UI (pause -> settings -> checkbox)
        pg.keyboard.press("Escape")
        pg.click("#btn-settings-pause")
        pg.click("#set-cb")
        pg.click("#btn-settings-done")
        pg.click("#btn-resume")
        pg.wait_for_function("game.ui === 'play'")
        pg.wait_for_timeout(300)
        R["colorblind_toggle_off_restores_palette"] = (
            pg.evaluate("game.settings.cb === false && !document.body.classList.contains('cb')")
            and pg.evaluate("shadeObjs.S1.userData.rimMat.color.getHex()") == 0x7A3CFF
            and pg.evaluate("getComputedStyle(document.body).getPropertyValue('--danger').trim().toLowerCase()") == "#ff5a5f")

        # ---- draining shade (default palette): tendril to the lantern + fuel falls faster than 1/s
        f0 = pg.evaluate("snap.lanterns[0].fuel")
        pg.wait_for_timeout(700)
        f1 = pg.evaluate("snap.lanterns[0].fuel")
        R["shade_drain_tendril_visible"] = pg.evaluate("shadeObjs.S1.userData.tendril.visible") and pg.evaluate("snap.shades[0].state") == "drain"
        R["shade_drain_speeds_up_fuel_loss"] = (f0 - f1) > 2.0
        shot(pg, "06d_shade_drain.png")

        # ---- lantern lit in the browser (teleport next to L1 with 10 motes, press E)
        enter_night(pg, 1)
        pyrun(pg, "g.player['pos'] = [0.0, 0.0, 23.5]\ng.player['carried'] = 10")
        calm(pg)
        pg.evaluate("game.setCam(8, 16)")
        pg.wait_for_timeout(250)
        R["interact_prompt_shown"] = (visible(pg, "prompt") and "Nạp ánh sáng" in pg.inner_text("#prompt")
                                      and "(0/10)" in pg.inner_text("#prompt"))
        tap(pg, "KeyE")
        pg.wait_for_timeout(700)
        s = pg.evaluate("snap")
        R["lantern_L1_lit_in_browser"] = s["lanterns"][0]["lit"]
        amb = pg.evaluate("ambient.intensity")
        R["ambient_follows_progress"] = abs(amb - (0.15 + 0.55 * 1 / 5)) < 1e-6
        R["capacity_grows_after_light"] = (s["player"]["capacity"] == 12 and pg.inner_text("#motecount").endswith("/12")
                                           and pg.evaluate("document.querySelectorAll('#motebar .slot').length") == 12)
        R["hud_lit_count_updates"] = pg.inner_text("#lanterns") == "1/5"
        R["lit_fuel_bar_visible"] = pg.evaluate(
            "(() => { const u = lanternObjs.L1.userData; return u.bar.visible && u.barFill.scale.x > 0.95 && Math.abs(u.shell.scale.y - 1) < 1e-6 && !u.tear.visible; })()")
        R["refuel_prompt_on_lit_lantern"] = visible(pg, "prompt") and "Châm dầu" in pg.inner_text("#prompt")
        shot(pg, "06_lantern_lit.png")

        # ---- refuel: 3 motes on a half-empty lantern (+30)
        pyrun(pg, "g.lanterns[0]['units'] = 3000\ng.player['carried'] = 3")
        tap(pg, "KeyE")
        pg.wait_for_timeout(400)
        s = pg.evaluate("snap")
        R["refuel_in_browser"] = 78.0 < s["lanterns"][0]["fuel"] <= 80.0 and s["player"]["carried"] == 0
        R["refuel_toast_shown"] = visible(pg, "toast") and "Châm dầu" in pg.inner_text("#toast")
        steady = sample_blink(pg, 1.0)
        R["no_blink_when_fuel_at_least_30"] = all(x[0] and not x[1] for x in steady)

        # ---- low fuel (< 30): lantern + bar blink slowly (1 Hz)
        set_fuel(pg, 0, 20)
        pg.wait_for_timeout(200)
        seq = sample_blink(pg, 3.0)
        flips = transitions([x[0] for x in seq])
        R["low_fuel_blinks"] = all(x[1] for x in seq) and {x[0] for x in seq} == {True, False}
        R["low_fuel_bar_blinks_too"] = len({x[3] for x in seq}) >= 2
        R["low_fuel_blink_rate_about_1hz"] = 4 <= flips <= 8      # 3 s sampled: ~3 full cycles = ~6 flips
        R["low_fuel_blink_flips_in_3s"] = flips
        pg.wait_for_function("lanternObjs.L1.userData.blinkOn === true")
        shot(pg, "06b_low_fuel_blink.png")

        # ---- the lantern runs dry: out, squashed + torn paper, ambient drops, relight costs 5
        set_fuel(pg, 0, 2 / 60)
        pg.wait_for_timeout(400)
        s = pg.evaluate("snap")
        l1 = s["lanterns"][0]
        R["lantern_out_in_browser"] = (not l1["lit"]) and l1["ever_lit"] is True and l1["fuel"] == 0
        R["lantern_out_ambient_drops"] = abs(pg.evaluate("ambient.intensity") - 0.15) < 1e-6
        R["lantern_out_toast_shown"] = visible(pg, "toast") and "tắt" in pg.inner_text("#toast")
        R["unlit_lantern_squashed_and_torn"] = pg.evaluate(
            "(() => { const u = lanternObjs.L1.userData; return Math.abs(u.shell.scale.y - 0.8) < 1e-6 && u.tear.visible && !u.bar.visible; })()")
        R["relight_prompt_cost_5"] = visible(pg, "prompt") and "Nạp ánh sáng (0/5)" in pg.inner_text("#prompt")
        shot(pg, "06c_lantern_out.png")
        pyrun(pg, "g.player['carried'] = 5")
        tap(pg, "KeyE")
        pg.wait_for_timeout(500)
        s = pg.evaluate("snap")
        l1 = s["lanterns"][0]
        R["relight_for_5_motes"] = (l1["lit"] and l1["relit_count"] == 1 and l1["fuel"] > 98
                                    and s["player"]["carried"] == 0 and s["player"]["capacity"] == 14)

        # ---- the draining shade again, now in the default palette
        drain_scene(pg)
        R["default_shade_rim_is_7A3CFF"] = pg.evaluate("shadeObjs.S1.userData.rimMat.color.getHex()") == 0x7A3CFF

        # ---- no early win: every lantern lit and fed does not end the Night any more
        enter_night(pg, 1)
        calm(pg)
        pyrun(pg, "for l in g.lanterns:\n    l['lit'] = True\n    l['deposited'] = 10\n    l['units'] = 6000\n    l['ever_lit'] = True")
        pg.wait_for_timeout(800)
        R["no_early_win_when_all_lit"] = pg.evaluate("snap.state") == "playing" and pg.evaluate("game.ui") == "play"

        # ---- game over by dawn (1 lit < 3 needed) -> result texts -> replay this night
        pyrun(pg, "for l in g.lanterns[1:]:\n    l['lit'] = False\n    l['units'] = 0\n    l['deposited'] = 0\ng.time_left_ticks = 3")
        pg.wait_for_function("game.ui === 'result'", timeout=10000)
        s = pg.evaluate("snap")
        R["game_over_dawn"] = s["state"] == "lost" and visible(pg, "btn-retry")
        R["result_text_dawn"] = (pg.evaluate("lastReason") == "dawn" and "Trời đã sáng" in pg.inner_text("#res-title")
                                 and "cần ít nhất 3" in pg.inner_text("#res-msg") and "(cần 3)" in pg.inner_text("#res-table"))
        shot(pg, "07_game_over.png")
        pg.click("#btn-retry")
        pg.wait_for_timeout(200)
        s = pg.evaluate("snap")
        R["replay_resets"] = (pg.evaluate("game.ui") == "intro" and pg.evaluate("game.night") == 1
                              and s["state"] == "playing" and s["score"] == 0 and 239 < s["time_left_s"] <= 240
                              and all(not l["lit"] and l["fuel"] == 0 for l in s["lanterns"]))
        pg.click("#btn-intro-go")
        pg.wait_for_function("game.ui === 'play'")

        # ---- game over by running out of flames
        calm(pg)
        pyrun(pg, "g.player['flames'] = 0")
        pg.wait_for_function("game.ui === 'result'", timeout=10000)
        R["result_text_no_flames"] = (pg.evaluate("lastReason") == "no_flames" and pg.evaluate("snap.state") == "lost"
                                      and "Ngọn lửa của Mây đã tắt" in pg.inner_text("#res-title"))
        shot(pg, "07b_game_over_no_flames.png")
        pg.click("#btn-retry")
        pg.wait_for_timeout(200)
        pg.click("#btn-intro-go")
        pg.wait_for_function("game.ui === 'play'")

        # ---- FPS at 1280x720 on night 1 (software GL -> lower bound)
        R["fps_night1_avg_5s"] = measure_fps(pg)

        # ---- nights 2 and 3 via the page's own functions: map screenshots
        enter_night(pg, 2)
        s = pg.evaluate("snap")
        R["night2_loaded"] = s["night"] == 2 and len(s["lanterns"]) == 6 and pg.evaluate("mapData.bridges.length") == 1
        R["night2_hud_need_4_of_6"] = pg.inner_text("#lanterns") == "0/6" and pg.inner_text("#need") == "(cần 4)"
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
        R["night3_hud_need_5_of_7"] = pg.inner_text("#lanterns") == "0/7" and pg.inner_text("#need") == "(cần 5)"
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

        # ---- win chain: night 1 -> 2 -> 3 -> Dawn, total = sum of won nights (dawn_survived each time)
        enter_night(pg, 1)
        won = []
        reasons = []
        for n in (1, 2, 3):
            force_win(pg)
            won.append(pg.evaluate("snap.score"))
            reasons.append(pg.evaluate("lastReason"))
            if n == 1:
                pg.wait_for_function("game.ui === 'result'")
                R["result_text_dawn_survived"] = ("vẫn sáng tới bình minh" in pg.inner_text("#res-title")
                                                  and "(cần 3)" in pg.inner_text("#res-table"))
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
        R["win_reason_dawn_survived_all_nights"] = reasons == ["dawn_survived"] * 3
        R["dawn_total_is_sum_of_won_nights"] = total == sum(won) and total > 0
        R["won_scores"] = won
        shot(pg, "13_dawn.png")
        b.close()
    httpd.shutdown()
    R["fps_note"] = ("headless Chromium uses SwiftShader software GL; real GPUs render much faster, "
                     "so these FPS numbers are a lower bound")
    R["js_errors"] = errors
    info = {"js_errors", "fps_note", "won_scores", "parity_night1_ticks", "parity_night3_ticks",
            "fps_night1_avg_5s", "fps_night3_avg_5s", "low_fuel_blink_flips_in_3s"}
    ok = all(v is True for k, v in R.items() if k not in info) and not errors
    R["ok"] = ok
    with open(os.path.join(OUT, "web_check.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(json.dumps(R, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
