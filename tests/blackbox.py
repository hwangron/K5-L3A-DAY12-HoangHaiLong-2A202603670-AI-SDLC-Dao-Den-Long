"""Black-box helpers for the unit tests (not a test module itself).

Everything goes through the headless CLI (Test Contract v1.1): we write the
scenario/inputs to temp files, call `headless.main(argv)` in-process (same code
path as `python headless.py ...`, no interpreter start-up per test) and read the
JSONL back. No test imports game internals except `game.sim.TUNING`, which the
contract requires to equal `game.contract.json`.
"""
import contextlib
import io
import itertools
import json
import math
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix="ddl_tests_")
_ids = itertools.count()

# Standard numbers from Ticket-02 part 1 (hard-coded on purpose: tests check the
# program against the ticket, not against itself).
SPEED = 6.0            # m/s -> 0.1 m per tick
TICK_M = 0.1
CARRY = 10
LANTERN_COST = 10
INTERACT_R = 2.0
PULSE_COST = 3
STUN_TICKS = 120
PULSE_CD_TICKS = 180
INVULN_TICKS = 90
DASH_TICKS = 12
DASH_CD_TICKS = 90
DASH_STEP = 14.0 / 60   # m per tick while dashing
SHADE_STEP = 4.0 / 60
PER_MOTE, PER_LANTERN, PER_STUN, PER_SEC, PER_FLAME = 10, 100, 5, 2, 50


def base(night=1, **kw):
    """Empty level: nothing random, no motes/shades/drifters/charms, no wind."""
    d = {"random_motes": False, "random_shades": False, "motes": [], "shades": []}
    if night != 1:
        d.update({"random_drifters": False, "drifters": [], "charms": [], "wind_enabled": False})
    d.update(kw)
    return d


def _write(obj, kind):
    p = os.path.join(_TMP, f"{next(_ids)}.{kind}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return p


def main_rc(argv):
    """Run `headless.py argv` in-process. Returns (exit_code, stderr_text)."""
    import headless  # imported lazily so a broken headless.py fails tests, not collection
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = headless.main(argv)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return (rc or 0), err.getvalue()


def run(scenario=None, frames=None, ticks=600, every=1, seed=1, night=1):
    """Headless run -> list of JSONL objects. `frames` = list of frames or {"frames": [...]}."""
    out = os.path.join(_TMP, f"{next(_ids)}.out.jsonl")
    argv = ["--seed", str(seed), "--night", str(night), "--ticks", str(ticks),
            "--out", out, "--snapshot-every", str(every)]
    if scenario is not None:
        argv += ["--scenario", _write(scenario, "scenario")]
    if frames is not None:
        if isinstance(frames, list):
            frames = {"frames": frames}
        argv += ["--inputs", _write(frames, "inputs")]
    rc, err = main_rc(argv)
    if rc != 0:
        raise AssertionError(f"headless exited {rc}: {err.strip()}")
    with open(out, encoding="utf-8") as f:
        return [json.loads(x) for x in f.read().splitlines()]


def cli(*args):
    """Real subprocess (for exit codes and timing)."""
    return subprocess.run([sys.executable, os.path.join(ROOT, "headless.py"), *args],
                          capture_output=True, text=True)


def events(lines, name=None):
    return [l for l in lines if l["type"] == "event" and (name is None or l["name"] == name)]


def ev_ticks(lines, name):
    return [e["tick"] for e in events(lines, name)]


def game_events(lines):
    """All events except the always-present night_start at tick 0."""
    return [e for e in events(lines) if e["name"] != "night_start"]


def snap(lines, tick):
    for l in lines:
        if l["type"] == "snapshot" and l["tick"] == tick:
            return l
    raise AssertionError(f"no snapshot at tick {tick}")


def last_snap(lines):
    return [l for l in lines if l["type"] == "snapshot"][-1]


def shade(s, sid):
    return next(x for x in s["shades"] if x["id"] == sid)


def drifter(s, did):
    found = [x for x in s["drifters"] if x["id"] == did]
    return found[0] if found else None


def dropped(s):
    return [m for m in s["motes"] if m["kind"] == "dropped"]


def dxz(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def press(tick, btn, **extra):
    """Rising edge at input tick `tick` (event appears at tick+1), released next tick."""
    f = {"tick": tick, btn: True}
    f.update(extra)
    return [f, {"tick": tick + 1, btn: False}]
