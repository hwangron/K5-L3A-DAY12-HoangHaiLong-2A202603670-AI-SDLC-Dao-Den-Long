"""Black-box tests for every new Ticket-03 rule ("Den can dau", contract v1.2).

Written from docs/lab/ticket-03.txt only; every expected number is computed by hand in the comments.
Where the ticket is silent and docs/notes/phase-3-design.md decides, the test says "DESIGN:" (and
tests/CHANGES-phase-3.md lists them).

Conventions (ticket + Ticket-02 tick model):
- An input frame at tick k is applied by the step that produces tick k+1 (events carry tick k+1).
- Fuel is counted in 1/60 units: "units" = fuel * 60 (max 6000). Step 2 of every tick removes 1 unit of decay per lit
  lantern and 5 units per Shade that was in `drain` at the end of the previous tick; right after step 2 a lantern with
  units <= 0 goes out. Interaction is step 5, i.e. AFTER the decay of the same tick.
- Snapshot fuel = units / 60 rounded to 1 decimal. I only assert values that are not exactly on a .x5 boundary.
- A lantern lit (or refuelled to the cap) in step 5 of tick t has 6000 units in the snapshot of tick t and
  6000 - n units at tick t + n.
- Walking = 0.1 m/tick, shade chase = 4/60 m/tick, shade wander = 1.5/60 = 0.025 m/tick.
"""
import json
import math
import os
import unittest

from blackbox import (ROOT, base, ev_ticks, events, game_events, last_snap, lantern, press, run, shade, snap,
                      PER_FLAME, PER_LANTERN, PER_MOTE, PER_RELIGHT, PER_STUN)

START3 = [0.0, 0.0, -30.0]


def lit(lid, fuel=None, **kw):
    d = {"id": lid, "lit": True}
    if fuel is not None:
        d["fuel"] = fuel
    d.update(kw)
    return d


def fuel_at(L, t, lid="L1"):
    return lantern(snap(L, t), lid)["fuel"]


def seq(L, names=None):
    """[(tick, name)] of game events (no night_start)."""
    return [(e["tick"], e["name"]) for e in game_events(L) if names is None or e["name"] in names]


