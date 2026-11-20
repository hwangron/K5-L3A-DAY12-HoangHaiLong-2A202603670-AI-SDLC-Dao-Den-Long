"""Record the demo video docs/demo/demo.mp4 automatically (nothing here is edited by hand, nothing is faked).

Run (Windows; Playwright + imageio-ffmpeg live in the lab venv; the project itself needs only the stdlib):
    "d:\\Lab 12\\.venv\\Scripts\\python.exe" tools/record_demo.py [--out docs/demo/demo.mp4] [--work DIR]
    ... --test-bot [SECONDS]     only run the gameplay bot (headed, no video) and print what it did

What it does
  1. starts the real server (serve.make_server; a temporary leaderboard file, never the player's own) and a headed
     Playwright Chromium with the GPU on (ANGLE / Direct3D 11), 1280x720;
  2. runs the evidence commands now: `python tools/check.py`, `python headless.py --seed 1 --night 1 --ticks 120`,
     `git log --oneline -15`, `git tag`, and reads docs/proof/phase-4/{bench,soak}.json and the harness files;
  3. renders a title card and the evidence cards (HTML -> PNG) from those real outputs;
  4. records ONE Playwright video (record_video_dir) of the real page: Night 1 played by a bot, a tour of Nights 2/3,
     pause, settings, leaderboard, then the ?bench=1 scene. The bot only reads `snap` (+ the camera yaw) from the page and
     holds real keys (WASD, E, F, Shift) through page.keyboard. No teleport, no change to the sim state. The only
     things injected into the page are an annotation box (captions) and the page's own camera helper game.setCam();
  5. joins everything with ffmpeg (imageio-ffmpeg's binary): libx264, crf 28, yuv420p, 30 fps, no audio track
     (Playwright video has no sound).
The official benchmark numbers come from `python bench.py` in real Chrome, not from this video.
"""
import argparse
import datetime
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

W, H, FPS, CRF = 1280, 720, 30, 28
VERSION = "v1.0.0"
PLAY_SECONDS = 70            # game seconds of Night 1 driven by the bot
TOUR_SECONDS = 10            # game seconds of each of Night 2 / Night 3
BENCH_SECONDS = 10           # ?bench=1&duration=10 (+3 s warm-up inside the page)
CARD_SECONDS = 8

CHROME_ARGS = ["--use-gl=angle", "--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
               "--autoplay-policy=no-user-gesture-required",
               "--disable-features=CalculateNativeWinOcclusion", "--disable-renderer-backgrounding",
               "--disable-backgrounding-occluded-windows", "--disable-background-timer-throttling"]


# ================================================================================================ small helpers
def log(*a):
    print(*a, flush=True)


def esc(s):
    return html.escape(s, quote=False)


