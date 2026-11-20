"""Dao Den Long - pure game logic (Ticket-03 "Den can dau", Test Contract v1.2).

No I/O, no rendering, no wall-clock. Shared by the headless CLI (headless.py)
and the web build (web/index.html runs this exact file through Pyodide,
together with game/maps.py loaded as module `maps`).
Fixed 60 ticks/second. Same seed + night + scenario + inputs => identical result.

All timers are integer tick counters, decremented in step 2 of a tick.
An effect of n ticks set at tick t is active on ticks t .. t+n-1 and over at t+n.
"""
import math
import random

try:  # headless: game/ package
    from . import maps
except ImportError:  # Pyodide: sim.py and maps.py side by side as top-level modules
    import maps

TICK_HZ = 60
DT = 1.0 / TICK_HZ

# Declared 1:1 in game.contract.json (a test checks they match). Ticket-02 Part 1 + Ticket-03.
TUNING = {
    "player_speed": 6.0,
    "carry_capacity": 10,
    "lantern_cost": 10,
    "lantern_count_night1": 5,
    "pickup_radius": 1.0,
    "interact_radius": 2.0,
    "pulse_cost": 3,
    "pulse_radius": 5.0,
    "night1_duration_s": 240,       # Ticket-03: was 300/330/360
    "night2_duration_s": 270,
    "night3_duration_s": 300,
    "flames": 3,
    "invuln_s": 1.5,
    "hit_drop_ratio": 0.5,
    "pulse_stun_s": 2.0,
    "pulse_push_m": 4.0,
    "pulse_cooldown_s": 3.0,
    "safe_radius": 6.0,
    "shade_speed": 4.0,
    "shade_hit_radius": 1.0,
    "fall_enabled": True,
    "dash_speed": 14.0,
    "dash_duration_s": 0.2,
    "dash_cooldown_s": 1.5,
    # Ticket-03 lantern fuel (stored internally in integer units = fuel x 60)
    "fuel_max": 100,
    "fuel_decay_per_s": 1.0,
    "fuel_per_mote": 10,
    "relight_cost": 5,
    "win_ratio": 0.6,
    "drain_per_s": 5,
    "low_fuel_threshold": 30,
    "capacity_max": 20,
    "score": {
        "per_mote": 5,              # Ticket-03: every mote put into a lantern (light, relight, refuel)
        "per_lantern": 100,         # first light
        "per_stun": 5,
        "per_second_left": 0,       # Ticket-03: time bonus removed
        "per_flame_left": 50,       # dawn bonus (win only)
        "per_relight": 40,
        "per_drain_stun": 15,       # pulse hit on a shade that was draining (total, not extra)
        "per_lit_lantern_dawn": 50,  # + floor(fuel) per lit lantern at dawn (win only)
    },
}

# Internal constants from Ticket-02 / docs/notes/phase-2-design.md (not contract keys).
JUMP_SPEED = 7.0            # m/s
GRAVITY = 20.0              # m/s^2
STEP_UP = 0.3               # max ground rise/drop the player follows while walking
PICKUP_DY = 1.5             # max |y_player - y_mote| for pickups
HIT_DY = 1.5                # max |y_player - y_shade| for a shade hit
CHARM_SPEED = 7.2           # run speed while the Wind Charm is active
CHARM_TICKS = 600
CHARM_RESPAWN_TICKS = 2700
MOTE_START = 20
MOTE_CAP = 30
MOTE_RESPAWN_TICKS = 240
DROP_TTL_TICKS = 480
DROP_RING = (1.5, 2.5)
FALL_Y = -10.0
RESPAWN_WAIT_TICKS = 60
PULSE_CENTER_DY = 0.8
PUSH_TICKS = 15
EXPEL_TICKS = 30
SHADE_Y_OFFSET = 1.0
SHADE_SPEED_NIGHT3 = 4.5
SHADE_FIRST_TICK = 300
SHADE_FIRST_COUNT = 2
SHADE_SPAWNING_TICKS = 1    # spawned at t: "spawning" in snapshot t, acts from t+1
SHADE_DETECT = 12.0
SHADE_LOSE = 18.0
SHADE_WANDER_SPEED = 1.5
SHADE_WANDER_R = 6.0
FUEL_UNIT = TICK_HZ         # fuel is stored as integer units = fuel x 60 (1 fuel/s = 1 unit/tick)
CAPACITY_PER_LIGHT = 2      # carry capacity grows by 2 per successful light
LANTERN_APPROACH_M = 4.0    # wander: walk to an unlit lantern until this close, then circle it
DRAIN_RANGE = 2.0           # a wandering shade this close (XZ) to a weak lit lantern starts draining
DRAIN_ALERT = 6.0           # a draining shade turns to chase when the player gets this close
DRAIN_EVENT_TICKS = 60      # fuel_drain event every 60 drained ticks per shade
WANDER_RETARGET_TICKS = 180
SPAWN_MIN_DIST = 15.0
RECOIL_TICKS = 60
RECOIL_M = 2.0
TOWER_R = 2.0               # Night 3 bell tower (shades / drifters are pushed out)
DRIFTER_Y_OFFSET = 1.5
DRIFTER_SPEED = 7.0
DRIFTER_IDLE_SPEED = 2.0
DRIFTER_WANDER_R = 8.0
DRIFTER_MAX = 2
DRIFTER_EVERY_TICKS = 1200
DRIFTER_CHASE_CARRY = 5
DRIFTER_CHASE_DIST = 15.0
DRIFTER_TOUCH = 1.2
DRIFTER_STEAL = 3
DRIFTER_FLEE_TICKS = 240
DRIFTER_DROP_FLEE_TICKS = 120
WIND_EVERY_TICKS = 1800
WIND_TICKS = 300
WIND_WARN_TICKS = 120
WIND_SPEED = 2.0

BUTTONS = ("jump", "interact", "pulse", "dash", "pause")
SHADE_STATES = ("spawning", "wander", "chase", "recoil", "stunned", "drain")
DRIFTER_STATES = ("idle", "chase", "flee")
# Radius checks use "<= r + EPS": 60 steps of 0.1 m sum to 5.9999999, not 6.0.
EPS = 1e-6


class ScenarioError(ValueError):
    """Malformed scenario or inputs file (headless exits with code 2)."""


def r3(x):
    v = round(float(x), 3)
    return 0.0 if v == 0 else v


def r1(x):
    v = round(float(x), 1)
    return 0.0 if v == 0 else v