# --------------------------------------------------------------------------- contract v1.2
class ContractV12(unittest.TestCase):
    NEW = {"fuel_max": 100, "fuel_decay_per_s": 1.0, "fuel_per_mote": 10, "relight_cost": 5, "win_ratio": 0.6,
           "drain_per_s": 5, "low_fuel_threshold": 30, "capacity_max": 20,
           "night1_duration_s": 240, "night2_duration_s": 270, "night3_duration_s": 300}

    def load(self):
        with open(os.path.join(ROOT, "game.contract.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_version_and_new_tuning_keys(self):
        from game.sim import TUNING
        c = self.load()
        self.assertEqual(c["contract_version"], "1.3")   # Ticket-04: contract v1.3 (was 1.2); tuning is unchanged
        for k, v in self.NEW.items():
            self.assertIn(k, c["tuning"], k)
            self.assertEqual(c["tuning"][k], v, k)
        self.assertEqual(c["tuning"], TUNING)
        # v1.1 keys are still there (the ticket only adds / changes durations)
        for k in ("player_speed", "carry_capacity", "lantern_cost", "pickup_radius", "interact_radius",
                  "pulse_cost", "pulse_radius", "safe_radius", "shade_speed", "dash_speed", "flames"):
            self.assertIn(k, c["tuning"], k)
        self.assertEqual(c["tuning"]["carry_capacity"], 10)   # base capacity before successful lights
        self.assertEqual(c["tuning"]["lantern_cost"], 10)
        self.assertEqual(c["tuning"]["safe_radius"], 6.0)

    def test_score_table(self):
        # DESIGN: the ticket gives the scoring rules but not the tuning.score key names; phase-3-design.md names them.
        sc = self.load()["tuning"]["score"]
        want = {"per_mote": 5, "per_lantern": 100, "per_stun": 5, "per_flame_left": 50, "per_second_left": 0,
                "per_relight": 40, "per_drain_stun": 15, "per_lit_lantern_dawn": 50}
        for k, v in want.items():
            self.assertEqual(sc.get(k), v, k)

    def test_default_night_durations_in_snapshot(self):
        for n, secs in ((1, 240.0), (2, 270.0), (3, 300.0)):
            self.assertEqual(run(None, ticks=0, night=n)[0]["time_left_s"], secs)

    def test_dawn_after_exactly_the_new_duration(self):
        # night 1 = 240 s = 14400 ticks; nothing lit -> lost dawn exactly at tick 14400, not before
        L = run(base(), ticks=15000, every=14400)
        self.assertEqual([(e["tick"], e["data"]) for e in events(L, "game_over")],
                         [(14400, {"result": "lost", "reason": "dawn"})])


# --------------------------------------------------------------------------- snapshot v1.2
class SnapshotV12(unittest.TestCase):
    def test_default_lantern_and_player_fields(self):
        s = run(None, ticks=0)[0]
        for l in s["lanterns"]:
            self.assertEqual(set(l), {"id", "pos", "lit", "deposited", "fuel", "ever_lit", "relit_count"})
            self.assertIs(l["lit"], False)
            self.assertEqual(l["fuel"], 0)                 # an unlit lantern has fuel 0
            self.assertIsInstance(l["fuel"], (int, float))
            self.assertIs(l["ever_lit"], False)
            self.assertEqual(l["relit_count"], 0)
            self.assertEqual(l["deposited"], 0)
        self.assertEqual(s["player"]["capacity"], 10)      # 10 + 2 * 0 successful lights
        self.assertIn("carried", s["player"])

    def test_preset_lit_defaults_to_fuel_100(self):
        s = run(base(lanterns=[{"id": "L1", "lit": True}, {"id": "L2", "lit": True, "fuel": 42.5}]), ticks=0)[0]
        self.assertEqual((lantern(s, "L1")["lit"], lantern(s, "L1")["fuel"]), (True, 100.0))
        self.assertEqual((lantern(s, "L2")["lit"], lantern(s, "L2")["fuel"]), (True, 42.5))

    def test_preset_ever_lit_and_unlit_fuel(self):
        s = run(base(lanterns=[{"id": "L1", "lit": False, "ever_lit": True}, {"id": "L2"}]), ticks=0)[0]
        self.assertIs(lantern(s, "L1")["ever_lit"], True)
        self.assertEqual(lantern(s, "L1")["fuel"], 0)
        self.assertIs(lantern(s, "L2")["ever_lit"], False)

    def test_preset_lit_lantern_has_ever_lit(self):
        # DESIGN: "ever_lit defaults to lit" (phase-3-design.md); the ticket only says a lantern that has been lit
        # remembers ever_lit = true.
        s = run(base(lanterns=[{"id": "L1", "lit": True}]), ticks=0)[0]
        self.assertIs(lantern(s, "L1")["ever_lit"], True)
        self.assertEqual(lantern(s, "L1")["relit_count"], 0)


# --------------------------------------------------------------------------- fuel decay, out, ever_lit
class FuelDecay(unittest.TestCase):
    def test_decay_is_one_per_second_at_tick_resolution(self):
        # units 6000 - n. n=1: 5999/60 = 99.983 -> 100.0; 2: 99.967 -> 100.0; 4: 5996/60 = 99.933 -> 99.9;
        # 6: 5994/60 = 99.9; 10: 5990/60 = 99.833 -> 99.8; 12: 5988/60 = 99.8. A once-per-second step would stay 100.0.
        L = run(base(lanterns=[lit("L1")]), ticks=12, every=1)
        self.assertEqual(fuel_at(L, 0), 100.0)
        for t, f in ((1, 100.0), (2, 100.0), (4, 99.9), (6, 99.9), (10, 99.8), (12, 99.8)):
            self.assertEqual(fuel_at(L, t), f, t)

    def test_decay_exactly_one_per_60_ticks_and_one_decimal(self):
        # n=20: 5980/60 = 99.667 -> 99.7; 30: 99.5; 60: 99.0; 90: 5910/60 = 98.5; 100: 5900/60 = 98.333 -> 98.3;
        # 600: 90.0; 3000: 50.0; 5940: 1.0; 5990: 10/60 = 0.167 -> 0.2; 5999: 1/60 -> 0.0 but still lit.
        L = run(base(lanterns=[lit("L1")]), ticks=6000, every=10)
        table = {0: 100.0, 20: 99.7, 30: 99.5, 60: 99.0, 90: 98.5, 100: 98.3, 600: 90.0, 3000: 50.0, 5940: 1.0,
                 5990: 0.2}
        for t, f in table.items():
            self.assertEqual(fuel_at(L, t), f, t)
        for l in [x for s in L if s["type"] == "snapshot" for x in s["lanterns"]]:
            self.assertEqual(round(l["fuel"], 1), l["fuel"])        # 1 decimal only
        self.assertEqual(ev_ticks(L, "lantern_out"), [6000])        # 6000 units -> out when units hit 0

    def test_lantern_out_tick_deposited_reset_and_ever_lit(self):
        # fuel 1.0 = 60 units -> 59 left at tick 1 ... 1 left at tick 59 (still lit, fuel 0.0), 0 at tick 60 -> out.
        # fuel 0.5 = 30 units -> out at tick 30. A lantern with fuel 1.5 (90 units) -> out at tick 90.
        sc = base(lanterns=[lit("L1", 1.0, deposited=10), lit("L2", 0.5), lit("L3", 1.5)])
        L = run(sc, ticks=100, every=1)
        self.assertEqual(seq(L, {"lantern_out"}), [(30, "lantern_out"), (60, "lantern_out"), (90, "lantern_out")])
        self.assertEqual([e["data"] for e in events(L, "lantern_out")],
                         [{"lantern_id": "L2"}, {"lantern_id": "L1"}, {"lantern_id": "L3"}])
        a, b = lantern(snap(L, 59), "L1"), lantern(snap(L, 60), "L1")
        self.assertEqual((a["lit"], a["fuel"]), (True, 0.0))
        self.assertEqual((b["lit"], b["fuel"], b["deposited"], b["ever_lit"]), (False, 0, 0, True))
        self.assertIs(lantern(snap(L, 29), "L2")["lit"], True)
        self.assertIs(lantern(snap(L, 30), "L2")["lit"], False)
        # stays out, stays at fuel 0, no second event
        self.assertEqual(lantern(snap(L, 100), "L1")["fuel"], 0)
        self.assertEqual(len(events(L, "lantern_out")), 3)

    def test_out_lantern_gives_no_safe_zone(self):
        # a lantern that burnt out is just an unlit lantern: a shade chasing from 10 m is no longer held at 6 m
        sc = base(lanterns=[lit("L1", 0.5)], shades=[{"id": "S1", "pos": [10, 1, 0], "state": "chase"}])
        L = run(sc, ticks=200)
        self.assertTrue(events(L, "player_hit"))


# --------------------------------------------------------------------------- lighting, relighting
class Relight(unittest.TestCase):
    def test_first_light_costs_10_and_reports_relight_false(self):
        # carried 9 -> deposit 9, 9/10 not lit; carried 10 -> lit. Score 10*5 + 100 = 150. Fuel 100 in the snapshot
        # of the lighting tick (units 6000), ever_lit true, relit_count 0, successful_lights 1 -> capacity 12.
        pos = [0, 0, 1.5]
        L = run(base(player={"pos": [0, 0, 0], "carried": 9}, lanterns=[{"id": "L1", "pos": pos}]),
                press(0, "interact"), ticks=3)
        self.assertEqual([(e["name"], e["data"]) for e in game_events(L)],
                         [("deposit", {"lantern_id": "L1", "amount": 9, "deposited": 9})])
        self.assertEqual(L[-1]["score"], 9 * PER_MOTE)
        L = run(base(player={"pos": [0, 0, 0], "carried": 10}, lanterns=[{"id": "L1", "pos": pos}]),
                press(0, "interact"), ticks=3)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(1, "deposit", {"lantern_id": "L1", "amount": 10, "deposited": 10}),
                          (1, "lantern_lit", {"lantern_id": "L1", "relight": False})])
        self.assertEqual(L[-1]["score"], 150)
        l = lantern(snap(L, 1), "L1")
        self.assertEqual((l["lit"], l["fuel"], l["ever_lit"], l["relit_count"]), (True, 100.0, True, 0))
        self.assertEqual(snap(L, 1)["player"]["capacity"], 12)

    def test_relight_costs_5_scores_40_and_counts(self):
        # ever_lit lantern, carried 8: deposit min(8, 5) = 5 -> lit, relight true, 3 left.
        # Score 5*5 + 40 = 65. relit_count 1, fuel 100 again, capacity 10 + 2*1 = 12 (relights count).
        sc = base(player={"pos": [0, 0, 0], "carried": 8},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.5], "lit": False, "ever_lit": True}])
        L = run(sc, press(0, "interact"), ticks=3)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(1, "deposit", {"lantern_id": "L1", "amount": 5, "deposited": 5}),
                          (1, "lantern_lit", {"lantern_id": "L1", "relight": True})])
        self.assertEqual(L[-1]["score"], 5 * PER_MOTE + PER_RELIGHT)
        self.assertEqual(5 * PER_MOTE + PER_RELIGHT, 65)
        self.assertEqual(snap(L, 1)["player"]["carried"], 3)
        l = lantern(snap(L, 1), "L1")
        self.assertEqual((l["lit"], l["fuel"], l["ever_lit"], l["relit_count"]), (True, 100.0, True, 1))
        self.assertEqual(snap(L, 1)["player"]["capacity"], 12)

    def test_relight_progress_is_remembered(self):
        # 3 carried -> 3/5 (+15); a later press with 4 carried and 3 already in: deposit min(4, 2) = 2 -> lit
        # (+10 +40 = 50), 2 left.
        sc = base(player={"pos": [0, 0, 0], "carried": 3},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.5], "lit": False, "ever_lit": True}])
        L = run(sc, press(0, "interact"), ticks=3)
        self.assertEqual([(e["name"], e["data"]) for e in game_events(L)],
                         [("deposit", {"lantern_id": "L1", "amount": 3, "deposited": 3})])
        self.assertEqual(L[-1]["score"], 15)
        self.assertEqual(lantern(snap(L, 3), "L1")["deposited"], 3)
        sc = base(player={"pos": [0, 0, 0], "carried": 4},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.5], "lit": False, "ever_lit": True, "deposited": 3}])
        L = run(sc, press(0, "interact"), ticks=3)
        self.assertEqual([(e["name"], e["data"]) for e in game_events(L)],
                         [("deposit", {"lantern_id": "L1", "amount": 2, "deposited": 5}),
                          ("lantern_lit", {"lantern_id": "L1", "relight": True})])
        self.assertEqual(L[-1]["score"], 2 * PER_MOTE + PER_RELIGHT)
        self.assertEqual(snap(L, 3)["player"]["carried"], 2)

    def test_two_relights_of_the_same_lantern(self):
        # relight at tick 1 (units 6000), out when units hit 0: 6000 - n = 0 at tick 1 + 6000 = 6001, relight again
        # on tick 6002 -> relit_count 2, capacity 10 + 2*2 = 14. carried 10 -> 5 -> 0. Score 2 * (25 + 40) = 130.
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, time_left_s=300,
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.5], "lit": False, "ever_lit": True}])
        L = run(sc, press(0, "interact") + press(6001, "interact"), ticks=6010, every=1)
        self.assertEqual(seq(L, {"lantern_out", "lantern_lit"}),
                         [(1, "lantern_lit"), (6001, "lantern_out"), (6002, "lantern_lit")])
        self.assertEqual([e["data"]["relight"] for e in events(L, "lantern_lit")], [True, True])
        self.assertEqual(lantern(snap(L, 6000), "L1")["relit_count"], 1)
        self.assertIs(lantern(snap(L, 6000), "L1")["lit"], True)
        self.assertIs(lantern(snap(L, 6001), "L1")["lit"], False)
        l = lantern(snap(L, 6002), "L1")
        self.assertEqual((l["lit"], l["relit_count"], l["fuel"]), (True, 2, 100.0))
        self.assertEqual(snap(L, 6002)["player"]["capacity"], 14)
        self.assertEqual(L[-1]["score"], 130)