def run_cmd(args, **kw):
    """Run a command in the repo, return (stdout+stderr text, exit code, seconds)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", NO_COLOR="1")
    t0 = time.time()
    p = subprocess.run(args, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    return p.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n"), p.returncode, time.time() - t0


def find_python():
    """The `python` the project is run with (stdlib only); fall back to this interpreter."""
    return shutil.which("python") or sys.executable


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        exe = shutil.which("ffmpeg")
        if not exe:
            sys.exit("need imageio-ffmpeg (pip install imageio-ffmpeg) or ffmpeg on PATH")
        return exe


# ================================================================================================ evidence (real outputs)
def gather_evidence(work):
    py = find_python()
    ev = {"when": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M (UTC%z)")}
    log("[evidence] python tools/check.py (about a minute) ...")
    out, code, secs = run_cmd([py, "tools/check.py"])
    ev["check"] = {"cmd": "python tools/check.py", "out": out, "code": code, "secs": secs}
    log(f"[evidence] check.py exit={code} in {secs:.1f}s ({len(out.splitlines())} lines)")

    jl = os.path.join(work, "headless_out.jsonl")
    out, code, secs = run_cmd([py, "headless.py", "--seed", "1", "--night", "1", "--ticks", "120", "--out", jl])
    lines = []
    if os.path.exists(jl):
        with open(jl, encoding="utf-8") as f:
            lines = f.read().splitlines()
    ev["headless"] = {"cmd": "python headless.py --seed 1 --night 1 --ticks 120 --out out.jsonl", "code": code,
                      "stdout": out, "lines": lines}

    out, code, _ = run_cmd(["git", "log", "--oneline", "-15"])
    ev["git_log"] = {"cmd": "git log --oneline -15", "out": out, "code": code}
    out, code, _ = run_cmd(["git", "tag"])
    ev["git_tag"] = {"cmd": "git tag", "out": out, "code": code}
    out, code, _ = run_cmd(["git", "status", "--short"])
    ev["git_status"] = [l for l in out.splitlines() if l.strip()]

    def read(rel):
        p = os.path.join(ROOT, *rel.split("/"))
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        return {"path": rel, "text": txt, "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")}
    ev["bench"] = read("docs/proof/phase-4/bench.json")
    ev["soak"] = read("docs/proof/phase-4/soak.json")

    harness = []
    files = ["AGENTS.md", "CLAUDE.md"]
    agents_dir = os.path.join(ROOT, ".claude", "agents")
    files += [".claude/agents/" + n for n in sorted(os.listdir(agents_dir)) if n.endswith(".md")]
    files += [".claude/settings.json"]
    skills_dir = os.path.join(ROOT, ".claude", "skills")
    for d in sorted(os.listdir(skills_dir)):
        sk = os.path.join(skills_dir, d, "SKILL.md")
        if os.path.exists(sk):
            files.append(f".claude/skills/{d}/SKILL.md")
    for rel in files:
        r = read(rel)
        txt = r["text"]
        info = {"path": rel, "lines": len(txt.splitlines()), "note": ""}
        fm = re.match(r"---\n(.*?)\n---", txt, re.S)
        if fm:
            kv = dict(re.findall(r"^(\w+):\s*(.*)$", fm.group(1), re.M))
            bits = [f"model: {kv['model']}"] if "model" in kv else []
            if "description" in kv:
                bits.append(kv["description"])
            info["note"] = " · ".join(bits)
        elif rel == ".claude/settings.json":
            cfg = json.loads(txt)
            parts = []
            for event, groups in cfg.get("hooks", {}).items():
                for g in groups:
                    for h in g.get("hooks", []):
                        parts.append(f"hook {event} ({h.get('type')}, timeout {h.get('timeout')} s): {h.get('command')}")
            info["note"] = "  ||  ".join(parts)
        else:
            info["note"] = txt.splitlines()[0] if txt.strip() else ""
        harness.append(info)
    ev["harness"] = harness
    return ev


# ================================================================================================ HTML cards
CARD_CSS = """
:root { --bg:#0b1030; --amber:#ffb340; --ink:#eef1ff; --dim:#a3aedf; --line:#2b3678; --ok:#7be0a0; --bad:#ff8a8a; }
* { box-sizing:border-box }
html,body { margin:0; width:1280px; height:720px; overflow:hidden }
body { background:radial-gradient(ellipse at 50% -10%, #25307a 0%, #0b1030 68%); color:var(--ink);
       font-family:"Segoe UI",system-ui,sans-serif; display:flex; flex-direction:column }
header { padding:22px 40px 8px }
h1 { margin:0; font-size:34px; color:var(--amber); font-weight:700 }
.sub { color:var(--dim); font-size:20px; margin-top:4px }
.cmd { font:20px/1.3 Consolas,"Cascadia Mono",monospace; color:#fff; background:#10174a; border:1px solid var(--line);
       border-radius:8px; padding:6px 12px; margin:10px 40px 8px; white-space:pre-wrap; word-break:break-all }
.cmd b { color:var(--amber) }
main { flex:1; min-height:0; padding:0 40px; display:flex; gap:24px }
pre { margin:0; font:19px/1.27 Consolas,"Cascadia Mono",monospace; white-space:pre; overflow:hidden }
.pass { color:var(--ok) } .fail { color:var(--bad) } .dim { color:var(--dim) }
footer { padding:9px 40px 14px; color:var(--dim); font-size:17px; border-top:1px solid var(--line) }
h3 { margin:2px 0 6px; font-size:19px; color:var(--amber) }
.col { min-width:0 }
table { border-collapse:collapse; width:100% } td { padding:5px 8px; border-bottom:1px solid var(--line); vertical-align:top; font-size:17px }
td.p { font:18px Consolas,"Cascadia Mono",monospace; color:var(--ok); white-space:nowrap } td.n { text-align:right; color:var(--dim); white-space:nowrap }
td.d { color:var(--ink) }
"""


def card_html(title, sub, cmd, body, footer):
    cmd_html = f'<div class="cmd"><b>$</b> {esc(cmd)}</div>' if cmd else ""
    return (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body>'
            f'<header><h1>{esc(title)}</h1><div class="sub">{esc(sub)}</div></header>{cmd_html}'
            f'<main>{body}</main><footer>{footer}</footer></body></html>')


def colorize(lines):
    out = []
    for l in lines:
        e = esc(l)
        if l.startswith("PASS"):
            e = '<span class="pass">PASS</span>' + e[4:]
        elif l.startswith("FAIL") or "FAIL" in l[:12]:
            e = f'<span class="fail">{e}</span>'
        out.append(e)
    return "\n".join(out)


def clip(line, n):
    return line if len(line) <= n else line[:n] + f" … [+{len(line) - n} ký tự]"


def build_cards(ev, meta):
    stamp = f"chạy lúc quay: {ev['when']}"
    cards = {}

    c = ev["check"]
    lines = c["out"].rstrip("\n").splitlines()
    half = math.ceil(len(lines) / 2)
    body = (f'<div class="col"><pre>{colorize(lines[:half])}</pre></div>'
            f'<div class="col"><pre>{colorize(lines[half:])}</pre></div>')
    verdict = "exit code 0 = xanh" if c["code"] == 0 else f"exit code {c['code']} (KHÔNG xanh)"
    cards["check"] = card_html("Bằng chứng 1/5 · kiểm tra toàn bộ", "Đầu ra thật của lệnh, chạy lại lúc quay video", c["cmd"], body,
                               f"{verdict} · {c['secs']:.0f} s · {len(lines)} dòng đầu ra (hiện đủ) · {stamp}")

    b, s = ev["bench"], ev["soak"]
    soak_lines = s["text"].rstrip("\n").splitlines()
    cut = next((i for i, l in enumerate(soak_lines) if '"per_night"' in l), 20) + 1
    shown = soak_lines[:cut]
    more = len(soak_lines) - len(shown)
    soak_txt = "\n".join(esc(l) for l in shown) + (f'\n<span class="dim">    … còn {more} dòng trong file (kết quả từng đêm)</span>' if more > 0 else "")
    body = (f'<div class="col" style="flex:0 0 560px"><h3>{esc(b["path"])}</h3>'
            f'<pre style="font-size:18px;white-space:pre-wrap;word-break:break-all">{esc(b["text"].rstrip())}</pre>'
            f'<p class="dim" style="font-size:17px;margin:10px 0 0">file ghi lúc {b["mtime"]}. Số chính thức do <b>python bench.py</b> đo trên Chrome thật, '
            f'không phải từ video này.</p></div>'
            f'<div class="col"><h3>{esc(s["path"])}</h3><pre style="font-size:18px">{soak_txt}</pre></div>')
    cards["proof"] = card_html("Bằng chứng 2/5 · bench và soak (Phase 4)", "Nội dung nguyên văn của hai file proof đã lưu trong repo",
                               "type docs\\proof\\phase-4\\bench.json  &  type docs\\proof\\phase-4\\soak.json", body,
                               f"đọc từ đĩa lúc quay · soak.json ghi lúc {s['mtime']} · {stamp}")

    h = ev["headless"]
    shown = [clip(l, 150) for l in h["lines"][:6]]
    body = (f'<div class="col" style="flex:1"><pre style="font-size:17px;white-space:pre-wrap;word-break:break-all">{esc(chr(10).join(shown))}</pre>'
            f'<p class="dim" style="font-size:18px;margin:12px 0 0">6 / {len(h["lines"])} dòng của out.jsonl (mỗi dòng là một JSON; snapshot cắt bớt để vừa màn hình) '
            f'· exit code {h["code"]}</p></div>')
    cards["headless"] = card_html("Bằng chứng 3/5 · chạy headless", "Cùng sim.py với bản web, chạy không giao diện: 120 tick, seed 1, Đêm 1",
                                  h["cmd"], body, f"đầu ra thật · {stamp}")

    g, t = ev["git_log"], ev["git_tag"]
    dirty = len(ev["git_status"])
    tags = t["out"].strip() or "(chưa có tag)"
    body = (f'<div class="col" style="flex:1"><h3>{esc(g["cmd"])}</h3><pre style="font-size:16.5px;white-space:pre-wrap;word-break:break-word">{esc(g["out"].rstrip())}</pre></div>'
            f'<div class="col" style="flex:0 0 170px"><h3>{esc(t["cmd"])}</h3><pre style="font-size:20px">{esc(tags)}</pre></div>')
    note = f"lúc quay cây làm việc còn {dirty} file chưa commit (git status --short)" if dirty else "cây làm việc sạch lúc quay (git status --short rỗng)"
    cards["git"] = card_html("Bằng chứng 4/5 · lịch sử git", "Commit và tag của repo", "", body, f"{note} · {stamp}")

    rows = "".join(f'<tr><td class="p">{esc(x["path"])}</td><td class="n">{x["lines"]} dòng</td><td class="d">{esc(clip(x["note"], 330))}</td></tr>'
                   for x in ev["harness"])
    body = f'<div class="col" style="flex:1"><table>{rows}</table></div>'
    cards["harness"] = card_html("Bằng chứng 5/5 · harness cho agent", "AGENTS.md, các subagent, hook Stop và skill verify (đọc từ file thật)", "", body,
                                 f"mô tả lấy từ phần frontmatter / settings.json · {stamp}")

    title_body = (
        '<div style="margin:auto;text-align:center;padding:0 80px">'
        f'<div style="font-size:64px;font-weight:700;color:var(--amber);line-height:1.15">Đảo Đèn Lồng {VERSION}</div>'
        '<div style="font-size:40px;margin-top:10px">demo tự động quay bằng Playwright</div>'
        '<div style="font-size:23px;line-height:1.5;margin-top:34px;color:var(--dim)">Video này do kịch bản <b style="color:var(--ink)">tools/record_demo.py</b> quay: '
        'một bot đọc trạng thái của trang và giữ phím như người chơi (không dịch chuyển, không sửa sim); '
        'số liệu trên các thẻ bằng chứng được chạy hoặc đọc lại ngay lúc quay.</div></div>')
    cards["title"] = (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body>'
                      f'{title_body}<footer style="text-align:center;font-size:16px">{esc(meta)}<br>quay lúc {esc(ev["when"])}</footer></body></html>')
    return cards


# ================================================================================================ page overlay + bot
CAPTION_JS = """
(() => {
  const css = `#demo-cap{position:fixed;z-index:2147483647;pointer-events:none;background:rgba(8,10,28,.80);
    border:1px solid rgba(255,179,64,.6);border-radius:10px;padding:8px 14px;color:#fff;
    font:600 18px/1.35 "Segoe UI",system-ui,sans-serif;left:12px;top:68px;width:410px}
    #demo-cap.bottom{left:12px;right:12px;top:auto;bottom:10px;width:auto}
    #demo-cap .t{color:#ffb340;font-weight:700} #demo-cap .s{font-weight:400;color:#dfe6ff;margin-top:2px;white-space:pre-line}
    #demo-cap:empty{display:none}`;
  const mount = () => {
    if (document.getElementById('demo-cap')) return;
    const st = document.createElement('style'); st.textContent = css; document.documentElement.appendChild(st);
    const d = document.createElement('div'); d.id = 'demo-cap'; document.documentElement.appendChild(d);
    window.__cap = (t, s, where) => {
      d.className = where === 'bottom' ? 'bottom' : '';
      d.innerHTML = t ? '<div class="t"></div>' + (s ? '<div class="s"></div>' : '') : '';
      if (t) { d.querySelector('.t').textContent = t; if (s) d.querySelector('.s').textContent = s; }
    };
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
"""

READ_JS = "() => ({ s: snap, x: extra, yaw: yaw, ui: game.ui })"
KEYS = {"up": "KeyW", "down": "KeyS", "left": "KeyA", "right": "KeyD"}   # default bindings; x+ (world +X at yaw 0) = left


def cap(pg, title, status="", where="top"):
    try:
        pg.evaluate("([t, s, w]) => window.__cap && window.__cap(t, s, w)", [title, status, where])
    except Exception:       # page navigating: the next call will do it
        pass


def dist(ax, az, bx, bz):
    return math.hypot(ax - bx, az - bz)


class Bot:
    """Plays like a person with a keyboard: reads the page's `snap`, decides, holds real keys. Nothing else."""
    LANTERN_COST = 10      # contract numbers (game.contract.json tuning): lantern_cost, interact_radius, pulse_cost
    INTERACT_R = 2.0
    PULSE_COST = 3

    def __init__(self, pg):
        self.pg = pg
        self.down = set()
        self.last_e = -9.0
        self.last_f = -9.0
        self.last_dash = -9.0
        self.skip_lantern = {}          # lantern id -> game time until which we do not try it again
        self.count = {"E": 0, "F": 0, "Shift": 0}
        self.lit_seen = set()
        self.events = []
        self.orbit = False
        self._i = 0
        self.flames = 3

    # -- keys
    def hold(self, codes):
        for c in sorted(self.down - codes):
            self.pg.keyboard.up(c)
            self.down.discard(c)
        for c in sorted(codes - self.down):
            self.pg.keyboard.down(c)
            self.down.add(c)

    def release_all(self):
        self.hold(set())

    def tap(self, code, ms=120):
        self.pg.keyboard.down(code)
        self.pg.wait_for_timeout(ms)
        self.pg.keyboard.up(code)

    def move_keys(self, wx, wz, yaw):
        """World direction (wx, wz) -> WASD, given the camera yaw (input -> world is a rotation by yaw)."""
        th = math.radians(yaw)
        mx = wx * math.cos(th) - wz * math.sin(th)
        mz = wx * math.sin(th) + wz * math.cos(th)
        n = math.hypot(mx, mz)
        keys = set()
        if n < 1e-6:
            return keys
        if abs(mz) > 0.383 * n:
            keys.add(KEYS["up"] if mz > 0 else KEYS["down"])
        if abs(mx) > 0.383 * n:
            keys.add(KEYS["left"] if mx > 0 else KEYS["right"])
        return keys

    # -- one decision
    def step(self, t_game):
        pg = self.pg
        st = pg.evaluate(READ_JS)
        if st["ui"] != "play":
            self.release_all()
            return None
        s, x, yaw = st["s"], st["x"], st["yaw"]
        p = s["player"]
        px, pz = p["pos"][0], p["pos"][2]
        carried = p["carried"]
        status = ""
        lit_now = {l["id"] for l in s["lanterns"] if l["lit"]}
        for lid in sorted(lit_now - self.lit_seen):
            self.events.append((round(240 - s["time_left_s"], 1), f"lantern {lid} lit"))
        self.lit_seen |= lit_now
        if p["flames"] < self.flames:
            self.events.append((round(240 - s["time_left_s"], 1), f"HIT: flames {self.flames} -> {p['flames']}, carried {carried}"))
        self.flames = p["flames"]
        keys = set()

        threats = sorted(((dist(px, pz, sh["pos"][0], sh["pos"][2]), sh) for sh in s["shades"]
                          if sh["state"] in ("chase", "wander", "drain", "spawning")), key=lambda a: a[0])
        near = threats[0] if threats else None
        target = None                      # (x, z, label, kind)

        # 1. a Bóng Mực close by: Tỏa Sáng (F) if we can pay 3 motes, otherwise run toward light / away
        if near and near[0] <= 6.5 and near[1]["state"] in ("chase", "drain", "wander"):
            d, sh = near
            can_pulse = carried >= self.PULSE_COST and x.get("pulse_ready")
            if can_pulse and d <= (3.6 if sh["state"] != "wander" else 2.6) and t_game - self.last_f > 0.5:
                self.release_all() if d < 2 else None
                self.tap("KeyF")
                self.count["F"] += 1
                self.last_f = t_game
                self.events.append((round(240 - s["time_left_s"], 1), f"F (pulse) at {d:.1f} m from {sh['id']}"))
                return f"Bóng Mực {sh['id']} cách {d:.1f} m: nhấn F (Tỏa Sáng)"
            wary = (not can_pulse) and (sh["state"] != "wander" or d <= 3.0)
            lit = [l for l in s["lanterns"] if l["lit"] and l["fuel"] >= 30]
            if wary and lit:
                l = min(lit, key=lambda l: dist(px, pz, l["pos"][0], l["pos"][2]))
                target = (l["pos"][0], l["pos"][2], f"chạy về vùng sáng của {l['id']}", "flee")
            elif wary:
                target = (px + (px - sh["pos"][0]) * 3, pz + (pz - sh["pos"][2]) * 3, f"tránh Bóng Mực {sh['id']} ({d:.1f} m)", "flee")
            if wary and d <= 2.4 and x.get("dash_ready") and t_game - self.last_dash > 1.0:
                self.hold(self.move_keys(target[0] - px, target[1] - pz, yaw))
                self.tap("ShiftLeft", 90)
                self.count["Shift"] += 1
                self.last_dash = t_game
                return f"Bóng Mực cách {d:.1f} m: lướt (Shift)"

        # 2. carrying enough motes: nearest lantern that needs them (unlit first); or top up a lit lantern that is low
        if target is None:
            unlit = [l for l in s["lanterns"] if not l["lit"] and self.skip_lantern.get(l["id"], -1) < t_game]
            lowfuel = [l for l in s["lanterns"] if l["lit"] and l["fuel"] <= 70 and self.skip_lantern.get(l["id"], -1) < t_game]
            pick = None
            if carried >= self.LANTERN_COST and unlit:
                pick = min(unlit, key=lambda l: dist(px, pz, l["pos"][0], l["pos"][2]))
            elif carried >= self.PULSE_COST + 1 and lowfuel:
                cand = min(lowfuel, key=lambda l: dist(px, pz, l["pos"][0], l["pos"][2]))
                if dist(px, pz, cand["pos"][0], cand["pos"][2]) <= 16:
                    pick = cand
            if pick:
                d = dist(px, pz, pick["pos"][0], pick["pos"][2])
                if d <= self.INTERACT_R - 0.35:
                    self.release_all()
                    if t_game - self.last_e > 0.8:
                        c0 = carried
                        self.tap("KeyE")
                        self.count["E"] += 1
                        self.last_e = t_game
                        what = "thắp đèn" if not pick["lit"] else "châm dầu"
                        self.events.append((round(240 - s["time_left_s"], 1), f"E at {pick['id']} ({what}, carried {c0})"))
                        # if nothing changed after a moment, do not insist on this lantern for a while
                        pg.wait_for_timeout(150)
                        c1 = pg.evaluate("snap.player.carried")
                        if c1 >= c0:
                            self.skip_lantern[pick["id"]] = t_game + 4
                        return f"ở {pick['id']}: nhấn E ({what})"
                    return f"ở {pick['id']}: nhấn E"
                target = (pick["pos"][0], pick["pos"][2], f"mang {carried} đom đóm tới {pick['id']} ({d:.0f} m)", "lantern")

        # 3. collect motes (nearest, avoiding ones next to a shade)
        if target is None:
            motes = s["motes"]
            if motes:
                def bad(m):
                    return near is not None and dist(m["pos"][0], m["pos"][2], near[1]["pos"][0], near[1]["pos"][2]) < 3.5
                good = [m for m in motes if not bad(m)] or motes
                m = min(good, key=lambda m: dist(px, pz, m["pos"][0], m["pos"][2]))
                d = dist(px, pz, m["pos"][0], m["pos"][2])
                target = (m["pos"][0], m["pos"][2], f"đi nhặt đom đóm {m['id']} ({d:.0f} m)", "mote")

        if target:
            keys |= self.move_keys(target[0] - px, target[1] - pz, yaw)
            status = target[2]
        # camera orbit for the tour (ArrowLeft in short bursts)
        if self.orbit:
            self._i += 1
            if self._i % 12 < 3:
                keys.add("ArrowLeft")
        self.hold(keys)
        return status

    def play(self, pg_cap, game_seconds, title, where="top", wall_limit=None):
        """Run the bot for `game_seconds` of game time (or until the night ends). Returns the game seconds played."""
        pg = self.pg
        s0 = pg.evaluate("snap.time_left_s")
        t_wall0 = time.time()
        last_cap = 0.0
        played = 0.0
        while True:
            now = pg.evaluate("snap.time_left_s")
            played = s0 - now
            if played >= game_seconds or (wall_limit and time.time() - t_wall0 > wall_limit):
                break
            try:
                status = self.step(played)
            except Exception as e:  # a page error must not kill the recording
                log("[bot] step error:", e)
                time.sleep(0.2)
                continue
            if status is None:
                break
            if time.time() - last_cap > 0.3:
                hud = pg.evaluate("[snap.player.carried, snap.player.capacity, snap.lanterns.filter((l) => l.lit).length, snap.lanterns.length, snap.player.flames]")
                pg_cap(title, f"{status}\nĐom đóm {hud[0]}/{hud[1]} · Đèn sáng {hud[2]}/{hud[3]} · Ngọn Lửa {hud[4]}", where)
                last_cap = time.time()
            time.sleep(0.02)
        self.release_all()
        return played


def make_cap(pg):
    def f(title, status="", where="top"):
        # the status contains newlines -> two lines in the box
        cap(pg, title, status, where)
    return f


# ================================================================================================ recording
def wait_ready(pg):
    pg.wait_for_function("window.__ready === true", timeout=180000)


def pause_ms(pg, ms):
    pg.wait_for_timeout(ms)


def enter_night_from_menu(pg, n, c):
    pg.click(f"#btn-night-{n}")
    pg.wait_for_function("game.ui === 'intro'")
    c(f"Đêm {n}: màn giới thiệu của Ông Đăng", "bấm nút “Đêm %d” của menu (hàm startRun của trang)" % n, "bottom")
    pause_ms(pg, 2200)
    pg.keyboard.press("Enter")
    pg.wait_for_function("game.ui === 'play'")


def record_game(pw_browser, base, work, args, bench_url_only=False):
    """One recorded context: Night 1 (bot) -> Night 2/3 tour -> pause -> settings -> leaderboard -> bench scene."""
    vid_dir = os.path.join(work, "video")
    shutil.rmtree(vid_dir, ignore_errors=True)
    ctx = pw_browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                 record_video_dir=vid_dir, record_video_size={"width": W, "height": H})
    ctx.add_init_script(CAPTION_JS)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    c = make_cap(pg)
    marks = {}
    t0 = time.time()

    def mark(name):
        marks[name] = round(time.time() - t0, 1)
        log(f"[rec] {marks[name]:6.1f}s  {name}")

    # ---- segment 2: Night 1 played by the bot
    mark("menu")
    pg.goto(f"{base}/web/?seed=11")
    c("Đang tải game…", "Pyodide chạy game/sim.py (Python) ngay trong trình duyệt", "bottom")
    wait_ready(pg)
    c("Màn hình chính", "Menu, chọn Đêm, bảng xếp hạng và cài đặt đều là phần của trang web", "bottom")
    pause_ms(pg, 2600)
    pg.click("#btn-start")
    pg.wait_for_function("game.ui === 'intro'")
    c("Đêm 1 · Đảo Bến: màn giới thiệu", "nhấn “Bắt đầu” (nút của trang), rồi Enter để vào đêm", "bottom")
    pause_ms(pg, 2600)
    pg.keyboard.press("Enter")
    pg.wait_for_function("game.ui === 'play'")
    mark("night1 play")
    bot = Bot(pg)
    title = "Bot tự chơi Đêm 1 (đọc snap, giữ phím)"
    played = bot.play(c, args.play_seconds, title)
    mark("night1 end of bot")
    log(f"[bot] night 1: {played:.1f} game s, presses {bot.count}")
    for e in bot.events:
        log("[bot]   t+%6.1f  %s" % e)
    n1 = pg.evaluate("[snap.state, snap.score, snap.player.flames, snap.lanterns.filter((l) => l.lit).length, snap.lanterns.length]")
    log("[bot] night 1 state/score/flames/lit/total:", n1)
    results = {"night1_bot_seconds": round(played, 1), "night1": n1, "presses": bot.count, "bot_events": bot.events}

    # ---- segment 3: tour. Nights 2 and 3 (the page's own start buttons), the bot keeps walking, camera pulled back
    for night in (2, 3):
        ui = pg.evaluate("game.ui")
        if ui == "play":
            pg.keyboard.press("Escape")
            pg.wait_for_function("game.ui === 'paused'")
            if night == 2:
                c("Menu tạm dừng (Esc)", "game đứng yên (sim không được gọi); ở đây có Tiếp tục, Chơi lại Đêm, Cài đặt, Về menu", "bottom")
                pause_ms(pg, 2800)
            pg.click("#btn-menu-pause")
        elif ui in ("ending", "result"):          # the bot lost the night (not expected): leave through the result screen
            log("[rec] night ended early; using the result screen's Về menu")
            pg.wait_for_function("game.ui === 'result'", timeout=10000)
            pg.click("#btn-menu-result")
        pg.wait_for_function("game.ui === 'menu'")
        pause_ms(pg, 300)
        enter_night_from_menu(pg, night, c)
        pg.evaluate("game.setCam(19, 40)")
        mark(f"night{night} play")
        bot = Bot(pg)
        bot.orbit = True
        pw = ("hai đảo nối bằng cầu, bệ nhảy, Bóng Mực + Kẻ Trộm Đom Đóm" if night == 2
              else "đảo nhiều tầng + tháp chuông, gió, bệ nhảy")
        played = bot.play(c, args.tour_seconds, f"Tham quan Đêm {night} · {pw}")
        log(f"[bot] night {night}: {played:.1f} game s, presses {bot.count}")
        results[f"night{night}_seconds"] = round(played, 1)

    # pause menu -> settings
    if pg.evaluate("game.ui") != "play":
        raise RuntimeError("Night 3 ended during the tour (ui=%s); re-run the recording" % pg.evaluate("game.ui"))
    pg.keyboard.press("Escape")
    pg.wait_for_function("game.ui === 'paused'")
    mark("pause + settings")
    c("Tạm dừng → Cài đặt", "Esc luôn là Tạm dừng / Quay lại. Mở “Cài đặt” từ menu tạm dừng", "bottom")
    pause_ms(pg, 1800)
    pg.click("#btn-settings-pause")
    pg.wait_for_function("!document.getElementById('settings').classList.contains('hidden')")
    pause_ms(pg, 1200)
    c("Cài đặt: Bảng màu dễ phân biệt (người mù màu)", "Bóng Mực viền xanh dương, cảnh báo màu trắng kèm ⚠", "bottom")
    pg.click("#set-cb")
    pause_ms(pg, 1700)
    c("Cài đặt: Giảm chuyển động", "tắt rung camera và chớp màn hình", "bottom")
    pg.click("#set-reduced")
    pause_ms(pg, 1500)
    c("Cài đặt: Chữ lớn ×1,25", "toàn bộ chữ của giao diện phóng to", "bottom")
    pg.click("#set-large")
    pause_ms(pg, 2000)
    pg.click("#set-large")
    pg.click("#set-reduced")
    pg.click("#set-cb")
    pause_ms(pg, 500)
    c("Cài đặt: đổi phím (key remapping)", "bấm vào một phím, rồi nhấn phím mới: Đi lên W → I", "bottom")
    pg.click("#key-up")
    pause_ms(pg, 900)
    pg.keyboard.press("KeyI")
    pause_ms(pg, 1300)
    c("Đổi phím: trùng phím sẽ có cảnh báo", "thử gán I (đang là “Đi lên”) cho “Sang trái”: bị từ chối, phím cũ được giữ", "bottom")
    pg.click("#key-left")
    pg.keyboard.press("KeyI")
    pause_ms(pg, 2300)
    c("Đổi phím: Khôi phục mặc định", "đưa mọi phím về W A S D, Space, Shift, E, F, P", "bottom")
    pg.click("#btn-keys-reset")
    pause_ms(pg, 1700)
    pg.click("#btn-settings-done")
    pause_ms(pg, 500)
    pg.click("#btn-menu-pause")
    pg.wait_for_function("game.ui === 'menu'")

    # leaderboard
    mark("leaderboard")
    c("Bảng xếp hạng", "bảng trống vì video dùng file điểm tạm (điểm thật lưu qua /api/leaderboard); không có dữ liệu bịa", "bottom")
    pg.click("#btn-leaderboard")
    pg.wait_for_function("window.__lbReady === true", timeout=15000)
    pause_ms(pg, 4500)
    pg.click("#btn-lb-back")
    c("")
    pause_ms(pg, 500)

    # ---- segment 4: bench scene
    mark("bench")
    pg.goto(f"{base}/web/index.html?bench=1&seed=42&duration={args.bench_seconds}")
    c("Cảnh benchmark: 200 Bóng Mực + 100 đom đóm (?bench=1&seed=42)",
      "Chỉ để minh hoạ. Số liệu chính thức lấy từ bench.py chạy trên Chrome thật (docs/proof/phase-4/bench.json), không phải từ video này", "bottom")
    pg.wait_for_function("window.__benchDone !== undefined || window.__loadError !== undefined", timeout=180000)
    c("Cảnh benchmark: 200 Bóng Mực + 100 đom đóm (?bench=1&seed=42)",
      "Đã chạy xong: trang gửi dt từng khung hình cho server. Số chính thức: bench.py trên Chrome thật", "bottom")
    pause_ms(pg, 1200)
    results["bench_done"] = pg.evaluate("window.__benchDone")
    results["bench_demo_note"] = "demo run only (screen recording slows rendering); official numbers: bench.py"
    mark("bench end")
    results["errors"] = errors[:10]
    video = pg.video
    ctx.close()
    path = video.path()
    log("[rec] video file:", path, f"{os.path.getsize(path) / 1e6:.1f} MB")
    return path, results


def test_bot(browser, base, seconds):
    ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
    ctx.add_init_script(CAPTION_JS)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: log("[pageerror]", e))
    c = make_cap(pg)
    pg.goto(f"{base}/web/?seed=11")
    wait_ready(pg)
    pg.click("#btn-start")
    pg.wait_for_function("game.ui === 'intro'")
    pg.keyboard.press("Enter")
    pg.wait_for_function("game.ui === 'play'")
    bot = Bot(pg)
    played = bot.play(c, seconds, "Bot tự chơi Đêm 1 (đọc snap, giữ phím)")
    log(f"[bot] {played:.1f} game s; presses {bot.count}")
    for e in bot.events:
        log("[bot]   t+%6.1f  %s" % e)
    log("[bot] state", pg.evaluate("[snap.state, snap.score, snap.player.flames, snap.lanterns.filter((l) => l.lit).length]"))
    ctx.close()


# ================================================================================================ ffmpeg
def ff(ffmpeg, *args):
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *args]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + " ".join(cmd) + "\n" + r.stderr.decode("utf-8", "replace"))


ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", str(CRF), "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
       "-r", str(FPS), "-an"]


