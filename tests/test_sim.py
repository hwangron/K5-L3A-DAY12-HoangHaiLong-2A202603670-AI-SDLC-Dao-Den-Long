"""Unit + contract tests. Run: python3 -m unittest discover -s tests"""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import headless  # noqa: E402
from game.sim import TUNING, Game, ScenarioError, parse_inputs  # noqa: E402

T = TUNING
S = T["score"]
EMPTY = {"random_motes": False, "random_shades": False, "motes": [], "shades": []}


def scen(**kw):
    d = dict(EMPTY)
    d.update(kw)
    return d


def run(scenario=None, frames=None, ticks=600, every=1, seed=1):
    lines = []
    headless.run(seed, scenario, parse_inputs(frames or {"frames": []}), ticks, every, lines.append)
    return lines


def events(lines, name=None):
    return [l for l in lines if l["type"] == "event" and (name is None or l["name"] == name)]


def snap(lines, tick):
    return next(l for l in lines if l["type"] == "snapshot" and l["tick"] == tick)


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "headless.py"), *args],
                          capture_output=True, text=True)


class ContractFile(unittest.TestCase):
    def test_contract_matches_game(self):
        with open(os.path.join(ROOT, "game.contract.json"), encoding="utf-8") as f:
            c = json.load(f)
        self.assertEqual(c["contract_version"], "1.0")
        for k in ("team", "build_cmd", "run_cmd", "headless_cmd"):
            self.assertTrue(isinstance(c[k], str) and c[k])
        self.assertEqual(c["tuning"], T)


class TickModel(unittest.TestCase):
    def test_snapshot0_before_input_and_event_tick(self):
        L = run(scen(motes=[[0, 0, 0.5]]), {"frames": [{"tick": 0, "move": [0, 1]}]}, ticks=5)
        self.assertEqual(L[0]["tick"], 0)
        self.assertEqual(L[0]["player"]["pos"], [0.0, 0.0, 0.0])
        self.assertEqual(L[0]["motes_active"], 1)          # setup does not pick up
        self.assertEqual(events(L, "mote_picked")[0]["tick"], 1)
        self.assertEqual(L[-1], {"type": "end", "ticks": 5, "state": "playing", "score": S["per_mote"]})

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
        self.assertEqual(snap(L, 60)["player"]["pos"], [T["player_speed"], 0.0, 0.0])

    def test_diagonal_normalised(self):
        L = run(scen(), {"frames": [{"tick": 0, "move": [1, 1]}]}, ticks=60)
        x, _, z = snap(L, 60)["player"]["pos"]
        self.assertAlmostEqual(math.hypot(x, z), T["player_speed"], places=2)

    def test_island_edge_clamp(self):
        L = run(scen(), {"frames": [{"tick": 0, "move": [1, 0]}]}, ticks=600)
        self.assertEqual(snap(L, 600)["player"]["pos"][0], 30.0)

    def test_scenario_position_outside_edge_not_moved(self):
        # review finding: standing still at x=40 used to be pulled back to 30
        L = run(scen(player={"pos": [40, 0, 0]}, motes=[[40, 0, 0.5]]), ticks=2)
        self.assertEqual(events(L, "mote_picked")[0]["tick"], 1)
        self.assertEqual(snap(L, 2)["player"]["pos"], [40.0, 0.0, 0.0])

    def test_jump_rises_and_lands(self):
        L = run(scen(), {"frames": [{"tick": 0, "jump": True}]}, ticks=60)
        self.assertGreater(snap(L, 20)["player"]["pos"][1], 0.5)
        self.assertEqual(snap(L, 60)["player"]["pos"][1], 0.0)


class Motes(unittest.TestCase):
    def test_pickup_radius_inclusive(self):
        r = T["pickup_radius"]
        L = run(scen(motes=[[r, 0, 0], [r + 0.01, 0, 0]]), ticks=1)
        self.assertEqual(len(events(L, "mote_picked")), 1)

    def test_capacity(self):
        cap = T["carry_capacity"]
        L = run(scen(player={"pos": [0, 0, 0], "carried": cap - 1}, motes=[[0, 0, 0]] * 3), ticks=1)
        self.assertEqual(snap(L, 1)["player"]["carried"], cap)
        self.assertEqual(snap(L, 1)["motes_active"], 2)