# --------------------------------------------------------------------------- refuel
class Refuel(unittest.TestCase):
    def sc(self, carried, fuel, **kw):
        return base(player={"pos": [0, 0, 0], "carried": carried},
                    lanterns=[lit("L1", fuel, pos=[0, 0, 1.5], ever_lit=True)], **kw)

    def test_example_fuel_25_5_carried_10_uses_8_and_fills(self):
        # tick 1: units 1530 - 1 = 1529 (25.483). missing 74.517 / 10 = 7.45 -> ceil 8. used = min(10, 8) = 8.
        # fuel = min(100, 25.483 + 80) = 100. carried 2. +8*5 = 40. No deposit / lantern_lit event.
        L = run(self.sc(10, 25.5), press(0, "interact"), ticks=3, every=1)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(1, "refuel", {"lantern_id": "L1", "amount": 8, "fuel": 100.0})])
        self.assertEqual(snap(L, 1)["player"]["carried"], 2)
        self.assertEqual(fuel_at(L, 1), 100.0)
        self.assertEqual(L[-1]["score"], 8 * PER_MOTE)
        self.assertEqual(8 * PER_MOTE, 40)
        # a refuel is not a (successful) light: capacity stays 10, relit_count stays 0
        self.assertEqual(snap(L, 1)["player"]["capacity"], 10)
        self.assertEqual(lantern(snap(L, 1), "L1")["relit_count"], 0)

    def test_limited_by_carried(self):
        # carried 3: used 3 -> units 1529 + 1800 = 3329 -> 55.483 -> 55.5, +15
        L = run(self.sc(3, 25.5), press(0, "interact"), ticks=2)
        self.assertEqual(events(L, "refuel")[0]["data"], {"lantern_id": "L1", "amount": 3, "fuel": 55.5})
        self.assertEqual(fuel_at(L, 1), 55.5)
        self.assertEqual((snap(L, 1)["player"]["carried"], L[-1]["score"]), (0, 15))
        # carried 1: units 1529 + 600 = 2129 -> 35.483 -> 35.5
        L = run(self.sc(1, 25.5), press(0, "interact"), ticks=2)
        self.assertEqual(events(L, "refuel")[0]["data"], {"lantern_id": "L1", "amount": 1, "fuel": 35.5})

    def test_decay_comes_before_interaction_in_the_same_tick(self):
        # fuel 80 = 4800 units; the interaction happens after step 2, so units = 4799: missing 1201 / 600 = 2.002
        # -> ceil 3 (not 2). used 3 -> fuel 100, carried 7, +15. Without the decay it would be used 2.
        L = run(self.sc(10, 80.0), press(0, "interact"), ticks=2)
        self.assertEqual(events(L, "refuel")[0]["data"], {"lantern_id": "L1", "amount": 3, "fuel": 100.0})
        self.assertEqual((snap(L, 1)["player"]["carried"], L[-1]["score"]), (7, 15))

    def test_nothing_to_refuel_with_empty_hands(self):
        # used = min(0, ...) = 0 -> not selectable: no event, no score (also no deposit into an unlit lantern)
        sc = base(player={"pos": [0, 0, 0], "carried": 0},
                  lanterns=[lit("L1", 25.5, pos=[0, 0, 1.5]), {"id": "L2", "pos": [1.0, 0, 0]}])
        L = run(sc, press(0, "interact"), ticks=3)
        self.assertFalse(game_events(L))
        self.assertEqual(L[-1]["score"], 0)

    def test_topping_up_costs_one_mote_per_decayed_unit_block(self):
        # After a refuel to exactly 100 the lantern is only "full" inside that tick: step 2 of the next tick takes
        # 1 unit (99.98), so ceil(0.0167 / 10) = 1 and a second press takes 1 mote (carried 2 -> 1) and fills again.
        # (A lantern with used = 0 is never selected; with this formula that can only happen when carried is 0.)
        again = [{"tick": 0, "interact": True}, {"tick": 1, "interact": False},
                 {"tick": 2, "interact": True}, {"tick": 3, "interact": False}]
        L = run(self.sc(10, 25.5), again, ticks=5)
        self.assertEqual([(e["tick"], e["data"]) for e in events(L, "refuel")],
                         [(1, {"lantern_id": "L1", "amount": 8, "fuel": 100.0}),
                          (3, {"lantern_id": "L1", "amount": 1, "fuel": 100.0})])
        self.assertEqual(snap(L, 3)["player"]["carried"], 1)
        self.assertEqual(L[-1]["score"], 9 * PER_MOTE)
        # carried 9: press 1 uses 8 (1 left), press 2 uses the last one (0 left), press 3 has empty hands -> no event
        three = again + [{"tick": 4, "interact": True}, {"tick": 5, "interact": False}]
        L = run(self.sc(9, 25.5), three, ticks=7)
        self.assertEqual(ev_ticks(L, "refuel"), [1, 3])
        self.assertEqual(snap(L, 7)["player"]["carried"], 0)

    def test_out_of_reach_lit_lantern_is_not_refuelled(self):
        for z, expect in ((2.0, True), (2.01, False)):      # reach is <= 2.0 m (XZ)
            sc = base(player={"pos": [0, 0, 0], "carried": 5}, lanterns=[lit("L1", 25.5, pos=[0, 0, z])])
            self.assertEqual(bool(events(run(sc, press(0, "interact"), ticks=2), "refuel")), expect, z)


