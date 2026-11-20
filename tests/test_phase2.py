"""Black-box tests for every new Ticket-02 rule (contract v1.1), updated for Ticket-03 (contract v1.2).

Ticket-03 edits carry a `# Ticket-03: ...` comment and are listed in tests/CHANGES-phase-3.md.

Conventions used in the hand calculations (ticket + docs/notes/phase-2-design.md section 2):
- An input frame at tick k is applied by the step that produces tick k+1 (events carry tick k+1).
- Counters are whole ticks and are decremented in step 2. An effect of n ticks set at tick t lasts
  t .. t+n-1 and is over at t+n (a scenario counter set "at tick 0" lasts 0 .. n-1).
- Walking = 6 m/s = 0.1 m/tick; dash = 14 m/s = 0.2333 m/tick; shade chase = 4/60 m/tick.
- Angles: x = r*cos(a), z = r*sin(a) (consistent with the ticket's "tier 1 is z > 0 and holds 20..160 deg").
"""
import json
import math
import os
import tempfile
import time
import unittest

from blackbox import (ROOT, base, cli, dropped, drifter, dxz, ev_ticks, events, game_events, last_snap,
                      press, run, shade, snap, PER_FLAME, PER_LANTERN, PER_MOTE, PER_STUN)

START3 = [0.0, 0.0, -30.0]  # night 3 start: design-doc decision (ticket gives none; tower is at the centre)


def r3(v):
    return round(v, 3)


# --------------------------------------------------------------------------- contract
class ContractV11(unittest.TestCase):
    STANDARD = {
        "player_speed": 6.0, "carry_capacity": 10, "lantern_cost": 10, "lantern_count_night1": 5,
        "pickup_radius": 1.0, "interact_radius": 2.0, "pulse_cost": 3, "pulse_radius": 5.0,
        # Ticket-03: night durations 240 / 270 / 300 s (were 300 / 330 / 360)
        "night1_duration_s": 240, "night2_duration_s": 270, "night3_duration_s": 300,
        "flames": 3, "invuln_s": 1.5, "hit_drop_ratio": 0.5, "pulse_stun_s": 2.0, "pulse_push_m": 4.0,
        "pulse_cooldown_s": 3.0, "safe_radius": 6.0, "shade_speed": 4.0, "shade_hit_radius": 1.0,
        "fall_enabled": True, "dash_speed": 14.0, "dash_duration_s": 0.2, "dash_cooldown_s": 1.5,
        # Ticket-03: the old score table (per_mote 10, per_second_left 2) was replaced; the full v1.2 tuning
        # (fuel_max ... capacity_max, score keys) is checked in test_phase3.py.
    }

    def test_version_tuning_equal_and_standard(self):
        from game.sim import TUNING
        with open(os.path.join(ROOT, "game.contract.json"), encoding="utf-8") as f:
            c = json.load(f)
        self.assertEqual(c["contract_version"], "1.3")   # Ticket-04: contract v1.3 (was 1.2 in Ticket-03)
        self.assertEqual(c["tuning"], TUNING)
        for k, v in self.STANDARD.items():
            self.assertIn(k, c["tuning"], k)
            self.assertEqual(c["tuning"][k], v, k)

    def test_night_flag_1_2_3_and_reject_others(self):
        for n in (1, 2, 3):
            L = run(None, ticks=0, night=n)
            self.assertEqual(L[0]["night"], n)
        out = os.path.join(tempfile.mkdtemp(), "o.jsonl")
        for bad in ("0", "4"):
            r = cli("--seed", "1", "--night", bad, "--ticks", "1", "--out", out)
            self.assertNotEqual(r.returncode, 0, bad)

    def test_night_start_event_right_after_snapshot0(self):
        for n in (1, 2, 3):
            L = run(base(n), ticks=1, night=n)
            self.assertEqual(L[0]["type"], "snapshot")
            self.assertEqual(L[1], {"type": "event", "tick": 0, "name": "night_start", "data": {"night": n}})

    def test_night_defaults_from_map(self):
        lan = {1: [(0, 0, 25), (23.8, 0, 7.7), (14.7, 0, -20.2), (-14.7, 0, -20.2), (-23.8, 0, 7.7)],
               2: [(0, 0, 20), (17, 0, -10), (-17, 0, -10), (70, 0, 20), (87, 0, -10), (53, 0, -10)],
               3: [(0, 6, 6), (18, 3, 10), (-18, 3, 10), (35, 0, -10), (-35, 0, -10), (20, 0, -35), (-20, 0, -35)]}
        dur = {1: 240.0, 2: 270.0, 3: 300.0}   # Ticket-03: 240 / 270 / 300 s (were 300 / 330 / 360)
        start = {1: [0.0, 0.0, 0.0], 2: [0.0, 0.0, 0.0], 3: START3}
        charms = {1: [], 2: ["C1"], 3: ["C1", "C2"]}
        for n in (1, 2, 3):
            s = run(None, ticks=0, night=n)[0]
            self.assertEqual([l["id"] for l in s["lanterns"]], [f"L{i + 1}" for i in range(len(lan[n]))])
            self.assertEqual([l["pos"] for l in s["lanterns"]], [[float(c) for c in p] for p in lan[n]])
            self.assertTrue(all(not l["lit"] and l["deposited"] == 0 for l in s["lanterns"]))
            self.assertEqual(s["time_left_s"], dur[n])
            self.assertEqual(s["player"]["pos"], start[n])
            self.assertEqual(s["player"]["flames"], 3)
            self.assertEqual([c["id"] for c in s["charms"]], charms[n])
            self.assertTrue(all(c["available"] for c in s["charms"]))
            self.assertEqual(s["drifters"], [])
            self.assertEqual(s["shades"], [])
            self.assertEqual(s["wind"], {"active": False, "dir_deg": 0})


class SnapshotV11(unittest.TestCase):
    def test_fields_and_initial_values(self):
        L = run(base(2, motes=[[5, 0, 5]], charms=[{"id": "C1", "pos": [35, 0, 0]}],
                     drifters=[{"id": "D1", "pos": [10, 1.5, 0]}]), ticks=0, night=2)
        s = L[0]
        for k in ("type", "tick", "sim_tick", "state", "time_left_s", "score", "player", "lanterns", "shades",
                  "motes_active", "night", "wind", "motes", "drifters", "charms"):
            self.assertIn(k, s)
        self.assertEqual(set(s["wind"]), {"active", "dir_deg"})
        p = s["player"]
        self.assertEqual(p["vel"], [0.0, 0.0, 0.0])
        self.assertIs(p["grounded"], True)
        self.assertIs(p["invuln"], False)
        self.assertEqual((p["dash_cd_s"], p["pulse_cd_s"], p["charm_s"]), (0.0, 0.0, 0.0))
        m = s["motes"][0]
        self.assertEqual(set(m), {"id", "pos", "kind", "ttl_s"})
        self.assertEqual((m["pos"], m["kind"], m["ttl_s"]), ([5.0, 0.0, 5.0], "random", None))
        d = s["drifters"][0]
        self.assertEqual(set(d), {"id", "pos", "state", "stolen"})
        self.assertEqual((d["id"], d["state"], d["stolen"]), ("D1", "idle", 0))
        c = s["charms"][0]
        self.assertEqual(set(c), {"id", "available", "respawn_s"})
        self.assertEqual((c["id"], c["available"]), ("C1", True))

    def test_vel_and_grounded(self):
        L = run(base(), [{"tick": 0, "move": [0, 1]}], ticks=10)
        self.assertEqual(snap(L, 10)["player"]["vel"], [0.0, 0.0, 6.0])
        self.assertIs(snap(L, 10)["player"]["grounded"], True)
        L = run(base(), [{"tick": 0, "jump": True}], ticks=5)
        self.assertIs(snap(L, 5)["player"]["grounded"], False)
        self.assertGreater(snap(L, 5)["player"]["vel"][1], 0)

    def test_scenario_player_counters(self):
        # set at tick 0 with n ticks -> active 0..n-1, over at n
        sc = base(player={"pos": [0, 0, 0], "carried": 3, "invuln_ticks": 30, "dash_cd_ticks": 30,
                          "pulse_cd_ticks": 30, "charm_ticks": 600})
        L = run(sc, ticks=60)
        self.assertIs(snap(L, 0)["player"]["invuln"], True)
        self.assertIs(snap(L, 29)["player"]["invuln"], True)
        self.assertIs(snap(L, 30)["player"]["invuln"], False)
        self.assertEqual(snap(L, 0)["player"]["dash_cd_s"], 0.5)        # 30/60
        self.assertEqual(snap(L, 0)["player"]["pulse_cd_s"], 0.5)
        self.assertEqual(snap(L, 0)["player"]["charm_s"], 10.0)         # 600/60
        self.assertEqual(snap(L, 60)["player"]["charm_s"], 9.0)         # 540/60
        # press at input 28 -> tick 29, 1 tick of cooldown left -> nothing; input 29 -> tick 30 -> ok
        sc2 = base(player={"pos": [0, 0, 0], "carried": 3, "dash_cd_ticks": 30, "pulse_cd_ticks": 30})
        self.assertFalse(events(run(sc2, press(28, "dash"), ticks=31), "dash"))
        self.assertEqual(ev_ticks(run(sc2, press(29, "dash"), ticks=31), "dash"), [30])
        self.assertEqual(snap(run(sc2, press(28, "pulse"), ticks=31), 31)["player"]["carried"], 3)
        self.assertEqual(snap(run(sc2, press(29, "pulse"), ticks=31), 31)["player"]["carried"], 0)


