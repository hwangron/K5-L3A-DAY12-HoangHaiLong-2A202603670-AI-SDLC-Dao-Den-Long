"""Dao Den Long - standard maps for Nights 1-3 (Ticket-02 Part 2, design doc section 4).

Pure data + geometry, stdlib only. Angle convention: measured from +X,
counter-clockwise seen from above:  x = r*cos(theta), z = r*sin(theta).
`ground_height` returns the walkable surface Y under (x, z), or None for the
cloud sea (falling).
"""
import math

NIGHTS = (1, 2, 3)
EPS = 1e-6

ISLAND_NAMES = {1: "Đảo Bến", 2: "Đảo Cau", 3: "Đảo Chuông"}

# ------------------------------------------------------------------ geometry
N1_RADIUS = 40.0

N2_ISLANDS = ((0.0, 0.0), (70.0, 0.0))
N2_RADIUS = 28.0
N2_BRIDGE_X = (26.0, 44.0)
N2_BRIDGE_Z = (-2.0, 2.0)

N3_RADIUS = 45.0
N3_TOWER_R = 2.0
N3_TOWER_TOP = 14.0          # tier 2 (6) + 8 m bell tower: acts as a wall
N3_TOWER_HEIGHT = 8.0
N3_TIER2_R = 8.0
N3_TIER2_Y = 6.0
N3_TIER1_R = (12.0, 24.0)    # annulus, only the half with z > 0
N3_TIER1_Y = 3.0
N3_RAMP_ANGLES = (30.0, 150.0)
N3_RAMP_S = (24.0, 30.0)     # top (Y=3) at s=24, foot (Y=0) at s=30
N3_RAMP_HALF_W = 1.5         # 3 m wide


def _clean(v):
    v = round(v, 6)
    return 0.0 if v == 0 else v


def _polar(r, deg, y=0.0):
    a = math.radians(deg)
    return [_clean(r * math.cos(a)), float(y), _clean(r * math.sin(a))]


def _ramp_height(x, z):
    for deg in N3_RAMP_ANGLES:
        a = math.radians(deg)
        ux, uz = math.cos(a), math.sin(a)
        s = x * ux + z * uz
        d = abs(-x * uz + z * ux)
        if N3_RAMP_S[0] - EPS <= s <= N3_RAMP_S[1] + EPS and d <= N3_RAMP_HALF_W + EPS:
            return N3_TIER1_Y * (N3_RAMP_S[1] - s) / (N3_RAMP_S[1] - N3_RAMP_S[0])
    return None


def ground_height(night, x, z):
    """Surface Y at (x, z) or None (cloud sea)."""
    if night == 1:
        return 0.0 if math.hypot(x, z) <= N1_RADIUS + EPS else None
    if night == 2:
        for cx, cz in N2_ISLANDS:
            if math.hypot(x - cx, z - cz) <= N2_RADIUS + EPS:
                return 0.0
        if (N2_BRIDGE_X[0] - EPS <= x <= N2_BRIDGE_X[1] + EPS
                and N2_BRIDGE_Z[0] - EPS <= z <= N2_BRIDGE_Z[1] + EPS):
            return 0.0
        return None
    if night == 3:
        r = math.hypot(x, z)
        if r > N3_RADIUS + EPS:
            return None
        if r < N3_TOWER_R - EPS:
            return N3_TOWER_TOP
        if r <= N3_TIER2_R + EPS:
            return N3_TIER2_Y
        if N3_TIER1_R[0] - EPS <= r <= N3_TIER1_R[1] + EPS and z > 0:
            return N3_TIER1_Y
        h = _ramp_height(x, z)
        if h is not None:
            return h
        return 0.0
    raise ValueError(f"unknown night {night}")


def _on_ground(night, pts):
    out = []
    for p in pts:
        g = ground_height(night, p[0], p[2])
        out.append([p[0], 0.0 if g is None else g, p[2]])
    return out


# ------------------------------------------------------------------ map data
def _n1_motes():
    return ([_polar(12.0, 45.0 * k) for k in range(8)]
            + [_polar(33.0, 22.5 * k) for k in range(16)])


def _n2_motes():
    out = []
    for cx, cz in N2_ISLANDS:
        for p in [_polar(10.0, 90.0 * k) for k in range(4)] + [_polar(22.0, 45.0 * k) for k in range(8)]:
            out.append([_clean(p[0] + cx), 0.0, _clean(p[2] + cz)])
    return out


def _n3_motes():
    return _on_ground(3, [_polar(34.0, 20.0 * k) for k in range(18)]
                      + [_polar(18.0, 20.0 * k) for k in range(1, 9)]
                      + [_polar(5.0, 45.0 + 90.0 * k) for k in range(4)])


def _n2_shades():
    out = []
    for cx, cz in N2_ISLANDS:
        for k in range(8):
            p = _polar(26.0, 22.5 + 45.0 * k)
            out.append([_clean(p[0] + cx), 0.0, _clean(p[2] + cz)])
    return out


def _dir_to(src, dst):
    dx, dz = dst[0] - src[0], dst[1] - src[1]
    d = math.hypot(dx, dz)
    return [dx / d, dz / d]


def _pad(pos, vy, h_speed, direction):
    return {"pos": [float(c) for c in pos], "radius": 1.0, "vy": float(vy),
            "vh": [h_speed * direction[0], h_speed * direction[1]]}