# --------------------------------------------------------------------------- choosing the lantern
class Selection(unittest.TestCase):
    def first(self, lanterns, carried=10):
        L = run(base(player={"pos": [0, 0, 0], "carried": carried}, lanterns=lanterns), press(0, "interact"), ticks=2)
        return [(e["name"], e["data"]) for e in game_events(L)]

    def test_nearest_candidate_wins_unlit_over_weak_lit(self):
        # L1 lit weak (fuel 22) at 1.5 m, L2 unlit at 1.0 m -> L2: deposit 10 and light it
        got = self.first([lit("L1", 22.0, pos=[0, 0, 1.5]), {"id": "L2", "pos": [1.0, 0, 0]}])
        self.assertEqual(got, [("deposit", {"lantern_id": "L2", "amount": 10, "deposited": 10}),
                               ("lantern_lit", {"lantern_id": "L2", "relight": False})])

    def test_nearest_candidate_wins_weak_lit_over_unlit(self):
        # L1 lit (fuel 22 -> 21.98 after decay) at 1.0 m, L2 unlit at 1.5 m -> L1 refuelled:
        # missing 78.017 / 10 = 7.8 -> 8; used 8; fuel 100; carried 10 -> 2
        got = self.first([lit("L1", 22.0, pos=[0, 0, 1.0]), {"id": "L2", "pos": [1.5, 0, 0]}])
        self.assertEqual(got, [("refuel", {"lantern_id": "L1", "amount": 8, "fuel": 100.0})])

    def test_tie_goes_to_smaller_id_both_ways(self):
        # both exactly 1.0 m away
        got = self.first([{"id": "L1", "pos": [0, 0, 1.0]}, lit("L2", 22.0, pos=[1.0, 0, 0])])
        self.assertEqual(got[0], ("deposit", {"lantern_id": "L1", "amount": 10, "deposited": 10}))
        got = self.first([lit("L1", 22.0, pos=[0, 0, 1.0]), {"id": "L2", "pos": [1.0, 0, 0]}])
        self.assertEqual(got, [("refuel", {"lantern_id": "L1", "amount": 8, "fuel": 100.0})])

    def test_only_one_lantern_per_press(self):
        got = self.first([lit("L1", 22.0, pos=[0, 0, 1.0]), lit("L2", 22.0, pos=[0, 0, 1.1])])
        self.assertEqual([n for n, _ in got], ["refuel"])
        self.assertEqual(got[0][1]["lantern_id"], "L1")


# --------------------------------------------------------------------------- safe zone needs fuel >= 30
class SafeZoneFuel(unittest.TestCase):
    def test_zone_kept_at_exactly_30_lost_below(self):
        # L1 at the player's feet, fuel 31 = 1860 units: units 1860 - n. n = 60 -> 1800 = exactly 30.0 (zone kept),
        # n = 61 -> 1799 = 29.98 (< 30, zone gone). S1 chases from (9,1,0) at 1/15 m per tick: held at the 6 m edge
        # from tick 45 to tick 60; at 61 it is free: 6 - 1/15 = 5.933 and keeps coming: touches (<= 1.0) when
        # 6 - (k - 60)/15 <= 1 -> k = 135.
        sc = base(lanterns=[lit("L1", 31.0, pos=[0, 0, 0])], shades=[{"id": "S1", "pos": [9, 1, 0], "state": "chase"}])
        L = run(sc, ticks=160, every=1)
        for t in range(46, 61):
            self.assertAlmostEqual(shade(snap(L, t), "S1")["pos"][0], 6.0, delta=0.002, msg=t)
        self.assertEqual(fuel_at(L, 60), 30.0)
        self.assertLess(shade(snap(L, 61), "S1")["pos"][0], 5.95)
        hits = ev_ticks(L, "player_hit")
        self.assertTrue(hits)
        self.assertTrue(133 <= hits[0] <= 137, hits)

    def test_low_fuel_lantern_gives_no_protection_from_the_start(self):
        # fuel 20 never had a zone: chase from 10 m touches at 15 * (10 - 1) = 135
        sc = base(lanterns=[lit("L1", 20.0, pos=[0, 0, 0])], shades=[{"id": "S1", "pos": [10, 1, 0], "state": "chase"}])
        hits = ev_ticks(run(sc, ticks=200), "player_hit")
        self.assertTrue(hits and 134 <= hits[0] <= 136, hits)

    def test_refuel_above_30_expels_shade_harmlessly(self):
        # L1 fuel 10 at the player's feet (no zone). S1 (0.5,1,0) would touch on tick 1. Press at tick 1 with
        # carried 5: units 599 + 5*600 = 3599 = 59.98 -> 60.0 >= 30 -> zone -> S1 expelled to the 6 m edge
        # ((6 - 0.5)/30 per tick, <= 30 ticks), harmless meanwhile, then held at 6.0.
        sc = base(player={"pos": [0, 0, 0], "carried": 5}, shades=[{"id": "S1", "pos": [0.5, 1, 0], "state": "chase"}],
                  lanterns=[lit("L1", 10.0, pos=[0, 0, 0])])
        L = run(sc, press(0, "interact"), ticks=300, every=1)
        self.assertEqual(events(L, "refuel")[0]["data"], {"lantern_id": "L1", "amount": 5, "fuel": 60.0})
        self.assertFalse(events(L, "player_hit"))
        xs = [shade(snap(L, t), "S1")["pos"][0] for t in range(1, 32)]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(shade(snap(L, 31), "S1")["pos"], [6.0, 1.0, 0.0])
        self.assertEqual(shade(snap(L, 300), "S1")["pos"], [6.0, 1.0, 0.0])

    def test_refuel_below_30_gives_no_zone(self):
        # carried 1: units 599 + 600 = 1199 = 19.98 -> 20.0 < 30 -> no zone, the shade touches on tick 1
        sc = base(player={"pos": [0, 0, 0], "carried": 1}, shades=[{"id": "S1", "pos": [0.5, 1, 0], "state": "chase"}],
                  lanterns=[lit("L1", 10.0, pos=[0, 0, 0])])
        L = run(sc, press(0, "interact"), ticks=3)
        self.assertEqual(events(L, "refuel")[0]["data"]["fuel"], 20.0)
        self.assertEqual(ev_ticks(L, "player_hit"), [1])


