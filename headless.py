"""Headless runner - Test Contract v1.0.

python3 headless.py --seed <int> --night 1 [--scenario f.json] [--inputs f.json]
                    --ticks <int> --out f.jsonl [--snapshot-every <int>]
Exit 0 = ok, 2 = malformed scenario/inputs, 1 = other error (message on stderr).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game.sim import Game, ScenarioError, parse_inputs  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"error: {message}\n")
        sys.exit(1)


def _load(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        sys.stderr.write(f"error: cannot read {what} file: {e}\n")
        sys.exit(1)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        sys.stderr.write(f"error: {what} is not valid JSON: {e}\n")
        sys.exit(2)


def dumps(o):
    return json.dumps(o, separators=(",", ":"), ensure_ascii=False)


def run(seed, scenario, frames, ticks, snapshot_every, write):
    game = Game(seed, scenario)
    write(game.snapshot())
    for k in range(ticks):
        for ev in game.step(frames.get(k)):
            write(ev)
        if game.tick % snapshot_every == 0:
            write(game.snapshot())
        if game.state != "playing":
            break
    write({"type": "end", "ticks": game.tick, "state": game.state, "score": game.score})
    return game


def main(argv=None):
    ap = _Parser(description="Dao Den Long headless (Test Contract v1.0)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--night", type=int, required=True)
    ap.add_argument("--scenario")
    ap.add_argument("--inputs")
    ap.add_argument("--ticks", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshot-every", type=int, default=10)
    a = ap.parse_args(argv)
    if a.night != 1:
        ap.error("only --night 1 exists in this version")
    if a.ticks < 0 or a.snapshot_every < 1:
        ap.error("--ticks must be >= 0 and --snapshot-every >= 1")

    try:
        scenario = _load(a.scenario, "scenario") if a.scenario else None
        frames = parse_inputs(_load(a.inputs, "inputs")) if a.inputs else {}
        lines = []
        run(a.seed, scenario, frames, a.ticks, a.snapshot_every, lambda o: lines.append(dumps(o)))
    except ScenarioError as e:
        sys.stderr.write(f"error: malformed scenario/inputs: {e}\n")
        return 2
    try:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        sys.stderr.write(f"error: cannot write output: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