# --------------------------------------------------------------------------- dash
class Dash(unittest.TestCase):
    def test_idle_dash_uses_facing_12_ticks_2_8m(self):
        # Facing starts +Z. Dash ticks 1..12 at 14/60: tick 6 z=1.4, tick 12 z=2.8, then stops (no input).
        L = run(base(), press(0, "dash"), ticks=20)
        self.assertEqual(events(L, "dash"), [{"type": "event", "tick": 1, "name": "dash", "data": {}}])
        self.assertEqual(snap(L, 6)["player"]["pos"], [0.0, 0.0, 1.4])
        self.assertEqual(snap(L, 12)["player"]["pos"], [0.0, 0.0, 2.8])
        self.assertEqual(snap(L, 13)["player"]["pos"], [0.0, 0.0, 2.8])
        self.assertEqual(snap(L, 20)["player"]["pos"], [0.0, 0.0, 2.8])

    def test_cooldown_90_from_start(self):
        # dash at tick 1 -> cooldown 90 -> next dash possible at tick 91 (input 90), not at tick 90 (input 89)
        first = press(0, "dash")
        L = run(base(), first + press(89, "dash"), ticks=100)
        self.assertEqual(ev_ticks(L, "dash"), [1])
        self.assertEqual(snap(L, 1)["player"]["dash_cd_s"], 1.5)
        self.assertEqual(snap(L, 31)["player"]["dash_cd_s"], 1.0)     # (90-30)/60
        L = run(base(), first + press(50, "dash") + press(90, "dash"), ticks=100)
        self.assertEqual(ev_ticks(L, "dash"), [1, 91])

    def test_direction_is_input_and_input_ignored_while_dashing(self):
        # yaw 90 + move [0,1] = world +X. Dash ticks 1..12 -> x 2.8. At input 5 the stick turns to world +Z
        # (yaw 90, move [-1,0]) but that is ignored until the dash ends; ticks 13..22 walk +Z 1.0 m.
        fr = [{"tick": 0, "move": [0, 1], "cam_yaw_deg": 90, "dash": True}, {"tick": 1, "dash": False},
              {"tick": 5, "move": [-1, 0]}]
        L = run(base(), fr, ticks=22)
        self.assertEqual(snap(L, 12)["player"]["pos"], [2.8, 0.0, 0.0])
        self.assertEqual(snap(L, 22)["player"]["pos"], [2.8, 0.0, 1.0])

    def test_facing_follows_movement(self):
        # walk +X 10 ticks (x=1.0), stop and dash at input 10 -> dash ticks 11..22 along facing +X -> x=3.8
        fr = [{"tick": 0, "move": [0, 1], "cam_yaw_deg": 90}, {"tick": 10, "move": [0, 0], "dash": True}]
        L = run(base(), fr, ticks=30)
        self.assertEqual(ev_ticks(L, "dash"), [11])
        self.assertEqual(snap(L, 22)["player"]["pos"], [3.8, 0.0, 0.0])

    def test_air_dash_keeps_altitude(self):
        fr = [{"tick": 0, "jump": True}, {"tick": 1, "jump": False}] + press(10, "dash")
        L = run(base(), fr, ticks=150)
        y11, y22 = snap(L, 11)["player"]["pos"][1], snap(L, 22)["player"]["pos"][1]
        self.assertGreater(y11, 0.5)
        self.assertEqual(y11, y22)                      # dash ticks 11..22: vy = 0, no gravity
        self.assertEqual(snap(L, 16)["player"]["vel"][1], 0.0)
        self.assertEqual(snap(L, 22)["player"]["pos"][2], 2.8)
        self.assertEqual(snap(L, 150)["player"]["pos"][1], 0.0)   # lands afterwards

    def test_not_invulnerable_while_dashing(self):
        # shade (0,1,1.5) chases; tick 2: player z 0.4667, shade 1.5-2/15 = 1.3667 -> 0.9 <= 1 -> hit
        L = run(base(shades=[{"id": "S1", "pos": [0, 1, 1.5]}]), press(0, "dash"), ticks=5)
        self.assertEqual(ev_ticks(L, "player_hit"), [2])


# --------------------------------------------------------------------------- motes
class Pickup(unittest.TestCase):
    def test_height_rule_dy_1_5(self):
        L = run(base(motes=[[0.5, 1.5, 0], [-0.5, 1.51, 0]]), ticks=1)
        self.assertEqual([e["data"] for e in events(L, "mote_picked")], [{"carried": 1}])
        self.assertEqual([m["pos"] for m in snap(L, 1)["motes"]], [[-0.5, 1.51, 0.0]])

    def test_pickup_scores_nothing(self):
        L = run(base(motes=[[0, 0, 0]]), ticks=2)
        self.assertEqual(snap(L, 2)["player"]["carried"], 1)
        self.assertEqual(L[-1]["score"], 0)


class DroppedMotes(unittest.TestCase):
    HIT = {"id": "S1", "pos": [0.5, 1, 0]}   # chases, 0.4333 m after its first step -> hit at tick 1

    def test_count_is_floor_half(self):
        for carried, drop in ((10, 5), (5, 2), (1, 0)):
            L = run(base(player={"pos": [0, 0, 0], "carried": carried}, shades=[self.HIT]), ticks=1)
            self.assertEqual(events(L, "player_hit")[0]["data"], {"by": "shade", "flames": 2, "dropped": drop})
            self.assertEqual(snap(L, 1)["player"]["carried"], carried - drop)
            self.assertEqual(len(dropped(snap(L, 1))), drop)

    def protected(self):
        # hit at tick 1 (drop 5 of 10); input 1 lights L1 (5 + 5 = 10) at tick 2, the shade is expelled
        # and then held 6 m from L1 = >= 4.5 m from the player, so no more hits.
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, shades=[self.HIT],
                  lanterns=[{"id": "L1", "pos": [0, 0, 1.5], "deposited": 5}])
        return run(sc, press(1, "interact"), ticks=481)

    def test_ring_ttl_and_expiry(self):
        L = self.protected()
        self.assertEqual(len(events(L, "player_hit")), 1)
        d = dropped(snap(L, 1))
        self.assertEqual(len(d), 5)
        for m in d:
            self.assertTrue(1.5 - 2e-3 <= dxz(m["pos"], [0, 0, 0]) <= 2.5 + 2e-3, m)
            self.assertEqual(m["pos"][1], 0.0)          # ground height of island 1
            self.assertEqual(m["ttl_s"], 8.0)           # 480/60
        self.assertEqual({m["ttl_s"] for m in dropped(snap(L, 2))}, {7.983})   # 479/60
        self.assertEqual({m["ttl_s"] for m in dropped(snap(L, 480))}, {0.017})  # 1/60, last tick alive
        self.assertEqual(dropped(snap(L, 481)), [])

    def test_invuln_90_after_hit(self):
        L = self.protected()
        self.assertIs(snap(L, 1)["player"]["invuln"], True)
        self.assertIs(snap(L, 90)["player"]["invuln"], True)
        self.assertIs(snap(L, 91)["player"]["invuln"], False)

    def test_dropped_mote_can_be_picked_up(self):
        sc = base(player={"pos": [0, 0, 0], "carried": 5}, shades=[self.HIT])
        m = dropped(snap(run(sc, ticks=1), 1))[0]
        d = dxz(m["pos"], [0, 0, 0])
        mv = [m["pos"][0] / d, m["pos"][2] / d]          # yaw 0: move [x, z] = world direction
        L = run(sc, [{"tick": 1, "move": mv}], ticks=40)
        # walking from tick 2 at 0.1 m/tick: in range after ceil((d-1)/0.1) ticks (+-1: d read rounded)
        k = math.ceil((d - 1.0) / 0.1)
        got = events(L, "mote_picked")
        self.assertTrue(got)
        self.assertEqual(got[0]["data"], {"carried": 4})
        self.assertTrue(max(2, k) <= got[0]["tick"] <= k + 2, (got[0]["tick"], k))