# --------------------------------------------------------------------------- drain
class Drain(unittest.TestCase):
    L1 = [0, 0, 25]

    def one_shade(self, **kw):
        # weak lantern L1 (fuel 20 = 1200 units) at (0,0,25); S1 1.5 m from it, 26.5 m from the player (> 12 m:
        # never chases). Entering drain on tick 1, units after tick 1: 1199 (only decay: the shade drains from tick 2).
        sc = base(lanterns=[lit("L1", 20.0, pos=self.L1, ever_lit=True)], shades=[{"id": "S1", "pos": [0, 1, 26.5]}])
        sc.update(kw)
        return sc

    def test_wander_shade_enters_drain_stands_still_and_drains_6_per_tick(self):
        # from tick 2 each tick removes 1 (decay) + 5 (drain) = 6 units: units(n) = 1199 - 6 (n - 1)
        # n=2: 1193 -> 19.88 -> 19.9; 10: 1145 -> 19.08 -> 19.1; 31: 1019 -> 16.98 -> 17.0; 70: 785 -> 13.08 -> 13.1;
        # 100: 605 -> 10.08 -> 10.1; 150: 305 -> 5.08 -> 5.1; 200: 5 -> 0.08 -> 0.1 (still lit); 201: -1 -> out.
        L = run(self.one_shade(), ticks=210, every=1)
        self.assertEqual(shade(snap(L, 1), "S1")["state"], "drain")
        for t in (2, 50, 200):
            self.assertEqual(shade(snap(L, t), "S1")["state"], "drain", t)
        self.assertEqual({tuple(shade(snap(L, t), "S1")["pos"]) for t in range(2, 201)}, {(0.0, 1.0, 26.5)})
        for t, f in ((2, 19.9), (10, 19.1), (31, 17.0), (70, 13.1), (100, 10.1), (150, 5.1), (200, 0.1)):
            self.assertEqual(fuel_at(L, t), f, t)
        self.assertIs(lantern(snap(L, 200), "L1")["lit"], True)
        self.assertEqual(ev_ticks(L, "lantern_out"), [201])
        l = lantern(snap(L, 201), "L1")
        self.assertEqual((l["lit"], l["fuel"], l["deposited"], l["ever_lit"]), (False, 0, 0, True))
        # the draining shade goes back to wander because the lantern went out (ticket: "sang wander neu den tat")
        self.assertEqual(shade(snap(L, 201), "S1")["state"], "wander")
        self.assertFalse(events(L, "player_hit"))

    def test_fuel_drain_event_every_60_ticks(self):
        # ticket: fuel_drain {lantern_id, shade_id, fuel} every 60 ticks while draining; fuel = the lantern's fuel.
        # 200 ticks of draining -> 3 events (a 4th would come at ~241, after the lantern went out at 201).
        L = run(self.one_shade(), ticks=260, every=1)
        ev = events(L, "fuel_drain")
        self.assertEqual(len(ev), 3)
        ticks = [e["tick"] for e in ev]
        self.assertEqual([b - a for a, b in zip(ticks, ticks[1:])], [60, 60])
        for e in ev:
            self.assertEqual(e["data"]["lantern_id"], "L1")
            self.assertEqual(e["data"]["shade_id"], "S1")
            self.assertEqual(set(e["data"]), {"lantern_id", "shade_id", "fuel"})
            self.assertEqual(e["data"]["fuel"], fuel_at(L, e["tick"]))     # same value as the snapshot of that tick
            self.assertEqual(round(e["data"]["fuel"], 1), e["data"]["fuel"])

    def test_fuel_drain_phase_design_decision(self):
        # DESIGN (phase-3-design.md): the count starts on the tick the shade enters drain (tick 1) and the first
        # event is written after 60 drain ticks, i.e. tick 61, then 121, 181. Values: units 839 -> 13.98 -> 14.0;
        # 479 -> 7.98 -> 8.0; 119 -> 1.98 -> 2.0. The ticket itself only says "every 60 ticks".
        L = run(self.one_shade(), ticks=260)
        self.assertEqual([(e["tick"], e["data"]["fuel"]) for e in events(L, "fuel_drain")],
                         [(61, 14.0), (121, 8.0), (181, 2.0)])

    def test_two_shades_stack_and_decay_still_applies(self):
        # both enter drain on tick 1. From tick 2: 1 + 5 + 5 = 11 units per tick: units(n) = 1199 - 11 (n - 1)
        # n=21: 979 -> 16.3; 31: 869 -> 14.48 -> 14.5; 61: 539 -> 8.98 -> 9.0; 100: 110 -> 1.83 -> 1.8;
        # 109: 11 -> 0.18 -> 0.2 (lit); 110: 0 -> out (fuel <= 0).
        sc = base(lanterns=[lit("L1", 20.0, pos=self.L1, ever_lit=True)],
                  shades=[{"id": "S1", "pos": [0, 1, 26.5]}, {"id": "S2", "pos": [1.5, 1, 25]}])
        L = run(sc, ticks=130, every=1)
        for t, f in ((21, 16.3), (31, 14.5), (61, 9.0), (100, 1.8), (109, 0.2)):
            self.assertEqual(fuel_at(L, t), f, t)
        self.assertIs(lantern(snap(L, 109), "L1")["lit"], True)
        self.assertEqual(ev_ticks(L, "lantern_out"), [110])
        self.assertIs(lantern(snap(L, 110), "L1")["lit"], False)
        for sid in ("S1", "S2"):
            self.assertEqual(shade(snap(L, 100), sid)["state"], "drain")
            self.assertEqual(shade(snap(L, 110), sid)["state"], "wander")
        fd = events(L, "fuel_drain")
        self.assertEqual(sorted(e["data"]["shade_id"] for e in fd), ["S1", "S2"])   # one round before the lantern dies
        self.assertEqual(len({e["tick"] for e in fd}), 1)

    def test_drain_only_within_2m_of_the_weak_lantern(self):
        # S1 at 2.5 m is not yet draining at tick 1 (it walks 1.5 m/s towards the lantern first)
        sc = base(lanterns=[lit("L1", 20.0, pos=self.L1, ever_lit=True)], shades=[{"id": "S1", "pos": [0, 1, 27.5]}])
        L = run(sc, ticks=1, every=1)
        self.assertEqual(shade(snap(L, 1), "S1")["state"], "wander")
        self.assertFalse(events(L, "fuel_drain"))
        # ... and at exactly 2.0 m it starts at once (<= 2 m)
        sc = base(lanterns=[lit("L1", 20.0, pos=self.L1, ever_lit=True)], shades=[{"id": "S1", "pos": [0, 1, 27.0]}])
        self.assertEqual(shade(snap(run(sc, ticks=1, every=1), 1), "S1")["state"], "drain")

    def test_drain_to_chase_when_cloud_within_6m(self):
        # L1 fuel 29 (1740 units, weak). S1 at (0,1,26.55), 1.55 m from L1. The player waits at z = 14.0
        # (12.55 m from S1 > 12 -> S1 enters drain on tick 1), then walks +Z at 0.1/tick from tick 10
        # (z = 14 + 0.1 (k - 9)). Distance to S1 = 26.55 - z: tick 74: z = 20.5 -> 6.05 (still drain);
        # tick 75: z = 20.6 -> 5.95 <= 6 -> chase. The shade drained on ticks 2..75 (the tick-75 drain is the one
        # decided at tick 74): units(75) = 1740 - 1 - 6*74 = 1295 -> 21.58 -> 21.6; after that only decay:
        # units(135) = 1295 - 60 = 1235 -> 20.58 -> 20.6 (exactly 1.0 lower).
        sc = base(player={"pos": [0, 0, 14.0]}, lanterns=[lit("L1", 29.0, pos=self.L1, ever_lit=True)],
                  shades=[{"id": "S1", "pos": [0, 1, 26.55]}])
        L = run(sc, [{"tick": 9, "move": [0, 1]}], ticks=140, every=1)
        self.assertEqual(shade(snap(L, 1), "S1")["state"], "drain")
        self.assertEqual(shade(snap(L, 50), "S1")["state"], "drain")          # 8.45 m away: > 6
        self.assertEqual(shade(snap(L, 74), "S1")["state"], "drain")
        self.assertEqual(shade(snap(L, 74), "S1")["pos"], [0.0, 1.0, 26.55])
        self.assertEqual(shade(snap(L, 75), "S1")["state"], "chase")
        self.assertEqual(fuel_at(L, 75), 21.6)
        self.assertEqual(fuel_at(L, 135), 20.6)
        self.assertEqual(fuel_at(L, 135), round(fuel_at(L, 75) - 1.0, 1))

    def test_chase_shade_keeps_chasing_and_does_not_drain(self):
        # "Bong dang chase khong doi muc tieu": S1 (chase) 5 m from the player, weak L1 1.0 m from S1:
        # it keeps running at the player: x(30) = 5 - 30/15 = 3.0, state chase, lantern only decays (1170 units = 19.5)
        sc = base(lanterns=[lit("L1", 20.0, pos=[6, 0, 0])], shades=[{"id": "S1", "pos": [5, 1, 0], "state": "chase"}])
        L = run(sc, ticks=30, every=1)
        s = shade(snap(L, 30), "S1")
        self.assertEqual((s["state"], s["pos"][0]), ("chase", 3.0))
        self.assertEqual(fuel_at(L, 30), 19.5)
        self.assertFalse(events(L, "fuel_drain"))

    def test_refuel_above_30_expels_a_draining_shade(self):
        # DESIGN: needs a scenario shade preset to state drain + target_lantern_id (a draining shade is always >
        # 6 m from the player, and the interact range is 2 m, so it cannot happen naturally).
        # L1 fuel 10 at the player's feet, S1 draining it from 0.5 m. Press with carried 10 on tick 1: used
        # min(10, ceil(~9.0)) = 10 -> fuel 100.0 (whether or not the preset drain already took 5 units on tick 1).
        # S1 is inside the new 6 m zone -> expelled to the edge (6.0 on tick 31), harmless, never drains again.
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, lanterns=[lit("L1", 10.0, pos=[0, 0, 0], ever_lit=True)],
                  shades=[{"id": "S1", "pos": [0.5, 1, 0], "state": "drain", "target_lantern_id": "L1"}])
        L = run(sc, press(0, "interact"), ticks=150, every=1)
        self.assertEqual(events(L, "refuel")[0]["data"], {"lantern_id": "L1", "amount": 10, "fuel": 100.0})
        self.assertFalse(events(L, "player_hit"))
        self.assertNotEqual(shade(snap(L, 1), "S1")["state"], "drain")
        self.assertIn(shade(snap(L, 1), "S1")["state"], ("wander", "chase"))   # ticket lists wander; chase is also listed
        self.assertEqual(shade(snap(L, 31), "S1")["pos"], [6.0, 1.0, 0.0])
        self.assertEqual(shade(snap(L, 150), "S1")["pos"], [6.0, 1.0, 0.0])
        self.assertFalse([e for e in events(L, "fuel_drain") if e["tick"] > 1])
        # decay only afterwards: units 6000 at tick 1 -> tick 121 = 5880 = 98.0
        self.assertEqual(fuel_at(L, 121), 98.0)

    def test_target_lantern_id_selects_the_drained_lantern(self):
        # two weak lanterns far apart; S1 (preset drain) is at L2 and names it. Only L2 is drained.
        # L1: fuel 20, only decay: tick 60 -> 1200 - 60 = 1140 -> 19.0. L2 is drained about 5 units per tick extra.
        sc = base(lanterns=[lit("L1", 20.0, pos=[0, 0, 25]), lit("L2", 20.0, pos=[0, 0, -25])],
                  shades=[{"id": "S1", "pos": [0, 1, -26], "state": "drain", "target_lantern_id": "L2"}])
        L = run(sc, ticks=130, every=1)
        self.assertEqual(shade(snap(L, 60), "S1")["state"], "drain")
        self.assertEqual(fuel_at(L, 60, "L1"), 19.0)
        self.assertLess(fuel_at(L, 60, "L2"), 15.0)         # 1200 - 60 - 5 * 59 = 845 (or 840): 14.1 / 14.0
        self.assertGreater(fuel_at(L, 60, "L2"), 13.9)
        self.assertTrue(events(L, "fuel_drain"))
        self.assertEqual({e["data"]["lantern_id"] for e in events(L, "fuel_drain")}, {"L2"})


