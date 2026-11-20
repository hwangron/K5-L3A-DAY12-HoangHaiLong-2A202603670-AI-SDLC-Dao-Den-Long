"""Phase-1 unit + contract tests, updated to Ticket-02 standard numbers and Ticket-03 rules (contract v1.2).

Run: python -m unittest discover -s tests
Every test whose expected value changed because Ticket-02 replaced a rule carries a
`# Ticket-02: ...` comment; Ticket-03 changes carry `# Ticket-03: ...`.
Full lists: tests/CHANGES-phase-2.md and tests/CHANGES-phase-3.md.
New Phase-2 rules are tested in tests/test_phase2.py, Phase-3 rules in tests/test_phase3.py.
"""
import json
import math
import os
import tempfile
import unittest

from blackbox import (ROOT, cli, events, game_events, run, snap, PER_FLAME, PER_LANTERN, PER_MOTE,
                      PER_SEC, PER_STUN)

EMPTY = {"random_motes": False, "random_shades": False, "motes": [], "shades": []}


def scen(**kw):
    d = dict(EMPTY)
    d.update(kw)
    return d


class ContractFile(unittest.TestCase):
    def test_contract_matches_game(self):
        from game.sim import TUNING
        with open(os.path.join(ROOT, "game.contract.json"), encoding="utf-8") as f:
            c = json.load(f)
        self.assertEqual(c["contract_version"], "1.2")  # Ticket-03: contract v1.2 (was 1.1 in Ticket-02)
        for k in ("team", "build_cmd", "run_cmd", "headless_cmd"):
            self.assertTrue(isinstance(c[k], str) and c[k])
        self.assertEqual(c["tuning"], TUNING)


class TickModel(unittest.TestCase):
    def test_snapshot0_before_input_and_event_tick(self):
        L = run(scen(motes=[[0, 0, 0.5]]), {"frames": [{"tick": 0, "move": [0, 1]}]}, ticks=5)
        self.assertEqual(L[0]["tick"], 0)
        self.assertEqual(L[0]["player"]["pos"], [0.0, 0.0, 0.0])
        self.assertEqual(L[0]["motes_active"], 1)          # setup does not pick up
        self.assertEqual(events(L, "mote_picked")[0]["tick"], 1)
        # Ticket-02: score is +10 per DEPOSITED mote, picking up scores 0
        self.assertEqual(L[-1], {"type": "end", "ticks": 5, "state": "playing", "score": 0})

    def test_time_left_and_snapshot_every(self):
        L = run(scen(time_left_s=100), ticks=120, every=10)
        snaps = [l for l in L if l["type"] == "snapshot"]
        self.assertEqual([s["tick"] for s in snaps], list(range(0, 121, 10)))
        self.assertEqual(snap(L, 120)["time_left_s"], 98.0)
        self.assertEqual(snaps[0]["sim_tick"], 0)

    def test_dawn(self):
        L = run(scen(time_left_s=1), ticks=1000)
        self.assertEqual(events(L, "game_over")[0], {"type": "event", "tick": 60, "name": "game_over",
                                                     "data": {"result": "lost", "reason": "dawn"}})
        self.assertEqual(L[-1]["ticks"], 60)
        self.assertEqual(L[-1]["state"], "lost")


class Movement(unittest.TestCase):
    def test_speed_and_yaw(self):
        L = run(scen(), {"frames": [{"tick": 0, "move": [0, 1], "cam_yaw_deg": 90}]}, ticks=60)
        self.assertEqual(snap(L, 60)["player"]["pos"], [6.0, 0.0, 0.0])

    def test_diagonal_normalised(self):
        L = run(scen(), {"frames": [{"tick": 0, "move": [1, 1]}]}, ticks=60)
        x, _, z = snap(L, 60)["player"]["pos"]
        self.assertAlmostEqual(math.hypot(x, z), 6.0, places=2)

    def test_island_edge_falls(self):
        # Ticket-02: island radius 40 m and walking off it falls (Phase-1 invisible shore at 30 m removed;
        # replaces test_island_edge_clamp).
        # +X at 0.1 m/tick: tick 399 x=39.9 still on the island. Float sum of 400 x 0.1 is 40.0000000000003,
        # so the player leaves at tick 400 (or 401). Euler fall y_n = -n(n-1)/360 < -10 first at n=61
        # airborne ticks -> player_hit(fall) at 400+60 .. 401+61.
        L = run(scen(), {"frames": [{"tick": 0, "move": [1, 0]}]}, ticks=600)
        self.assertEqual(snap(L, 399)["player"]["pos"], [39.9, 0.0, 0.0])
        hit = events(L, "player_hit")[0]
        self.assertEqual(hit["data"]["by"], "fall")
        self.assertIn(hit["tick"], (460, 461, 462))

    def test_scenario_position_outside_edge_not_moved(self):
        # review finding: standing still at x=40 used to be pulled back to 30 (x=40 is the new edge, r<=40 is land)
        L = run(scen(player={"pos": [40, 0, 0]}, motes=[[40, 0, 0.5]]), ticks=2)
        self.assertEqual(events(L, "mote_picked")[0]["tick"], 1)
        self.assertEqual(snap(L, 2)["player"]["pos"], [40.0, 0.0, 0.0])

    def test_jump_rises_and_lands(self):
        L = run(scen(), {"frames": [{"tick": 0, "jump": True}]}, ticks=60)
        self.assertGreater(snap(L, 20)["player"]["pos"][1], 0.5)
        self.assertEqual(snap(L, 60)["player"]["pos"][1], 0.0)