# --------------------------------------------------------------------------- safe zone
class SafeZone(unittest.TestCase):
    def test_lit_lantern_expels_shade_harmlessly(self):
        # L1 lit at tick 1 (step 5) while the shade is 0.5 m away inside 6 m: pushed (6-0.5)/30 per tick
        # along +X for <= 30 ticks, harmless meanwhile, then held at the 6 m edge: [6,1,0].
        sc = base(player={"pos": [0, 0, 0], "carried": 10}, shades=[{"id": "S1", "pos": [0.5, 1, 0]}],
                  lanterns=[{"id": "L1", "pos": [0, 0, 0]}])
        L = run(sc, press(0, "interact"), ticks=600)
        self.assertEqual(ev_ticks(L, "lantern_lit"), [1])
        self.assertFalse(events(L, "player_hit"))
        xs = [shade(snap(L, t), "S1")["pos"][0] for t in range(1, 32)]
        self.assertEqual(xs, sorted(xs))                # only ever pushed outward
        self.assertEqual(shade(snap(L, 31), "S1")["pos"], [6.0, 1.0, 0.0])
        self.assertEqual(shade(snap(L, 600), "S1")["pos"], [6.0, 1.0, 0.0])
        # Ticket-03: +5 per mote now (the PER_MOTE constant changed): 10 * 5 + 100 = 150 (was 200)
        self.assertEqual(L[-1]["score"], 10 * PER_MOTE + PER_LANTERN)
        self.assertEqual(10 * PER_MOTE + PER_LANTERN, 150)


# --------------------------------------------------------------------------- pulse
class PulseV11(unittest.TestCase):
    def test_radius_is_3d_from_feet_plus_0_8(self):
        # centre (0,0.8,0). S1 (4.99,1,0): sqrt(24.9001+0.04)=4.994 hit. S2 (0,1,-5): sqrt(25.04)=5.004 miss
        # (a 2D check would hit S2).
        sc = base(player={"pos": [0, 0, 0], "carried": 5},
                  shades=[{"id": "S1", "pos": [4.99, 1, 0]}, {"id": "S2", "pos": [0, 1, -5.0]}])
        L = run(sc, press(0, "pulse"), ticks=1)
        self.assertEqual(events(L, "pulse")[0]["data"], {"stunned_ids": ["S1"]})
        # player in the air at y=3 -> centre y 3.8 (3.794 if gravity already applied):
        # S1 (4,1,0): sqrt(16+7.84)=4.88 hit; S2 (4.5,1,0) [XZ 4.5 < 5]: sqrt(20.25+7.84)=5.30 miss
        sc = base(player={"pos": [0, 3, 0], "carried": 5},
                  shades=[{"id": "S1", "pos": [4, 1, 0]}, {"id": "S2", "pos": [0, 1, 4.5]}])
        L = run(sc, press(0, "pulse"), ticks=1)
        self.assertEqual(events(L, "pulse")[0]["data"], {"stunned_ids": ["S1"]})

    def test_cost_3_needs_3(self):
        L = run(base(player={"pos": [0, 0, 0], "carried": 2}), press(0, "pulse"), ticks=2)
        self.assertFalse(events(L, "pulse"))
        self.assertEqual((snap(L, 2)["player"]["carried"], snap(L, 2)["player"]["pulse_cd_s"]), (2, 0.0))
        L = run(base(player={"pos": [0, 0, 0], "carried": 3}), press(0, "pulse"), ticks=2)
        self.assertEqual(snap(L, 1)["player"]["carried"], 0)
        self.assertEqual(snap(L, 1)["player"]["pulse_cd_s"], 3.0)     # 180/60

    def test_stun_120_exact_push_4m_over_15_ticks(self):
        # S1 (3,1,0) stunned ticks 1..120; push 4/15 m per tick on ticks 1..15 -> 3.267 .. 7.0
        # tick 121: chases again, 7 - 1/15 = 6.933
        sc = base(player={"pos": [0, 0, 0], "carried": 3}, shades=[{"id": "S1", "pos": [3, 1, 0]}])
        L = run(sc, press(0, "pulse"), ticks=121)
        x = lambda t: shade(snap(L, t), "S1")["pos"][0]
        self.assertEqual(x(1), r3(3 + 4 / 15))
        self.assertEqual(x(14), r3(3 + 14 * 4 / 15))
        self.assertEqual(x(15), 7.0)
        self.assertEqual(x(120), 7.0)
        self.assertEqual(shade(snap(L, 120), "S1")["state"], "stunned")
        # Ticket-03: stun end -> wander; S1 is 7 m <= 12 m from the player so the wander->chase check fires in the
        # same tick: still "chase" at 121 and it moves at once.
        self.assertEqual(shade(snap(L, 121), "S1")["state"], "chase")
        self.assertEqual(x(121), r3(7 - 1 / 15))
        self.assertEqual(snap(L, 1)["score"], PER_STUN)

    def test_same_spot_pushes_plus_x_and_no_hit(self):
        sc = base(player={"pos": [0, 0, 0], "carried": 3}, shades=[{"id": "S1", "pos": [0, 1, 0]}])
        L = run(sc, press(0, "pulse"), ticks=120)
        self.assertEqual(events(L, "pulse")[0]["data"], {"stunned_ids": ["S1"]})
        self.assertEqual(shade(snap(L, 15), "S1")["pos"], [4.0, 1.0, 0.0])
        self.assertFalse(events(L, "player_hit"))

    def test_cooldown_180(self):
        # S1 stunned at 1, chases from 121 (7 m away), at tick 181 it is 7-60/15 = 3 m away -> hit again
        sc = base(player={"pos": [0, 0, 0], "carried": 6}, shades=[{"id": "S1", "pos": [3, 1, 0]}])
        L = run(sc, press(0, "pulse") + press(179, "pulse"), ticks=182)
        self.assertEqual(ev_ticks(L, "pulse"), [1])
        self.assertEqual(snap(L, 181)["player"]["carried"], 3)
        L = run(sc, press(0, "pulse") + press(180, "pulse"), ticks=182)
        self.assertEqual(ev_ticks(L, "pulse"), [1, 181])
        self.assertEqual(L[-1]["score"], 2 * PER_STUN)

    def test_repulse_refreshes_stun_and_scores_stunned_shade(self):
        # S1 already stunned with 50 ticks left: pulse at tick 1 refreshes to 120 (stunned 1..120), +5,
        # pushed again 4 m -> 7.0 by tick 15
        sc = base(player={"pos": [0, 0, 0], "carried": 3},
                  shades=[{"id": "S1", "pos": [3, 1, 0], "state": "stunned", "state_ticks_left": 50}])
        L = run(sc, press(0, "pulse"), ticks=121)
        self.assertEqual(events(L, "pulse")[0]["data"], {"stunned_ids": ["S1"]})
        self.assertEqual(L[-1]["score"], PER_STUN)
        self.assertEqual(shade(snap(L, 15), "S1")["pos"][0], 7.0)
        self.assertEqual(shade(snap(L, 60), "S1")["state"], "stunned")
        self.assertEqual(shade(snap(L, 120), "S1")["state"], "stunned")
        self.assertEqual(shade(snap(L, 121), "S1")["state"], "chase")

    def test_two_shades_score_each(self):
        sc = base(player={"pos": [0, 0, 0], "carried": 3},
                  shades=[{"id": "S1", "pos": [2, 1, 0]}, {"id": "S2", "pos": [-2, 1, 0]}])
        L = run(sc, press(0, "pulse"), ticks=1)
        self.assertEqual(events(L, "pulse")[0]["data"], {"stunned_ids": ["S1", "S2"]})
        self.assertEqual(L[-1]["score"], 2 * PER_STUN)