# --------------------------------------------------------------------------- wander target selection
class WanderTargets(unittest.TestCase):
    def dist(self, L, t, sid, target):
        p = shade(snap(L, t), sid)["pos"]
        return math.hypot(p[0] - target[0], p[2] - target[1])   # target = (x, z)

    def test_wander_goes_to_weak_lantern_not_nearest_unlit(self):
        # night 1 default lanterns are unlit. L1 (0,0,25) lit weak (fuel 20). S1 at (-23.8,1,12): the nearest unlit
        # lantern is L5 (-23.8,0,7.7) at 4.3 m, the weak L1 is hypot(23.8, 13) = 27.119 m away. Wander speed 1.5 m/s:
        # after 60 ticks S1 is 27.119 - 1.5 = 25.619 m from L1 (straight line). The player (origin) is 26.7 m away.
        sc = base(lanterns=[lit("L1", 20.0, pos=[0, 0, 25])], shades=[{"id": "S1", "pos": [-23.8, 1, 12]}])
        L = run(sc, ticks=60, every=60)
        self.assertAlmostEqual(self.dist(L, 0, "S1", [0, 25]), 27.119, delta=0.002)
        self.assertAlmostEqual(self.dist(L, 60, "S1", [0, 25]), 25.619, delta=0.01)

    def test_nearest_weak_lantern_wins(self):
        # S1 (0,1,20); weak L1 (-18,0,20) at 18 m, weak L2 (8,0,20) at 8 m -> moves +X: (1.5, 1, 20) after 60 ticks
        sc = base(player={"pos": [0, 0, -30]},
                  lanterns=[lit("L1", 20.0, pos=[-18, 0, 20]), lit("L2", 25.0, pos=[8, 0, 20])],
                  shades=[{"id": "S1", "pos": [0, 1, 20]}])
        L = run(sc, ticks=60, every=60)
        p = shade(snap(L, 60), "S1")["pos"]
        self.assertAlmostEqual(p[0], 1.5, delta=0.01)
        self.assertAlmostEqual(p[2], 20.0, delta=0.01)

    def test_equal_distance_weak_lanterns_pick_smaller_id(self):
        # S1 (0,1,20) exactly 10 m from L1 (-10,0,20) and L2 (10,0,20), both weak -> L1: x = -1.5 after 60 ticks
        sc = base(player={"pos": [0, 0, -30]},
                  lanterns=[lit("L1", 20.0, pos=[-10, 0, 20]), lit("L2", 20.0, pos=[10, 0, 20])],
                  shades=[{"id": "S1", "pos": [0, 1, 20]}])
        L = run(sc, ticks=60, every=60)
        p = shade(snap(L, 60), "S1")["pos"]
        self.assertAlmostEqual(p[0], -1.5, delta=0.01)
        self.assertAlmostEqual(p[2], 20.0, delta=0.01)

    def test_without_weak_lantern_wander_heads_for_nearest_unlit(self):
        # no lantern is lit: S1 (10,1,-38) -> nearest unlit L3 (14.7,0,-20.2): hypot(4.7, 17.8) = 18.410 m;
        # beyond 4 m it walks straight at 1.5 m/s: 18.410 - 1.5 = 16.910 after 60 ticks. (Player 39 m away.)
        L = run(base(shades=[{"id": "S1", "pos": [10, 1, -38]}]), ticks=60, every=60)
        self.assertAlmostEqual(self.dist(L, 0, "S1", [14.7, -20.2]), 18.410, delta=0.002)
        self.assertAlmostEqual(self.dist(L, 60, "S1", [14.7, -20.2]), 16.910, delta=0.01)

    def test_strong_lit_lantern_is_not_a_weak_target(self):
        # a lit lantern with fuel >= 30 is not "weak": S1 still heads for the nearest unlit lantern (L3),
        # not for the strong L1 (0,0,-22) next to it
        sc = base(lanterns=[lit("L1", 60.0, pos=[0, 0, -34])], shades=[{"id": "S1", "pos": [10, 1, -38]}])
        L = run(sc, ticks=60, every=60)
        self.assertAlmostEqual(self.dist(L, 60, "S1", [14.7, -20.2]), 16.910, delta=0.01)