def still_to_mp4(ffmpeg, png, out, seconds):
    fade = 0.4
    vf = (f"scale={W}:{H}:flags=lanczos,fade=t=in:st=0:d={fade},fade=t=out:st={seconds - fade}:d={fade},format=yuv420p")
    ff(ffmpeg, "-loop", "1", "-framerate", str(FPS), "-t", str(seconds), "-i", png, "-vf", vf, *ENC, out)


def video_to_mp4(ffmpeg, webm, out, trim_start=0.5):
    vf = f"fps={FPS},scale={W}:{H}:flags=lanczos,fade=t=in:st=0:d=0.3,format=yuv420p"
    ff(ffmpeg, "-ss", str(trim_start), "-i", webm, "-vf", vf, *ENC, out)


def probe_duration(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr.decode("utf-8", "replace"))
    if not m:
        raise RuntimeError("cannot read duration of " + path)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ================================================================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "demo", "demo.mp4"))
    ap.add_argument("--work", default=None, help="temp dir for intermediates (default: a new temp dir)")
    ap.add_argument("--test-bot", nargs="?", const=75, type=float, metavar="SECONDS")
    ap.add_argument("--play-seconds", type=float, default=PLAY_SECONDS)
    ap.add_argument("--tour-seconds", type=float, default=TOUR_SECONDS)
    ap.add_argument("--bench-seconds", type=float, default=BENCH_SECONDS)
    ap.add_argument("--evidence-from", default=None, help="reuse evidence.json from a previous run (skips check.py)")
    args = ap.parse_args()

    work = os.path.abspath(args.work or tempfile.mkdtemp(prefix="ddl-demo-"))
    os.makedirs(work, exist_ok=True)
    os.environ["DDL_LEADERBOARD"] = os.path.join(work, "leaderboard.json")      # never touch the player's real file
    if os.path.exists(os.environ["DDL_LEADERBOARD"]):
        os.remove(os.environ["DDL_LEADERBOARD"])
    import serve
    from playwright.sync_api import sync_playwright

    httpd = serve.make_server(0, bench_sink=lambda d: None, quiet=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    log("[server]", base, "leaderboard:", os.environ["DDL_LEADERBOARD"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=CHROME_ARGS)
        if args.test_bot is not None:
            test_bot(browser, base, args.test_bot)
            browser.close()
            return 0

        # renderer string (real GPU?) for the title card
        probe_ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        probe = probe_ctx.new_page()
        renderer = probe.evaluate("""() => { const gl = document.createElement('canvas').getContext('webgl');
            const e = gl && gl.getExtension('WEBGL_debug_renderer_info'); return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'unknown'; }""")
        meta = f"Playwright · Chromium {browser.version} · {renderer} · {W}×{H} · {FPS} fps"
        log("[gpu]", meta)

        if args.evidence_from:
            with open(args.evidence_from, encoding="utf-8") as f:
                ev = json.load(f)
        else:
            ev = gather_evidence(work)
            with open(os.path.join(work, "evidence.json"), "w", encoding="utf-8") as f:
                json.dump(ev, f, ensure_ascii=False, indent=1)
        cards = build_cards(ev, meta)
        for name, doc in cards.items():
            probe.set_content(doc)
            probe.wait_for_timeout(250)
            probe.screenshot(path=os.path.join(work, f"card_{name}.png"))
        probe_ctx.close()

        webm, results = record_game(browser, base, work, args)
        browser.close()

    ffmpeg = find_ffmpeg()
    log("[ffmpeg]", ffmpeg)
    seg = []
    still_to_mp4(ffmpeg, os.path.join(work, "card_title.png"), os.path.join(work, "s1_title.mp4"), 6)
    seg.append("s1_title.mp4")
    video_to_mp4(ffmpeg, webm, os.path.join(work, "s2_game.mp4"))
    seg.append("s2_game.mp4")
    for i, name in enumerate(("check", "proof", "headless", "git", "harness"), start=3):
        out = f"s{i}_{name}.mp4"
        still_to_mp4(ffmpeg, os.path.join(work, f"card_{name}.png"), os.path.join(work, out), CARD_SECONDS + (1 if name == "check" else 0))
        seg.append(out)
    lst = os.path.join(work, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in seg:
            f.write("file '" + os.path.join(work, s).replace("\\", "/") + "'\n")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    ff(ffmpeg, "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", args.out)

    dur = probe_duration(ffmpeg, args.out)
    size = os.path.getsize(args.out)
    log(f"[done] {args.out}")
    log(f"[done] duration {dur:.1f} s ({int(dur // 60)}:{int(dur % 60):02d}), size {size / 1e6:.2f} MB")
    for s in seg:
        log(f"[done]   {s}: {probe_duration(ffmpeg, os.path.join(work, s)):.1f} s")
    log("[done] results:", json.dumps(results, ensure_ascii=False))
    ok = dur < 300 and size < 50 * 1024 * 1024
    log("[done] limits (< 300 s, < 50 MB):", "OK" if ok else "EXCEEDED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
