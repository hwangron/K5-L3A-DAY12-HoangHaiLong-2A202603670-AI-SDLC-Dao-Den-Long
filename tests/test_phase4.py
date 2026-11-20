"""Black-box tests for Ticket-04 ("Binh minh v1.0.0", contract v1.3): bench scene, bench statistics, soak CLI,
local leaderboard (HTTP API + export CLI), contract file.

Written from docs/lab/ticket-04.txt only; every expected number is computed by hand in the comments.
Where the ticket is silent and docs/notes/phase-4-design.md decides, the test says "DESIGN:" (and
tests/CHANGES-phase-4.md lists them).

Interfaces used (ticket + design doc): game.benchstats.compute, Game(seed, None, night=1, bench=True), web_bench_new,
`soak.py --seed --nights --out`, `serve.py [port] [--no-browser]` + GET/POST /api/leaderboard,
`serve.py --export-leaderboard out.json`, env DDL_LEADERBOARD. Every subprocess gets its own DDL_LEADERBOARD so the
real ~/.dao-den-long file is never touched.
"""
import datetime
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
import urllib.error
import urllib.request

from blackbox import ROOT

PY = sys.executable


# --------------------------------------------------------------------------- contract v1.3
class ContractV13(unittest.TestCase):
    # Tuning of contract v1.2 (Ticket-02 + Ticket-03 numbers). Ticket-04 section 6: "Moi yeu cau cua v1.0-v1.2 van giu".
    V12_TUNING = {
        "player_speed": 6.0, "carry_capacity": 10, "lantern_cost": 10, "lantern_count_night1": 5,
        "pickup_radius": 1.0, "interact_radius": 2.0, "pulse_cost": 3, "pulse_radius": 5.0,
        "night1_duration_s": 240, "night2_duration_s": 270, "night3_duration_s": 300, "flames": 3,
        "invuln_s": 1.5, "hit_drop_ratio": 0.5, "pulse_stun_s": 2.0, "pulse_push_m": 4.0,
        "pulse_cooldown_s": 3.0, "safe_radius": 6.0, "shade_speed": 4.0, "shade_hit_radius": 1.0,
        "fall_enabled": True, "dash_speed": 14.0, "dash_duration_s": 0.2, "dash_cooldown_s": 1.5,
        "fuel_max": 100, "fuel_decay_per_s": 1.0, "fuel_per_mote": 10, "relight_cost": 5, "win_ratio": 0.6,
        "drain_per_s": 5, "low_fuel_threshold": 30, "capacity_max": 20,
        "score": {"per_mote": 5, "per_lantern": 100, "per_stun": 5, "per_second_left": 0, "per_flame_left": 50,
                  "per_relight": 40, "per_drain_stun": 15, "per_lit_lantern_dawn": 50},
    }

    def load(self):
        with open(os.path.join(ROOT, "game.contract.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_version_is_1_3(self):
        self.assertEqual(self.load()["contract_version"], "1.3")

    def test_bench_and_soak_cmd_present(self):
        c = self.load()
        for k in ("bench_cmd", "soak_cmd"):
            self.assertIsInstance(c.get(k), str, k)
            self.assertTrue(c[k].strip(), k)
        # DESIGN: the commands run the two root scripts (design doc: "python3 bench.py" / "python3 soak.py").
        self.assertTrue(c["bench_cmd"].split()[-1].endswith("bench.py"), c["bench_cmd"])
        self.assertTrue(c["soak_cmd"].split()[-1].endswith("soak.py"), c["soak_cmd"])

    def test_old_fields_still_there(self):
        c = self.load()
        for k in ("team", "build_cmd", "run_cmd", "headless_cmd"):
            self.assertTrue(isinstance(c.get(k), str) and c[k], k)

    def test_v12_tuning_unchanged(self):
        from game.sim import TUNING
        c = self.load()
        for k, v in self.V12_TUNING.items():
            self.assertIn(k, c["tuning"], k)
            self.assertEqual(c["tuning"][k], v, k)
        self.assertEqual(c["tuning"], TUNING)   # the file must still equal the game's TUNING


# --------------------------------------------------------------------------- benchstats.compute
class BenchStats(unittest.TestCase):
    """Ticket part 1: avg_fps = 1000 N / sum(dt); k = max(1, ceil(0.01 N)), p1_low_fps = 1000 / mean(k largest dt);
    frame_ms_p95 = 95th percentile of dt. DESIGN: nearest rank sorted(dt)[ceil(0.95 N) - 1], results rounded to 1
    decimal (the ticket's example JSON shows 1 decimal), N = 0 raises."""

    def check(self, dts, frames, avg, low, p95):
        from game.benchstats import compute
        r = compute(list(dts))
        self.assertEqual(r["frames"], frames)
        for key, want in (("avg_fps", avg), ("p1_low_fps", low), ("frame_ms_p95", p95)):
            self.assertIn(key, r)
            self.assertAlmostEqual(r[key], want, delta=1e-9, msg=f"{key}: got {r[key]} want {want}")
            self.assertEqual(round(r[key], 1), r[key], f"{key} must be rounded to 1 decimal")
        return r

    def test_single_frame(self):
        # N=1, dt=16: avg = 1000*1/16 = 62.5; k = max(1, ceil(0.01)) = 1 -> 1000/16 = 62.5; p95 rank ceil(0.95)=1 -> 16
        self.check([16.0], 1, 62.5, 62.5, 16.0)

    def test_two_frames(self):
        # [20,10]: sum 30 -> 2000/30 = 66.667 -> 66.7; k = max(1, ceil(0.02)) = 1 -> 1000/20 = 50.0;
        # p95 rank ceil(1.9) = 2 -> sorted[1] = 20
        self.check([20.0, 10.0], 2, 66.7, 50.0, 20.0)

    def test_three_frames_unsorted(self):
        # [30,10,20]: sum 60 -> 3000/60 = 50.0; k = 1 -> 1000/30 = 33.333 -> 33.3; rank ceil(2.85) = 3 -> sorted[2] = 30
        self.check([30.0, 10.0, 20.0], 3, 50.0, 33.3, 30.0)

    def test_fractional_dts(self):
        # [16.7, 16.7, 16.6]: sum 50.0 -> 3000/50 = 60.0; k = 1 -> 1000/16.7 = 59.880 -> 59.9; rank 3 -> 16.7
        self.check([16.7, 16.7, 16.6], 3, 60.0, 59.9, 16.7)

    def test_ticket_example_shape_100x10ms_plus_one_50ms(self):
        # 100 frames of 10 ms + 1 of 50 ms: N=101, sum = 1000 + 50 = 1050 -> 1000*101/1050 = 96.190 -> 96.2
        # k = max(1, ceil(1.01)) = 2 -> top two {50, 10}: mean 30 -> 1000/30 = 33.333 -> 33.3
        # p95: rank ceil(0.95*101) = ceil(95.95) = 96 -> sorted[95] = 10 (indices 0..99 are 10 ms) -> 10.0
        self.check([10.0] * 100 + [50.0], 101, 96.2, 33.3, 10.0)

    def test_p95_is_nearest_rank_not_interpolated(self):
        # dt = 1..100 ms (shuffled): sum 5050 -> 100000/5050 = 19.802 -> 19.8; k = max(1, ceil(1.00)) = 1 -> 100 ->
        # 1000/100 = 10.0; rank ceil(95.0) = 95 -> sorted[94] = 95 (an interpolating percentile would give 95.05)
        dts = [(i * 37) % 100 + 1 for i in range(100)]   # 37 is coprime to 100: a permutation of 1..100
        self.assertEqual(sorted(dts), list(range(1, 101)))
        self.check([float(x) for x in dts], 100, 19.8, 10.0, 95.0)

    def test_p95_rank_n40(self):
        # dt = 40..1 ms: sum 820 -> 40000/820 = 48.780 -> 48.8; k = ceil(0.4) -> 1 -> 1000/40 = 25.0;
        # rank ceil(0.95*40) = 38 -> sorted[37] = 38
        self.check([float(x) for x in range(40, 0, -1)], 40, 48.8, 25.0, 38.0)

    def test_p95_rank_n20(self):
        # dt = 1..20 ms in a scrambled order: sum 210 -> 20000/210 = 95.238 -> 95.2; k = 1 -> 1000/20 = 50.0;
        # rank ceil(19.0) = 19 -> sorted[18] = 19
        dts = [(i * 7) % 20 + 1 for i in range(20)]
        self.assertEqual(sorted(dts), list(range(1, 21)))
        self.check([float(x) for x in dts], 20, 95.2, 50.0, 19.0)

    def test_k_is_1_at_n100(self):
        # 99 x 1 ms + one 100 ms: sum 199 -> 100000/199 = 502.51 -> 502.5; k = ceil(1.00) = 1 -> 1000/100 = 10.0
        # (k=2 would give 1000/50.5 = 19.8); rank 95 -> sorted[94] = 1.0
        self.check([1.0] * 99 + [100.0], 100, 502.5, 10.0, 1.0)

    def test_k_is_2_at_n101(self):
        # 99 x 1 + {100, 50}: sum 99 + 150 = 249 -> 101000/249 = 405.62 -> 405.6; k = ceil(1.01) = 2 -> mean 75 ->
        # 1000/75 = 13.333 -> 13.3 (k=1 -> 10.0, k=3 -> 1000/50.33 = 19.9); rank 96 -> sorted[95] = 1.0
        self.check([1.0] * 99 + [100.0, 50.0], 101, 405.6, 13.3, 1.0)

    def test_k_is_2_at_n200(self):
        # 197 x 1 + {100, 50, 20}: sum 197 + 170 = 367 -> 200000/367 = 544.96 -> 545.0; k = ceil(2.00) = 2 -> mean 75
        # -> 13.3 (k=3 would give 1000/56.67 = 17.6); rank 190 -> sorted[189] = 1.0
        self.check([1.0] * 197 + [100.0, 50.0, 20.0], 200, 545.0, 13.3, 1.0)

    def test_k_is_3_at_n201(self):
        # 198 x 1 + {100, 50, 20}: sum 198 + 170 = 368 -> 201000/368 = 546.20 -> 546.2; k = ceil(2.01) = 3 ->
        # mean 170/3 = 56.667 -> 1000/56.667 = 17.647 -> 17.6; rank ceil(190.95) = 191 -> sorted[190] = 1.0
        self.check([1.0] * 198 + [100.0, 50.0, 20.0], 201, 546.2, 17.6, 1.0)

    def test_k_is_10_at_n1000(self):
        # 990 x 2 + {10, 20, ..., 100}: sum 1980 + 550 = 2530 -> 1e6/2530 = 395.26 -> 395.3; k = ceil(10.0) = 10 ->
        # mean 55 -> 1000/55 = 18.182 -> 18.2 (k=9 -> 16.7, k=11 -> 19.9); rank 950 -> sorted[949] = 2.0
        self.check([2.0] * 990 + [10.0 * j for j in range(1, 11)], 1000, 395.3, 18.2, 2.0)

    def test_k_is_11_at_n1001(self):
        # 990 x 2 + {10, 20, ..., 110}: spikes sum 660, total 2640 -> 1001000/2640 = 379.17 -> 379.2;
        # k = ceil(10.01) = 11 -> all eleven spikes: mean 60 -> 1000/60 = 16.667 -> 16.7 (k=10 -> mean 65 -> 15.4);
        # rank ceil(950.95) = 951 -> sorted[950] = 2.0
        self.check([2.0] * 990 + [10.0 * j for j in range(1, 12)], 1001, 379.2, 16.7, 2.0)

    def test_empty_raises(self):
        from game.benchstats import compute
        with self.assertRaises(Exception):
            compute([])


# --------------------------------------------------------------------------- bench scene (simulation side)
def _bench_game(seed, steps):
    from game.sim import Game
    g = Game(seed, None, night=1, bench=True)
    first = g.snapshot()
    events = list(g.initial_events())
    for _ in range(steps):
        events += g.step(None)
    return g, first, g.snapshot(), events


def _xz(p):
    return math.hypot(p[0], p[2])


class BenchScene(unittest.TestCase):
    """Ticket part 1: Night 1; exactly 200 Shades in `wander`, exactly 100 motes, L1-L3 lit with fuel 100;
    spawns / damage / pickups / fuel loss / end conditions are off; no input; the Shades keep moving."""

    STEPS = 600   # 10 s of simulated time

    @classmethod
    def setUpClass(cls):
        cls.g, cls.s0, cls.s1, cls.events = _bench_game(42, cls.STEPS)

    def test_start_counts_and_states(self):
        s = self.s0
        self.assertEqual(s["night"], 1)
        self.assertEqual(s["state"], "playing")
        self.assertEqual(len(s["shades"]), 200)
        self.assertEqual(len({x["id"] for x in s["shades"]}), 200, "Shade ids must be unique")
        self.assertEqual({x["state"] for x in s["shades"]}, {"wander"})
        self.assertEqual(len(s["motes"]), 100)
        self.assertEqual(s["motes_active"], 100)
        self.assertEqual(len({m["id"] for m in s["motes"]}), 100, "mote ids must be unique")

    def test_design_shade_ids_s1_to_s200(self):
        # DESIGN: ids S1..S200 (same naming as normal play, Ticket-02 "Id S1, S2, ...").
        self.assertEqual({x["id"] for x in self.s0["shades"]}, {f"S{i}" for i in range(1, 201)})

    def test_lanterns_l1_l3_lit_fuel_100_l4_l5_unlit(self):
        by_id = {x["id"]: x for x in self.s0["lanterns"]}
        self.assertEqual(sorted(by_id), ["L1", "L2", "L3", "L4", "L5"])   # Night 1 has 5 lanterns (tuning)
        for lid in ("L1", "L2", "L3"):
            self.assertTrue(by_id[lid]["lit"], lid)
            self.assertEqual(by_id[lid]["fuel"], 100.0, lid)
        for lid in ("L4", "L5"):
            self.assertFalse(by_id[lid]["lit"], lid)
            self.assertEqual(by_id[lid]["fuel"], 0.0, lid)

    def test_shades_and_motes_are_spread_over_the_island(self):
        # "rai deu tren dao": each of the 4 quadrants holds a fair share. Uniform on a disk: a quadrant gets 1/4 of
        # the points; 200 shades -> mean 50, sd sqrt(200*.25*.75) = 6.1, so >= 25 is a 4-sd bound; 100 motes ->
        # mean 25, sd 4.3, so >= 8 is a 4-sd bound. Mean radius of a uniform disk of R = 38 is 2R/3 = 25.3.
        for items, floor in ((self.s0["shades"], 25), (self.s0["motes"], 8)):
            q = {}
            for it in items:
                q[(it["pos"][0] >= 0, it["pos"][2] >= 0)] = q.get((it["pos"][0] >= 0, it["pos"][2] >= 0), 0) + 1
            self.assertEqual(len(q), 4)
            self.assertTrue(all(v >= floor for v in q.values()), q)
            mean_r = sum(_xz(it["pos"]) for it in items) / len(items)
            self.assertTrue(20 <= mean_r <= 31, mean_r)
        # no two shades share a spot
        self.assertEqual(len({tuple(x["pos"]) for x in self.s0["shades"]}), 200)

    def test_design_everything_inside_radius_38(self):
        # DESIGN: r = 38 * sqrt(u) for both shades and motes (positions are rounded to 3 decimals).
        for it in self.s0["shades"] + self.s0["motes"]:
            self.assertLessEqual(_xz(it["pos"]), 38.001, it)

    def test_after_600_steps_counts_unchanged(self):
        s = self.s1
        self.assertEqual(s["tick"], self.STEPS)
        self.assertEqual(len(s["shades"]), 200)
        self.assertEqual(len(s["motes"]), 100)
        self.assertEqual(s["motes_active"], 100)
        self.assertEqual(len({x["id"] for x in s["shades"]}), 200)

    def test_after_600_steps_motes_not_picked_or_moved(self):
        a = {m["id"]: m["pos"] for m in self.s0["motes"]}
        b = {m["id"]: m["pos"] for m in self.s1["motes"]}
        self.assertEqual(a, b)

    def test_after_600_steps_fuel_flames_and_state(self):
        s = self.s1
        by_id = {x["id"]: x for x in s["lanterns"]}
        for lid in ("L1", "L2", "L3"):
            self.assertTrue(by_id[lid]["lit"], lid)
            self.assertEqual(by_id[lid]["fuel"], 100.0, f"{lid}: no fuel loss in bench")
        for lid in ("L4", "L5"):
            self.assertFalse(by_id[lid]["lit"], lid)
        self.assertEqual(s["player"]["flames"], self.s0["player"]["flames"])
        self.assertEqual(s["player"]["flames"], 3)
        self.assertEqual(s["state"], "playing")
        self.assertEqual(s["score"], 0)
        self.assertEqual(s["player"]["carried"], 0)

    def test_no_spawn_hit_pickup_or_game_over_events(self):
        forbidden = {"shade_spawned", "player_hit", "mote_picked", "game_over", "fuel_drain", "lantern_out"}
        names = [e["name"] for e in self.events if e["name"] != "night_start"]
        self.assertEqual([n for n in names if n in forbidden], [], names)

    def test_shades_keep_moving(self):
        # wander speed is 1.5 m/s = 0.025 m/tick -> up to 15 m in 600 ticks; most Shades must have left their spot
        # by well over half a metre (a few may sit at a safe-zone edge or on the player).
        a = {x["id"]: x["pos"] for x in self.s0["shades"]}
        moved = sum(1 for x in self.s1["shades"] if math.hypot(x["pos"][0] - a[x["id"]][0], x["pos"][2] - a[x["id"]][2]) > 0.5)
        self.assertGreaterEqual(moved, 150, f"only {moved} of 200 shades moved more than 0.5 m")
        self.assertTrue(all(math.isfinite(c) for x in self.s1["shades"] for c in x["pos"]))
        self.assertTrue({x["state"] for x in self.s1["shades"]} <= {"wander", "chase"},
                        {x["state"] for x in self.s1["shades"]})

    def test_same_seed_identical_different_seed_different(self):
        g2, t0, t1, _ = _bench_game(42, self.STEPS)
        pos = lambda s: [(x["id"], x["pos"]) for x in s["shades"]]
        self.assertEqual(pos(t0), pos(self.s0))
        self.assertEqual(pos(t1), pos(self.s1))
        self.assertEqual(json.dumps(t1, sort_keys=True), json.dumps(self.s1, sort_keys=True))
        g3, u0, u1, _ = _bench_game(43, self.STEPS)
        self.assertNotEqual(pos(u0), pos(self.s0))
        self.assertNotEqual(pos(u1), pos(self.s1))
        self.assertNotEqual([m["pos"] for m in u0["motes"]], [m["pos"] for m in self.s0["motes"]])

    def test_bench_never_ends_even_past_the_night(self):
        # Night 1 lasts 240 s = 14400 ticks (tuning night1_duration_s); in a normal night the dawn check fires at the
        # end of tick 14400 (lost / dawn). The bench has no end condition: 14401 steps must still be `playing`.
        # (~20 s of pure simulation: the one slow test of this file.)
        from game.sim import Game
        g = Game(42, None, night=1, bench=True)
        for _ in range(14401):
            g.step(None)
        s = g.snapshot()
        self.assertEqual(s["state"], "playing")
        self.assertEqual(len(s["shades"]), 200)
        self.assertEqual(len(s["motes"]), 100)
        self.assertEqual(s["player"]["flames"], 3)

    def test_design_web_bench_new_glue(self):
        # DESIGN: web_bench_new(seed) returns the same JSON shape as web_new: {events, snap, extra}.
        from game.sim import web_bench_new
        o = json.loads(web_bench_new(42))
        self.assertTrue({"events", "snap", "extra"} <= set(o))
        self.assertEqual(len(o["snap"]["shades"]), 200)
        self.assertEqual(len(o["snap"]["motes"]), 100)
        self.assertEqual(o["snap"]["night"], 1)


class NormalModeUnchanged(unittest.TestCase):
    """Ticket: "dau ra headless khong doi" - bench=False (the default) is the ordinary Night 1."""

    def test_default_equals_bench_false_and_ticket02_start(self):
        from game.sim import Game
        a, b = Game(1, None, night=1), Game(1, None, night=1, bench=False)
        s = a.snapshot()
        # Ticket-02: 20 motes at the start, 0 Shades until tick 300 (then 2), nothing lit
        self.assertEqual(len(s["motes"]), 20)
        self.assertEqual(len(s["shades"]), 0)
        self.assertFalse(any(l["lit"] for l in s["lanterns"]))
        for _ in range(310):
            a.step(None)
            b.step(None)
        sa = a.snapshot()
        self.assertEqual(json.dumps(sa, sort_keys=True), json.dumps(b.snapshot(), sort_keys=True))
        self.assertEqual(len(sa["shades"]), 2)   # "2 con tai tick 300"


# --------------------------------------------------------------------------- soak CLI
class SoakCLI(unittest.TestCase):
    """Ticket part 2: `soak.py --seed 7 --nights N --out soak.json` -> nights, crashes, results, mem_start_mb,
    mem_end_mb, duration_s; pass = crashes 0 and mem_end <= 1.2 x mem_start."""

    @staticmethod
    def run_soak(seed, nights, out):
        t = time.time()
        r = subprocess.run([PY, os.path.join(ROOT, "soak.py"), "--seed", str(seed), "--nights", str(nights),
                            "--out", out], capture_output=True, text=True, cwd=ROOT, timeout=300)
        elapsed = time.time() - t
        data = None
        if os.path.exists(out):
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
        return r, data, elapsed

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ddl_soak_")
        cls.r3a, cls.d3a, cls.t3 = cls.run_soak(7, 3, os.path.join(cls.tmp, "a.json"))
        cls.r3b, cls.d3b, _ = cls.run_soak(7, 3, os.path.join(cls.tmp, "b.json"))
        cls.r10 = cls.d10 = None
        if cls.t3 / 3 * 10 < 60:          # only run the full 10 nights when it is cheap enough for check.py
            cls.r10, cls.d10, _ = cls.run_soak(7, 10, os.path.join(cls.tmp, "c.json"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check_schema(self, r, d, nights):
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIsNotNone(d, "soak.py wrote no output file")
        for k in ("nights", "crashes", "results", "mem_start_mb", "mem_end_mb", "duration_s"):
            self.assertIn(k, d, k)
        self.assertEqual(d["nights"], nights)
        self.assertEqual(d["crashes"], 0)                 # pass criterion
        self.assertIsInstance(d["results"], list)
        self.assertEqual(len(d["results"]), nights)
        for res in d["results"]:
            self.assertIn(res, ("won", "lost"))
        for k in ("mem_start_mb", "mem_end_mb", "duration_s"):
            self.assertTrue(isinstance(d[k], (int, float)) and not isinstance(d[k], bool), k)
        self.assertGreater(d["mem_start_mb"], 0)
        self.assertGreater(d["mem_end_mb"], 0)
        self.assertGreaterEqual(d["duration_s"], 0)
        self.assertLessEqual(d["mem_end_mb"], 1.2 * d["mem_start_mb"])   # pass criterion

    def test_three_nights_schema_and_thresholds(self):
        self.check_schema(self.r3a, self.d3a, 3)

    def test_ten_nights_schema_and_thresholds(self):
        if self.d10 is None and self.r10 is None:
            self.skipTest("10-night run skipped: 3 nights took too long for check.py")
        self.check_schema(self.r10, self.d10, 10)

    def test_same_seed_same_results(self):
        self.check_schema(self.r3b, self.d3b, 3)
        self.assertEqual(self.d3a["results"], self.d3b["results"])
        self.assertEqual(self.d3a["nights"], self.d3b["nights"])

    def test_design_per_night_seeds_and_nights(self):
        # DESIGN: night i (1-based) is night ((i-1) mod 3)+1 with seed 7+i; per_night has one row per night.
        rows = self.d3a.get("per_night")
        self.assertIsInstance(rows, list)
        self.assertEqual([(r["night"], r["seed"]) for r in rows], [(1, 8), (2, 9), (3, 10)])
        self.assertEqual([r["result"] for r in rows], self.d3a["results"])
        if self.d10:
            self.assertEqual([r["night"] for r in self.d10["per_night"]], [1, 2, 3, 1, 2, 3, 1, 2, 3, 1])
            self.assertEqual([r["seed"] for r in self.d10["per_night"]], list(range(8, 18)))
            # night i only depends on seed 7+i: the first 3 results of the long run equal the 3-night run
            self.assertEqual(self.d10["results"][:3], self.d3a["results"])


# --------------------------------------------------------------------------- leaderboard (HTTP API + export CLI)
ISO_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never go through a proxy for 127.0.0.1


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LBServer:
    """`python serve.py <port> --no-browser` with DDL_LEADERBOARD=<path>."""

    def __init__(self, lb_path):
        self.port = _free_port()
        env = dict(os.environ, DDL_LEADERBOARD=lb_path, PYTHONUTF8="1")
        self.proc = subprocess.Popen([PY, os.path.join(ROOT, "serve.py"), str(self.port), "--no-browser"],
                                     cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 20
        while True:
            if self.proc.poll() is not None:
                raise AssertionError(f"serve.py exited early with code {self.proc.returncode}")
            try:
                self.get()
                return
            except (urllib.error.URLError, OSError):
                if time.time() > deadline:
                    self.stop()
                    raise AssertionError("serve.py did not start listening within 20 s")
                time.sleep(0.1)

    def request(self, method, path, obj=None):
        data = None if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with _OPENER.open(req, timeout=10) as resp:
                status, body = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
            e.close()
        try:
            return status, json.loads(body.decode("utf-8"))
        except ValueError:
            return status, None

    def get(self):
        status, body = self.request("GET", "/api/leaderboard")
        if status != 200 or not isinstance(body, dict) or "entries" not in body:
            raise AssertionError(f"GET /api/leaderboard -> {status} {body!r}")
        return body["entries"]

    def post(self, name, score=100, nights_won=1, seed=1, **extra):
        payload = {"name": name, "score": score, "nights_won": nights_won, "seed": seed}
        payload.update(extra)
        return self.request("POST", "/api/leaderboard", payload)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)


class LeaderboardBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ddl_lb_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def lb_path(self, name="leaderboard.json"):
        return os.path.join(self.tmp, name)

    def server(self, path=None):
        s = LBServer(path or self.lb_path())
        self.addCleanup(s.stop)
        return s

    def export(self, lb_path, out_name="out.json"):
        out = os.path.join(self.tmp, out_name)
        env = dict(os.environ, DDL_LEADERBOARD=lb_path, PYTHONUTF8="1")
        r = subprocess.run([PY, os.path.join(ROOT, "serve.py"), "--export-leaderboard", out], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        with open(out, encoding="utf-8") as f:
            return json.load(f)


class LeaderboardNames(LeaderboardBase):
    """Ticket part 3: name = 3-12 characters [A-Za-z0-9_]; Vietnamese letters with diacritics are a bonus."""

    def accept(self, s, names):
        score = 10
        for n in names:
            score += 10     # a rising score puts each new entry first, so the 10-entry cut never hides it
            status, body = s.post(n, score=score)
            self.assertEqual(status, 200, f"{n!r} should be accepted, got {status} {body}")
            self.assertEqual(body["entries"][0]["name"], unicodedata.normalize("NFC", n), n)

    def test_ascii_names_accepted(self):
        # 3 chars, 12 chars (upper bound), underscore only, digits only, mixed
        self.accept(self.server(), ["abc", "abcdefghijkl", "___", "123", "A_b_9", "Long_Hai_26"])

    def test_vietnamese_names_accepted(self):
        # "May" = M, a-circumflex, y = 3 chars; "Viet_Nam" = 8 chars; "DaoDenLong12" with D-stroke, a-grave,
        # e-grave, o-circumflex-acute... counted in characters (12), not bytes
        self.accept(self.server(), ["Mây", "Việt_Nam", "ĐàoĐènLồng12"])

    def test_design_decomposed_vietnamese_is_normalised_before_the_length_check(self):
        # DESIGN: NFC first. "ĐàoĐènLồng12" is 12 characters in NFC but 16 code points when decomposed
        # (a-grave +1, e-grave +1, o-circumflex-acute +2).
        nfd = unicodedata.normalize("NFD", "ĐàoĐènLồng12")
        self.assertEqual(len(nfd), 16)
        s = self.server()
        status, body = s.post(nfd)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["entries"][0]["name"], "ĐàoĐènLồng12")

    def test_invalid_names_rejected_with_400_and_nothing_stored(self):
        bad = ["", "a", "ab",                      # too short (0, 1, 2)
               "abcdefghijklm",                    # 13 characters
               "x" * 1000,
               "ĐàoĐènLồng123",                    # 13 Vietnamese characters
               "a b c", "abc def", " abc", "abc ", "abc\n", "abc\t", "ab c",   # whitespace
               "abc!", "abc-def", "abc.def", "abc@x", "a/b/c", "abc;", "<b>x</b>",   # punctuation
               "ab😀", "tên đẹp", "Đào Đèn"]
        s = self.server()
        for n in bad:
            status, body = s.post(n)
            self.assertEqual(status, 400, f"{n!r} must be rejected, got {status} {body}")
        status, _ = s.request("POST", "/api/leaderboard", {"score": 5, "nights_won": 1, "seed": 1})   # no name at all
        self.assertEqual(status, 400)
        self.assertEqual(s.get(), [], "a rejected entry must not be stored")

    def test_design_rejection_carries_a_message(self):
        # DESIGN: 400 with {"error": "<message>"}
        status, body = self.server().post("ab")
        self.assertEqual(status, 400)
        self.assertTrue(isinstance(body, dict) and isinstance(body.get("error"), str) and body["error"], body)

    def test_nights_won_range_0_to_3(self):
        s = self.server()
        for w in (0, 1, 2, 3):
            status, body = s.post("Player", score=10 + w, nights_won=w)
            self.assertEqual(status, 200, f"nights_won={w}: {body}")
        for w in (4, -1):
            status, _ = s.post("Player", score=999, nights_won=w)
            self.assertEqual(status, 400, f"nights_won={w} must be rejected")
        self.assertEqual(len(s.get()), 4)


class LeaderboardOrdering(LeaderboardBase):
    def test_entry_fields_and_iso_timestamp_with_timezone(self):
        s = self.server()
        before = datetime.datetime.now(datetime.timezone.utc)
        status, body = s.post("Long_Hai", score=1234, nights_won=2, seed=99)
        after = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(status, 200, body)
        e = body["entries"][0]
        self.assertEqual((e["name"], e["score"], e["nights_won"], e["seed"]), ("Long_Hai", 1234, 2, 99))
        self.assertTrue({"name", "score", "nights_won", "achieved_at", "seed"} <= set(e), sorted(e))
        self.assertRegex(e["achieved_at"], ISO_TZ)                      # ISO 8601 with an explicit offset
        t = datetime.datetime.fromisoformat(e["achieved_at"])
        self.assertIsNotNone(t.tzinfo)
        self.assertIsNotNone(t.utcoffset())
        slack = datetime.timedelta(seconds=5)
        self.assertTrue(before - slack <= t <= after + slack, (before, t, after))   # it is "now", not a made-up value
        self.assertEqual(s.get(), [e])

    def test_design_client_cannot_set_achieved_at(self):
        # DESIGN: achieved_at is set by the server.
        s = self.server()
        status, body = s.post("Cheat_er", score=5, achieved_at="2001-01-01T00:00:00+00:00")
        self.assertEqual(status, 200, body)
        self.assertNotEqual(body["entries"][0]["achieved_at"], "2001-01-01T00:00:00+00:00")
        self.assertTrue(datetime.datetime.fromisoformat(body["entries"][0]["achieved_at"]).year >= 2024)

    def test_sorted_by_score_descending(self):
        s = self.server()
        for name, score in (("Third", 300), ("Fifth", 100), ("First", 500), ("Fourth", 200), ("Second", 400)):
            s.post(name, score=score)
        got = s.get()
        self.assertEqual([e["name"] for e in got], ["First", "Second", "Third", "Fourth", "Fifth"])
        self.assertEqual([e["score"] for e in got], [500, 400, 300, 200, 100])

    def test_tie_goes_to_whoever_got_there_first(self):
        # T1, T2, T3 all score 700 (posted in that order), HI scores 900, LO scores 50
        # -> HI (900), then the 700s by achieved_at ascending = T1, T2, T3, then LO.
        s = self.server()
        for name, score in (("Tie_1", 700), ("Tie_2", 700), ("High", 900), ("Tie_3", 700), ("Low", 50)):
            status, _ = s.post(name, score=score)
            self.assertEqual(status, 200)
            time.sleep(0.05)
        got = s.get()
        self.assertEqual([e["name"] for e in got], ["High", "Tie_1", "Tie_2", "Tie_3", "Low"])
        stamps = [datetime.datetime.fromisoformat(e["achieved_at"]) for e in got if e["score"] == 700]
        self.assertEqual(stamps, sorted(stamps))

    def test_post_response_matches_get(self):
        s = self.server()
        s.post("Aaa", score=10)
        status, body = s.post("Bbb", score=20)
        self.assertEqual(status, 200)
        self.assertEqual(body["entries"], s.get())
        self.assertEqual([e["name"] for e in body["entries"]], ["Bbb", "Aaa"])

    def test_keeps_only_the_top_10(self):
        # 12 scores in scrambled order; sorted descending: 120 110 100 90 80 70 60 50 40 30 | 20 10 (cut)
        scores = [50, 120, 10, 90, 30, 110, 70, 20, 100, 60, 40, 80]
        s = self.server()
        for i, sc in enumerate(scores):
            status, _ = s.post(f"Player{i:02d}", score=sc)
            self.assertEqual(status, 200)
            self.assertLessEqual(len(s.get()), 10)
        got = s.get()
        self.assertEqual(len(got), 10)
        self.assertEqual([e["score"] for e in got], [120, 110, 100, 90, 80, 70, 60, 50, 40, 30])
        self.assertNotIn("Player02", [e["name"] for e in got])   # the 10 point entry
        self.assertNotIn("Player07", [e["name"] for e in got])   # the 20 point entry

    def test_tie_at_the_cut_the_later_entry_drops_out(self):
        # ten entries on 50 (Tie01..Tie10), then a late 50: it ties the 10th place but got there later -> not kept;
        # then a 51 enters on top and pushes the latest 50 (Tie10) out.
        s = self.server()
        for i in range(1, 11):
            s.post(f"Tie{i:02d}", score=50)
            time.sleep(0.02)
        s.post("Late11", score=50)
        self.assertEqual([e["name"] for e in s.get()], [f"Tie{i:02d}" for i in range(1, 11)])
        s.post("Better", score=51)
        got = [e["name"] for e in s.get()]
        self.assertEqual(got, ["Better"] + [f"Tie{i:02d}" for i in range(1, 10)])


class LeaderboardPersistence(LeaderboardBase):
    def test_entries_survive_a_restart_in_order(self):
        path = self.lb_path()
        s1 = LBServer(path)
        try:
            for name, score in (("Mid_One", 200), ("Top_One", 900), ("Low_One", 50), ("Mid_Two", 200)):
                self.assertEqual(s1.post(name, score=score, nights_won=1, seed=7)[0], 200)
                time.sleep(0.03)
            before = s1.get()
        finally:
            s1.stop()
        self.assertTrue(os.path.isfile(path), "the leaderboard must be stored on disk at $DDL_LEADERBOARD")
        self.assertEqual([e["name"] for e in before], ["Top_One", "Mid_One", "Mid_Two", "Low_One"])
        s2 = self.server(path)
        self.assertEqual(s2.get(), before)                  # same entries, same order, same achieved_at
        s2.post("New_One", score=300)
        self.assertEqual([e["name"] for e in s2.get()], ["Top_One", "New_One", "Mid_One", "Mid_Two", "Low_One"])

    def test_a_fresh_file_starts_empty(self):
        self.assertEqual(self.server(self.lb_path("fresh.json")).get(), [])


class LeaderboardExport(LeaderboardBase):
    def test_export_cli_writes_entries_in_order_without_starting_a_server(self):
        path = self.lb_path()
        s = LBServer(path)
        try:
            for name, score in (("Aaa", 30), ("Bbb", 90), ("Ccc", 60), ("Ddd", 90), ("Mây_Đỏ", 45)):
                self.assertEqual(s.post(name, score=score, nights_won=3, seed=5)[0], 200)
                time.sleep(0.03)
            live = s.get()
        finally:
            s.stop()
        data = self.export(path)                            # subprocess with a 30 s timeout: it must exit by itself
        self.assertEqual(set(data), {"entries"})
        self.assertEqual(data["entries"], live)
        # 90 (Bbb first), 90 (Ddd), 60, 45, 30
        self.assertEqual([e["name"] for e in data["entries"]], ["Bbb", "Ddd", "Ccc", "Mây_Đỏ", "Aaa"])

    def test_export_with_no_leaderboard_yet_is_an_empty_list(self):
        self.assertEqual(self.export(self.lb_path("never_written.json")), {"entries": []})


# --------------------------------------------------------------------------- committed proof files (if present)
class CommittedProof(unittest.TestCase):
    """DoD: bench.json and soak.json are committed. Their location is not fixed by the ticket, so look in the repo
    root and docs/proof/phase-4/; skip when absent."""

    @staticmethod
    def find(name):
        for p in (os.path.join(ROOT, name), os.path.join(ROOT, "docs", "proof", "phase-4", name)):
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        return None

    def test_bench_json_schema_and_consistency(self):
        d = self.find("bench.json")
        if d is None:
            self.skipTest("no committed bench.json yet")
        self.assertEqual(d["contract_version"], "1.3")
        for k in ("avg_fps", "p1_low_fps", "frame_ms_p95", "frames", "load_ms", "peak_mem_mb", "vsync_off",
                  "renderer", "os"):
            self.assertIn(k, d, k)
        self.assertIsInstance(d["frames"], int)
        self.assertGreater(d["frames"], 0)
        self.assertIsInstance(d["vsync_off"], bool)
        self.assertTrue(isinstance(d["renderer"], str) and d["renderer"])
        self.assertTrue(isinstance(d["os"], str) and d["os"])
        self.assertTrue(d["peak_mem_mb"] is None or isinstance(d["peak_mem_mb"], (int, float)))
        # avg_fps = 1000 N / sum(dt) -> sum(dt) = N / avg_fps seconds = the measured window, 30 s by the ticket
        self.assertAlmostEqual(d["frames"] / d["avg_fps"], 30.0, delta=1.0)
        # the mean of the largest 1% of dt is >= the mean of all dt
        self.assertLessEqual(d["p1_low_fps"], d["avg_fps"] + 0.05)
        self.assertGreater(d["frame_ms_p95"], 0)

    def test_soak_json_schema_and_thresholds(self):
        d = self.find("soak.json")
        if d is None:
            self.skipTest("no committed soak.json yet")
        for k in ("nights", "crashes", "results", "mem_start_mb", "mem_end_mb", "duration_s"):
            self.assertIn(k, d, k)
        self.assertEqual(d["nights"], 10)
        self.assertEqual(len(d["results"]), 10)
        self.assertEqual(d["crashes"], 0)
        self.assertLessEqual(d["mem_end_mb"], 1.2 * d["mem_start_mb"])


if __name__ == "__main__":
    unittest.main()