# --------------------------------------------------------------------------- stun / pulse
class StunAndPulse(unittest.TestCase):
    def test_stun_end_goes_to_wander(self):
        # stunned 5 ticks at 15 m from the player (old rule: <= 18 m -> chase). New: wander (15 m > 12 m).
        # set at tick 0 with 5 -> stunned 0..4, wander from tick 5.
        sc = base(shades=[{"id": "S1", "pos": [15, 1, 0], "state": "stunned", "state_ticks_left": 5}])
        L = run(sc, ticks=30, every=1)
        self.assertEqual(shade(snap(L, 4), "S1")["state"], "stunned")
        for t in (5, 6, 20, 30):
            self.assertEqual(shade(snap(L, t), "S1")["state"], "wander", t)

    def test_pulse_on_normal_shade_is_5_on_drain_shade_15(self):
        # pulse centre (4, 0.8, 0). S1 (1,1,0) drains L1 (fuel 20): sqrt(9 + 0.04) = 3.007 <= 5.
        # S2 (7,1,0) wander: same distance. S1 +15, S2 +5 -> 20; stunned ids in order.
        # DESIGN: scenario state "drain" + target_lantern_id (see Drain.test_refuel_above_30...)
        sc = base(player={"pos": [4, 0, 0], "carried": 6}, lanterns=[lit("L1", 20.0, pos=[0, 0, 0])],
                  shades=[{"id": "S1", "pos": [1, 1, 0], "state": "drain", "target_lantern_id": "L1"},
                          {"id": "S2", "pos": [7, 1, 0]}])
        L = run(sc, press(0, "pulse"), ticks=3, every=1)
        self.assertEqual(events(L, "pulse")[0]["data"], {"stunned_ids": ["S1", "S2"]})
        self.assertEqual(snap(L, 1)["score"], 15 + 5)
        self.assertEqual(shade(snap(L, 1), "S1")["state"], "stunned")
        self.assertEqual(snap(L, 1)["player"]["carried"], 3)
        # only the normal (wander) shade: +5
        sc["shades"] = [{"id": "S2", "pos": [7, 1, 0]}]
        self.assertEqual(run(sc, press(0, "pulse"), ticks=3)[-1]["score"], PER_STUN)
        # a chasing shade on the same spot as the drainer: +5
        sc["shades"] = [{"id": "S1", "pos": [1, 1, 0], "state": "chase"}]
        self.assertEqual(run(sc, press(0, "pulse"), ticks=3)[-1]["score"], PER_STUN)
        # a stunned shade pulsed again: +5 (it is no longer draining)
        sc["shades"] = [{"id": "S1", "pos": [1, 1, 0], "state": "stunned", "state_ticks_left": 50}]
        self.assertEqual(run(sc, press(0, "pulse"), ticks=3)[-1]["score"], PER_STUN)


