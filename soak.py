"""Soak test - Ticket-04 part 2 (Test Contract v1.3).

python3 soak.py --seed 7 --nights 10 --out soak.json

Runs N nights back to back in this one process, headless (no rendering). Night i (1-based) is
Night ((i - 1) % 3) + 1 and uses seed SEED + i. Each night runs until it ends or hits the cap
(MAX_TICKS). Input is random but seeded: a fresh unit move vector every 30 ticks (10% of the time
standing still); every tick jump 5%, dash 3%, pulse 2%, interact 10% (held for that tick only, so
each fires on its rising edge).
Output: {"nights", "crashes", "results", "mem_start_mb", "mem_end_mb", "duration_s", "seed", "per_night"}.
Pass: crashes == 0 and mem_end_mb <= 1.2 * mem_start_mb.
An exception inside a night counts as a crash (result "crash") and the soak carries on.
Exit 0 once soak.json is written, 2 on bad arguments, 1 if the file cannot be written.
"""
import argparse
import gc
import json
import math
import os
import random
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game.procmem import rss_mb  # noqa: E402
from game.sim import Game  # noqa: E402

MAX_TICKS = 21600           # 6 minutes at 60 ticks/s: above every night's duration
MOVE_EVERY = 30
P_JUMP, P_DASH, P_PULSE, P_INTERACT = 0.05, 0.03, 0.02, 0.10
P_STILL = 0.10
MEM_RATIO_LIMIT = 1.2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"error: {message}\n")
        sys.exit(2)


def night_for(i):
    return (i - 1) % 3 + 1


def random_move(rng):
    if rng.random() < P_STILL:
        return [0.0, 0.0]
    a = rng.uniform(0.0, 2.0 * math.pi)
    return [round(math.cos(a), 6), round(math.sin(a), 6)]


def play_night(night, seed, max_ticks=MAX_TICKS, game_hook=None):
    """Play one night with random seeded input. Returns (game, ticks_played)."""
    game = Game(seed, None, night=night)
    if game_hook is not None:
        game_hook(game)
    rng = random.Random(seed)       # input stream, separate from the sim's own RNG
    move = [0.0, 0.0]
    for t in range(max_ticks):
        if t % MOVE_EVERY == 0:
            move = random_move(rng)
        game.step({"move": move,
                   "jump": rng.random() < P_JUMP,
                   "dash": rng.random() < P_DASH,
                   "pulse": rng.random() < P_PULSE,
                   "interact": rng.random() < P_INTERACT})
        if game.state not in ("playing", "paused"):
            break
    return game, game.tick


def soak(seed, nights, log=None):
    t0 = time.perf_counter()
    results, per_night = [], []
    crashes = 0
    mem = {}

    def hook(game):
        if "start" not in mem:      # RSS right after the first night's Game exists
            mem["start"] = rss_mb()

    game = None
    for i in range(1, nights + 1):
        night, nseed = night_for(i), seed + i
        try:
            game, ticks = play_night(night, nseed, game_hook=hook)
            result, score = game.state, game.score
            if result not in ("won", "lost"):      # hit the tick cap while still running
                result = "timeout"
        except Exception:
            crashes += 1
            traceback.print_exc(file=sys.stderr)
            result, ticks, score = "crash", 0, 0
        game = None
        results.append(result)
        per_night.append({"night": night, "seed": nseed, "ticks": ticks, "result": result, "score": score})
        if log:
            log(f"night {i}/{nights}: Night {night} seed {nseed} -> {result} ({ticks} ticks, score {score})")
    gc.collect()
    mem_end = rss_mb()
    mem_start = mem.get("start", mem_end)
    return {"nights": nights, "crashes": crashes, "results": results,
            "mem_start_mb": mem_start, "mem_end_mb": mem_end,
            "duration_s": round(time.perf_counter() - t0, 1),
            "seed": seed, "per_night": per_night}


def main(argv=None):
    ap = _Parser(description="Dao Den Long soak test (Test Contract v1.3)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--nights", type=int, default=10)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.nights < 1:
        ap.error("--nights must be >= 1")
    out = soak(a.seed, a.nights, log=lambda m: print(m, file=sys.stderr, flush=True))
    try:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, indent=2)
            f.write("\n")
    except OSError as e:
        sys.stderr.write(f"error: cannot write output: {e}\n")
        return 1
    ok = out["crashes"] == 0 and out["mem_end_mb"] <= MEM_RATIO_LIMIT * out["mem_start_mb"]
    print(f"soak {'PASS' if ok else 'FAIL'}: crashes={out['crashes']} "
          f"mem {out['mem_start_mb']} -> {out['mem_end_mb']} MB "
          f"(limit {round(MEM_RATIO_LIMIT * out['mem_start_mb'], 1)}) in {out['duration_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