# --------------------------------------------------------------------------- shades
class ShadesV11(unittest.TestCase):
    def test_scenario_state_ticks_left(self):
        # stunned 50 set at tick 0 -> stunned 0..49, moves at 50: 3 - 1/15 = 2.933
        sc = base(shades=[{"id": "S1", "pos": [3, 1, 0], "state": "stunned", "state_ticks_left": 50}])
        L = run(sc, ticks=50)
        self.assertEqual((shade(snap(L, 49), "S1")["state"], shade(snap(L, 49), "S1")["pos"][0]), ("stunned", 3.0))
        self.assertEqual((shade(snap(L, 50), "S1")["state"], shade(snap(L, 50), "S1")["pos"][0]),
                         ("chase", r3(3 - 1 / 15)))

    def test_detect_12(self):
        L = run(base(shades=[{"id": "S1", "pos": [12, 1, 0]}, {"id": "S2", "pos": [0, 1, -12.5]}]), ticks=1)
        self.assertEqual(shade(snap(L, 0), "S1")["state"], "wander")      # scenario default state
        self.assertEqual(shade(snap(L, 1), "S1")["state"], "chase")
        self.assertEqual(shade(snap(L, 1), "S2")["state"], "wander")

    def test_give_up_beyond_18(self):
        # player runs -X at 0.1/tick, shade (17.05,1,0) chasing at 1/15 per tick. Check at tick k (player
        # already moved, shade not yet): d = 17.05 + 0.1k - (k-1)/15.
        # k=26: 17.983 <= 18 chase; k=27: 18.017 > 18 -> wander.
        sc = base(shades=[{"id": "S1", "pos": [17.05, 1, 0], "state": "chase"}])
        L = run(sc, [{"tick": 0, "move": [-1, 0]}], ticks=27)
        self.assertEqual(shade(snap(L, 26), "S1")["state"], "chase")
        self.assertEqual(shade(snap(L, 27), "S1")["state"], "wander")

    def test_speed_night3_is_4_5(self):
        # night 3 start (0,0,-30); shade at (0,1,-20) is 10 m away -> chase, 60 ticks * 4.5/60 = 4.5 m
        L = run(base(3, shades=[{"id": "S1", "pos": [0, 1, -20]}]), ticks=60, night=3)
        self.assertEqual(shade(snap(L, 60), "S1")["pos"], [0.0, 1.0, -24.5])

    def test_hit_needs_dy_1_5(self):
        # player at y=2.5: dy = 1.5 -> hit at tick 1
        L = run(base(player={"pos": [0, 2.5, 0]}, shades=[{"id": "S1", "pos": [0.5, 1, 0]}]), ticks=1)
        self.assertEqual(ev_ticks(L, "player_hit"), [1])
        # player at y=2.6 falling (Euler as Phase 1: y_n = 2.6 - n(n-1)/360): n=6 2.5167 (dy 1.517 no),
        # n=7 2.4833 (dy 1.483) -> first hit at tick 7
        L = run(base(player={"pos": [0, 2.6, 0]}, shades=[{"id": "S1", "pos": [0.5, 1, 0]}]), ticks=10)
        self.assertEqual(ev_ticks(L, "player_hit"), [7])

    def test_one_flame_per_tick_lowest_id_first(self):
        # both touch at tick 1; only one flame lost; S9 < S10 numerically, so S9 hits and recoils
        sc = base(shades=[{"id": "S10", "pos": [0.5, 1, 0]}, {"id": "S9", "pos": [-0.5, 1, 0]}])
        L = run(sc, ticks=1)
        self.assertEqual([e["data"]["flames"] for e in events(L, "player_hit")], [2])
        s = snap(L, 1)
        self.assertEqual((shade(s, "S9")["state"], shade(s, "S10")["state"]), ("recoil", "chase"))

    def test_recoil_60_ticks_2m(self):
        # shade steps to 0.4333 then hits at tick 1; recoil ticks 1..60 moving 2 m away (+X) -> ~2.43
        # (+-1 recoil step of 2/60 depending on whether the hit tick itself moves); chase again at 61
        L = run(base(shades=[{"id": "S1", "pos": [0.5, 1, 0]}]), ticks=61)
        self.assertEqual(shade(snap(L, 1), "S1")["state"], "recoil")
        self.assertEqual(shade(snap(L, 60), "S1")["state"], "recoil")
        self.assertEqual(shade(snap(L, 61), "S1")["state"], "chase")
        self.assertAlmostEqual(shade(snap(L, 60), "S1")["pos"][0], 0.5 - 1 / 15 + 2, delta=0.04)

    def test_touch_while_invulnerable_does_nothing(self):
        L = run(base(player={"pos": [0, 0, 0], "invuln_ticks": 100}, shades=[{"id": "S1", "pos": [0.5, 1, 0]}]),
                ticks=99)
        self.assertFalse(events(L, "player_hit"))
        self.assertEqual(shade(snap(L, 99), "S1")["state"], "chase")