# --------------------------------------------------------------------------- win / lose at dawn
class DawnRules(unittest.TestCase):
    def dawn(self, night, lit_ids, **kw):
        sc = base(night, lanterns=[lit(i) for i in lit_ids], time_left_s=1, **kw)
        return run(sc, ticks=100, night=night)

    def test_thresholds_3_of_5_4_of_6_5_of_7(self):
        # ceil(0.6*5) = 3, ceil(0.6*6) = ceil(3.6) = 4, ceil(0.6*7) = ceil(4.2) = 5. Dawn (1 s) is tick 60.
        # Win score = lit * (50 + floor(fuel)) + 3 flames * 50; fuel = 100 - 60/60 = 99 exactly.
        #   night 1, 3 lit: 3 * 149 + 150 = 597; night 2, 4 lit: 4 * 149 + 150 = 746; night 3, 5 lit: 5*149 + 150 = 895
        cases = [(1, 5, 3, 597), (2, 6, 4, 746), (3, 7, 5, 895)]
        for night, total, need, score in cases:
            ids = [f"L{i}" for i in range(1, need + 1)]
            L = self.dawn(night, ids)
            self.assertEqual(len(snap(L, 0)["lanterns"]), total)
            self.assertEqual([(e["tick"], e["data"]) for e in events(L, "game_over")],
                             [(60, {"result": "won", "reason": "dawn_survived"})], (night, need))
            self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "won", "score": score}, night)
            L = self.dawn(night, ids[:-1])                      # one lantern short
            self.assertEqual([(e["tick"], e["data"]) for e in events(L, "game_over")],
                             [(60, {"result": "lost", "reason": "dawn"})], (night, need - 1))
            self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "lost", "score": 0}, night)

    def test_no_early_win_when_everything_is_lit(self):
        # all 5 lit from the start, 3 s of night: nothing happens until dawn at tick 180, then won.
        # units 6000 - 180 = 5820 = 97.0 -> 5 * (50 + 97) + 3 * 50 = 735 + 150 = 885
        sc = base(lanterns=[lit(f"L{i}") for i in range(1, 6)], time_left_s=3)
        L = run(sc, ticks=300)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(180, "game_over", {"result": "won", "reason": "dawn_survived"})])
        self.assertEqual(L[-1], {"type": "end", "ticks": 180, "state": "won", "score": 885})
        # and lighting the last one by deposit does not end the night either
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, time_left_s=3,
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.0]}] + [lit(f"L{i}") for i in range(2, 6)])
        L = run(sc, press(0, "interact"), ticks=170)
        self.assertEqual([e["name"] for e in game_events(L)], ["deposit", "lantern_lit"])
        self.assertEqual(L[-1]["state"], "playing")

    def test_all_lit_reason_is_never_used(self):
        for kw in ({"lanterns": [lit(f"L{i}") for i in range(1, 6)]}, {"lanterns": [lit("L1")]}, {}):
            L = run(base(time_left_s=1, **kw), ticks=100)
            self.assertNotIn(events(L, "game_over")[0]["data"]["reason"], ("all_lit",))
            self.assertIn(events(L, "game_over")[0]["data"]["reason"], ("dawn_survived", "dawn", "no_flames"))

    def test_lantern_dying_on_the_dawn_tick_does_not_count(self):
        # L1 fuel 1.0 (60 units) goes out on tick 60 (right after step 2) = the dawn tick; the verdict comes after
        # every update, so only L2, L3 are lit: 2 < 3 -> lost dawn. Event order: lantern_out, then game_over.
        sc = base(lanterns=[lit("L1", 1.0), lit("L2"), lit("L3")], time_left_s=1)
        L = run(sc, ticks=100)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(60, "lantern_out", {"lantern_id": "L1"}),
                          (60, "game_over", {"result": "lost", "reason": "dawn"})])
        # with a 4th lantern the night is won with 3 lit: 3 * (50 + 99) + 150 = 597 (the dead one adds nothing)
        sc = base(lanterns=[lit("L1", 1.0), lit("L2"), lit("L3"), lit("L4")], time_left_s=1)
        L = run(sc, ticks=100)
        self.assertEqual(events(L, "game_over")[0]["data"], {"result": "won", "reason": "dawn_survived"})
        self.assertEqual(L[-1]["score"], 597)

    def test_dawn_bonus_per_lantern_fuel_and_flames(self):
        # 2 s of night = 120 ticks, 2 flames left. units at tick 120: L1 6000-120 = 5880 -> 98;
        # L2 3000-120 = 2880 -> 48; L3 4800-120 = 4680 -> 78. (50+98) + (50+48) + (50+78) = 374; 2 flames = 100.
        sc = base(player={"pos": [0, 0, 0], "flames": 2}, time_left_s=2,
                  lanterns=[lit("L1", 100.0), lit("L2", 50.0), lit("L3", 80.0)])
        L = run(sc, ticks=200)
        self.assertEqual(L[-1], {"type": "end", "ticks": 120, "state": "won", "score": 474})
        self.assertEqual((50 + 98) + (50 + 48) + (50 + 78) + 2 * PER_FLAME, 474)

    def test_no_dawn_bonus_when_lost(self):
        # deposit 10 into L1 (+50 +100) with only 2 lit at dawn (< 3): lost dawn, score stays 150
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, time_left_s=1,
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.0]}, lit("L2")])
        L = run(sc, press(0, "interact"), ticks=100)
        self.assertEqual(events(L, "game_over")[0]["data"], {"result": "lost", "reason": "dawn"})
        self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "lost", "score": 150})


# --------------------------------------------------------------------------- capacity
class Capacity(unittest.TestCase):
    def test_formula_and_cap(self):
        # 10 + 2 * successful_lights, max 20: 0 -> 10, 2 -> 14, 4 -> 18, 5 -> 20, 7 -> min(20, 24) = 20
        for n, cap in ((0, 10), (2, 14), (4, 18), (5, 20), (7, 20)):
            s = run(base(player={"pos": [0, 0, 0], "successful_lights": n}), ticks=0)[0]
            self.assertEqual(s["player"]["capacity"], cap, n)

    def test_pickup_stops_at_capacity(self):
        # successful_lights 2 -> capacity 14: carrying 13, 3 motes on the spot -> 14, 2 left
        sc = base(player={"pos": [0, 0, 0], "carried": 13, "successful_lights": 2}, motes=[[0, 0, 0]] * 3)
        L = run(sc, ticks=1)
        self.assertEqual((snap(L, 1)["player"]["carried"], snap(L, 1)["motes_active"]), (14, 2))
        # at the max: successful_lights 6 -> 20: carrying 18, 5 motes -> 20, 3 left
        sc = base(player={"pos": [0, 0, 0], "carried": 18, "successful_lights": 6}, motes=[[0, 0, 0]] * 5)
        L = run(sc, ticks=1)
        self.assertEqual((snap(L, 1)["player"]["carried"], snap(L, 1)["motes_active"]), (20, 3))

    def test_lighting_grows_capacity_and_more_motes_fit(self):
        # tick 1: carried 10 = capacity 10, so the 14 motes on the spot stay; the deposit lights L1 (carried 0,
        # successful_lights 1 -> capacity 12). Tick 2: pickup up to 12 -> carried 12, 2 motes left.
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, motes=[[0, 0, 0]] * 14,
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.0]}])
        L = run(sc, press(0, "interact"), ticks=4, every=1)
        self.assertEqual((snap(L, 1)["player"]["carried"], snap(L, 1)["player"]["capacity"],
                          snap(L, 1)["motes_active"]), (0, 12, 14))
        self.assertEqual((snap(L, 2)["player"]["carried"], snap(L, 2)["motes_active"]), (12, 2))
        self.assertEqual(snap(L, 4)["player"]["carried"], 12)

    def test_relight_counts_and_max_is_20(self):
        # successful_lights 4 -> 18; a relight makes it 5 -> 20; another light would still be 20
        sc = base(player={"pos": [0, 0, 0], "carried": 5, "successful_lights": 4},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.0], "lit": False, "ever_lit": True}])
        L = run(sc, press(0, "interact"), ticks=2)
        self.assertEqual(snap(L, 0)["player"]["capacity"], 18)
        self.assertEqual(snap(L, 1)["player"]["capacity"], 20)
        sc = base(player={"pos": [0, 0, 0], "carried": 5, "successful_lights": 5},
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.0], "lit": False, "ever_lit": True}])
        self.assertEqual(snap(run(sc, press(0, "interact"), ticks=2), 1)["player"]["capacity"], 20)

    def test_preset_lit_lanterns_do_not_count(self):
        # two scenario-preset lit lanterns: successful_lights stays 0 -> capacity 10: carried 9 + 3 motes -> 10
        sc = base(player={"pos": [0, 0, 0], "carried": 9}, motes=[[0, 0, 0]] * 3, lanterns=[lit("L1"), lit("L2")])
        L = run(sc, ticks=3)
        self.assertEqual(snap(L, 3)["player"]["capacity"], 10)
        self.assertEqual((snap(L, 3)["player"]["carried"], snap(L, 3)["motes_active"]), (10, 2))

    def test_refuel_does_not_count(self):
        sc = base(player={"pos": [0, 0, 0], "carried": 4},
                  lanterns=[lit("L1", 40.0, pos=[0, 0, 1.0])])
        L = run(sc, press(0, "interact"), ticks=3)
        self.assertTrue(events(L, "refuel"))
        self.assertEqual(snap(L, 3)["player"]["capacity"], 10)


if __name__ == "__main__":
    unittest.main()