class Lanterns(unittest.TestCase):
    def press(self, tick, btn):
        return [{"tick": tick, btn: True}, {"tick": tick + 1, btn: False}]

    def test_deposit_partial_then_lit(self):
        sc = scen(player={"pos": [0, 0, 0], "carried": 3},
                  lanterns=[{"id": "L1", "pos": [0, 0, T["interact_radius"]]}],
                  motes=[[5, 0, 5]] )
        fr = {"frames": self.press(0, "interact")}
        L = run(sc, fr, ticks=3)
        self.assertEqual(events(L, "deposit")[0]["data"], {"lantern_id": "L1", "amount": 3, "deposited": 3})
        self.assertFalse(events(L, "lantern_lit"))
        sc["player"]["carried"] = 5
        sc["lanterns"][0]["deposited"] = 3
        L = run(sc, fr, ticks=3)
        self.assertEqual(events(L, "deposit")[0]["data"], {"lantern_id": "L1", "amount": 2, "deposited": 5})
        self.assertEqual(events(L, "lantern_lit")[0]["data"], {"lantern_id": "L1"})
        self.assertEqual(snap(L, 3)["player"]["carried"], 3)
        self.assertEqual(L[-1]["score"], S["per_lantern"])

    def test_out_of_range_no_deposit(self):
        sc = scen(player={"pos": [0, 0, 0], "carried": 3},
                  lanterns=[{"id": "L1", "pos": [0, 0, T["interact_radius"] + 0.01]}])
        self.assertFalse(events(run(sc, {"frames": self.press(0, "interact")}, ticks=3)))

    def test_held_button_triggers_once(self):
        sc = scen(player={"pos": [0, 0, 0], "carried": 5}, lanterns=[{"id": "L1", "pos": [0, 0, 0], "deposited": 0}])
        L = run(sc, {"frames": [{"tick": 0, "interact": True}]}, ticks=10)
        self.assertEqual(len(events(L, "deposit")), 1)

    def test_win_all_lit_with_bonus(self):
        lits = [{"id": f"L{i}", "lit": True} for i in range(2, 6)]
        sc = scen(player={"pos": [0, 0, 0], "carried": 5, "flames": 2},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1]}] + lits, time_left_s=100)
        L = run(sc, {"frames": self.press(0, "interact")}, ticks=100)
        go = events(L, "game_over")[0]
        self.assertEqual((go["tick"], go["data"]), (1, {"result": "won", "reason": "all_lit"}))
        # time_left after 1 step = 99.983 -> 99 whole seconds
        expect = S["per_lantern"] + 99 * S["per_second_left"] + 2 * S["per_flame_left"]
        self.assertEqual(L[-1], {"type": "end", "ticks": 1, "state": "won", "score": expect})

    def test_prelit_lantern_gives_no_score(self):
        L = run(scen(lanterns=[{"id": "L3", "lit": True}]), ticks=10)
        self.assertFalse(events(L))
        self.assertEqual(L[-1]["score"], 0)
        self.assertEqual(L[0]["lanterns"][2]["lit"], True)


