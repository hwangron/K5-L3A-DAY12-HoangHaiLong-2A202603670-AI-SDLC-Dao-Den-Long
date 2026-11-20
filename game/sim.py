"""Dao Den Long - pure game logic.

No I/O, no rendering, no wall-clock. Shared by the headless CLI (headless.py)
and the web build (web/index.html runs this exact file through Pyodide).
Fixed 60 ticks/second. Same seed + scenario + inputs => identical result.
"""
import math
import random

TICK_HZ = 60
DT = 1.0 / TICK_HZ

# Declared 1:1 in game.contract.json (a test checks they match).
TUNING = {
    "player_speed": 6.0,
    "carry_capacity": 5,
    "lantern_cost": 5,
    "lantern_count_night1": 5,
    "pickup_radius": 1.0,
    "interact_radius": 2.5,
    "pulse_cost": 1,
    "pulse_radius": 6.0,
    "night1_duration_s": 300,
    "flames": 3,
    "invuln_s": 2.0,
    "hit_drop_ratio": 0.5,
    "pulse_stun_s": 3.0,
    "pulse_push_m": 4.0,
    "pulse_cooldown_s": 1.0,
    "safe_radius": 4.0,
    "shade_speed": 3.5,
    "shade_hit_radius": 1.0,
    "fall_enabled": False,
    "score": {
        "per_mote": 10,
        "per_lantern": 100,
        "per_stun": 20,
        "per_second_left": 2,
        "per_flame_left": 50,
    },
}

# Internal constants (not part of the contract; see docs/notes/phase-1.md).
ISLAND_RADIUS = 30.0       # player is clamped inside (fall disabled)
LANTERN_RING = 18.0        # default lanterns sit on this circle
JUMP_SPEED = 7.0           # m/s
GRAVITY = 20.0             # m/s^2
SHADE_Y = 1.0              # shade centre height
MOTE_COUNT = 40            # random motes at start / cap for respawn
MOTE_RESPAWN_TICKS = 240   # +1 mote every 4 s while below cap
SHADE_FIRST_TICK = 300     # first random shade at 5 s
SHADE_EVERY_TICKS = 1200   # then every 20 s
SHADE_MAX = 6
SHADE_SPAWN_MIN_DIST = 12.0

BUTTONS = ("jump", "interact", "pulse", "dash")
# Radius checks use "<= r + EPS": 60 steps of 0.1 m sum to 5.9999999, not 6.0.
EPS = 1e-6


class ScenarioError(ValueError):
    """Malformed scenario or inputs file (headless exits with code 2)."""


def r3(x):
    v = round(float(x), 3)
    return 0.0 if v == 0 else v