class Motes(unittest.TestCase):
    def test_pickup_radius_inclusive(self):
        L = run(scen(motes=[[1.0, 0, 0], [1.01, 0, 0]]), ticks=1)
        self.assertEqual(len(events(L, "mote_picked")), 1)

    def test_capacity(self):
        # Ticket-02: carry capacity 10 (was 5): 9 + 3 motes on the spot -> 10 carried, 2 left
        L = run(scen(player={"pos": [0, 0, 0], "carried": 9}, motes=[[0, 0, 0]] * 3), ticks=1)
        self.assertEqual(snap(L, 1)["player"]["carried"], 10)
        self.assertEqual(snap(L, 1)["motes_active"], 2)


class Lanterns(unittest.TestCase):
    def press(self, tick, btn):
        return [{"tick": tick, btn: True}, {"tick": tick + 1, btn: False}]

    def test_deposit_partial_then_lit(self):
        # Ticket-02: lantern cost 10, interact radius 2.0, +10 per deposited mote.
        # Ticket-03: +5 per mote now, lantern_lit has relight:false (first light).
        # run 1: carry 3 -> deposit 3 (3/10, not lit), score 3*5 = 15.
        # run 2: carry 9, already 3 -> deposit min(9, 7) = 7 -> lit, 2 left, score 7*5 + 100 = 135.
        sc = scen(player={"pos": [0, 0, 0], "carried": 3},
                  lanterns=[{"id": "L1", "pos": [0, 0, 2.0]}],
                  motes=[[5, 0, 5]])
        fr = {"frames": self.press(0, "interact")}
        L = run(sc, fr, ticks=3)
        self.assertEqual(events(L, "deposit")[0]["data"], {"lantern_id": "L1", "amount": 3, "deposited": 3})
        self.assertFalse(events(L, "lantern_lit"))
        self.assertEqual(L[-1]["score"], 3 * PER_MOTE)
        self.assertEqual(3 * PER_MOTE, 15)                  # Ticket-03: 3 x 5 (was 30)
        sc["player"]["carried"] = 9
        sc["lanterns"][0]["deposited"] = 3
        L = run(sc, fr, ticks=3)
        self.assertEqual(events(L, "deposit")[0]["data"], {"lantern_id": "L1", "amount": 7, "deposited": 10})
        # Ticket-03: lantern_lit now carries relight (false for a first light)
        self.assertEqual(events(L, "lantern_lit")[0]["data"], {"lantern_id": "L1", "relight": False})
        self.assertEqual(snap(L, 3)["player"]["carried"], 2)
        self.assertEqual(L[-1]["score"], 7 * PER_MOTE + PER_LANTERN)
        self.assertEqual(7 * PER_MOTE + PER_LANTERN, 135)   # Ticket-03: 35 + 100

    def test_out_of_range_no_deposit(self):
        # Ticket-02: interact radius 2.0; night_start is now always emitted at tick 0, so look at game events only
        sc = scen(player={"pos": [0, 0, 0], "carried": 3},
                  lanterns=[{"id": "L1", "pos": [0, 0, 2.01]}])
        self.assertFalse(game_events(run(sc, {"frames": self.press(0, "interact")}, ticks=3)))

    def test_held_button_triggers_once(self):
        sc = scen(player={"pos": [0, 0, 0], "carried": 5}, lanterns=[{"id": "L1", "pos": [0, 0, 0], "deposited": 0}])
        L = run(sc, {"frames": [{"tick": 0, "interact": True}]}, ticks=10)
        self.assertEqual(len(events(L, "deposit")), 1)

    def test_all_lit_does_not_end_the_night(self):
        # Ticket-03: REPLACES test_win_all_lit_with_bonus. "Thang ngay khi tat ca den sang" is gone: lighting the
        # 5th lantern (carried 10 = cost 10 at tick 1) must not end the night; no game_over, state stays playing.
        # Score only 10*5 + 100 = 150 (no time bonus, no dawn bonus before dawn).
        lits = [{"id": f"L{i}", "lit": True} for i in range(2, 6)]
        sc = scen(player={"pos": [0, 0, 0], "carried": 10, "flames": 2},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1]}] + lits, time_left_s=100)
        L = run(sc, {"frames": self.press(0, "interact")}, ticks=100)
        self.assertEqual([e["name"] for e in game_events(L)], ["deposit", "lantern_lit"])
        self.assertEqual(L[-1], {"type": "end", "ticks": 100, "state": "playing", "score": 10 * PER_MOTE + PER_LANTERN})
        self.assertEqual(10 * PER_MOTE + PER_LANTERN, 150)

    def test_win_at_dawn_with_bonus(self):
        # Ticket-03: REPLACES the all-lit win. 5 lit (L1 by deposit at tick 1, L2..L5 preset fuel 100), 1 s of night
        # left = dawn at tick 60, 2 flames left. Lit at tick 1 -> fuel 100 - 59/60 -> units 6000-59 = 5941 -> floor 99;
        # preset lanterns 100 - 60/60 = 99 -> floor 99. Score 10*5 + 100 (light) + 5*(50 + 99) + 2*50 = 995.
        lits = [{"id": f"L{i}", "lit": True} for i in range(2, 6)]
        sc = scen(player={"pos": [0, 0, 0], "carried": 10, "flames": 2},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1]}] + lits, time_left_s=1)
        L = run(sc, {"frames": self.press(0, "interact")}, ticks=100)
        go = events(L, "game_over")[0]
        self.assertEqual((go["tick"], go["data"]), (60, {"result": "won", "reason": "dawn_survived"}))
        expect = 10 * PER_MOTE + PER_LANTERN + 5 * (50 + 99) + 2 * PER_FLAME
        self.assertEqual(expect, 995)
        self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "won", "score": expect})

    def test_prelit_lantern_gives_no_score(self):
        # Ticket-02: only night_start may appear (it is a v1.1 event at tick 0)
        L = run(scen(lanterns=[{"id": "L3", "lit": True}]), ticks=10)
        self.assertFalse(game_events(L))
        self.assertEqual(L[-1]["score"], 0)
        self.assertEqual(L[0]["lanterns"][2]["lit"], True)