class Schedules(unittest.TestCase):
    def guarded(self, night, start):
        sc = {"random_motes": False, "lanterns": [{"id": "L1", "pos": start, "lit": True}]}
        if night != 1:
            sc.update({"random_drifters": False, "wind_enabled": False})
        return sc

    def spawns(self, night, start, ticks):
        L = run(self.guarded(night, start), ticks=ticks, every=ticks, night=night)
        self.assertFalse(events(L, "player_hit"))
        return [(e["tick"], e["data"]["id"]) for e in events(L, "shade_spawned")]

    def test_shade_schedule_night1(self):
        # 2 at 300, then 300+480k: 780, 1260, 1740, 2220 -> 6 = max, 2700 skipped
        self.assertEqual(self.spawns(1, [0, 0, 0], 2800),
                         [(300, "S1"), (300, "S2"), (780, "S3"), (1260, "S4"), (1740, "S5"), (2220, "S6")])

    def test_shade_schedule_night2(self):
        # 300+420k up to 8 shades
        self.assertEqual(self.spawns(2, [0, 0, 0], 3000),
                         [(300, "S1"), (300, "S2"), (720, "S3"), (1140, "S4"), (1560, "S5"), (1980, "S6"),
                          (2400, "S7"), (2820, "S8")])

    def test_shade_schedule_night3(self):
        # 300+360k up to 10 shades
        self.assertEqual(self.spawns(3, START3, 3300),
                         [(300, "S1"), (300, "S2"), (660, "S3"), (1020, "S4"), (1380, "S5"), (1740, "S6"),
                          (2100, "S7"), (2460, "S8"), (2820, "S9"), (3180, "S10")])

    def test_spawn_points_states_and_id_skip(self):
        sc = self.guarded(1, [0, 0, 0])
        sc["shades"] = [{"id": "S1", "pos": [-30, 1, 0]}]
        L = run(sc, ticks=360)
        self.assertEqual([e["data"]["id"] for e in events(L, "shade_spawned")], ["S2", "S3"])
        s300 = snap(L, 300)
        for sid in ("S2", "S3"):
            p = shade(s300, sid)["pos"]
            self.assertAlmostEqual(math.hypot(p[0], p[2]), 37.0, delta=2e-3)    # 12 points on r=37
            a = math.degrees(math.atan2(p[2], p[0])) % 360
            self.assertAlmostEqual((a - 15) % 30, 0, delta=0.01)                  # at 15, 45, 75 ...
            self.assertEqual(shade(s300, sid)["state"], "spawning")
            # Review: spawning 60 -> 1 tick
            self.assertEqual(shade(snap(L, 301), sid)["state"], "wander")         # spawning only at 300
            self.assertEqual(shade(snap(L, 360), sid)["state"], "wander")         # 37 m > 12 m

    @staticmethod
    def points(night):
        P = []
        ring = lambda r, angs, y=0.0, cx=0.0: [(cx + r * math.cos(math.radians(a)), y, r * math.sin(math.radians(a)))
                                               for a in angs]
        if night == 1:
            P = ring(12, range(0, 360, 45)) + ring(33, [i * 22.5 for i in range(16)])
        elif night == 2:
            for cx in (0.0, 70.0):
                P += ring(10, (0, 90, 180, 270), cx=cx) + ring(22, range(0, 360, 45), cx=cx)
        else:
            P = ring(34, range(0, 360, 20)) + ring(18, range(20, 161, 20), 3.0) + ring(5, (45, 135, 225, 315), 6.0)
        return P

    def check_motes(self, s, night):
        P = self.points(night)
        pos = [tuple(m["pos"]) for m in s["motes"]]
        self.assertEqual(len(set(pos)), len(pos), "two motes on one point")
        for m in s["motes"]:
            self.assertEqual((m["kind"], m["ttl_s"]), ("random", None))
            self.assertTrue(any(all(abs(a - b) <= 2e-3 for a, b in zip(m["pos"], p)) for p in P), m["pos"])

    def test_mote_schedule_night1(self):
        # 24 points: 20 at start, +1 at 240, 480, 720, 960 -> 24, then no free point: stays 24
        L = run({"random_shades": False}, ticks=1200)
        self.check_motes(snap(L, 0), 1)
        counts = {t: snap(L, t)["motes_active"] for t in (0, 239, 240, 479, 480, 960, 1200)}
        self.assertEqual(counts, {0: 20, 239: 20, 240: 21, 479: 21, 480: 22, 960: 24, 1200: 24})
        self.check_motes(snap(L, 960), 1)

    def test_mote_schedule_night2(self):
        L = run({"random_shades": False, "random_drifters": False}, ticks=960, every=240, night=2)
        self.check_motes(snap(L, 0), 2)
        self.assertEqual([snap(L, t)["motes_active"] for t in (0, 240, 960)], [20, 21, 24])

    def test_mote_schedule_night3_cap_30(self):
        # 30 points: 20 + 1 per 240 ticks -> 30 at 2400, cap holds at 2640
        L = run({"random_shades": False, "random_drifters": False, "wind_enabled": False},
                ticks=2640, every=240, night=3)
        self.check_motes(snap(L, 0), 3)
        self.assertEqual([snap(L, t)["motes_active"] for t in (0, 240, 2160, 2400, 2640)], [20, 21, 29, 30, 30])
        self.check_motes(snap(L, 2400), 3)


# --------------------------------------------------------------------------- fall
class Fall(unittest.TestCase):
    OFF = [50, -10.5, 0]   # over the cloud sea, already below -10 -> falls on tick 1 whatever the integrator

    def test_fall_loses_flame_and_all_motes(self):
        L = run(base(player={"pos": self.OFF, "carried": 4}), ticks=1)
        self.assertEqual(events(L, "player_hit"), [{"type": "event", "tick": 1, "name": "player_hit",
                                                    "data": {"by": "fall", "flames": 2, "dropped": 0, "lost": 4}}])
        self.assertEqual(snap(L, 1)["player"]["carried"], 0)

    def test_wait_60_then_respawn_at_start_with_invuln(self):
        # fall at 1 -> waiting 1..60 -> respawn at tick 61 at (0,0,0), vel 0, invuln 61..150
        L = run(base(player={"pos": self.OFF, "carried": 4}), ticks=151)
        self.assertNotEqual(snap(L, 60)["player"]["pos"], [0.0, 0.0, 0.0])
        p = snap(L, 61)["player"]
        self.assertEqual((p["pos"], p["vel"], p["invuln"]), ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], True))
        self.assertIs(snap(L, 150)["player"]["invuln"], True)
        self.assertIs(snap(L, 151)["player"]["invuln"], False)
        self.assertEqual(len(events(L, "player_hit")), 1)            # exactly once per fall

    def test_no_pickup_while_waiting(self):
        L = run(base(player={"pos": self.OFF}, motes=[[50, -10.5, 0.5]]), ticks=60)
        self.assertFalse(events(L, "mote_picked"))

    def test_respawn_invuln_then_shade_hits_at_151(self):
        # shade stunned 0..99 next to the start, chases from 100, but the player is invulnerable 61..150
        sc = base(player={"pos": self.OFF, "carried": 4},
                  shades=[{"id": "S1", "pos": [0.5, 1, 0], "state": "stunned", "state_ticks_left": 100}])
        L = run(sc, ticks=200)
        self.assertEqual([(e["tick"], e["data"]["by"]) for e in events(L, "player_hit")], [(1, "fall"), (151, "shade")])

    def test_fall_ignores_invuln(self):
        L = run(base(player={"pos": self.OFF, "invuln_ticks": 300}), ticks=1)
        self.assertEqual(ev_ticks(L, "player_hit"), [1])

    def test_fall_on_last_flame_loses_now(self):
        L = run(base(player={"pos": self.OFF, "flames": 1, "carried": 2}), ticks=100)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(1, "player_hit", {"by": "fall", "flames": 0, "dropped": 0, "lost": 2}),
                          (1, "game_over", {"result": "lost", "reason": "no_flames"})])
        self.assertEqual(L[-1], {"type": "end", "ticks": 1, "state": "lost", "score": 0})

    def test_walk_off_edge(self):
        # x = 39.55 + 0.1k: tick 4 at 39.95 (land), tick 5 at 40.05 (sea). Euler from that tick:
        # y_n = -n(n-1)/360 < -10 first at n = 61 -> tick 65 (66 if gravity starts the tick after).
        L = run(base(player={"pos": [39.55, 0, 0]}), [{"tick": 0, "move": [1, 0]}], ticks=100)
        hit = events(L, "player_hit")
        self.assertEqual(hit[0]["data"]["by"], "fall")
        self.assertIn(hit[0]["tick"], (65, 66))