def dist_xz(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def _ticks(seconds):
    return int(round(seconds * TICK_HZ))


def _id_key(ident):
    """Sort 'S2' before 'S10'; non-numeric ids after numeric ones."""
    tail = ident[1:]
    if tail.isdigit():
        return (0, int(tail), ident)
    return (1, 0, ident)


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


def _obj(v, what):
    if not isinstance(v, dict):
        raise ScenarioError(f"{what} must be an object")
    return v


def _list(v, what):
    if not isinstance(v, list):
        raise ScenarioError(f"{what} must be a list")
    return v


def default_lantern_positions(night=1):
    return maps.lanterns(night)


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
    def __init__(self, seed=0, scenario=None, night=1):
        if night not in maps.NIGHTS:
            raise ValueError(f"night must be one of {maps.NIGHTS}")
        T = TUNING
        self.night = night
        self.rng = random.Random(seed)
        self.tick = 0
        self.sim_tick = 0
        self.state = "playing"
        self.score = 0
        self.events = []
        self.time_left_ticks = maps.duration_ticks(night, T)
        self.start_pos = maps.start(night)
        self.mote_points = maps.mote_points(night)
        self.shade_points = maps.shade_points(night)
        self.pads = maps.jump_pads(night)
        self.shade_interval = maps.shade_interval_ticks(night)
        self.shade_max = maps.shade_max(night)
        self.shade_speed = SHADE_SPEED_NIGHT3 if night == 3 else T["shade_speed"]
        self.player = {"pos": list(self.start_pos), "vy": 0.0, "vel": [0.0, 0.0, 0.0],
                       "grounded": True, "flames": T["flames"], "carried": 0,
                       "invuln": 0, "dash_cd": 0, "pulse_cd": 0, "charm": 0,
                       "dash": 0, "dash_dir": [0.0, 1.0], "facing": [0.0, 1.0],
                       "launched": False, "launch_v": [0.0, 0.0],
                       "respawning": False, "respawn": 0, "successful_lights": 0}
        # units = fuel x 60 (integer); 0 while unlit. ever_lit survives going out (relight cost 5).
        self.lanterns = [{"id": f"L{i + 1}", "pos": p, "lit": False, "deposited": 0,
                          "units": 0, "ever_lit": False, "relit_count": 0}
                         for i, p in enumerate(maps.lanterns(night))]
        self.charms = [{"id": cid, "pos": pos, "available": True, "respawn": 0}
                       for cid, pos in maps.charms(night)]
        self.motes = []
        self.shades = []
        self.drifters = []
        self.next_mote = 1
        self.next_shade = 1
        self.next_drifter = 1
        self.reserved_shade_ids = []
        self.reserved_drifter_ids = []
        self.random_motes = True
        self.random_shades = True
        self.random_drifters = maps.has_drifters(night)
        self.wind_enabled = maps.has_wind(night)
        self.wind_ticks = 0
        self.wind_dir = 0.0
        self.wind_pending = None
        self.held = {"move": [0.0, 0.0], "cam_yaw_deg": 0.0}
        self.held.update({b: False for b in BUTTONS})
        self.prev_buttons = {b: False for b in BUTTONS}
        self._setup({} if scenario is None else scenario)

    # ------------------------------------------------------------- geometry
    def _ground(self, x, z):
        g = maps.ground_height(self.night, x, z)
        if g is None and not TUNING["fall_enabled"]:
            return 0.0
        return g

    def _floor_y(self, x, z):
        g = maps.ground_height(self.night, x, z)
        return 0.0 if g is None else g

    # ---------------------------------------------------------------- setup
    def _setup(self, sc):
        _obj(sc, "scenario")
        T = TUNING
        p = self.player
        for flag in ("random_motes", "random_shades", "random_drifters", "wind_enabled"):
            if flag in sc:
                setattr(self, flag, _bool(sc[flag], flag))
        if "player" in sc:
            sp = _obj(sc["player"], "player")
            if "pos" in sp:
                p["pos"] = _vec3(sp["pos"], "player.pos")
                g = self._ground(p["pos"][0], p["pos"][2])
                p["grounded"] = g is not None and p["pos"][1] <= g + EPS
            for key, field in (("carried", "carried"), ("flames", "flames"),
                               ("invuln_ticks", "invuln"), ("dash_cd_ticks", "dash_cd"),
                               ("pulse_cd_ticks", "pulse_cd"), ("charm_ticks", "charm"),
                               ("successful_lights", "successful_lights")):
                if key in sp:
                    p[field] = _int(sp[key], f"player.{key}")
        if "lanterns" in sc:
            by_id = {l["id"]: l for l in self.lanterns}
            for i, l in enumerate(_list(sc["lanterns"], "lanterns")):
                if not isinstance(l, dict) or l.get("id") not in by_id:
                    raise ScenarioError(f"lanterns[{i}] needs an id in L1..L{len(self.lanterns)}")
                tgt = by_id[l["id"]]
                if "pos" in l:
                    tgt["pos"] = _vec3(l["pos"], f"lanterns[{i}].pos")
                fuel_u = None
                if "fuel" in l:
                    f = l["fuel"]
                    if not _is_num(f) or f < 0 or f > T["fuel_max"]:
                        raise ScenarioError(f"lanterns[{i}].fuel must be a number in 0..{T['fuel_max']}")
                    fuel_u = int(round(f * FUEL_UNIT))
                if "lit" in l:
                    tgt["lit"] = _bool(l["lit"], f"lanterns[{i}].lit")
                elif fuel_u:
                    tgt["lit"] = True   # a fuel > 0 without "lit" can only mean a burning lantern
                if "ever_lit" in l:
                    tgt["ever_lit"] = _bool(l["ever_lit"], f"lanterns[{i}].ever_lit")
                if "relit_count" in l:
                    tgt["relit_count"] = _int(l["relit_count"], f"lanterns[{i}].relit_count")
                if tgt["lit"]:
                    # lit: true without fuel -> fuel_max; a lit lantern has always been lit
                    tgt["units"] = self._fuel_max_u() if fuel_u is None else fuel_u
                    tgt["ever_lit"] = True
                else:
                    tgt["units"] = 0
                if "deposited" in l:
                    tgt["deposited"] = _int(l["deposited"], f"lanterns[{i}].deposited")
                elif tgt["lit"]:
                    tgt["deposited"] = T["lantern_cost"]
        if "motes" in sc:
            for i, m in enumerate(_list(sc["motes"], "motes")):
                pos = m.get("pos") if isinstance(m, dict) else m
                pos = _vec3(pos, f"motes[{i}]")
                kind = m.get("kind", "random") if isinstance(m, dict) else "random"
                if kind not in ("random", "dropped"):
                    raise ScenarioError(f"motes[{i}].kind must be 'random' or 'dropped'")
                if kind == "dropped":
                    ttl = DROP_TTL_TICKS
                    if "ttl_ticks" in m:
                        ttl = _int(m["ttl_ticks"], f"motes[{i}].ttl_ticks", lo=1)
                    elif "ttl_s" in m:
                        if not _is_num(m["ttl_s"]) or m["ttl_s"] <= 0:
                            raise ScenarioError(f"motes[{i}].ttl_s must be a number > 0")
                        ttl = max(1, _ticks(m["ttl_s"]))
                    self._add_mote(pos, "dropped", ttl=ttl)
                    continue
                point = None
                for k, pt in enumerate(self.mote_points):
                    if dist_xz(pos, pt) < 1e-3:
                        point = k
                        break
                self._add_mote(pos, "random", point=point)
        elif self.random_motes:
            n = min(MOTE_START, len(self.mote_points))
            for k in sorted(self.rng.sample(range(len(self.mote_points)), n)):
                self._add_mote(list(self.mote_points[k]), "random", point=k)
        if "shades" in sc:
            shades = _list(sc["shades"], "shades")
            self.reserved_shade_ids = self._reserve_ids(shades, "shades")
            for i, s in enumerate(shades):
                pos = _vec3(s.get("pos"), f"shades[{i}].pos")
                state = s.get("state", "wander")
                if state not in SHADE_STATES:
                    raise ScenarioError(f"shades[{i}].state must be one of {SHADE_STATES}")
                default_left = {"spawning": SHADE_SPAWNING_TICKS, "stunned": _ticks(T["pulse_stun_s"]),
                                "recoil": RECOIL_TICKS}.get(state, 0)
                left = default_left
                if "state_ticks_left" in s:
                    left = _int(s["state_ticks_left"], f"shades[{i}].state_ticks_left")
                sid = s.get("id") or self._new_id("S", "next_shade", self.shades, self.reserved_shade_ids)
                sh = self._make_shade(sid, pos, state, left)
                if state == "recoil":
                    sh["recoil_dir"] = self._away_from_player(pos)
                tid = s.get("target_lantern_id")
                if tid is not None and not isinstance(tid, str):
                    raise ScenarioError(f"shades[{i}].target_lantern_id must be a lantern id string")
                tl = self._lantern(tid) if tid is not None else None
                weak = tl is not None and self._is_weak(tl)
                if state == "drain":
                    # drain target: the given weak lit lantern, else the nearest one
                    if not weak:
                        tl = self._weak_lantern(pos)
                    sh["tl"] = None if tl is None else tl["id"]
                elif tl is not None and (weak or not tl["lit"]):
                    sh["tl0"] = tl["id"]    # initial wander target (only if the lantern is a valid one)
                self.shades.append(sh)
        if "drifters" in sc:
            drifters = _list(sc["drifters"], "drifters")
            self.reserved_drifter_ids = self._reserve_ids(drifters, "drifters")
            for i, d in enumerate(drifters):
                pos = _vec3(d.get("pos"), f"drifters[{i}].pos")
                state = d.get("state", "idle")
                if state not in DRIFTER_STATES:
                    raise ScenarioError(f"drifters[{i}].state must be one of {DRIFTER_STATES}")
                stolen = _int(d["stolen"], f"drifters[{i}].stolen") if "stolen" in d else 0
                flee = DRIFTER_FLEE_TICKS if state == "flee" else 0
                if "state_ticks_left" in d:
                    flee = _int(d["state_ticks_left"], f"drifters[{i}].state_ticks_left")
                did = d.get("id") or self._new_id("D", "next_drifter", self.drifters,
                                                  self.reserved_drifter_ids)
                dr = self._make_drifter(did, pos)
                dr["state"], dr["stolen"], dr["flee"] = state, stolen, flee
                self.drifters.append(dr)
        if "charms" in sc:
            defaults = {c["id"]: c["pos"] for c in self.charms}
            self.charms = []
            charms = _list(sc["charms"], "charms")
            seen = self._reserve_ids(charms, "charms")
            next_c = [1]
            for i, c in enumerate(charms):
                cid = c.get("id")
                if cid is None:  # auto id C1, C2 ... skipping ids already used
                    taken = seen + [x["id"] for x in self.charms]
                    while f"C{next_c[0]}" in taken:
                        next_c[0] += 1
                    cid = f"C{next_c[0]}"
                    next_c[0] += 1
                if "pos" in c:
                    pos = _vec3(c["pos"], f"charms[{i}].pos")
                elif cid in defaults:
                    pos = list(defaults[cid])
                else:
                    raise ScenarioError(f"charms[{i}].pos is required for a new charm id")
                avail = _bool(c["available"], f"charms[{i}].available") if "available" in c else True
                respawn = 0 if avail else CHARM_RESPAWN_TICKS
                if "respawn_ticks" in c:
                    respawn = _int(c["respawn_ticks"], f"charms[{i}].respawn_ticks")
                elif "respawn_s" in c:
                    if not _is_num(c["respawn_s"]) or c["respawn_s"] < 0:
                        raise ScenarioError(f"charms[{i}].respawn_s must be a number >= 0")
                    respawn = _ticks(c["respawn_s"])
                self.charms.append({"id": cid, "pos": pos, "available": avail,
                                    "respawn": 0 if avail else respawn})
        if "time_left_s" in sc:
            if not _is_num(sc["time_left_s"]) or sc["time_left_s"] < 0:
                raise ScenarioError("time_left_s must be a number >= 0")
            self.time_left_ticks = _ticks(sc["time_left_s"])

    @staticmethod
    def _reserve_ids(items, what):
        given = []
        for i, s in enumerate(items):
            if not isinstance(s, dict):
                raise ScenarioError(f"{what}[{i}] must be an object")
            if "id" in s:
                if not isinstance(s["id"], str) or not s["id"] or s["id"] in given:
                    raise ScenarioError(f"{what}[{i}].id must be a unique string")
                given.append(s["id"])
        return given

    def _new_id(self, prefix, counter, existing, reserved):
        taken = [e["id"] for e in existing] + list(reserved)
        n = getattr(self, counter)
        while f"{prefix}{n}" in taken:
            n += 1
        setattr(self, counter, n + 1)
        return f"{prefix}{n}"

    @staticmethod
    def _make_shade(sid, pos, state, left):
        return {"id": sid, "pos": pos, "home": [pos[0], pos[2]], "state": state, "left": left,
                "push": 0, "push_dir": [1.0, 0.0], "recoil_dir": [1.0, 0.0],
                "expel": 0, "expel_dir": [1.0, 0.0], "expel_step": 0.0,
                "target": None, "wander": 0, "wc": None,
                "tl": None,       # lantern being drained (state "drain")
                "tl0": None,      # scenario target_lantern_id, used once as the first wander target
                "drain_n": 0}     # ticks drained so far (fuel_drain event every 60)

    # ---------------------------------------------------------------- lantern helpers
    @staticmethod
    def _fuel_max_u():
        return int(round(TUNING["fuel_max"] * FUEL_UNIT))

    @staticmethod
    def _low_fuel_u():
        return TUNING["low_fuel_threshold"] * FUEL_UNIT

    @staticmethod
    def _num(x):
        """Per-tick units from a per-second tuning value (1 fuel/s = 1 unit/tick); int when whole."""
        return int(x) if float(x).is_integer() else float(x)

    def _lantern(self, lid):
        for l in self.lanterns:
            if l["id"] == lid:
                return l
        return None

    def _is_weak(self, l):
        """Lit with fuel < 30: no safe zone, shades go for it."""
        return l["lit"] and l["units"] < self._low_fuel_u()

    def _has_safe_zone(self, l):
        return l["lit"] and l["units"] >= self._low_fuel_u()   # exactly 30 still counts

    def _nearest_lantern(self, pos, pred):
        best = None
        for l in self.lanterns:
            if pred(l):
                key = (dist_xz(pos, l["pos"]), _id_key(l["id"]))
                if best is None or key < best[0]:
                    best = (key, l)
        return None if best is None else best[1]

    def _weak_lantern(self, pos):
        return self._nearest_lantern(pos, self._is_weak)

    def capacity(self):
        T = TUNING
        return min(T["capacity_max"],
                   T["carry_capacity"] + CAPACITY_PER_LIGHT * self.player["successful_lights"])

    @staticmethod
    def _make_drifter(did, pos):
        return {"id": did, "pos": pos, "home": [pos[0], pos[2]], "state": "idle", "stolen": 0,
                "flee": 0, "target": None, "wander": 0}

    def _add_mote(self, pos, kind, point=None, ttl=None):
        self.motes.append({"id": f"M{self.next_mote}", "pos": [float(c) for c in pos],
                           "kind": kind, "ttl": ttl, "point": point})
        self.next_mote += 1

    def _away_from_player(self, pos):
        pp = self.player["pos"]
        dx, dz = pos[0] - pp[0], pos[2] - pp[2]
        d = math.hypot(dx, dz)
        return [dx / d, dz / d] if d > 1e-9 else [1.0, 0.0]

    def initial_events(self):
        """Events written right after the tick-0 snapshot."""
        return [{"type": "event", "tick": 0, "name": "night_start", "data": {"night": self.night}}]

    # ----------------------------------------------------------------- step
    def _emit(self, name, data):
        self.events.append({"type": "event", "tick": self.tick, "name": name, "data": data})

    def _end(self, result, reason):
        self.state = result
        if result == "won":
            # Dawn bonus (win only): each lit lantern 50 + floor(fuel), each flame 50, no time bonus
            S = TUNING["score"]
            self.score += S["per_second_left"] * (max(0, self.time_left_ticks) // TICK_HZ)
            for l in self.lanterns:
                if l["lit"]:
                    self.score += S["per_lit_lantern_dawn"] + int(l["units"] // FUEL_UNIT)
            self.score += S["per_flame_left"] * self.player["flames"]
        self._emit("game_over", {"result": result, "reason": reason})

    def step(self, frame=None):
        """Advance one tick. `frame` = dict of changed input fields (or None).
        Returns the list of events produced by this step."""
        self.events = []
        if self.state not in ("playing", "paused"):
            return self.events
        # 1. input (pause first)
        if frame:
            for k in ("move", "cam_yaw_deg") + BUTTONS:
                if k in frame:
                    self.held[k] = frame[k]
        edge = {b: bool(self.held[b]) and not self.prev_buttons[b] for b in BUTTONS}
        self.prev_buttons = {b: bool(self.held[b]) for b in BUTTONS}
        self.tick += 1
        if edge["pause"]:
            if self.state == "playing":
                self.state = "paused"
                self._emit("paused", {})
                return self.events
            self.state = "playing"
            self._emit("resumed", {})
        elif self.state == "paused":
            return self.events
        self.sim_tick += 1

        self._tick_counters()                 # 2
        self._move_player(edge)               # 3
        self._pickups()                       # 4
        self._interact(edge)                  # 5
        self._safe_zones()                    # 6
        self._pulse(edge)                     # 7
        self._move_shades()                   # 8
        self._move_drifters()
        self._collisions()                    # 9
        self._spawns()                        # 10
        self._evaluate()                      # 11
        return self.events

    # 2 ---------------------------------------------------------- counters
    def _tick_counters(self):
        self.time_left_ticks -= 1
        p = self.player
        for k in ("invuln", "dash_cd", "pulse_cd", "charm", "dash", "respawn"):
            if p[k] > 0:
                p[k] -= 1
        if self.wind_ticks > 0:
            self.wind_ticks -= 1
        for s in self.shades:
            for k in ("left", "push", "expel", "wander"):
                if s[k] > 0:
                    s[k] -= 1
        kept = []
        for d in self.drifters:
            if d["wander"] > 0:
                d["wander"] -= 1
            if d["flee"] > 0:
                d["flee"] -= 1
                if d["flee"] == 0 and d["state"] == "flee":
                    continue  # vanished (with whatever it stole)
            kept.append(d)
        self.drifters = kept
        kept = []
        for m in self.motes:
            if m["kind"] == "dropped":
                m["ttl"] -= 1
                if m["ttl"] <= 0:
                    continue
            kept.append(m)
        self.motes = kept
        for c in self.charms:
            if not c["available"]:
                if c["respawn"] > 0:
                    c["respawn"] -= 1
                if c["respawn"] == 0:
                    c["available"] = True
        self._burn_fuel()

    def _burn_fuel(self):
        """Step 2 (Ticket-03): every lit lantern loses 1 unit (1 fuel/s) plus 5 units (5 fuel/s) per
        shade that was draining it on the previous tick; right after, lanterns with fuel <= 0 go out."""
        T = TUNING
        decay = self._num(T["fuel_decay_per_s"])
        drain = self._num(T["drain_per_s"])
        drainers = {}
        for s in sorted(self.shades, key=lambda s: _id_key(s["id"])):
            if s["state"] == "drain" and s["tl"] is not None:
                drainers.setdefault(s["tl"], []).append(s)
        for l in self.lanterns:
            if not l["lit"]:
                continue
            ds = drainers.get(l["id"], ())
            l["units"] -= decay + drain * len(ds)
            for s in ds:
                s["drain_n"] += 1
                if s["drain_n"] % DRAIN_EVENT_TICKS == 0:
                    self._emit("fuel_drain", {"lantern_id": l["id"], "shade_id": s["id"],
                                              "fuel": r1(max(0, l["units"]) / FUEL_UNIT)})
        for l in self.lanterns:
            if l["lit"] and l["units"] <= 0:
                l["lit"] = False
                l["units"] = 0
                l["deposited"] = 0
                l["ever_lit"] = True
                self._emit("lantern_out", {"lantern_id": l["id"]})

    # 3 ---------------------------------------------------------- player
    def _try_step(self, x, z, dx, dz, y):
        """Horizontal step; walls (ground > foot + STEP_UP) block, then slide per axis."""
        if dx == 0.0 and dz == 0.0:
            return x, z
        for cx, cz in ((x + dx, z + dz), (x + dx, z), (x, z + dz)):
            g = self._ground(cx, cz)
            if g is None or g <= y + STEP_UP + EPS:
                return cx, cz
        return x, z

    def _move_player(self, edge):
        T = TUNING
        p = self.player
        pos = p["pos"]
        # wind schedule (Night 3): direction chosen 120 ticks before each gust
        if self.wind_enabled:
            st = self.sim_tick
            if st % WIND_EVERY_TICKS == WIND_EVERY_TICKS - WIND_WARN_TICKS:
                self.wind_pending = self.rng.uniform(0.0, 360.0)
            if st > 0 and st % WIND_EVERY_TICKS == 0 and self.wind_pending is not None:
                self.wind_dir = self.wind_pending
                self.wind_pending = None
                self.wind_ticks = WIND_TICKS
        if p["respawning"]:
            p["vel"] = [0.0, 0.0, 0.0]
            p["vy"] = 0.0
            if p["respawn"] > 0:
                return
            # respawn at the night's start point
            p["respawning"] = False
            p["pos"] = list(self.start_pos)
            p["grounded"] = True
            p["invuln"] = _ticks(T["invuln_s"])
            p["facing"] = [0.0, 1.0]
            p["dash"] = 0
            p["launched"] = False
            return

        # input -> world direction (camera relative)
        mx, mz = self.held["move"]
        ln = math.hypot(mx, mz)
        if ln > 1.0:
            mx, mz = mx / ln, mz / ln
        th = math.radians(self.held["cam_yaw_deg"])
        wx = mx * math.cos(th) + mz * math.sin(th)
        wz = -mx * math.sin(th) + mz * math.cos(th)
        wl = math.hypot(wx, wz)
        moving = wl > 1e-9

        if edge["dash"] and p["dash"] == 0 and (p["dash_cd"] == 0 or p["charm"] > 0):
            p["dash_dir"] = [wx / wl, wz / wl] if moving else list(p["facing"])
            p["dash"] = _ticks(T["dash_duration_s"])
            p["dash_cd"] = 0 if p["charm"] > 0 else _ticks(T["dash_cooldown_s"])
            self._emit("dash", {})
        dashing = p["dash"] > 0

        if dashing:
            hx, hz = p["dash_dir"][0] * T["dash_speed"], p["dash_dir"][1] * T["dash_speed"]
        elif p["launched"]:
            hx, hz = p["launch_v"]
        else:
            speed = CHARM_SPEED if p["charm"] > 0 else T["player_speed"]
            hx, hz = wx * speed, wz * speed
            if moving:
                p["facing"] = [wx / wl, wz / wl]
        if self.wind_ticks > 0:
            a = math.radians(self.wind_dir)
            hx += WIND_SPEED * math.cos(a)
            hz += WIND_SPEED * math.sin(a)

        ox, oz = pos[0], pos[2]
        pos[0], pos[2] = self._try_step(ox, oz, hx * DT, hz * DT, pos[1])
        g = self._ground(pos[0], pos[2])

        if dashing:
            p["vy"] = 0.0  # dash holds height, no gravity
            if p["grounded"]:
                if g is not None and pos[1] - g <= STEP_UP + EPS:
                    pos[1] = g
                else:
                    p["grounded"] = False
            elif g is not None and pos[1] <= g:
                pos[1] = g
                p["grounded"] = True
                p["launched"] = False
        else:
            if edge["jump"] and p["grounded"]:
                p["vy"] = JUMP_SPEED
                p["grounded"] = False
            elif p["grounded"]:
                if g is not None and pos[1] - g <= STEP_UP + EPS:
                    pos[1] = g
                    p["vy"] = 0.0
                else:
                    p["grounded"] = False
                    p["vy"] = 0.0
            if not p["grounded"]:
                pos[1] += p["vy"] * DT
                p["vy"] -= GRAVITY * DT
                if g is not None and pos[1] <= g and p["vy"] <= 0:
                    pos[1] = g
                    p["vy"] = 0.0
                    p["grounded"] = True
                    p["launched"] = False
        p["vel"] = [(pos[0] - ox) / DT, p["vy"], (pos[2] - oz) / DT]

        # jump pads
        if p["grounded"] and not dashing:
            for pad in self.pads:
                pp = pad["pos"]
                if dist_xz(pos, pp) <= pad["radius"] + EPS and abs(pos[1] - pp[1]) < 0.05:
                    p["vy"] = pad["vy"]
                    p["launch_v"] = list(pad["vh"])
                    p["launched"] = True
                    p["grounded"] = False
                    break

        # fell off the island
        if T["fall_enabled"] and pos[1] < FALL_Y:
            lost = p["carried"]
            p["carried"] = 0
            p["flames"] = max(0, p["flames"] - 1)
            p["respawning"] = True
            p["respawn"] = RESPAWN_WAIT_TICKS
            p["vy"] = 0.0
            p["vel"] = [0.0, 0.0, 0.0]
            p["dash"] = 0
            p["launched"] = False
            self._emit("player_hit", {"by": "fall", "flames": p["flames"], "dropped": 0, "lost": lost})

    # 4 ---------------------------------------------------------- pickups
    def _reach(self, obj_pos):
        pos = self.player["pos"]
        return (dist_xz(pos, obj_pos) <= TUNING["pickup_radius"] + EPS
                and abs(pos[1] - obj_pos[1]) <= PICKUP_DY + EPS)

    def _pickups(self):
        p = self.player
        if p["respawning"]:
            return
        cap = self.capacity()
        kept = []
        for m in self.motes:
            if p["carried"] < cap and self._reach(m["pos"]):
                p["carried"] += 1
                self._emit("mote_picked", {"carried": p["carried"]})
            else:
                kept.append(m)
        self.motes = kept
        for c in self.charms:
            if c["available"] and self._reach(c["pos"]):
                c["available"] = False
                c["respawn"] = CHARM_RESPAWN_TICKS
                p["charm"] = CHARM_TICKS
                self._emit("charm_picked", {"charm_id": c["id"], "charm_ticks": CHARM_TICKS})

    # 5 ---------------------------------------------------------- lanterns
    def _interact(self, edge):
        T = TUNING
        p = self.player
        pos = p["pos"]
        if not edge["interact"] or p["carried"] <= 0 or p["respawning"]:
            return
        S = T["score"]
        # Candidates: an unlit lantern, or a lit one that can still take fuel (used > 0).
        cands = [l for l in self.lanterns
                 if dist_xz(pos, l["pos"]) <= T["interact_radius"] + EPS
                 and (not l["lit"] or self._refuel_amount(l) > 0)]
        if not cands:
            return
        l = min(cands, key=lambda l: (dist_xz(pos, l["pos"]), _id_key(l["id"])))
        if l["lit"]:
            # Refuel: used = min(carried, ceil((100 - fuel) / 10)), fuel += 10 per mote, capped at 100
            used = self._refuel_amount(l)
            p["carried"] -= used
            l["units"] = min(self._fuel_max_u(), l["units"] + used * T["fuel_per_mote"] * FUEL_UNIT)
            self.score += S["per_mote"] * used
            self._emit("refuel", {"lantern_id": l["id"], "amount": used,
                                  "fuel": r1(l["units"] / FUEL_UNIT)})
            return
        cost = T["relight_cost"] if l["ever_lit"] else T["lantern_cost"]
        amount = min(p["carried"], cost - l["deposited"])
        if amount > 0:
            p["carried"] -= amount
            l["deposited"] += amount
            self.score += S["per_mote"] * amount
            self._emit("deposit", {"lantern_id": l["id"], "amount": amount, "deposited": l["deposited"]})
        if l["deposited"] >= cost:
            relight = l["ever_lit"]
            l["lit"] = True
            l["units"] = self._fuel_max_u()
            l["ever_lit"] = True
            p["successful_lights"] += 1        # capacity grows (relights count, scenario-placed lamps don't)
            if relight:
                l["relit_count"] += 1
                self.score += S["per_relight"]
            else:
                self.score += S["per_lantern"]
            self._emit("lantern_lit", {"lantern_id": l["id"], "relight": relight})

    def _refuel_amount(self, l):
        """Motes a lit lantern would take now: min(carried, ceil((fuel_max - fuel) / fuel_per_mote))."""
        per = TUNING["fuel_per_mote"] * FUEL_UNIT
        missing = self._fuel_max_u() - l["units"]
        if missing <= 0:
            return 0
        return min(self.player["carried"], int(math.ceil(round(missing / per, 9))))

    # 6 ---------------------------------------------------------- safe zones
    def _safe_zones(self):
        R = TUNING["safe_radius"]
        lit = [l for l in self.lanterns if self._has_safe_zone(l)]   # lit and fuel >= 30
        for s in self.shades:
            if s["expel"] == 0:
                for l in lit:
                    dx, dz = s["pos"][0] - l["pos"][0], s["pos"][2] - l["pos"][2]
                    d0 = math.hypot(dx, dz)
                    if d0 < R - EPS:
                        s["expel"] = EXPEL_TICKS
                        s["expel_dir"] = [dx / d0, dz / d0] if d0 > 1e-9 else [1.0, 0.0]
                        s["expel_step"] = max((R - d0) / EXPEL_TICKS, 0.0)
                        if s["state"] == "drain":   # pushed out of the light -> back to wandering
                            s["state"], s["tl"], s["target"] = "wander", None, None
                        break
            if s["expel"] > 0:
                s["pos"][0] += s["expel_dir"][0] * s["expel_step"]
                s["pos"][2] += s["expel_dir"][1] * s["expel_step"]
                self._fix_shade(s, keep_out=False)

    def _keep_out_of_light(self, s):
        R = TUNING["safe_radius"]
        for l in self.lanterns:
            if not self._has_safe_zone(l):
                continue
            dx, dz = s["pos"][0] - l["pos"][0], s["pos"][2] - l["pos"][2]
            dd = math.hypot(dx, dz)
            if dd < R - EPS:
                ux, uz = (dx / dd, dz / dd) if dd > 1e-9 else (1.0, 0.0)
                s["pos"][0] = l["pos"][0] + ux * R
                s["pos"][2] = l["pos"][2] + uz * R

    def _tower_out(self, e):
        """Night 3: push an entity out of the bell tower. Returns True if it was inside."""
        if self.night != 3:
            return False
        x, z = e["pos"][0], e["pos"][2]
        r = math.hypot(x, z)
        if r >= TOWER_R:
            return False
        if r > 1e-9:
            e["pos"][0], e["pos"][2] = x / r * TOWER_R, z / r * TOWER_R
        else:
            e["pos"][0], e["pos"][2] = TOWER_R, 0.0
        return True

    def _fix_shade(self, s, keep_out=True):
        self._tower_out(s)
        if keep_out:
            self._keep_out_of_light(s)
        s["pos"][1] = self._floor_y(s["pos"][0], s["pos"][2]) + SHADE_Y_OFFSET

    # 7 ---------------------------------------------------------- pulse
    def _pulse(self, edge):
        T = TUNING
        p = self.player
        if (not edge["pulse"] or p["respawning"] or p["pulse_cd"] > 0
                or p["carried"] < T["pulse_cost"]):
            return
        p["carried"] -= T["pulse_cost"]
        p["pulse_cd"] = _ticks(T["pulse_cooldown_s"])
        pos = p["pos"]
        c = (pos[0], pos[1] + PULSE_CENTER_DY, pos[2])
        R = T["pulse_radius"] + EPS

        def in_range(e):
            q = e["pos"]
            return math.sqrt((q[0] - c[0]) ** 2 + (q[1] - c[1]) ** 2 + (q[2] - c[2]) ** 2) <= R

        ids = []
        for s in sorted(self.shades, key=lambda s: _id_key(s["id"])):
            if in_range(s):
                # +5 per shade, +15 in total if it was draining a lantern right before the hit
                self.score += T["score"]["per_drain_stun" if s["state"] == "drain" else "per_stun"]
                s["state"] = "stunned"
                s["tl"] = None
                s["left"] = _ticks(T["pulse_stun_s"])
                s["push"] = PUSH_TICKS
                s["push_dir"] = self._away_from_player(s["pos"])
                ids.append(s["id"])
        for d in sorted(self.drifters, key=lambda d: _id_key(d["id"])):
            if not in_range(d):
                continue
            if d["state"] == "chase":
                d["state"] = "flee"
                d["flee"] = DRIFTER_FLEE_TICKS
            elif d["state"] == "flee" and d["stolen"] > 0:
                amount = d["stolen"]
                y = self._ground(d["pos"][0], d["pos"][2])
                y = pos[1] if y is None else y
                for _ in range(amount):
                    self._add_mote([d["pos"][0], y, d["pos"][2]], "dropped", ttl=DROP_TTL_TICKS)
                d["stolen"] = 0
                d["flee"] = DRIFTER_DROP_FLEE_TICKS
                self._emit("drifter_drop", {"drifter_id": d["id"], "amount": amount})
        self._emit("pulse", {"stunned_ids": ids})

    # 8 ---------------------------------------------------------- shades / drifters
    def _pick_target(self, e, radius, center=None):
        cx, cz = (e["home"][0], e["home"][1]) if center is None else center
        a = self.rng.uniform(0.0, 2.0 * math.pi)
        r = radius * math.sqrt(self.rng.random())
        e["target"] = [cx + r * math.cos(a), cz + r * math.sin(a)]
        e["wander"] = WANDER_RETARGET_TICKS
        e["wc"] = center

    @staticmethod
    def _toward(e, tx, tz, speed):
        dx, dz = tx - e["pos"][0], tz - e["pos"][2]
        d = math.hypot(dx, dz)
        if d > 1e-9:
            k = min(speed * DT, d) / d
            e["pos"][0] += dx * k
            e["pos"][2] += dz * k
        return d

    def _wander(self, e, radius, speed, center=None):
        """Roam at `speed` toward a random point within `radius` of `center` (default: the entity's
        home). A new point is drawn on arrival, every 180 ticks, or when the centre changes."""
        t = e["target"]
        if (t is None or e["wander"] == 0 or e.get("wc") != center
                or math.hypot(t[0] - e["pos"][0], t[1] - e["pos"][2]) < 1e-9):
            self._pick_target(e, radius, center)
            t = e["target"]
        self._toward(e, t[0], t[1], speed)

    def _shade_wander(self, s):
        """Ticket-03 wander: head for the nearest weak lit lantern (and drain it once within 2 m);
        else the nearest unlit lantern (walk to 4 m, then roam within 6 m of it); else roam at home."""
        pos = s["pos"]
        tl0, s["tl0"] = s["tl0"], None      # scenario target_lantern_id: only for the first choice
        lant = self._lantern(tl0) if tl0 is not None else None
        if lant is not None and not (self._is_weak(lant) or not lant["lit"]):
            lant = None
        if lant is None:
            lant = self._weak_lantern(pos)
        if lant is not None and lant["lit"]:
            if dist_xz(pos, lant["pos"]) <= DRAIN_RANGE + EPS:
                s["state"], s["tl"], s["drain_n"], s["target"] = "drain", lant["id"], 0, None
                return
            self._toward(s, lant["pos"][0], lant["pos"][2], SHADE_WANDER_SPEED)
            return
        if lant is None:
            lant = self._nearest_lantern(pos, lambda l: not l["lit"])
        if lant is None:
            self._wander(s, SHADE_WANDER_R, SHADE_WANDER_SPEED)
            return
        c = (lant["pos"][0], lant["pos"][2])
        if s["wc"] != c and dist_xz(pos, lant["pos"]) > LANTERN_APPROACH_M + EPS:
            self._toward(s, c[0], c[1], SHADE_WANDER_SPEED)     # still on the way
        else:
            self._wander(s, SHADE_WANDER_R, SHADE_WANDER_SPEED, c)   # circle the lantern

    def _move_shades(self):
        ppos = self.player["pos"]
        push_step = TUNING["pulse_push_m"] / PUSH_TICKS
        for s in self.shades:
            if s["push"] > 0:
                s["pos"][0] += s["push_dir"][0] * push_step
                s["pos"][2] += s["push_dir"][1] * push_step
                if self._tower_out(s):
                    s["push"] = 0  # blocked by the bell tower
                self._fix_shade(s, keep_out=s["expel"] == 0)
            if s["expel"] > 0:
                continue  # being pushed out of a safe zone (step 6)
            st = s["state"]
            if st == "spawning":
                if s["left"] > 0:
                    continue
                st = s["state"] = "wander"
                s["target"] = None
            elif st in ("stunned", "recoil"):
                if s["left"] > 0:
                    if st == "recoil":
                        self._recoil_step(s)
                    continue
                if st == "stunned":     # Ticket-03: stun always ends in wander
                    st = s["state"] = "wander"
                else:                   # recoil ends as in Phase 2
                    st = s["state"] = "chase" if dist_xz(ppos, s["pos"]) <= SHADE_LOSE + EPS else "wander"
                s["target"] = None
            d = dist_xz(ppos, s["pos"])
            if st == "drain":
                lant = self._lantern(s["tl"]) if s["tl"] is not None else None
                if d <= DRAIN_ALERT + EPS:
                    st = s["state"] = "chase"
                elif (lant is None or not self._is_weak(lant)
                      or dist_xz(s["pos"], lant["pos"]) > DRAIN_RANGE + EPS):
                    st = s["state"] = "wander"      # lantern out / refuelled to >= 30 / too far
                if st != "drain":
                    s["tl"], s["target"] = None, None
            if st == "wander" and d <= SHADE_DETECT + EPS:
                st = s["state"] = "chase"
            elif st == "chase" and d > SHADE_LOSE + EPS:
                st = s["state"] = "wander"
                s["target"] = None
            if st == "chase":
                self._toward(s, ppos[0], ppos[2], self.shade_speed)
            elif st == "wander":
                self._shade_wander(s)       # may switch to "drain" (and then stands still)
            self._fix_shade(s)

    def _recoil_step(self, s):
        k = RECOIL_M / RECOIL_TICKS
        s["pos"][0] += s["recoil_dir"][0] * k
        s["pos"][2] += s["recoil_dir"][1] * k
        self._fix_shade(s)

    def _move_drifters(self):
        p = self.player
        ppos = p["pos"]
        for d in self.drifters:
            if d["state"] == "flee":
                ux, uz = self._away_from_player(d["pos"])
                d["pos"][0] += ux * DRIFTER_SPEED * DT
                d["pos"][2] += uz * DRIFTER_SPEED * DT
            else:
                want = (not p["respawning"] and p["carried"] >= DRIFTER_CHASE_CARRY
                        and dist_xz(ppos, d["pos"]) <= DRIFTER_CHASE_DIST + EPS)
                if d["state"] == "idle" and want:
                    d["state"] = "chase"
                elif d["state"] == "chase" and not want:
                    d["state"] = "idle"
                    d["target"] = None
                if d["state"] == "chase":
                    self._toward(d, ppos[0], ppos[2], DRIFTER_SPEED)
                else:
                    self._wander(d, DRIFTER_WANDER_R, DRIFTER_IDLE_SPEED)
            self._tower_out(d)
            d["pos"][1] = self._floor_y(d["pos"][0], d["pos"][2]) + DRIFTER_Y_OFFSET

    # 9 ---------------------------------------------------------- collisions
    def _collisions(self):
        T = TUNING
        p = self.player
        pos = p["pos"]
        if p["respawning"]:
            return
        for d in sorted(self.drifters, key=lambda d: _id_key(d["id"])):
            if (d["state"] in ("idle", "chase") and p["carried"] > 0
                    and dist_xz(pos, d["pos"]) <= DRIFTER_TOUCH + EPS):
                amount = min(DRIFTER_STEAL, p["carried"])
                p["carried"] -= amount
                d["stolen"] = amount
                d["state"] = "flee"
                d["flee"] = DRIFTER_FLEE_TICKS
                self._emit("drifter_steal", {"drifter_id": d["id"], "amount": amount,
                                             "carried": p["carried"]})
        if p["invuln"] > 0:
            return
        for s in sorted(self.shades, key=lambda s: _id_key(s["id"])):
            if (s["state"] in ("chase", "wander", "drain") and s["expel"] == 0
                    and dist_xz(pos, s["pos"]) <= T["shade_hit_radius"] + EPS
                    and abs(pos[1] - s["pos"][1]) <= HIT_DY + EPS):
                p["flames"] = max(0, p["flames"] - 1)
                dropped = int(math.floor(p["carried"] * T["hit_drop_ratio"]))
                p["carried"] -= dropped
                for _ in range(dropped):
                    a = self.rng.uniform(0.0, 2.0 * math.pi)
                    r = self.rng.uniform(DROP_RING[0], DROP_RING[1])
                    x, z = pos[0] + r * math.cos(a), pos[2] + r * math.sin(a)
                    g = self._ground(x, z)
                    self._add_mote([x, pos[1] if g is None else g, z], "dropped", ttl=DROP_TTL_TICKS)
                p["invuln"] = _ticks(T["invuln_s"])
                self._emit("player_hit", {"by": "shade", "flames": p["flames"], "dropped": dropped})
                s["state"] = "recoil"
                s["left"] = RECOIL_TICKS
                s["push"] = 0
                s["recoil_dir"] = self._away_from_player(s["pos"])
                self._recoil_step(s)  # first of 60 recoil steps (2 m over ticks t..t+59)
                break

    # 10 --------------------------------------------------------- spawns
    def _spawns(self):
        st = self.sim_tick
        ppos = self.player["pos"]
        if self.random_motes and st % MOTE_RESPAWN_TICKS == 0 and len(self.motes) < MOTE_CAP:
            used = [m["point"] for m in self.motes if m["kind"] == "random" and m["point"] is not None]
            free = [k for k in range(len(self.mote_points)) if k not in used]
            if free:
                k = self.rng.choice(free)
                self._add_mote(list(self.mote_points[k]), "random", point=k)
        if self.random_shades:
            n = 0
            if st == SHADE_FIRST_TICK:
                n = SHADE_FIRST_COUNT
            elif st > SHADE_FIRST_TICK and (st - SHADE_FIRST_TICK) % self.shade_interval == 0:
                n = 1
            n = min(n, self.shade_max - len(self.shades))
            taken = []
            for _ in range(max(0, n)):
                valid = [k for k, pt in enumerate(self.shade_points)
                         if k not in taken and dist_xz(pt, ppos) >= SPAWN_MIN_DIST - EPS]
                if not valid:
                    break
                k = self.rng.choice(valid)
                taken.append(k)
                pt = self.shade_points[k]
                sid = self._new_id("S", "next_shade", self.shades, self.reserved_shade_ids)
                pos = [pt[0], pt[1] + SHADE_Y_OFFSET, pt[2]]
                self.shades.append(self._make_shade(sid, pos, "spawning", SHADE_SPAWNING_TICKS))
                self._emit("shade_spawned", {"id": sid})
        if (self.random_drifters and st % DRIFTER_EVERY_TICKS == 0
                and len(self.drifters) < DRIFTER_MAX):
            valid = [k for k, pt in enumerate(self.shade_points)
                     if dist_xz(pt, ppos) >= SPAWN_MIN_DIST - EPS]
            if valid:
                pt = self.shade_points[self.rng.choice(valid)]
                did = self._new_id("D", "next_drifter", self.drifters, self.reserved_drifter_ids)
                self.drifters.append(self._make_drifter(did, [pt[0], pt[1] + DRIFTER_Y_OFFSET, pt[2]]))

    # 11 --------------------------------------------------------- win / lose
    def _evaluate(self):
        if self.player["flames"] <= 0:
            self._end("lost", "no_flames")
        elif self.time_left_ticks <= 0:     # dawn: no early win any more
            lit = sum(1 for l in self.lanterns if l["lit"])
            needed = math.ceil(round(TUNING["win_ratio"] * len(self.lanterns), 9))
            if lit >= needed:
                self._end("won", "dawn_survived")
            else:
                self._end("lost", "dawn")

    # ------------------------------------------------------------- snapshot
    def snapshot(self):
        p = self.player
        return {
            "type": "snapshot",
            "tick": self.tick,
            "sim_tick": self.sim_tick,
            "night": self.night,
            "state": self.state,
            "time_left_s": r3(max(0, self.time_left_ticks) / TICK_HZ),
            "score": self.score,
            "wind": {"active": self.wind_ticks > 0, "dir_deg": r3(self.wind_dir)},
            "player": {"pos": [r3(c) for c in p["pos"]], "vel": [r3(c) for c in p["vel"]],
                       "grounded": p["grounded"], "flames": p["flames"], "carried": p["carried"],
                       "capacity": self.capacity(),
                       "invuln": p["invuln"] > 0, "dash_cd_s": r3(p["dash_cd"] / TICK_HZ),
                       "pulse_cd_s": r3(p["pulse_cd"] / TICK_HZ), "charm_s": r3(p["charm"] / TICK_HZ)},
            "lanterns": [{"id": l["id"], "pos": [r3(c) for c in l["pos"]], "lit": l["lit"],
                          "deposited": l["deposited"],
                          "fuel": r1(l["units"] / FUEL_UNIT) if l["lit"] else 0.0,
                          "ever_lit": l["ever_lit"], "relit_count": l["relit_count"]}
                         for l in self.lanterns],
            "shades": [{"id": s["id"], "pos": [r3(c) for c in s["pos"]], "state": s["state"]}
                       for s in self.shades],
            "motes_active": len(self.motes),
            "motes": [{"id": m["id"], "pos": [r3(c) for c in m["pos"]], "kind": m["kind"],
                       "ttl_s": None if m["ttl"] is None else r3(m["ttl"] / TICK_HZ)}
                      for m in self.motes],
            "drifters": [{"id": d["id"], "pos": [r3(c) for c in d["pos"]], "state": d["state"],
                          "stolen": d["stolen"]} for d in self.drifters],
            "charms": [{"id": c["id"], "available": c["available"],
                        "respawn_s": r3(c["respawn"] / TICK_HZ)} for c in self.charms],
        }

    def extra(self):
        """UI-only hints for the web client (not part of the headless contract)."""
        p = self.player
        return {"dash_ready": (p["dash"] == 0 and not p["respawning"]
                               and (p["dash_cd"] == 0 or p["charm"] > 0)),
                "pulse_ready": p["pulse_cd"] == 0 and not p["respawning"],
                "wind_warning": None if self.wind_pending is None else r3(self.wind_pending),
                "respawning": p["respawning"]}


# ------------------------------------------------------------------ web glue
_web_game = None


def web_new(seed, night=1):
    global _web_game
    _web_game = Game(int(seed), None, int(night))
    return _web_json({"events": _web_game.initial_events(), "snap": _web_game.snapshot(),
                      "extra": _web_game.extra()})


def web_step(frame_json):
    import json
    frame = json.loads(frame_json) if isinstance(frame_json, str) else frame_json
    ev = _web_game.step(frame if isinstance(frame, dict) else None)
    return _web_json({"events": ev, "snap": _web_game.snapshot(), "extra": _web_game.extra()})


def web_map(night):
    return _web_json(maps.describe(int(night)))


def _web_json(o):
    import json
    return json.dumps(o, separators=(",", ":"))