class Shades(unittest.TestCase):
    def test_chase_speed(self):
        # Ticket-02: shade speed 4.0 and detection 12 m (a shade at 20 m would only wander now).
        # Shade at 10 m chases: 60 ticks * 4/60 = 4 m -> x = 6.0
        L = run(scen(shades=[{"id": "A", "pos": [10, 1, 0]}]), ticks=60)
        s = snap(L, 60)["shades"][0]
        self.assertEqual((s["id"], s["pos"], s["state"]), ("A", [6.0, 1.0, 0.0], "chase"))

    def test_hit_drop_invuln_and_lose(self):
        # Ticket-02: invulnerable 90 ticks (was 120). Hit at tick 1 (shade 0.5 m away) -> flames 1, drop
        # floor(4/2)=2. Shade recoils 2 m in 60 ticks, comes back by ~tick 84, waits for invuln to end ->
        # second hit exactly at 1+90 = 91 -> flames 0 -> lost.
        sc = scen(player={"pos": [0, 0, 0], "carried": 4, "flames": 2}, shades=[{"pos": [0.5, 1, 0]}])
        L = run(sc, ticks=2000)
        hits = events(L, "player_hit")
        self.assertEqual(hits[0]["tick"], 1)
        self.assertEqual(hits[0]["data"], {"by": "shade", "flames": 1, "dropped": 2})
        self.assertEqual(hits[1]["tick"], 91)
        self.assertEqual(events(L, "game_over")[0]["data"], {"result": "lost", "reason": "no_flames"})
        self.assertEqual(L[-1]["state"], "lost")

    def test_safe_radius_of_lit_lantern(self):
        # Ticket-02: safe radius 6 m (was 4)
        sc = scen(player={"pos": [0, 0, 0]}, lanterns=[{"id": "L1", "pos": [0, 0, 0], "lit": True}],
                  shades=[{"pos": [10, 1, 0]}])
        L = run(sc, ticks=600)
        self.assertFalse(events(L, "player_hit"))
        self.assertAlmostEqual(snap(L, 600)["shades"][0]["pos"][0], 6.0, places=3)

    def test_unlit_lantern_is_not_safe(self):
        sc = scen(player={"pos": [0, 0, 0]}, lanterns=[{"id": "L1", "pos": [0, 0, 0]}], shades=[{"pos": [10, 1, 0]}])
        self.assertTrue(events(run(sc, ticks=600), "player_hit"))