# --------------------------------------------------------------------------- win / lose
class WinLose(unittest.TestCase):
    LIT = [{"id": f"L{i}", "lit": True} for i in range(2, 6)]

    # Ticket-03: win only at dawn with >= ceil(0.6 * N) lit lanterns; all_lit and the early win are gone.
    # The three Ticket-02 tests below were rewritten around the dawn tick (see tests/CHANGES-phase-3.md).

    def test_win_on_the_dawn_tick(self):
        # Ticket-03: was "light the last lantern on tick 60 -> won all_lit (350)". Now: L2..L5 preset lit (fuel 100),
        # 1 s = 60 ticks, L1 lit by deposit on tick 60 (the dawn tick) -> won dawn_survived, judged after the tick.
        # Score: deposit 10*5 + first light 100 = 150. Dawn: L1 lit this tick has units 6000 -> 50 + 100 = 150;
        # L2..L5 lost 60 units = exactly 1.0 -> 99 -> 4 * (50 + 99) = 596; 3 flames * 50 = 150. Total 1046.
        sc = base(player={"pos": [0, 0, 24], "carried": 10}, lanterns=self.LIT, time_left_s=1)
        L = run(sc, press(59, "interact"), ticks=100)
        self.assertEqual(events(L, "game_over")[0]["data"], {"result": "won", "reason": "dawn_survived"})
        self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "won", "score": 1046})

    def test_no_flames_beats_dawn(self):
        # Ticket-03: was test_no_flames_beats_win (fall + last lantern). Now the last flame is lost on the dawn tick.
        # 3 of 5 lanterns are lit (enough to win) and 1 s = 60 ticks of night left. A shade chasing from 5 m at
        # 4/60 m per tick touches (<= 1.0 m) after 15 * (5 - 1) = 60 ticks -> hit on tick 60 with the last flame
        # -> lost no_flames (not won dawn_survived), score 0.
        sc = base(player={"pos": [0, 0, 0], "flames": 1}, shades=[{"id": "S1", "pos": [5, 1, 0], "state": "chase"}],
                  lanterns=self.LIT[:3], time_left_s=1)
        L = run(sc, ticks=100)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(60, "player_hit", {"by": "shade", "flames": 0, "dropped": 0}),
                          (60, "game_over", {"result": "lost", "reason": "no_flames"})])
        self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "lost", "score": 0})
        # control: same night but invulnerable until tick 100 -> no hit, 3 lit >= 3 -> won at dawn:
        # 3 lit * (50 + 99) + 1 flame (the player starts with flames: 1) * 50 = 497
        sc["player"]["invuln_ticks"] = 100
        L = run(sc, ticks=100)
        self.assertEqual(events(L, "game_over")[0]["data"], {"result": "won", "reason": "dawn_survived"})
        self.assertEqual(L[-1]["score"], 3 * (50 + 99) + 1 * PER_FLAME)
        self.assertEqual(3 * (50 + 99) + 1 * PER_FLAME, 497)

    def test_rest_of_tick_runs_before_dawn_verdict(self):
        # Ticket-03: was test_rest_of_tick_runs_after_last_lantern (all_lit win at tick 1). Win/lose is still judged
        # at the end of the tick, but now at the dawn tick: tick 60 has deposit 3 (7 -> 10, lit), then pulse, then the
        # verdict. S1 stunned at (0,1,4.5) is 6.5 m from L1 (outside its 6 m zone) and sqrt(4.5^2 + 0.2^2) = 4.504 m
        # from the pulse centre -> stunned again, +5. carried 10 - 3 - 3 = 4.
        # Score: deposit 3*5 + 100 = 115; pulse 5; dawn: L1 (fresh, 100) 150 + L2..L5 4*(50 + 99) = 596; flames 150.
        # 115 + 5 + 150 + 596 + 150 = 1016
        sc = base(player={"pos": [0, 0, 0], "carried": 10},
                  shades=[{"id": "S1", "pos": [0, 1, 4.5], "state": "stunned", "state_ticks_left": 100}],
                  lanterns=[{"id": "L1", "pos": [0, 0, -2], "deposited": 7}] + self.LIT, time_left_s=1)
        L = run(sc, [{"tick": 59, "interact": True, "pulse": True}, {"tick": 60, "interact": False, "pulse": False}],
                ticks=100)
        self.assertEqual([e["name"] for e in game_events(L)], ["deposit", "lantern_lit", "pulse", "game_over"])
        self.assertEqual([e["tick"] for e in game_events(L)], [60, 60, 60, 60])
        self.assertEqual(L[-1], {"type": "end", "ticks": 60, "state": "won", "score": 1016})


# --------------------------------------------------------------------------- pause
class Pause(unittest.TestCase):
    FR = [{"tick": 0, "move": [0, 1]}] + press(10, "pause") + press(20, "pause")

    def test_pause_freezes_sim(self):
        # walk ticks 1..10 (z=1.0); pause at tick 11 (sim_tick stays 10) until resumed at tick 21 (sim 11)
        L = run(base(), self.FR, ticks=25)
        self.assertEqual([(e["tick"], e["name"], e["data"]) for e in game_events(L)],
                         [(11, "paused", {}), (21, "resumed", {})])
        for t in (11, 15, 20):
            s = snap(L, t)
            self.assertEqual((s["state"], s["tick"], s["sim_tick"]), ("paused", t, 10))
            self.assertEqual(s["player"]["pos"], [0.0, 0.0, 1.0])
            # Ticket-03: night 1 is 240 s = 14400 ticks (was 18000); sim_tick 10 -> (14400 - 10) / 60 = 239.833
            self.assertEqual(s["time_left_s"], r3((14400 - 10) / 60))
            self.assertEqual(s["time_left_s"], 239.833)
        s = snap(L, 21)
        self.assertEqual((s["state"], s["sim_tick"], s["player"]["pos"]), ("playing", 11, [0.0, 0.0, 1.1]))
        self.assertEqual(snap(L, 25)["sim_tick"], 15)

    def test_cooldowns_frozen(self):
        # pulse at tick 1 -> 180; tick 10 leaves 171 (2.85 s), frozen while paused (ticks 11..20);
        # resumed at tick 21 -> 170
        fr = press(0, "pulse") + press(10, "pause") + press(20, "pause")
        L = run(base(player={"pos": [0, 0, 0], "carried": 3}), fr, ticks=21)
        self.assertEqual(snap(L, 10)["player"]["pulse_cd_s"], 2.85)
        self.assertEqual(snap(L, 20)["player"]["pulse_cd_s"], 2.85)
        self.assertEqual(snap(L, 21)["player"]["pulse_cd_s"], r3(170 / 60))

    def test_buttons_ignored_while_paused(self):
        fr = press(2, "pause") + [{"tick": 5, "pulse": True}] + press(10, "pause")
        L = run(base(player={"pos": [0, 0, 0], "carried": 3}), fr, ticks=30)
        self.assertFalse(events(L, "pulse"))
        self.assertEqual(snap(L, 30)["player"]["carried"], 3)

    def test_end_line_while_paused_says_playing(self):
        L = run(base(), press(10, "pause"), ticks=15)
        self.assertEqual(snap(L, 15)["state"], "paused")
        self.assertEqual(L[-1], {"type": "end", "ticks": 15, "state": "playing", "score": 0})