class Shades(unittest.TestCase):
    def test_chase_speed(self):
        L = run(scen(shades=[{"id": "A", "pos": [20, 1, 0]}]), ticks=60)
        s = snap(L, 60)["shades"][0]
        self.assertEqual((s["id"], s["pos"], s["state"]), ("A", [20 - T["shade_speed"], 1.0, 0.0], "chase"))

    def test_hit_drop_invuln_and_lose(self):
        sc = scen(player={"pos": [0, 0, 0], "carried": 4, "flames": 2}, shades=[{"pos": [0.5, 1, 0]}])
        L = run(sc, ticks=2000)
        hits = events(L, "player_hit")
        self.assertEqual(hits[0]["tick"], 1)
        self.assertEqual(hits[0]["data"], {"by": "shade", "flames": 1,
                                           "dropped": math.floor(4 * T["hit_drop_ratio"])})
        self.assertEqual(hits[1]["tick"], 1 + round(T["invuln_s"] * 60))
        self.assertEqual(events(L, "game_over")[0]["data"], {"result": "lost", "reason": "no_flames"})
        self.assertEqual(L[-1]["state"], "lost")

    def test_safe_radius_of_lit_lantern(self):
        sc = scen(player={"pos": [0, 0, 0]}, lanterns=[{"id": "L1", "pos": [0, 0, 0], "lit": True}],
                  shades=[{"pos": [10, 1, 0]}])
        L = run(sc, ticks=600)
        self.assertFalse(events(L, "player_hit"))
        self.assertAlmostEqual(snap(L, 600)["shades"][0]["pos"][0], T["safe_radius"], places=3)

    def test_unlit_lantern_is_not_safe(self):
        sc = scen(player={"pos": [0, 0, 0]}, lanterns=[{"id": "L1", "pos": [0, 0, 0]}], shades=[{"pos": [10, 1, 0]}])
        self.assertTrue(events(run(sc, ticks=600), "player_hit"))


class Pulse(unittest.TestCase):
    def test_pulse_stun_push_cost_score(self):
        r = T["pulse_radius"]
        sc = scen(player={"pos": [0, 0, 0], "carried": 2},
                  shades=[{"id": "S1", "pos": [r, 1, 0]}, {"id": "S2", "pos": [-(r + 0.5), 1, 0]}])
        L = run(sc, {"frames": [{"tick": 0, "pulse": True}, {"tick": 1, "pulse": False}]}, ticks=400)
        p = events(L, "pulse")
        self.assertEqual((p[0]["tick"], p[0]["data"]), (1, {"stunned_ids": ["S1"]}))
        s1 = snap(L, 1)["shades"][0]
        self.assertEqual((s1["pos"][0], s1["state"]), (r + T["pulse_push_m"], "stunned"))
        stun = round(T["pulse_stun_s"] * 60)
        self.assertEqual(snap(L, stun)["shades"][0]["state"], "stunned")
        self.assertEqual(snap(L, stun + 1)["shades"][0]["state"], "chase")
        self.assertEqual(snap(L, 1)["player"]["carried"], 2 - T["pulse_cost"])
        self.assertEqual(snap(L, 1)["score"], S["per_stun"])

    def test_pulse_needs_light_and_cooldown(self):
        cd = round(T["pulse_cooldown_s"] * 60)
        fr = {"frames": [{"tick": 0, "pulse": True}, {"tick": 1, "pulse": False},
                         {"tick": 2, "pulse": True}, {"tick": 3, "pulse": False},
                         {"tick": cd, "pulse": True}]}
        L = run(scen(player={"pos": [0, 0, 0], "carried": 5}), fr, ticks=cd + 2)
        self.assertEqual([e["tick"] for e in events(L, "pulse")], [1, cd + 1])
        L = run(scen(player={"pos": [0, 0, 0], "carried": 0}), {"frames": [{"tick": 0, "pulse": True}]}, ticks=5)
        self.assertFalse(events(L, "pulse"))


class Determinism(unittest.TestCase):
    def test_same_seed_same_output_default_level(self):
        a = run(None, {"frames": [{"tick": 0, "move": [0.3, 1]}, {"tick": 300, "pulse": True}]}, ticks=3000, every=10, seed=42)
        b = run(None, {"frames": [{"tick": 0, "move": [0.3, 1]}, {"tick": 300, "pulse": True}]}, ticks=3000, every=10, seed=42)
        self.assertEqual(a, b)
        c = run(None, ticks=10, seed=43)
        self.assertNotEqual(a[0]["motes"], c[0]["motes"])

    def test_default_level(self):
        L = run(None, ticks=0)
        self.assertEqual(len(L[0]["lanterns"]), 5)
        self.assertEqual(L[0]["player"], {"pos": [0.0, 0.0, 0.0], "flames": T["flames"], "carried": 0})
        self.assertEqual(L[0]["motes_active"], 40)
        L = run(None, ticks=400)
        self.assertEqual(events(L, "shade_spawned")[0]["data"], {"id": "S1"})


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