class Pulse(unittest.TestCase):
    def test_pulse_stun_push_cost_score(self):
        # Ticket-02: cost 3, radius 5 (3D from feet+0.8), stun 120, push 4 m over 15 ticks, +5 per shade.
        # S1 (4.99,1,0): sqrt(4.99^2+0.2^2)=4.994 <= 5 -> hit. S2 (-5.5,1,0): 5.504 -> miss.
        # S1 pushed +X to 4.99+4 = 8.99 by tick 15, stunned ticks 1..120, chasing again at 121.
        sc = scen(player={"pos": [0, 0, 0], "carried": 5},
                  shades=[{"id": "S1", "pos": [4.99, 1, 0]}, {"id": "S2", "pos": [-5.5, 1, 0]}])
        L = run(sc, {"frames": [{"tick": 0, "pulse": True}, {"tick": 1, "pulse": False}]}, ticks=400)
        p = events(L, "pulse")
        self.assertEqual((p[0]["tick"], p[0]["data"]), (1, {"stunned_ids": ["S1"]}))
        s1 = snap(L, 15)["shades"][0]
        self.assertEqual((s1["pos"][0], s1["state"]), (8.99, "stunned"))
        self.assertEqual(snap(L, 120)["shades"][0]["state"], "stunned")
        self.assertEqual(snap(L, 121)["shades"][0]["state"], "chase")
        self.assertEqual(snap(L, 1)["player"]["carried"], 5 - 3)
        self.assertEqual(snap(L, 1)["score"], PER_STUN)

    def test_pulse_needs_light_and_cooldown(self):
        # Ticket-02: cooldown 180 ticks and cost 3. carried 6 pays for two pulses (ticks 1 and 181);
        # the press at input tick 2 is inside the cooldown. carried 2 < 3 -> no pulse.
        cd = 180
        fr = {"frames": [{"tick": 0, "pulse": True}, {"tick": 1, "pulse": False},
                         {"tick": 2, "pulse": True}, {"tick": 3, "pulse": False},
                         {"tick": cd, "pulse": True}]}
        L = run(scen(player={"pos": [0, 0, 0], "carried": 6}, shades=[{"id": "S1", "pos": [3, 1, 0]}]),
                fr, ticks=cd + 2)
        self.assertEqual([e["tick"] for e in events(L, "pulse")], [1, cd + 1])
        self.assertEqual(snap(L, cd + 1)["player"]["carried"], 0)
        L = run(scen(player={"pos": [0, 0, 0], "carried": 2}), {"frames": [{"tick": 0, "pulse": True}]}, ticks=5)
        self.assertFalse(events(L, "pulse"))
        self.assertEqual(snap(L, 5)["player"]["carried"], 2)


class Determinism(unittest.TestCase):
    def test_same_seed_same_output_default_level(self):
        fr = {"frames": [{"tick": 0, "move": [0.3, 1]}, {"tick": 300, "pulse": True}]}
        a = run(None, fr, ticks=3000, every=10, seed=42)
        b = run(None, fr, ticks=3000, every=10, seed=42)
        self.assertEqual(a, b)
        c = run(None, ticks=10, seed=43)
        self.assertNotEqual(a[0]["motes"], c[0]["motes"])

    def test_default_level(self):
        # Ticket-02: 20 motes at start (was 40); player snapshot has extra v1.1 fields
        L = run(None, ticks=0)
        self.assertEqual(len(L[0]["lanterns"]), 5)
        p = L[0]["player"]
        self.assertEqual((p["pos"], p["flames"], p["carried"]), ([0.0, 0.0, 0.0], 3, 0))
        self.assertEqual(L[0]["motes_active"], 20)
        L = run(None, ticks=400, every=100)
        self.assertEqual(events(L, "shade_spawned")[0], {"type": "event", "tick": 300, "name": "shade_spawned",
                                                        "data": {"id": "S1"}})


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def write(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_ok_and_jsonl(self):
        out = os.path.join(self.d, "o.jsonl")
        r = cli("--seed", "3", "--night", "1", "--ticks", "100", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f.read().splitlines()]
        self.assertEqual(lines[-1]["type"], "end")
        self.assertTrue(all(l["type"] in ("snapshot", "event", "end") for l in lines))

    def test_malformed_exit_2(self):
        out = os.path.join(self.d, "o.jsonl")
        bad_json = self.write("a.json", "{not json")
        bad_ticks = self.write("b.json", '{"frames":[{"tick":5},{"tick":5}]}')
        bad_scen = self.write("c.json", '{"player":{"pos":[0,0]}}')
        not_obj = self.write("d.json", '[]')  # review finding: used to be accepted
        for flag, path in (("--inputs", bad_json), ("--inputs", bad_ticks), ("--scenario", bad_scen),
                           ("--scenario", not_obj)):
            r = cli("--seed", "1", "--night", "1", "--ticks", "10", "--out", out, flag, path)
            self.assertEqual(r.returncode, 2, (flag, path))
            self.assertTrue(r.stderr)

    def test_other_error_nonzero(self):
        r = cli("--seed", "1", "--night", "1", "--ticks", "10")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
