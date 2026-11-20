# AGENTS.md - Dao Den Long

3D game (Python logic + Three.js web view). Lab spec: `docs/lab/`. Phase notes: `docs/notes/`.

## Commands
- Verify everything (must be green before you stop): `python3 tools/check.py`
- Save proof for a phase: `PHASE=phase-N python3 tools/check.py --save`
- Browser proof (needs playwright): `PHASE=phase-N python tools/web_check.py`
- Headless: `python3 headless.py --seed 1 --night 1 --ticks 600 --out out.jsonl [--scenario f] [--inputs f]`
- Play: `python3 serve.py` -> http://127.0.0.1:8000/web/
- Single-file build (Release/Artifact): `python3 tools/build_web.py`

## Layout
- `game/sim.py` - ALL game rules. Pure Python stdlib, no I/O, deterministic (seeded `random.Random`, no time).
- `headless.py` - Test Contract CLI. `web/index.html` - renders + reads keys only, runs `game/sim.py` via Pyodide.
- `game.contract.json` - `tuning` must equal `sim.TUNING` (a test enforces it).
- `tests/test_sim.py` unit tests; `tests/scenarios/NAME.{scenario,inputs,expect}.json` headless scenarios.

## Rules
- Never put game rules in JS. Web and headless must share `game/sim.py`.
- Contract text is exact: event names, field names, exit codes (malformed file -> 2), tick model, 3-decimal rounding.
- Radius checks use `<= r + EPS` (float accumulation once shifted a pickup by 1 tick).
- Expected values in `*.expect.json` are computed by hand from the rules (write `_why`), never copied from output.
- Creative extras must not change headless output (visual/sound only, or disabled in headless).
- When a ticket changes a rule: update test + note the reason in `docs/notes/phase-N.md`; do not delete tests silently.
- Do not edit `docs/lab/` (instructor files).