def dist_xz(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def _ticks(seconds):
    return int(round(seconds * TICK_HZ))


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _vec3(v, what):
    if not (isinstance(v, list) and len(v) == 3 and all(_is_num(c) for c in v)):
        raise ScenarioError(f"{what} must be [x, y, z] numbers")
    return [float(c) for c in v]


def _int(v, what, lo=0):
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # accept 2.0 as 2
    if not (isinstance(v, int) and not isinstance(v, bool) and v >= lo):
        raise ScenarioError(f"{what} must be an integer >= {lo}")
    return v


def _bool(v, what):
    if not isinstance(v, bool):
        raise ScenarioError(f"{what} must be true/false")
    return v


def default_lantern_positions():
    out = []
    for i in range(TUNING["lantern_count_night1"]):
        a = 2 * math.pi * i / TUNING["lantern_count_night1"]
        out.append([r3(LANTERN_RING * math.sin(a)), 0.0, r3(LANTERN_RING * math.cos(a))])
    return out


def parse_inputs(data):
    """Validate an inputs document -> {tick: frame}. Raises ScenarioError."""
    if not isinstance(data, dict) or not isinstance(data.get("frames"), list):
        raise ScenarioError("inputs must be an object with a 'frames' list")
    frames = {}
    last = -1
    for i, f in enumerate(data["frames"]):
        if not isinstance(f, dict):
            raise ScenarioError(f"frame {i} must be an object")
        t = _int(f.get("tick"), f"frame {i}.tick")
        if t <= last:
            raise ScenarioError(f"frame {i}: tick must be strictly increasing")
        last = t
        fr = {}
        if "move" in f:
            m = f["move"]
            if not (isinstance(m, list) and len(m) == 2 and all(_is_num(c) for c in m)):
                raise ScenarioError(f"frame {i}.move must be [x, z] numbers")
            # components are specified in [-1, 1]; out-of-range values are clamped
            fr["move"] = [max(-1.0, min(1.0, float(c))) for c in m]
        if "cam_yaw_deg" in f:
            if not _is_num(f["cam_yaw_deg"]):
                raise ScenarioError(f"frame {i}.cam_yaw_deg must be a number")
            fr["cam_yaw_deg"] = float(f["cam_yaw_deg"])
        for b in BUTTONS:
            if b in f:
                fr[b] = _bool(f[b], f"frame {i}.{b}")
        frames[t] = fr
    return frames


class Game:
    def __init__(self, seed=0, scenario=None):
        self.rng = random.Random(seed)
        self.tick = 0
        self.state = "playing"
        self.score = 0
        self.events = []
        T = TUNING
        self.time_left_ticks = _ticks(T["night1_duration_s"])
        self.player = {"pos": [0.0, 0.0, 0.0], "vy": 0.0, "grounded": True,
                       "flames": T["flames"], "carried": 0,
                       "invuln_until": 0, "pulse_ready": 0}
        self.lanterns = [{"id": f"L{i + 1}", "pos": p, "lit": False, "deposited": 0}
                         for i, p in enumerate(default_lantern_positions())]
        self.motes = []
        self.shades = []
        self.next_mote = 1
        self.next_shade = 1
        self.random_motes = True
        self.random_shades = True
        self.held = {"move": [0.0, 0.0], "cam_yaw_deg": 0.0}
        self.held.update({b: False for b in BUTTONS})
        self.prev_buttons = {b: False for b in BUTTONS}
        self._setup({} if scenario is None else scenario)

    # ---------------------------------------------------------------- setup
    def _setup(self, sc):
        if not isinstance(sc, dict):
            raise ScenarioError("scenario must be an object")
        T = TUNING
        if "random_motes" in sc:
            self.random_motes = _bool(sc["random_motes"], "random_motes")
        if "random_shades" in sc:
            self.random_shades = _bool(sc["random_shades"], "random_shades")
        if "player" in sc:
            p = sc["player"]
            if not isinstance(p, dict):
                raise ScenarioError("player must be an object")
            if "pos" in p:
                self.player["pos"] = _vec3(p["pos"], "player.pos")
                self.player["grounded"] = self.player["pos"][1] <= 0
            if "carried" in p:
                self.player["carried"] = _int(p["carried"], "player.carried")
            if "flames" in p:
                self.player["flames"] = _int(p["flames"], "player.flames")
        if "lanterns" in sc:
            if not isinstance(sc["lanterns"], list):
                raise ScenarioError("lanterns must be a list")
            by_id = {l["id"]: l for l in self.lanterns}
            for i, l in enumerate(sc["lanterns"]):
                if not isinstance(l, dict) or l.get("id") not in by_id:
                    raise ScenarioError(f"lanterns[{i}] needs an id in L1..L5")
                tgt = by_id[l["id"]]
                if "pos" in l:
                    tgt["pos"] = _vec3(l["pos"], f"lanterns[{i}].pos")
                if "lit" in l:
                    tgt["lit"] = _bool(l["lit"], f"lanterns[{i}].lit")
                if "deposited" in l:
                    tgt["deposited"] = _int(l["deposited"], f"lanterns[{i}].deposited")
                elif tgt["lit"]:
                    tgt["deposited"] = T["lantern_cost"]
        if "motes" in sc:
            if not isinstance(sc["motes"], list):
                raise ScenarioError("motes must be a list")
            for i, m in enumerate(sc["motes"]):
                pos = m.get("pos") if isinstance(m, dict) else m
                self._add_mote(_vec3(pos, f"motes[{i}]"))
        elif self.random_motes:
            for _ in range(MOTE_COUNT):
                self._add_mote(self._random_mote_pos())
        if "shades" in sc:
            if not isinstance(sc["shades"], list):
                raise ScenarioError("shades must be a list")
            given = set()
            for i, s in enumerate(sc["shades"]):
                if not isinstance(s, dict):
                    raise ScenarioError(f"shades[{i}] must be an object")
                if "id" in s:
                    if not isinstance(s["id"], str) or s["id"] in given:
                        raise ScenarioError(f"shades[{i}].id must be a unique string")
                    given.add(s["id"])
            for i, s in enumerate(sc["shades"]):
                pos = _vec3(s.get("pos"), f"shades[{i}].pos")
                sid = s.get("id") or self._new_shade_id(given)
                self.shades.append({"id": sid, "pos": pos, "state": "chase", "stun_until": 0})
            self._reserved_ids = given
        if "time_left_s" in sc:
            if not _is_num(sc["time_left_s"]) or sc["time_left_s"] < 0:
                raise ScenarioError("time_left_s must be a number >= 0")
            self.time_left_ticks = _ticks(sc["time_left_s"])
        self.next_shade_tick = SHADE_FIRST_TICK

    def _new_shade_id(self, taken=()):
        taken = set(taken) | {s["id"] for s in self.shades} | getattr(self, "_reserved_ids", set())
        while f"S{self.next_shade}" in taken:
            self.next_shade += 1
        sid = f"S{self.next_shade}"
        self.next_shade += 1
        return sid

    def _add_mote(self, pos):
        self.motes.append({"id": f"M{self.next_mote}", "pos": [pos[0], 0.0, pos[2]]})
        self.next_mote += 1

    def _random_mote_pos(self):
        r = math.sqrt(self.rng.uniform(3.0 ** 2, (ISLAND_RADIUS - 2.0) ** 2))
        a = self.rng.uniform(0, 2 * math.pi)
        return [r * math.sin(a), 0.0, r * math.cos(a)]

    # ----------------------------------------------------------------- step
    def _emit(self, name, data):
        self.events.append({"type": "event", "tick": self.tick, "name": name, "data": data})

    def _end(self, result, reason):
        if self.state != "playing":
            return
        self.state = result
        if result == "won":
            S = TUNING["score"]
            self.score += S["per_second_left"] * (max(0, self.time_left_ticks) // TICK_HZ)
            self.score += S["per_flame_left"] * self.player["flames"]
        self._emit("game_over", {"result": result, "reason": reason})

    def step(self, frame=None):
        """Advance one tick. `frame` = dict of changed input fields (or None).
        Returns the list of events produced by this step."""
        self.events = []
        if self.state != "playing":
            return self.events
        if frame:
            self.held.update(frame)
        edge = {b: self.held[b] and not self.prev_buttons[b] for b in BUTTONS}
        self.prev_buttons = {b: self.held[b] for b in BUTTONS}

        self.tick += 1
        self.time_left_ticks -= 1
        t = self.tick
        T = TUNING
        S = T["score"]
        p = self.player
        pos = p["pos"]

        # 1. movement (camera-relative, normalised) + jump
        mx, mz = self.held["move"]
        ln = math.hypot(mx, mz)
        if ln > 1.0:
            mx, mz = mx / ln, mz / ln
        th = math.radians(self.held["cam_yaw_deg"])
        wx = mx * math.cos(th) + mz * math.sin(th)
        wz = -mx * math.sin(th) + mz * math.cos(th)
        d_old = math.hypot(pos[0], pos[2])
        pos[0] += wx * T["player_speed"] * DT
        pos[2] += wz * T["player_speed"] * DT
        d = math.hypot(pos[0], pos[2])
        # invisible shore: only blocks moving outward past the edge; a position
        # placed outside by a scenario is never teleported back
        if d > ISLAND_RADIUS and d > d_old:
            lim = max(ISLAND_RADIUS, d_old)
            pos[0] *= lim / d
            pos[2] *= lim / d
        if edge["jump"] and p["grounded"]:
            p["vy"] = JUMP_SPEED
            p["grounded"] = False
        if not p["grounded"]:
            pos[1] += p["vy"] * DT
            p["vy"] -= GRAVITY * DT
            if pos[1] <= 0.0:
                pos[1] = 0.0
                p["vy"] = 0.0
                p["grounded"] = True

        # 2. pick up motes (auto, while not full)
        kept = []
        for m in self.motes:
            if p["carried"] < T["carry_capacity"] and dist_xz(pos, m["pos"]) <= T["pickup_radius"] + EPS:
                p["carried"] += 1
                self.score += S["per_mote"]
                self._emit("mote_picked", {"carried": p["carried"]})
            else:
                kept.append(m)
        self.motes = kept

        # 3. interact: deposit into nearest unlit lantern in range
        if edge["interact"] and p["carried"] > 0:
            cands = [l for l in self.lanterns
                     if not l["lit"] and dist_xz(pos, l["pos"]) <= T["interact_radius"] + EPS]
            if cands:
                l = min(cands, key=lambda l: (dist_xz(pos, l["pos"]), l["id"]))
                amount = min(p["carried"], T["lantern_cost"] - l["deposited"])
                if amount > 0:
                    p["carried"] -= amount
                    l["deposited"] += amount
                    self._emit("deposit", {"lantern_id": l["id"], "amount": amount,
                                           "deposited": l["deposited"]})
                if l["deposited"] >= T["lantern_cost"]:
                    l["lit"] = True
                    self.score += S["per_lantern"]
                    self._emit("lantern_lit", {"lantern_id": l["id"]})
                    if all(x["lit"] for x in self.lanterns):
                        self._end("won", "all_lit")
                        return self.events

        # 4. pulse: costs carried light, stuns + pushes shades in radius
        if edge["pulse"] and t >= p["pulse_ready"] and p["carried"] >= T["pulse_cost"]:
            p["carried"] -= T["pulse_cost"]
            p["pulse_ready"] = t + _ticks(T["pulse_cooldown_s"])
            ids = []
            for s in self.shades:
                dd = dist_xz(pos, s["pos"])
                if dd <= T["pulse_radius"] + EPS:
                    s["state"] = "stunned"
                    s["stun_until"] = t + _ticks(T["pulse_stun_s"])
                    ux, uz = ((s["pos"][0] - pos[0]) / dd, (s["pos"][2] - pos[2]) / dd) if dd > 1e-9 else (1.0, 0.0)
                    s["pos"][0] += ux * T["pulse_push_m"]
                    s["pos"][2] += uz * T["pulse_push_m"]
                    self._keep_out_of_light(s)
                    ids.append(s["id"])
                    self.score += S["per_stun"]
            self._emit("pulse", {"stunned_ids": ids})

        # 5. shades chase (stunned ones wait), never enter a lit lantern's safe radius
        step_len = T["shade_speed"] * DT
        for s in self.shades:
            if s["state"] == "stunned":
                if t < s["stun_until"]:
                    continue
                s["state"] = "chase"
            dx, dz = pos[0] - s["pos"][0], pos[2] - s["pos"][2]
            dd = math.hypot(dx, dz)
            if dd > 1e-9:
                k = min(step_len, dd) / dd
                s["pos"][0] += dx * k
                s["pos"][2] += dz * k
            self._keep_out_of_light(s)

        # 6. shade touches player
        if t >= p["invuln_until"]:
            for s in self.shades:
                if s["state"] != "stunned" and dist_xz(pos, s["pos"]) <= T["shade_hit_radius"] + EPS:
                    p["flames"] = max(0, p["flames"] - 1)
                    dropped = int(math.floor(p["carried"] * T["hit_drop_ratio"]))
                    p["carried"] -= dropped
                    p["invuln_until"] = t + _ticks(T["invuln_s"])
                    self._emit("player_hit", {"by": "shade", "flames": p["flames"], "dropped": dropped})
                    if p["flames"] <= 0:
                        self._end("lost", "no_flames")
                        return self.events
                    break

        # 7. spawns
        if self.random_shades and t >= self.next_shade_tick:
            self.next_shade_tick += SHADE_EVERY_TICKS
            if len(self.shades) < SHADE_MAX:
                self._spawn_shade()
        if self.random_motes and t % MOTE_RESPAWN_TICKS == 0 and len(self.motes) < MOTE_COUNT:
            self._add_mote(self._random_mote_pos())

        # 8. dawn
        if self.time_left_ticks <= 0:
            self._end("lost", "dawn")
        return self.events

    def _keep_out_of_light(self, s):
        R = TUNING["safe_radius"]
        for l in self.lanterns:
            if not l["lit"]:
                continue
            dx, dz = s["pos"][0] - l["pos"][0], s["pos"][2] - l["pos"][2]
            dd = math.hypot(dx, dz)
            if dd < R - EPS:
                ux, uz = (dx / dd, dz / dd) if dd > 1e-9 else (1.0, 0.0)
                s["pos"][0] = l["pos"][0] + ux * R
                s["pos"][2] = l["pos"][2] + uz * R

    def _spawn_shade(self):
        pos = None
        for _ in range(12):
            a = self.rng.uniform(0, 2 * math.pi)
            cand = [(ISLAND_RADIUS - 1) * math.sin(a), SHADE_Y, (ISLAND_RADIUS - 1) * math.cos(a)]
            pos = cand
            if dist_xz(cand, self.player["pos"]) >= SHADE_SPAWN_MIN_DIST and not any(
                    l["lit"] and dist_xz(cand, l["pos"]) < TUNING["safe_radius"] for l in self.lanterns):
                break
        sid = self._new_shade_id()
        s = {"id": sid, "pos": pos, "state": "chase", "stun_until": 0}
        self._keep_out_of_light(s)
        self.shades.append(s)
        self._emit("shade_spawned", {"id": sid})

    # ------------------------------------------------------------- snapshot
    def snapshot(self):
        p = self.player
        return {
            "type": "snapshot",
            "tick": self.tick,
            "sim_tick": self.tick,
            "state": self.state,
            "time_left_s": r3(max(0, self.time_left_ticks) / TICK_HZ),
            "score": self.score,
            "player": {"pos": [r3(c) for c in p["pos"]], "flames": p["flames"], "carried": p["carried"]},
            "lanterns": [{"id": l["id"], "pos": [r3(c) for c in l["pos"]], "lit": l["lit"],
                          "deposited": l["deposited"]} for l in self.lanterns],
            "shades": [{"id": s["id"], "pos": [r3(c) for c in s["pos"]], "state": s["state"]}
                       for s in self.shades],
            "motes_active": len(self.motes),
            "motes": [{"id": m["id"], "pos": [r3(c) for c in m["pos"]]} for m in self.motes],
        }


# ------------------------------------------------------------------ web glue
_web_game = None


def web_new(seed):
    global _web_game
    _web_game = Game(int(seed))
    return _web_json({"events": [], "snap": _web_game.snapshot()})


def web_step(frame_json):
    import json
    frame = json.loads(frame_json)
    ev = _web_game.step(frame)
    return _web_json({"events": ev, "snap": _web_game.snapshot(),
                      "invuln": _web_game.tick < _web_game.player["invuln_until"],
                      "pulse_ready": _web_game.tick >= _web_game.player["pulse_ready"]})


def _web_json(o):
    import json
    return json.dumps(o, separators=(",", ":"))
