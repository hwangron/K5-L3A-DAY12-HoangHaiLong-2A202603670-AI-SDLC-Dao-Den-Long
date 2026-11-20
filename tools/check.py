"""One-command verification: unit tests + headless scenarios + determinism + output format.

Scenario expectations (tests/scenarios/NAME.expect.json): `events` (exact list), `end` (exact last line) and, new in
Phase 3, `snapshots` (partial checks of the snapshots written every 10 ticks, matched by lantern/shade id).

python3 tools/check.py           # verify only (used by the Claude Stop hook and CI)
python3 tools/check.py --save    # also write proof to docs/proof/<PHASE>/ (PHASE env, default phase-1)
Exit 0 = all green, 2 = something failed (exit 2 also makes the Stop hook block the agent).
"""
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = os.path.join(ROOT, "tests", "scenarios")
PHASE = os.environ.get("PHASE", "phase-1")
# Test Contract v1.2 (Ticket-02 part 4 + Ticket-03 part 7)
SNAP_KEYS = {"type", "tick", "sim_tick", "state", "time_left_s", "score", "player", "lanterns", "shades", "motes_active",
             "night", "wind", "motes", "drifters", "charms"}
# Ticket-03: player.capacity; lantern fuel / ever_lit / relit_count
PLAYER_KEYS = {"pos", "flames", "carried", "vel", "grounded", "invuln", "dash_cd_s", "pulse_cd_s", "charm_s", "capacity"}
ITEM_KEYS = {"lanterns": {"id", "pos", "lit", "deposited", "fuel", "ever_lit", "relit_count"},
             "shades": {"id", "pos", "state"},
             "motes": {"id", "pos", "kind", "ttl_s"}, "drifters": {"id", "pos", "state", "stolen"},
             "charms": {"id", "available", "respawn_s"}}
# Ticket-03: new shade state "drain"
STATES = {"snapshot": {"playing", "paused", "won", "lost"},
          "shades": {"spawning", "wander", "chase", "recoil", "stunned", "drain"},
          "drifters": {"idle", "chase", "flee"}}
# event name -> exact data keys
# Ticket-03: lantern_lit.relight, new events refuel / lantern_out / fuel_drain
EVENT_FIELDS = {"mote_picked": {"carried"}, "deposit": {"lantern_id", "amount", "deposited"},
                "lantern_lit": {"lantern_id", "relight"}, "refuel": {"lantern_id", "amount", "fuel"},
                "lantern_out": {"lantern_id"}, "fuel_drain": {"lantern_id", "shade_id", "fuel"},
                "pulse": {"stunned_ids"}, "player_hit": {"by", "flames", "dropped"}, "shade_spawned": {"id"},
                "game_over": {"result", "reason"}, "dash": set(), "charm_picked": {"charm_id", "charm_ticks"},
                "drifter_steal": {"drifter_id", "amount", "carried"}, "drifter_drop": {"drifter_id", "amount"},
                "night_start": {"night"}, "paused": set(), "resumed": set()}
EVENT_NAMES = set(EVENT_FIELDS)
# Ticket-03: win only at dawn (dawn_survived); lose by dawn or no_flames; all_lit is gone
GAME_OVER = {("won", "dawn_survived"), ("lost", "dawn"), ("lost", "no_flames")}


def run_unit():
    buf = io.StringIO()
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"))
    res = unittest.TextTestRunner(stream=buf, verbosity=1).run(suite)
    return res.wasSuccessful(), res.testsRun, buf.getvalue()


def headless(name, exp, out):
    cmd = [sys.executable, os.path.join(ROOT, "headless.py"), "--seed", str(exp.get("seed", 1)),
           "--night", str(exp.get("night", 1)),
           "--ticks", str(exp["ticks"]), "--out", out, "--snapshot-every", "10"]
    for kind in ("scenario", "inputs"):
        p = os.path.join(SCEN, f"{name}.{kind}.json")
        if os.path.exists(p):
            cmd += [f"--{kind}", p]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stderr, cmd


def _show(c):
    if os.path.isabs(c):
        try:
            return os.path.relpath(c, ROOT).replace("\\", "/")
        except ValueError:  # different drive (temp dir on Windows)
            return "out.jsonl"
    return c


