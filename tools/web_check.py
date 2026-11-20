"""Drive the real web build in headless Chromium and save proof screenshots.

Needs: pip install playwright && python -m playwright install chromium
Run:   PHASE=phase-4 python tools/web_check.py      -> docs/proof/$PHASE/web/  (PHASE default phase-4)
Servers: the real serve.make_server (API + bench sink, leaderboard file in a temp dir) on PORT, and a plain static
server (no API) on PORT + 1 to test the localStorage fallback.
Checks:
  - page loads with no JS errors; main menu -> night intro -> play (WASD moves Mây); vendor-first loading
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
  - Ticket-04 benchmark page (?bench=1&seed=42&duration=3): fixed 1280x720 canvas, no UI, 200 shades + 100 motes as
    instances, camera on the 30 m / 15 m circle, 3 s warm-up, then exactly `duration` s of rAF dts POSTed to /api/bench
    (valid payload; benchstats.compute works on it)
  - Ticket-04 leaderboard: name entry after Dawn and after losses (validation errors, Vietnamese name, NFC, Enter key),
    saved through the API to the leaderboard file, leaderboard screen order (score desc, earlier first on ties),
    back navigation, and the localStorage fallback on a server without the API (survives a reload)
  - Ticket-04 accessibility: key remapping (persists, duplicate + reserved-key warnings, reset to defaults, the new keys
    really drive the input frame, remapped pause key), captions + edge arrow on shade spawn, wind soon, last 10 s and
    fuel < 30, reduced motion (no camera shake / screen flash) and large text persist, every UI font >= 18 px at
    1280x720 (>= 22.5 px with large text) by computed style
  - average FPS over 5 s at 1280x720 (headless Chromium = software GL, so this is a lower bound)
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
LB_FILE = os.path.join(tempfile.mkdtemp(prefix="ddl-webcheck-"), "leaderboard.json")
os.environ["DDL_LEADERBOARD"] = LB_FILE          # before serve / leaderboard read it: never touch the player's real file
from game import benchstats, leaderboard, sim  # noqa: E402
import serve  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PHASE = os.environ.get("PHASE", "phase-4")
OUT = os.path.join(ROOT, "docs", "proof", PHASE, "web")
PORT = 8765
PORT_STATIC = PORT + 1
BENCH_RESULTS = []                               # payloads POSTed to /api/bench (the bench sink of the real server)
MIN_FONT_PX = 18.0


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


def serve_api():
    """The real server (game files + /api/leaderboard + /api/bench into BENCH_RESULTS)."""
    httpd = serve.make_server(PORT, bench_sink=BENCH_RESULTS.append, quiet=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def serve_static():
    """A plain static server: no /api at all (what a single-file / Artifact build sees) -> localStorage fallback."""
    h = functools.partial(_Quiet, directory=ROOT)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT_STATIC), h)
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


def watch(pg, errors, no_api=False):
    """Collect JS errors. A 404 of web/vendor/* is expected when tools/fetch_vendor.py was not run (CDN fallback);
    on the static server (no_api) the failing /api/* requests are the fallback being exercised."""
    pg.on("pageerror", lambda e: errors.append(str(e)))

    def on_console(m):
        if m.type != "error":
            return
        url = (m.location or {}).get("url", "")
        if "Failed to load resource" in m.text and ("/vendor/" in url or (no_api and "/api/" in url)):
            return
        errors.append(m.text)
    pg.on("console", on_console)


def wait_ready(pg):
    pg.wait_for_function("window.__ready === true", timeout=180000)


FONT_CHECK = """(minPx) => {
  const skip = new Set(["SCRIPT", "STYLE", "TITLE", "NOSCRIPT", "HEAD", "HTML", "META", "LINK"]);
  const bad = []; let checked = 0;
  for (const el of document.body.querySelectorAll("*")) {
    if (skip.has(el.tagName)) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const field = el.tagName === "INPUT" && el.type === "text";
    if (!own && !field) continue;
    checked++;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < minPx - 0.01) bad.push([el.id || el.className || el.tagName, fs, (el.textContent || "").trim().slice(0, 24)]);
  }
  return { bad, checked };
}"""


def font_check(pg, min_px):
    r = pg.evaluate(FONT_CHECK, min_px)
    return r["bad"], r["checked"]


SHAKE = """async () => {
  const xs = [[], [], []];
  for (let i = 0; i < 14; i++) {
    hitFx = 1;                                   // as right after a hit
    await new Promise((r) => requestAnimationFrame(r));
    xs[0].push(camera.position.x); xs[1].push(camera.position.y); xs[2].push(camera.position.z);
  }
  const spread = Math.max(...xs.map((v) => Math.max(...v) - Math.min(...v)));
  return { spread, vignette: parseFloat(document.getElementById('vignette').style.opacity || '0') };
}"""


def lb_rows(pg):
    return pg.evaluate("[...document.querySelectorAll('#lb-body tr')].map((tr) => [...tr.children].map((td) => td.textContent))")


def open_lb_from_menu(pg):
    pg.click("#btn-leaderboard")
    pg.wait_for_function("window.__lbReady === true")


def save_name(pg, name, enter=False):
    pg.fill("#name-input", name)
    if enter:
        pg.press("#name-input", "Enter")
    else:
        pg.click("#btn-save-score")
    pg.wait_for_function("!document.getElementById('nameform-done').classList.contains('hidden')", timeout=10000)


def lose_night(pg):
    """Start Night 1 from the menu and lose it at once (Ngọn Lửa = 0) -> result screen with the name form."""
    pg.click("#btn-night-1")
    pg.wait_for_timeout(150)
    pg.click("#btn-intro-go")
    pg.wait_for_function("game.ui === 'play'")
    calm(pg)
    pyrun(pg, "g.player['flames'] = 0")
    pg.wait_for_function("game.ui === 'result'", timeout=10000)


def trigger_cues(pg):
    """Make the sim itself raise two cues: a lantern at fuel 20 (< 30) and the first Bóng Mực spawn (real _spawns path)."""
    set_fuel(pg, 0, 20)
    pyrun(pg, "g.shades.clear()\ng.random_shades = True\ng.sim_tick = 299\ng.player['flames'] = 3")
    pg.wait_for_function("document.querySelector('#hud .edgearrow.shade') !== null && document.querySelectorAll('#captions .cap').length >= 2",
                         timeout=8000)


# ---------------------------------------------------------------------------------------- Ticket-04 checks
def check_leaderboard(pg, R):
    """Starts on the Dawn screen (after the win chain)."""
    total = int(pg.inner_text("#dawn-total"))
    R["dawn_name_form_in_dawn_card"] = visible(pg, "nameform") and pg.evaluate("document.getElementById('nameform').parentElement.id") == "dawn-form-slot"
    shot(pg, "13b_dawn_name_form.png")
    bad_ok = True
    for bad, frag in (("ab", "ngắn"), ("", "ngắn"), ("x" * 13, "dài"), ("ab cd", "chỉ gồm"), ("tên!!", "chỉ gồm")):
        pg.fill("#name-input", bad)
        pg.click("#btn-save-score")
        msg = pg.inner_text("#name-msg")
        bad_ok = bad_ok and msg.startswith("⚠") and frag in msg and not visible(pg, "nameform-done")
    R["name_validation_messages"] = bad_ok
    R["name_not_saved_when_invalid"] = leaderboard.load(LB_FILE) == []
    shot(pg, "13c_name_error.png")
    # Vietnamese name typed in decomposed form (NFD, 13 code points) = 11 characters after NFC: accepted, stored as NFC
    nfc = unicodedata.normalize("NFC", "Nguyễn_Long")
    nfd = unicodedata.normalize("NFD", nfc)
    R["vietnamese_nfd_name_is_longer_raw"] = len(nfd) > 12 and len(nfc) == 11
    save_name(pg, nfd)
    saved = pg.inner_text("#name-saved")
    entries = leaderboard.load(LB_FILE)
    when = entries[0]["achieved_at"] if entries else ""
    R["lb_dawn_saved_via_api"] = (pg.evaluate("window.__lastSave.via") == "server" and len(entries) == 1
                                  and entries[0]["name"] == nfc and entries[0]["score"] == total and total > 0
                                  and entries[0]["nights_won"] == 3 and "T" in when and (when.endswith("Z") or when[-6] in "+-"))
    R["lb_saved_message_has_rank"] = "hạng 1" in saved and nfc in saved
    shot(pg, "13d_name_saved.png")
    pg.click("#btn-view-lb")
    pg.wait_for_function("window.__lbReady === true")
    rows = lb_rows(pg)
    R["lb_screen_from_dawn"] = (visible(pg, "leaderboard") and not visible(pg, "dawn") and len(rows) == 1
                                and rows[0][:4] == ["1", nfc, str(total), "3"] and len(rows[0][4]) > 5)
    pg.click("#btn-lb-back")
    R["lb_back_returns_to_dawn"] = visible(pg, "dawn") and not visible(pg, "leaderboard") and pg.evaluate("game.ui") == "dawn"
    pg.click("#btn-dawn-menu")
    # two losses from the main menu: score 0 each -> ranked after the Dawn entry, ties in the order achieved
    pg.wait_for_function("game.ui === 'menu'")
    lose_night(pg)
    R["loss_name_form_in_result_card"] = visible(pg, "nameform") and pg.evaluate("document.getElementById('nameform').parentElement.id") == "res-form-slot"
    shot(pg, "07c_loss_name_form.png")
    save_name(pg, "An_Binh")
    r1 = "hạng 2" in pg.inner_text("#name-saved")
    pg.click("#btn-menu-result")
    lose_night(pg)
    pg.fill("#name-input", "Bao_Chau")
    pg.press("#name-input", "Enter")                         # Enter in the box saves (it must not "continue" the result screen)
    pg.wait_for_function("!document.getElementById('nameform-done').classList.contains('hidden')", timeout=10000)
    R["enter_in_name_box_saves_not_retry"] = pg.evaluate("game.ui") == "result" and visible(pg, "result")
    r2 = "hạng 3" in pg.inner_text("#name-saved")
    R["lb_ranks_reported"] = r1 and r2
    pg.click("#btn-menu-result")
    open_lb_from_menu(pg)
    rows = lb_rows(pg)
    disk = [e["name"] for e in leaderboard.load(LB_FILE)]
    R["lb_order_score_desc_then_earlier_first"] = [r[1] for r in rows] == [nfc, "An_Binh", "Bao_Chau"] and disk == [nfc, "An_Binh", "Bao_Chau"]
    R["lb_columns_rank_name_score_nights_date"] = (all(len(r) == 5 for r in rows) and [r[0] for r in rows] == ["1", "2", "3"]
                                                  and [r[2] for r in rows][1:] == ["0", "0"] and [r[3] for r in rows][1:] == ["0", "0"])
    R["lb_source_is_server"] = pg.evaluate("window.__lbSource") == "server"
    shot(pg, "14_leaderboard.png")
    pg.click("#btn-lb-back")
    R["lb_back_returns_to_menu"] = visible(pg, "menu") and not visible(pg, "leaderboard")
    R["lb_file_persisted"] = len(leaderboard.load(LB_FILE)) == 3 and os.path.exists(LB_FILE)
    open_lb_from_menu(pg)
    pg.keyboard.press("Escape")                               # Escape also closes the screen
    R["lb_escape_closes"] = visible(pg, "menu") and not visible(pg, "leaderboard")


def check_keys(pg, R):
    """Starts on the main menu. Rebinding through the Settings screen, as a player would."""
    pg.click("#btn-settings-menu")

    def key(a):
        return pg.inner_text("#key-" + a)
    R["keys_default_labels"] = [key(a) for a in ("up", "down", "left", "right", "jump", "dash", "interact", "pulse", "pause")] == [
        "W", "S", "A", "D", "Space", "Shift", "E", "F", "P"]
    pg.click("#key-up")
    R["key_listening_prompt"] = "Nhấn phím" in pg.inner_text("#key-msg") and key("up") == "Nhấn phím…"
    pg.keyboard.press("KeyI")
    R["remap_up_to_I"] = pg.evaluate("game.settings.keys.up") == "KeyI" and key("up") == "I"
    pg.click("#key-left")
    pg.keyboard.press("KeyI")                                  # I is taken by "up"
    msg = pg.inner_text("#key-msg")
    R["remap_duplicate_warns_and_keeps_old_key"] = ("Trùng phím" in msg and "Đi lên" in msg and msg.startswith("⚠")
                                                    and pg.evaluate("game.settings.keys.left") == "KeyA" and key("left") == "A")
    shot(pg, "15_keys_duplicate_warning.png")
    pg.click("#key-left")
    pg.keyboard.press("Enter")                                 # reserved
    R["remap_reserved_key_warns"] = "dành riêng" in pg.inner_text("#key-msg") and pg.evaluate("game.settings.keys.left") == "KeyA"
    pg.click("#key-left")
    pg.keyboard.press("Escape")                                # cancels, and does not close the Settings screen
    R["remap_escape_cancels"] = ("hủy" in pg.inner_text("#key-msg") and visible(pg, "settings") and key("left") == "A"
                                 and pg.evaluate("game.settings.keys.left") == "KeyA")
    for a, code in (("jump", "KeyJ"), ("dash", "KeyK"), ("pause", "KeyO"), ("interact", "Space")):
        pg.click("#key-" + a)
        pg.keyboard.press(code)
    R["remap_space_binds_cleanly"] = key("interact") == "Space" and pg.evaluate("game.settings.keys.interact") == "Space"
    R["remap_all_set"] = pg.evaluate("game.settings.keys") == {"up": "KeyI", "down": "KeyS", "left": "KeyA", "right": "KeyD", "jump": "KeyJ",
                                                               "dash": "KeyK", "pulse": "KeyF", "pause": "KeyO", "interact": "Space"}
    shot(pg, "15b_keys_remapped.png")
    pg.click("#btn-settings-done")
    pg.reload()
    wait_ready(pg)
    keys_now = pg.evaluate("game.settings.keys")
    R["remap_persists_after_reload"] = keys_now["up"] == "KeyI" and keys_now["pause"] == "KeyO" and keys_now["interact"] == "Space"
    R["remap_menu_help_shows_new_keys"] = "I" in pg.inner_text("#controls-help").split("\n")[0] and "K" in pg.inner_text("#controls-help")
    # the new keys drive the input frame; the old ones no longer do
    enter_night(pg, 1)
    R["remap_hud_key_labels"] = pg.inner_text("#cd-dash .key") == "K" and pg.inner_text("#cd-pulse .key") == "F"

    def frame_while(code, expr):
        pg.keyboard.down(code)
        v = pg.evaluate(expr)
        pg.keyboard.up(code)
        return v
    fwd = frame_while("KeyI", "buildFrame().move")
    old = frame_while("KeyW", "buildFrame().move")
    jump = frame_while("KeyJ", "buildFrame().jump")
    dash = frame_while("KeyK", "buildFrame().dash")
    old_dash = frame_while("ShiftLeft", "buildFrame().dash")
    inter = frame_while("Space", "buildFrame().interact")
    old_jump = frame_while("Space", "buildFrame().jump")
    R["remap_keys_drive_input_frame"] = fwd == [0, 1] and old == [0, 0] and jump is True and dash is True and inter is True
    R["remap_old_keys_dead"] = old_dash is False and old_jump is False
    p0 = pg.evaluate("snap.player.pos")
    pg.keyboard.down("KeyI")
    pg.wait_for_timeout(700)
    pg.keyboard.up("KeyI")
    p1 = pg.evaluate("snap.player.pos")
    R["remapped_key_moves_player"] = p0 != p1
    # remapped pause key (Esc still works too)
    tap(pg, "KeyO")
    pg.wait_for_timeout(100)
    paused = pg.evaluate("game.ui") == "paused"
    tap(pg, "Escape")
    pg.wait_for_timeout(100)
    R["remapped_pause_key_pauses"] = paused and pg.evaluate("game.ui") == "play"
    # reset to defaults (from the pause menu, saved)
    tap(pg, "KeyO")
    pg.click("#btn-settings-pause")
    pg.click("#btn-keys-reset")
    raw = pg.evaluate("JSON.parse(localStorage.getItem('dao-den-long.settings')).keys")
    R["keys_reset_to_defaults_and_saved"] = (raw == {"up": "KeyW", "down": "KeyS", "left": "KeyA", "right": "KeyD", "jump": "Space",
                                                     "dash": "ShiftLeft", "interact": "KeyE", "pulse": "KeyF", "pause": "KeyP"}
                                             and key("up") == "W" and pg.inner_text("#cd-dash .key") == "Shift")
    shot(pg, "15c_keys_reset.png")
    pg.click("#btn-settings-done")
    pg.click("#btn-resume")
    pg.wait_for_function("game.ui === 'play'")


def check_cues_and_motion(pg, R):
    """In play (Night 1). Captions + edge arrow, last 10 s, reduced motion, large text, font sizes."""
    calm(pg)
    pg.evaluate("game.setCam(10, 22)")
    # --- caption + edge arrow when Bóng Mực appears (the sim raises shade_spawned), and the fuel < 30 caption
    trigger_cues(pg)
    caps = pg.inner_text("#captions")
    R["cue_shade_spawn_caption"] = "Bóng Mực xuất hiện" in caps and "⚠" in caps and "m!" in caps
    R["cue_low_fuel_caption"] = "sắp hết dầu" in caps and "L1" in caps
    pg.wait_for_timeout(200)
    r = pg.evaluate("""() => { const t = document.querySelector('#hud .edgearrow.shade .tri').getBoundingClientRect();
        return { x: t.x + t.width / 2, y: t.y + t.height / 2, label: document.querySelector('#hud .edgearrow.shade .lbl').textContent }; }""")
    R["cue_shade_edge_arrow_on_screen_edge"] = (-1 <= r["x"] <= 1281 and -1 <= r["y"] <= 721 and r["label"] == "Bóng Mực"
                                                and (r["x"] < 120 or r["x"] > 1160 or r["y"] < 100 or r["y"] > 620))
    shot(pg, "16_cues_shade_spawn.png")
    bad, n = font_check(pg, MIN_FONT_PX)
    R["font_min_18px_default"] = not bad
    R["font_check_elements"] = n
    R["font_violations_default"] = bad
    # --- last 10 s
    pyrun(pg, "g.shades.clear()\ng.random_shades = False\ng.time_left_ticks = 630")
    pg.wait_for_function("document.getElementById('captions').innerText.includes('10 giây cuối')", timeout=5000)
    R["cue_last_10s_caption"] = pg.evaluate("document.getElementById('timer').classList.contains('last10')")
    shot(pg, "16b_cue_last_10s.png")
    # --- reduced motion + large text, through the Settings screen
    pyrun(pg, "g.time_left_ticks = 20000")
    pg.keyboard.press("Escape")
    pg.click("#btn-settings-pause")
    R["a11y_defaults_off"] = (not pg.evaluate("game.settings.reduced") and not pg.evaluate("game.settings.large")
                              and pg.evaluate("game.settings.captions") is True)
    before = pg.evaluate("[document.getElementById('btn-settings-done').getBoundingClientRect().height, getComputedStyle(document.body).fontSize]")
    pg.click("#set-reduced")
    pg.click("#set-large")
    after = pg.evaluate("[document.getElementById('btn-settings-done').getBoundingClientRect().height, getComputedStyle(document.body).fontSize]")
    R["large_text_scales_ui"] = before[1] == "18px" and after[1] == "22.5px" and after[0] > before[0]
    shot(pg, "17_settings_large_text.png")
    pg.click("#btn-settings-done")
    pg.click("#btn-resume")
    pg.wait_for_function("game.ui === 'play'")
    trigger_cues(pg)
    bad, _ = font_check(pg, MIN_FONT_PX * 1.25)
    R["font_min_22_5px_large"] = not bad
    R["font_violations_large"] = bad
    shot(pg, "17b_hud_large_text.png")
    sh = pg.evaluate(SHAKE)
    R["reduced_motion_no_camera_shake_no_flash"] = sh["spread"] < 1e-6 and sh["vignette"] == 0
    R["reduced_spread_vignette"] = [round(sh["spread"], 6), sh["vignette"]]
    pg.reload()
    wait_ready(pg)
    R["reduced_and_large_persist_after_reload"] = pg.evaluate(
        "game.settings.reduced === true && game.settings.large === true && document.body.classList.contains('reduced')"
        " && document.body.classList.contains('large') && document.getElementById('set-reduced').checked"
        " && document.getElementById('set-large').checked")
    raw = pg.evaluate("JSON.parse(localStorage.getItem('dao-den-long.settings'))")
    R["a11y_saved_in_localstorage"] = raw["reduced"] is True and raw["large"] is True and raw["captions"] is True and "keys" in raw
    # ... and back to normal through the UI: the shake and the flash return, text is 18 px again
    enter_night(pg, 1)
    calm(pg)
    pg.keyboard.press("Escape")
    pg.click("#btn-settings-pause")
    pg.click("#set-reduced")
    pg.click("#set-large")
    pg.click("#btn-settings-done")
    pg.click("#btn-resume")
    pg.wait_for_function("game.ui === 'play'")
    pg.wait_for_timeout(200)
    sh = pg.evaluate(SHAKE)
    R["motion_returns_when_reduced_off"] = sh["spread"] > 0.05 and sh["vignette"] > 0.5
    trigger_cues(pg)
    bad, _ = font_check(pg, MIN_FONT_PX)
    R["font_min_18px_after_large_off"] = not bad and pg.evaluate("getComputedStyle(document.body).fontSize") == "18px"
    # --- captions can be switched off
    pg.keyboard.press("Escape")
    pg.click("#btn-settings-pause")
    pg.click("#set-captions")
    pg.click("#btn-settings-done")
    pg.click("#btn-resume")
    pg.wait_for_function("game.ui === 'play'")
    R["captions_off_clears_cues"] = (pg.evaluate("game.settings.captions") is False and pg.evaluate("document.querySelectorAll('#captions .cap').length") == 0
                                     and pg.evaluate("document.querySelectorAll('#hud .edgearrow.shade').length") == 0)
    set_fuel(pg, 0, 25)
    pyrun(pg, "g.shades.clear()\ng.random_shades = True\ng.sim_tick = 299")
    pg.wait_for_function("snap.shades.length > 0", timeout=5000)
    pg.wait_for_timeout(300)
    R["captions_off_no_new_cues"] = pg.evaluate("document.querySelectorAll('#captions .cap').length") == 0
    pg.keyboard.press("Escape")
    pg.click("#btn-settings-pause")
    pg.click("#set-captions")
    pg.click("#btn-settings-done")
    pg.click("#btn-resume")
    R["captions_back_on"] = pg.evaluate("game.settings.captions") is True


def check_bench(ctx, R, errors):
    """The benchmark page against the real server's /api/bench sink: a 3 s run."""
    n0 = len(BENCH_RESULTS)
    t_before = time.time() * 1000
    pg = ctx.new_page()
    watch(pg, errors)
    pg.goto(f"http://127.0.0.1:{PORT}/web/index.html?bench=1&seed=42&duration=3")
    pg.wait_for_function("window.__benchDone !== undefined || window.__loadError !== undefined", timeout=300000)
    R["bench_no_load_error"] = pg.evaluate("window.__loadError === undefined")
    done = pg.evaluate("window.__benchDone")
    R["bench_posted_ok"] = bool(done and done.get("ok")) and len(BENCH_RESULTS) == n0 + 1
    if not R["bench_posted_ok"] or not R["bench_no_load_error"]:
        R["bench_error_detail"] = str(done) + " / " + str(pg.evaluate("window.__loadError"))
        pg.close()
        return
    pl = BENCH_RESULTS[-1]
    dts = pl.get("dts_ms") or []
    R["bench_payload_fields"] = {"first_frame_epoch_ms", "dts_ms", "renderer", "warmup_s"} <= set(pl) and pl["warmup_s"] == 3
    R["bench_dts_valid"] = len(dts) >= 2 and all(isinstance(d, (int, float)) and 0 < d < 30000 for d in dts)
    total = sum(dts)
    R["bench_measured_exactly_duration"] = bool(dts) and 3000 <= total < 3000 + max(dts) + 1
    R["bench_first_frame_epoch_plausible"] = t_before <= pl["first_frame_epoch_ms"] <= time.time() * 1000
    R["bench_renderer_string"] = isinstance(pl["renderer"], str) and " · " in pl["renderer"] and len(pl["renderer"]) > 8
    stats = benchstats.compute(dts)
    R["bench_stats_computable"] = stats["frames"] == len(dts) and stats["avg_fps"] > 0 and stats["p1_low_fps"] > 0
    R["bench_stats"] = stats
    R["bench_renderer"] = pl["renderer"]
    R["bench_first_frame_ms_after_navigation"] = round(pl["first_frame_epoch_ms"] - t_before)
    R["bench_canvas_1280x720"] = pg.evaluate(
        "(() => { const c = renderer.domElement, r = c.getBoundingClientRect(); return c.width === 1280 && c.height === 720"
        " && Math.round(r.width) === 1280 && Math.round(r.height) === 720 && renderer.getPixelRatio() === 1; })()")
    R["bench_no_ui"] = pg.evaluate(
        "[...document.querySelectorAll('.overlay, #hud, #fps')].every((e) => getComputedStyle(e).display === 'none')")
    info = pg.evaluate("game.benchInfo()")
    R["bench_200_shades_100_motes_instanced"] = info["shades"] == 200 and info["motes"] == 100
    s = pg.evaluate("[snap.shades.length, snap.shades.every((s) => s.state === 'wander' || s.state === 'spawning'), snap.motes.length,"
                    " snap.lanterns.filter((l) => l.lit).length, snap.night]")
    R["bench_scene_from_sim"] = s[0] == 200 and s[1] is True and s[2] == 100 and s[3] == 3 and s[4] == 1
    cam = pg.evaluate("""() => { const a = Math.atan2(camera.position.z, camera.position.x), want = 2 * Math.PI * benchT / 15;
        return { r: Math.hypot(camera.position.x, camera.position.z), y: camera.position.y,
                 dAng: Math.atan2(Math.sin(a - want), Math.cos(a - want)) }; }""")
    R["bench_camera_circle_r30_y15"] = abs(cam["r"] - 30) < 1e-6 and abs(cam["y"] - 15) < 1e-9 and abs(cam["dAng"]) < 1e-6
    R["bench_sim_stepped"] = pg.evaluate("snap.tick") > 0
    R["bench_ignores_input"] = pg.evaluate(
        "(() => { for (const k of ['KeyW', 'Space']) dispatchEvent(new KeyboardEvent('keydown', { code: k })); return Object.keys(keys).length === 0; })()")
    shot(pg, "18_bench_scene.png")
    pg.close()


def check_static_fallback(ctx, R, errors):
    """A server without /api (single-file / Artifact build): the leaderboard lives in localStorage and survives a reload."""
    pg = ctx.new_page()
    watch(pg, errors, no_api=True)
    pg.goto(f"http://127.0.0.1:{PORT_STATIC}/web/")
    wait_ready(pg)
    lose_night(pg)
    save_name(pg, "Local_One")
    R["lb_fallback_local_storage_used"] = (pg.evaluate("window.__lastSave.via") == "local" and "trình duyệt" in pg.inner_text("#name-saved")
                                           and "hạng 1" in pg.inner_text("#name-saved"))
    pg.click("#btn-menu-result")
    lose_night(pg)
    save_name(pg, "Local_Two")
    R["lb_fallback_ties_keep_time_order"] = "hạng 2" in pg.inner_text("#name-saved")
    pg.click("#btn-menu-result")
    pg.reload()
    wait_ready(pg)
    open_lb_from_menu(pg)
    rows = lb_rows(pg)
    R["lb_fallback_persists_after_reload"] = ([r[1] for r in rows] == ["Local_One", "Local_Two"] and pg.evaluate("window.__lbSource") == "local"
                                              and "localStorage" in pg.inner_text("#lb-source"))
    shot(pg, "14b_leaderboard_local.png")
    R["lb_fallback_did_not_touch_server_file"] = len(leaderboard.load(LB_FILE)) == 3
    pg.close()


def main():
    os.makedirs(OUT, exist_ok=True)
    httpd = serve_api()
    httpd_static = serve_static()
    R = {}
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                     "--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1280, "height": 720})
        pg = ctx.new_page()
        watch(pg, errors)
        pg.goto(f"http://127.0.0.1:{PORT}/web/")
        wait_ready(pg)
        pg.wait_for_timeout(300)
        R["menu_shown"] = visible(pg, "menu")
        # vendor-first loading: when web/vendor/ exists (tools/fetch_vendor.py) the page must use it, not the CDN
        res = pg.evaluate("performance.getEntriesByType('resource').map((e) => e.name)")
        has_three = os.path.exists(os.path.join(ROOT, "web", "vendor", "three.min.js"))
        has_pyo = os.path.exists(os.path.join(ROOT, "web", "vendor", "pyodide", "pyodide.js"))
        R["vendor_three_used"] = any("vendor/three.min.js" in u for u in res)
        R["vendor_pyodide_used"] = any("vendor/pyodide/pyodide.js" in u for u in res)
        R["vendor_first_when_present"] = ((not has_three or R["vendor_three_used"]) and (not has_pyo or R["vendor_pyodide_used"])
                                          and not any("cdnjs.cloudflare.com" in u and has_three for u in res)
                                          and not any("cdn.jsdelivr.net" in u and has_pyo for u in res))
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
        R["cb_shade_rim_is_00B3FF"] = pg.evaluate("shadeObjs.S1.userData.rimHex") == 0x00B3FF
        R["cb_shade_eyes_are_00B3FF"] = pg.evaluate("shadeObjs.S1.userData.eyeHex") == 0x00B3FF
        # ... and the GPU instance buffers really carry it (rim instance 0 = #00B3FF, eyes too)
        col = pg.evaluate("[Array.from(shadeInst.rim.userData.colArr.slice(0, 3)), Array.from(shadeInst.eyes.userData.colArr.slice(0, 3))]")
        R["cb_shade_instance_colours_00B3FF"] = all(abs(c[0] - 0) < 0.01 and abs(c[1] - 0xB3 / 255) < 0.01 and abs(c[2] - 1) < 0.01 for c in col)
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
            and pg.evaluate("shadeObjs.S1.userData.rimHex") == 0x7A3CFF
            and pg.evaluate("getComputedStyle(document.body).getPropertyValue('--danger').trim().toLowerCase()") == "#ff5a5f")

        # ---- draining shade (default palette): tendril to the lantern + fuel falls faster than 1/s
        f0 = pg.evaluate("snap.lanterns[0].fuel")
        pg.wait_for_timeout(700)
        f1 = pg.evaluate("snap.lanterns[0].fuel")
        R["shade_drain_tendril_visible"] = pg.evaluate("!!(shadeObjs.S1.userData.tendril && shadeObjs.S1.userData.tendril.visible)") and pg.evaluate("snap.shades[0].state") == "drain"
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
        R["default_shade_rim_is_7A3CFF"] = pg.evaluate("shadeObjs.S1.userData.rimHex") == 0x7A3CFF

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
        R["cue_wind_soon_caption"] = "Gió sắp thổi" in pg.inner_text("#captions") and "⚠" in pg.inner_text("#captions")
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

        # ---- Ticket-04: leaderboard (Dawn + losses), key remapping, cues / reduced motion / large text / fonts
        check_leaderboard(pg, R)
        check_keys(pg, R)
        enter_night(pg, 1)
        check_cues_and_motion(pg, R)
        # ---- Ticket-04: the benchmark page (new page) and the no-API leaderboard fallback (static server)
        pg.goto("about:blank")                    # stop the main page's render loop: the benchmark gets the GPU to itself
        check_bench(ctx, R, errors)
        check_static_fallback(ctx, R, errors)
        b.close()
    httpd.shutdown()
    httpd_static.shutdown()
    R["fps_note"] = ("headless Chromium uses SwiftShader software GL; real GPUs render much faster, "
                     "so these FPS numbers are a lower bound")
    R["js_errors"] = errors
    info = {"js_errors", "fps_note", "won_scores", "parity_night1_ticks", "parity_night3_ticks",
            "fps_night1_avg_5s", "fps_night3_avg_5s", "low_fuel_blink_flips_in_3s", "font_check_elements",
            "font_violations_default", "font_violations_large", "reduced_spread_vignette", "bench_stats", "bench_renderer",
            "bench_first_frame_ms_after_navigation", "bench_error_detail"}
    ok = all(v is True for k, v in R.items() if k not in info) and not errors
    R["ok"] = ok
    with open(os.path.join(OUT, "web_check.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)
    print(json.dumps(R, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