# --------------------------------------------------------------------------- drifters
class Drifters(unittest.TestCase):
    def sc(self, carried, d, **kw):
        return base(2, player={"pos": [0, 0, 0], "carried": carried, **kw.pop("player", {})}, drifters=[d], **kw)

    def test_chase_steal_flee_remove(self):
        # D1 10 m away, carried 5 -> chase from tick 1 at 7/60 m/tick; touch (<= 1.2) when
        # 10 - 7k/60 <= 1.2 -> k = 76 (1.133; k=75 gives 1.25). Steal 3, flee 76..315, gone at 316.
        L = run(self.sc(5, {"id": "D1", "pos": [10, 1.5, 0]}), ticks=316, night=2)
        self.assertEqual(drifter(snap(L, 1), "D1")["state"], "chase")
        self.assertEqual(events(L, "drifter_steal"), [{"type": "event", "tick": 76, "name": "drifter_steal",
                                                       "data": {"drifter_id": "D1", "amount": 3, "carried": 2}}])
        d = drifter(snap(L, 76), "D1")
        self.assertEqual((d["state"], d["stolen"]), ("flee", 3))
        self.assertIsNotNone(drifter(snap(L, 315), "D1"))
        self.assertIsNone(drifter(snap(L, 316), "D1"))
        self.assertEqual(snap(L, 316)["player"]["flames"], 3)       # never costs a flame
        self.assertEqual(len(events(L, "drifter_steal")), 1)

    def test_ignores_invuln_and_safe_zone(self):
        sc = self.sc(5, {"id": "D1", "pos": [10, 1.5, 0]}, player={"invuln_ticks": 600},
                     lanterns=[{"id": "L1", "pos": [0, 0, 0], "lit": True}])
        self.assertEqual(ev_ticks(run(sc, ticks=100, night=2), "drifter_steal"), [76])

    def test_no_chase_below_5_or_beyond_15(self):
        L = run(self.sc(4, {"id": "D1", "pos": [10, 1.5, 0]}), ticks=200, night=2)
        self.assertEqual(drifter(snap(L, 1), "D1")["state"], "idle")
        self.assertFalse(events(L, "drifter_steal"))               # idle home radius 8 -> never within 2 m
        L = run(self.sc(5, {"id": "D1", "pos": [15.5, 1.5, 0]}), ticks=1, night=2)
        self.assertEqual(drifter(snap(L, 1), "D1")["state"], "idle")
        L = run(self.sc(5, {"id": "D1", "pos": [15, 1.5, 0]}), ticks=1, night=2)
        self.assertEqual(drifter(snap(L, 1), "D1")["state"], "chase")

    def test_steal_is_min_3_carried(self):
        # Ticket: "Cham (XZ <= 1.2): cuop min(3, dang mang)" - the touch rule has no state condition, and
        # min(3, c) only matters when c < 3, i.e. a touch while not chasing (chase needs >= 5).
        # Touching (1.0 m) with only 2 carried -> takes min(3, 2) = 2
        L = run(self.sc(2, {"id": "D1", "pos": [1.0, 1.5, 0]}), ticks=1, night=2)
        self.assertEqual(events(L, "drifter_steal")[0]["data"], {"drifter_id": "D1", "amount": 2, "carried": 0})

    def test_pulse_on_chasing_drifter_makes_it_flee_empty(self):
        # D1 (4,1.5,0): sqrt(16+0.49) = 4.06 <= 5 -> flee with nothing, gone after 240 (present 1..240)
        L = run(self.sc(5, {"id": "D1", "pos": [4, 1.5, 0], "state": "chase"}), press(0, "pulse"),
                ticks=241, night=2)
        d = drifter(snap(L, 1), "D1")
        self.assertEqual((d["state"], d["stolen"]), ("flee", 0))
        self.assertFalse(events(L, "drifter_steal"))
        self.assertIsNotNone(drifter(snap(L, 240), "D1"))
        self.assertIsNone(drifter(snap(L, 241), "D1"))
        self.assertEqual(L[-1]["score"], 0)                         # +5 is for shades only

    def test_pulse_on_fleeing_drifter_drops_loot(self):
        # D1 fleeing with 3 at (3,1.5,0): sqrt(9+0.49)=3.08 -> drops 3 motes at (3, ground 0, 0),
        # stolen 0, disappears 120 ticks later (present 1..120)
        L = run(self.sc(3, {"id": "D1", "pos": [3, 1.5, 0], "state": "flee", "stolen": 3}), press(0, "pulse"),
                ticks=121, night=2)
        self.assertEqual(events(L, "drifter_drop")[0]["data"], {"drifter_id": "D1", "amount": 3})
        self.assertEqual(events(L, "drifter_drop")[0]["tick"], 1)
        d = dropped(snap(L, 1))
        self.assertEqual([(m["pos"], m["ttl_s"]) for m in d], [([3.0, 0.0, 0.0], 8.0)] * 3)
        self.assertEqual(drifter(snap(L, 1), "D1")["stolen"], 0)
        self.assertIsNotNone(drifter(snap(L, 120), "D1"))
        self.assertIsNone(drifter(snap(L, 121), "D1"))

    def test_spawn_schedule_night2_max_2(self):
        sc = {"random_shades": False, "random_motes": False}   # random_drifters left at the night-2 default
        n = lambda t: [d["id"] for d in last_snap(run(sc, ticks=t, every=t, night=2))["drifters"]]
        self.assertEqual(n(1199), [])
        self.assertEqual(n(1200), ["D1"])
        self.assertEqual(n(2400), ["D1", "D2"])
        self.assertEqual(n(3600), ["D1", "D2"])

    def test_none_on_night1(self):
        L = run({"random_shades": False}, ticks=1200, every=1200)
        self.assertEqual(last_snap(L)["drifters"], [])


# --------------------------------------------------------------------------- charm
class Charm(unittest.TestCase):
    def walk(self, ticks, stop=None):
        fr = [{"tick": 0, "move": [0, 1]}] + ([{"tick": stop, "move": [0, 0]}] if stop else [])
        return run(base(2, charms=[{"id": "C1", "pos": [0, 0, 2]}]), fr, ticks=ticks, every=1 if ticks < 100 else ticks,
                   night=2)

    def test_pick_and_speed_7_2(self):
        # z = 1.0 at tick 10 -> picked; then 7.2 m/s = 0.12 m/tick: tick 20 z = 1.0 + 10*0.12 = 2.2
        L = self.walk(20)
        self.assertEqual(events(L, "charm_picked"), [{"type": "event", "tick": 10, "name": "charm_picked",
                                                      "data": {"charm_id": "C1", "charm_ticks": 600}}])
        self.assertEqual(snap(L, 10)["player"]["charm_s"], 10.0)
        self.assertEqual(snap(L, 20)["player"]["pos"], [0.0, 0.0, 2.2])
        c = snap(L, 10)["charms"][0]
        self.assertEqual((c["available"], c["respawn_s"]), (False, 45.0))   # 2700/60

    def test_respawn_after_2700(self):
        # picked at 10 -> back at 2710 (player walked away to z=4.6 at tick 40)
        self.assertIs(last_snap(self.walk(2709, stop=40))["charms"][0]["available"], False)
        self.assertIs(last_snap(self.walk(2710, stop=40))["charms"][0]["available"], True)

    def test_refresh_not_stack(self):
        # already charmed (7.2 m/s = 0.12 m/tick): z = 0.12k reaches 1.0 at k = 9 (1.08) -> picked at tick 9;
        # counter is reset to 600 (10.0 s), not 600 + what was left
        sc = base(2, player={"pos": [0, 0, 0], "charm_ticks": 100}, charms=[{"id": "C1", "pos": [0, 0, 2]}])
        L = run(sc, [{"tick": 0, "move": [0, 1]}], ticks=10, night=2)
        self.assertEqual(ev_ticks(L, "charm_picked"), [9])
        self.assertEqual(snap(L, 9)["player"]["charm_s"], 10.0)

    def test_no_dash_cooldown_but_press_while_dashing_ignored(self):
        # dash 1..12; press at tick 6 (dashing) ignored; press at tick 13 dashes again (no 90-tick cooldown)
        fr = press(0, "dash") + press(5, "dash") + press(12, "dash")
        L = run(base(player={"pos": [0, 0, 0], "charm_ticks": 600}), fr, ticks=30)
        self.assertEqual(ev_ticks(L, "dash"), [1, 13])
        self.assertEqual(snap(L, 24)["player"]["pos"], [0.0, 0.0, 5.6])     # 2 x 2.8 m, dash still 14 m/s
        self.assertEqual(ev_ticks(run(base(), fr, ticks=30), "dash"), [1])   # control: no charm

    def test_default_positions(self):
        # night 2 C1 (35,0,0): from (35,0,-1.5) on the bridge walking +Z, in range at z=-1.0 -> tick 5
        sc = {k: v for k, v in base(2).items() if k != "charms"}   # no "charms" key -> night default
        sc["player"] = {"pos": [35, 0, -1.5]}
        L = run(sc, [{"tick": 0, "move": [0, 1]}], ticks=6, night=2)
        self.assertEqual([(e["tick"], e["data"]["charm_id"]) for e in events(L, "charm_picked")], [(5, "C1")])
        # night 3 C1 (30,0,25), C2 (-30,0,25): from z=23.5 walking +Z -> tick 5
        for x, cid in ((30, "C1"), (-30, "C2")):
            sc = {k: v for k, v in base(3).items() if k != "charms"}
            sc["player"] = {"pos": [x, 0, 23.5]}
            L = run(sc, [{"tick": 0, "move": [0, 1]}], ticks=6, night=3)
            self.assertEqual([(e["tick"], e["data"]["charm_id"]) for e in events(L, "charm_picked")], [(5, cid)])