def _unrounded(v, path, out):
    """Contract: floats are rounded to 3 decimals."""
    if isinstance(v, float) and round(v, 3) != v:
        out.append(f"{path}={v} not rounded to 3 decimals")
    elif isinstance(v, dict):
        for k, x in v.items():
            _unrounded(x, f"{path}.{k}", out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _unrounded(x, f"{path}[{i}]", out)


def _one_decimal(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and round(v, 1) == v


def lantern_errors(i, j, it):
    """Ticket-03: fuel is a real with 1 decimal in [0, 100] (0 when unlit); lit implies ever_lit."""
    errs = []
    f = it["fuel"]
    if not _one_decimal(f) or not 0 <= f <= 100:
        errs.append(f"line {i}: lanterns[{j}].fuel={f!r} must be a number in [0, 100] with at most 1 decimal")
    elif not it["lit"] and f != 0:
        errs.append(f"line {i}: lanterns[{j}] is unlit but fuel={f}")
    if not isinstance(it["lit"], bool) or not isinstance(it["ever_lit"], bool):
        errs.append(f"line {i}: lanterns[{j}] lit/ever_lit must be booleans")
    elif it["lit"] and not it["ever_lit"]:
        errs.append(f"line {i}: lanterns[{j}] is lit but ever_lit is false")
    rc = it["relit_count"]
    if not (isinstance(rc, int) and not isinstance(rc, bool) and rc >= 0):
        errs.append(f"line {i}: lanterns[{j}].relit_count={rc!r} must be an integer >= 0")
    return errs


def snapshot_errors(i, l):
    errs = []
    if not SNAP_KEYS <= set(l):
        return [f"line {i}: snapshot missing {sorted(SNAP_KEYS - set(l))}"]
    if l["state"] not in STATES["snapshot"]:
        errs.append(f"line {i}: bad state {l['state']!r}")
    if not (isinstance(l["wind"], dict) and set(l["wind"]) == {"active", "dir_deg"}):
        errs.append(f"line {i}: wind must be {{active, dir_deg}}")
    p = l["player"]
    if not (isinstance(p, dict) and PLAYER_KEYS <= set(p)):
        errs.append(f"line {i}: player missing {sorted(PLAYER_KEYS - set(p or {}))}")
    for arr, keys in ITEM_KEYS.items():
        if not isinstance(l[arr], list):
            errs.append(f"line {i}: {arr} is not a list")
            continue
        for j, it in enumerate(l[arr]):
            if not (isinstance(it, dict) and keys <= set(it)):
                errs.append(f"line {i}: {arr}[{j}] missing {sorted(keys - set(it or {}))}")
            elif arr in STATES and it["state"] not in STATES[arr]:
                errs.append(f"line {i}: {arr}[{j}] bad state {it['state']!r}")
            elif arr == "motes" and it["kind"] not in ("random", "dropped"):
                errs.append(f"line {i}: motes[{j}] bad kind {it['kind']!r}")
            elif arr == "lanterns":
                errs += lantern_errors(i, j, it)
    cap = p.get("capacity") if isinstance(p, dict) else None
    if not (isinstance(cap, int) and not isinstance(cap, bool) and 10 <= cap <= 20 and cap % 2 == 0):
        errs.append(f"line {i}: player.capacity={cap!r} must be an even integer in [10, 20] (10 + 2 x successful lights)")
    if l["motes_active"] != len(l["motes"]):
        errs.append(f"line {i}: motes_active != len(motes)")
    _unrounded(l, f"line {i}", errs)
    return errs


def format_errors(lines):
    errs = []
    if not lines or lines[-1].get("type") != "end":
        errs.append("last line is not 'end'")
    for i, l in enumerate(lines):
        t = l.get("type")
        if t == "snapshot":
            errs += snapshot_errors(i, l)
        elif t == "event":
            name, data = l.get("name"), l.get("data")
            if name not in EVENT_NAMES:
                errs.append(f"line {i}: unknown event {name}")
                continue
            want = set(EVENT_FIELDS[name])
            if name == "player_hit" and isinstance(data, dict) and data.get("by") == "fall":
                want.add("lost")   # v1.1: a fall also reports the motes lost
            if not (isinstance(data, dict) and set(data) == want):
                errs.append(f"line {i}: {name} data keys {sorted(data or {})} != {sorted(want)}")
                continue
            if name == "lantern_lit" and not isinstance(data["relight"], bool):
                errs.append(f"line {i}: lantern_lit.relight must be true/false, got {data['relight']!r}")
            if name in ("refuel", "fuel_drain") and not _one_decimal(data["fuel"]):
                errs.append(f"line {i}: {name}.fuel={data['fuel']!r} must be a number with at most 1 decimal")
            if name == "refuel" and not (isinstance(data["amount"], int) and data["amount"] >= 1):
                errs.append(f"line {i}: refuel.amount must be an integer >= 1 (a lantern that takes nothing is not selected)")
            if name == "game_over" and (data["result"], data["reason"]) not in GAME_OVER:
                errs.append(f"line {i}: game_over {data['result']}/{data['reason']} not allowed in v1.2 "
                            f"(won only as dawn_survived, lost as dawn or no_flames; all_lit is gone)")
        elif t == "end":
            if i != len(lines) - 1:
                errs.append(f"line {i}: 'end' is not last")
            if l.get("state") not in ("playing", "won", "lost"):
                errs.append(f"line {i}: end state {l.get('state')!r}")
        else:
            errs.append(f"line {i}: bad type {t}")
    return errs[:20]


def _by_id(v):
    """Snapshot arrays of items -> {id: item} so an expectation can name lantern "L1" / shade "S1"."""
    if isinstance(v, list) and all(isinstance(x, dict) and "id" in x for x in v):
        return {x["id"]: x for x in v}
    return v


def _subset(exp, got, path, out):
    """Partial match: every key in `exp` must equal the same key in `got` (arrays of items matched by id)."""
    if isinstance(exp, dict):
        got = _by_id(got)
        if not isinstance(got, dict):
            out.append(f"{path}: expected an object, got {got!r}")
            return
        for k, v in exp.items():
            if k not in got:
                out.append(f"{path}.{k}: missing")
            else:
                _subset(v, got[k], f"{path}.{k}", out)
    elif exp != got:
        out.append(f"{path}: expected {exp!r} got {got!r}")


def snapshot_expect_errors(exp_snaps, lines):
    """expect.json `snapshots`: [{"tick": 60, "lanterns": {"L1": {"fuel": 99.0}}, "player": {"capacity": 12}, ...}].
    Ticks must be multiples of the 10-tick snapshot interval used by this script."""
    by_tick = {l["tick"]: l for l in lines if l.get("type") == "snapshot"}
    errs = []
    for e in exp_snaps:
        t = e["tick"]
        if t not in by_tick:
            errs.append(f"snapshot expectation at tick {t}: no snapshot (script snapshots every 10 ticks)")
            continue
        _subset({k: v for k, v in e.items() if k != "tick"}, by_tick[t], f"snapshot@{t}", errs)
    return errs


def main():
    save = "--save" in sys.argv
    out_dir = os.path.join(ROOT, "docs", "proof", PHASE, "runs") if save else tempfile.mkdtemp()
    os.makedirs(out_dir, exist_ok=True)
    ok, n, log = run_unit()
    rows, fails = [], []
    if not ok:
        fails.append("unit tests failed:\n" + log[-3000:])
    for exp_path in sorted(glob.glob(os.path.join(SCEN, "*.expect.json"))):
        name = os.path.basename(exp_path)[: -len(".expect.json")]
        with open(exp_path, encoding="utf-8") as f:
            exp = json.load(f)
        a, b = os.path.join(out_dir, f"{name}.jsonl"), os.path.join(tempfile.mkdtemp(), "b.jsonl")
        rc1, err1, cmd = headless(name, exp, a)
        rc2, _, _ = headless(name, exp, b)
        problems = []
        if rc1 != 0 or rc2 != 0:
            problems.append(f"exit code {rc1}/{rc2}: {err1.strip()}")
        else:
            with open(a, "rb") as f1, open(b, "rb") as f2:
                same = f1.read() == f2.read()
            if not same:
                problems.append("NOT deterministic (two runs differ)")
            with open(a, encoding="utf-8") as f:
                lines = [json.loads(x) for x in f.read().splitlines()]
            problems += format_errors(lines)
            got_ev = [[l["tick"], l["name"], l["data"]] for l in lines if l["type"] == "event"]
            if "events" in exp and got_ev != exp["events"]:
                problems.append(f"events differ:\n  expected {exp['events']}\n  got      {got_ev}")
            if "end" in exp and lines[-1] != exp["end"]:
                problems.append(f"end differs: expected {exp['end']} got {lines[-1]}")
            if "snapshots" in exp:   # Ticket-03: partial snapshot checks (fuel, capacity, shade state, ...)
                problems += snapshot_expect_errors(exp["snapshots"], lines)
        rows.append((name, "PASS" if not problems else "FAIL", exp.get("_why", ""), " ".join(_show(c) for c in cmd[1:])))
        if problems:
            fails.append(f"scenario {name}: " + "; ".join(problems))

    summary = [f"unit tests: {n} run, {'PASS' if ok else 'FAIL'}"] + [f"{r[1]}  {r[0]}" for r in rows]
    print("\n".join(summary))
    if save:
        md = [f"# Headless scenario report ({PHASE})", "", "Generated by `python3 tools/check.py --save`. "
              "Each scenario is run twice and must be byte-identical (determinism).", "",
              f"Unit tests: **{n} run, {'PASS' if ok else 'FAIL'}**", "",
              "| Scenario | Result | What it proves | Command |", "|---|---|---|---|"]
        md += [f"| `{r[0]}` | {r[1]} | {r[2]} | `python3 {r[3]}` |" for r in rows]
        with open(os.path.join(os.path.dirname(out_dir), "scenario_report.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(md) + "\n")
    if fails:
        sys.stderr.write("CHECK FAILED - fix before finishing:\n" + "\n".join(fails) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # a crash must also block, not slip through as exit 1
        sys.stderr.write(f"CHECK CRASHED: {e!r}\n")
        sys.exit(2)