_MAPS = {
    1: {
        "start": [0.0, 0.0, 0.0],
        "lanterns": [[0.0, 0.0, 25.0], [23.8, 0.0, 7.7], [14.7, 0.0, -20.2],
                     [-14.7, 0.0, -20.2], [-23.8, 0.0, 7.7]],
        "mote_points": _n1_motes(),
        "shade_points": [_polar(37.0, 15.0 + 30.0 * k) for k in range(12)],
        "charms": [],
        "pads": [],
        "shade_interval_ticks": 480,
        "shade_max": 6,
        "has_drifters": False,
        "has_wind": False,
    },
    2: {
        "start": [0.0, 0.0, 0.0],
        "lanterns": [[0.0, 0.0, 20.0], [17.0, 0.0, -10.0], [-17.0, 0.0, -10.0],
                     [70.0, 0.0, 20.0], [87.0, 0.0, -10.0], [53.0, 0.0, -10.0]],
        "mote_points": _n2_motes(),
        "shade_points": _n2_shades(),
        "charms": [["C1", [35.0, 0.0, 0.0]]],
        "pads": [_pad((20.0, 0.0, 18.0), 14.0, 24.0, _dir_to((20.0, 18.0), N2_ISLANDS[1])),
                 _pad((50.0, 0.0, -18.0), 14.0, 24.0, _dir_to((50.0, -18.0), N2_ISLANDS[0]))],
        "shade_interval_ticks": 420,
        "shade_max": 8,
        "has_drifters": True,
        "has_wind": False,
    },
    3: {
        "start": [0.0, 0.0, -30.0],
        "lanterns": [[0.0, 6.0, 6.0], [18.0, 3.0, 10.0], [-18.0, 3.0, 10.0],
                     [35.0, 0.0, -10.0], [-35.0, 0.0, -10.0], [20.0, 0.0, -35.0],
                     [-20.0, 0.0, -35.0]],
        "mote_points": _n3_motes(),
        "shade_points": _on_ground(3, [_polar(43.0, 22.5 * k) for k in range(16)]),
        "charms": [["C1", [30.0, 0.0, 25.0]], ["C2", [-30.0, 0.0, 25.0]]],
        "pads": [_pad((0.0, 3.0, 13.0), 12.0, 8.0, (0.0, -1.0))],
        "shade_interval_ticks": 360,
        "shade_max": 10,
        "has_drifters": True,
        "has_wind": True,
    },
}


def _m(night):
    if night not in _MAPS:
        raise ValueError(f"unknown night {night}")
    return _MAPS[night]


def _copy(pts):
    return [list(p) for p in pts]


def island_name(night):
    _m(night)
    return ISLAND_NAMES[night]


def start(night):
    return list(_m(night)["start"])


def lanterns(night):
    """[[x, y, z], ...] in id order L1, L2, ..."""
    return _copy(_m(night)["lanterns"])


def mote_points(night):
    return _copy(_m(night)["mote_points"])


def shade_points(night):
    return _copy(_m(night)["shade_points"])


def charms(night):
    """[(id, [x, y, z]), ...]"""
    return [(cid, list(pos)) for cid, pos in _m(night)["charms"]]


def jump_pads(night):
    """[{pos, radius, vy, vh: [vx, vz]}, ...]"""
    return [{"pos": list(p["pos"]), "radius": p["radius"], "vy": p["vy"], "vh": list(p["vh"])}
            for p in _m(night)["pads"]]


def shade_interval_ticks(night):
    return _m(night)["shade_interval_ticks"]


def shade_max(night):
    return _m(night)["shade_max"]


def duration_ticks(night, tuning):
    """Night length in ticks, read from the TUNING dict (single source of truth)."""
    _m(night)
    return int(round(tuning[f"night{night}_duration_s"] * 60))


def has_drifters(night):
    return _m(night)["has_drifters"]


def has_wind(night):
    return _m(night)["has_wind"]


def describe(night):
    """Geometry for the web renderer (web_map)."""
    m = _m(night)
    d = {"night": night, "name": ISLAND_NAMES[night], "islands": [], "bridges": [], "tiers": [],
         "ramps": [], "tower": None}
    if night == 1:
        d["islands"] = [{"center": [0.0, 0.0], "radius": N1_RADIUS, "y": 0.0}]
    elif night == 2:
        d["islands"] = [{"center": [cx, cz], "radius": N2_RADIUS, "y": 0.0} for cx, cz in N2_ISLANDS]
        d["bridges"] = [{"x": list(N2_BRIDGE_X), "z": list(N2_BRIDGE_Z), "y": 0.0}]
    else:
        d["islands"] = [{"center": [0.0, 0.0], "radius": N3_RADIUS, "y": 0.0}]
        d["tiers"] = [{"kind": "annulus", "r": list(N3_TIER1_R), "half": "z>0", "y": N3_TIER1_Y},
                      {"kind": "disk", "r": N3_TIER2_R, "y": N3_TIER2_Y}]
        d["ramps"] = [{"angle_deg": a, "s": list(N3_RAMP_S), "width": 2 * N3_RAMP_HALF_W,
                       "y": [0.0, N3_TIER1_Y]} for a in N3_RAMP_ANGLES]
        d["tower"] = {"pos": [0.0, N3_TIER2_Y, 0.0], "radius": N3_TOWER_R, "height": N3_TOWER_HEIGHT}
    d["pads"] = [{"pos": list(p["pos"]), "radius": p["radius"]} for p in m["pads"]]
    d["lanterns"] = [{"id": f"L{i + 1}", "pos": list(p)} for i, p in enumerate(m["lanterns"])]
    d["charms"] = [{"id": cid, "pos": list(pos)} for cid, pos in m["charms"]]
    d["start"] = list(m["start"])
    d["mote_points"] = _copy(m["mote_points"])
    d["shade_points"] = _copy(m["shade_points"])
    return d