# --------------------------------------------------------------------------- wind
class Wind(unittest.TestCase):
    def test_gust_1800_for_300_ticks_2ms(self):
        sc = {k: v for k, v in base(3, player={"pos": [0, 0, -25]}).items() if k != "wind_enabled"}
        L = run(sc, ticks=2100, every=1, night=3)
        self.assertIs(snap(L, 1799)["wind"]["active"], False)
        w = snap(L, 1800)["wind"]
        self.assertIs(w["active"], True)
        self.assertTrue(0 <= w["dir_deg"] < 360)
        self.assertIs(snap(L, 2099)["wind"]["active"], True)
        self.assertIs(snap(L, 2100)["wind"]["active"], False)
        self.assertEqual(snap(L, 1799)["player"]["pos"], [0.0, 0.0, -25.0])
        # 300 ticks * 2/60 m = 10 m along (cos, sin) of dir_deg; ground is flat 0 within 10 m of (0,-25)
        a = math.radians(w["dir_deg"])
        p = snap(L, 2100)["player"]["pos"]
        self.assertAlmostEqual(p[0], 10 * math.cos(a), delta=0.01)
        self.assertAlmostEqual(p[2], -25 + 10 * math.sin(a), delta=0.01)
        self.assertEqual(p[1], 0.0)

    def test_wind_enabled_false(self):
        L = run(base(3, player={"pos": [0, 0, -25]}), ticks=2100, every=300, night=3)
        self.assertIs(snap(L, 1800)["wind"]["active"], False)
        self.assertEqual(snap(L, 2100)["player"]["pos"], [0.0, 0.0, -25.0])

    def test_no_wind_on_night1_and_2(self):
        for n in (1, 2):
            sc = {"random_motes": False, "random_shades": False}
            if n == 2:
                sc["random_drifters"] = False
            L = run(sc, ticks=1800, every=1800, night=n)
            self.assertIs(last_snap(L)["wind"]["active"], False)
            self.assertEqual(last_snap(L)["player"]["pos"], [0.0, 0.0, 0.0])


# --------------------------------------------------------------------------- jump pads + terrain
class JumpPads(unittest.TestCase):
    def test_night2_pad_a_to_b_ignores_stick(self):
        # pad (20,0,18) -> towards B (70,0,0): dir (50,-18)/53.14 = (0.9409,-0.3387), 0.4 m/tick, vy 14.
        # Euler y_n = (14n - n(n-1)/6)/60 returns to 0 at n = 85 -> 34 m flown -> lands near (51.99, 0, 6.48),
        # 19.1 m from B's centre (radius 28). Holding the stick backwards in flight (from input 1, i.e. after
        # the launch on tick 1; the launch tick itself is not specified) changes nothing.
        sc = base(2, player={"pos": [20, 0, 18]})
        a = run(sc, ticks=150, night=2)
        b = run(sc, [{"tick": 1, "move": [-1, 0]}, {"tick": 80, "move": [0, 0]}], ticks=150, night=2)
        self.assertIs(snap(a, 1)["player"]["grounded"], False)
        self.assertGreater(snap(a, 40)["player"]["pos"][1], 4.0)
        p = snap(a, 150)["player"]
        self.assertIs(p["grounded"], True)
        self.assertEqual(p["pos"][1], 0.0)
        self.assertLessEqual(dxz(p["pos"], [51.99, 0, 6.48]), 0.6)
        self.assertLessEqual(dxz(p["pos"], [70, 0, 0]), 28)
        self.assertEqual(snap(b, 150)["player"]["pos"], p["pos"])
        self.assertFalse(events(a, "player_hit"))

    def test_night2_pad_b_to_a(self):
        L = run(base(2, player={"pos": [50, 0, -18]}), ticks=150, night=2)
        p = snap(L, 150)["player"]["pos"]
        self.assertLessEqual(dxz(p, [18.01, 0, -6.48]), 0.6)

    def test_night3_pad_to_tier2(self):
        # pad (0,3,13): vy 12, 8 m/s to -Z. y_n = 3 + (12n - n(n-1)/6)/60 <= 6 again at n = 53,
        # z = 13 - 53*8/60 = 5.933 (inside the r=8 disk at y=6, clear of the tower r=2)
        L = run(base(3, player={"pos": [0, 3, 13]}), ticks=100, night=3)
        p = snap(L, 100)["player"]
        self.assertIs(p["grounded"], True)
        self.assertEqual((p["pos"][0], p["pos"][1]), (0.0, 6.0))
        self.assertAlmostEqual(p["pos"][2], 5.933, delta=0.3)


class Night3Terrain(unittest.TestCase):
    def walk(self, pos, move, ticks, stop=None):
        fr = [{"tick": 0, "move": move}] + ([{"tick": stop, "move": [0, 0]}] if stop else [])
        return snap(run(base(3, player={"pos": pos}), fr, ticks=ticks, every=ticks, night=3), ticks)["player"]

    def test_cliff_blocks_walking_up(self):
        # (0,0,26.05) walking -Z: z=24.05 after 20 steps is tier 0 (r > 24); 23.95 is tier 1 (y=3, +3 m > 0.3)
        self.assertEqual(self.walk([0, 0, 26.05], [0, -1], 100)["pos"], [0.0, 0.0, 24.05])

    def test_ramp_lets_you_up(self):
        # ramp at 30 deg, u = (0.8660, 0.5). Start s=31 on its centre line, walk -u for 110 ticks (11 m)
        # -> s = 20 on tier 1: (17.321, 3, 10)
        start = [31 * math.cos(math.radians(30)), 0, 15.5]
        p = self.walk(start, [-math.cos(math.radians(30)), -0.5], 120, stop=110)
        self.assertEqual(p["pos"], [r3(20 * math.cos(math.radians(30))), 3.0, 10.0])

    def test_step_off_tier_drops_down(self):
        # (0,3,20) walking +Z: leaves tier 1 after r=24, drops 3 m to tier 0, keeps going: z=30 at tick 100
        p = self.walk([0, 3, 20], [0, 1], 100)
        self.assertEqual(p["pos"], [0.0, 0.0, 30.0])

    def test_tower_blocks(self):
        # tier 2 (0,6,5.05) walking -Z: 2.05 after 30 steps, 1.95 is inside the tower (r<2)
        self.assertEqual(self.walk([0, 6, 5.05], [0, -1], 60)["pos"], [0.0, 6.0, 2.05])


# --------------------------------------------------------------------------- performance
class Performance(unittest.TestCase):
    def test_full_night3_under_30s(self):
        # Ticket-03: night 3 is now 300 s = 18000 ticks (was 21600) and a lit lantern only protects while its fuel is
        # >= 30 (it burns out at tick 6000), so "stand in a lit lantern" no longer keeps the player alive to dawn.
        # Instead the player is invulnerable for 18000 ticks (counter set at tick 0 -> active 0..17999) and nobody can
        # win: no lantern lit -> lost dawn at tick 18000. Wind off so the player stays on the island (a fall ignores
        # invulnerability). Everything else (motes, shades, drifters) stays on.
        tmp = tempfile.mkdtemp()
        scp = os.path.join(tmp, "s.json")
        with open(scp, "w", encoding="utf-8") as f:
            json.dump({"player": {"pos": START3, "invuln_ticks": 18000}, "wind_enabled": False}, f)
        out = os.path.join(tmp, "o.jsonl")
        t0 = time.perf_counter()
        r = cli("--seed", "5", "--night", "3", "--ticks", "21600", "--out", out, "--scenario", scp)
        dt = time.perf_counter() - t0
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(dt, 30.0)
        with open(out, encoding="utf-8") as f:
            last = json.loads(f.read().splitlines()[-1])
        self.assertEqual(last, {"type": "end", "ticks": 18000, "state": "lost", "score": 0})


class CliV11(unittest.TestCase):
    def test_malformed_v11_fields_exit_2(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "o.jsonl")
        cases = [("--inputs", '{"frames":[{"tick":0,"dash":"yes"}]}'),
                 ("--inputs", '{"frames":[{"tick":0,"pause":1}]}'),
                 ("--scenario", '{"drifters":"x"}'),
                 ("--scenario", '{"charms":5}'),
                 ("--scenario", '{"wind_enabled":"no"}')]
        for i, (flag, text) in enumerate(cases):
            p = os.path.join(d, f"{i}.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            r = cli("--seed", "1", "--night", "3", "--ticks", "5", "--out", out, flag, p)
            self.assertEqual(r.returncode, 2, text)


if __name__ == "__main__":
    unittest.main()
