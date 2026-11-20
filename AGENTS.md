# AGENTS.md - Dao Den Long

3D game, 3 nights (Python logic + Three.js web view). Lab spec: `docs/lab/` (current: `ticket-02.txt`, contract v1.1). Phase notes: `docs/notes/`.

## Commands
- Verify everything (must be green before you stop): `python3 tools/check.py`
- Save proof for a phase: `PHASE=phase-N python3 tools/check.py --save` (PHASE defaults to phase-1, always set it)
- Browser proof (needs playwright): `PHASE=phase-N python tools/web_check.py`
- Headless: `python3 headless.py --seed 1 --night 1|2|3 --ticks 600 --out out.jsonl [--scenario f] [--inputs f]`
- Play: `python3 serve.py` -> http://127.0.0.1:8000/web/ (`?hq` = antialiasing)
- Single-file build (Release/Artifact): `python3 tools/build_web.py`

## Layout
- `game/sim.py` - ALL game rules. Pure Python stdlib, no I/O, deterministic (seeded `random.Random`, no time).
- `game/maps.py` - the 3 nights' geometry (`ground_height`, lanterns, spawn points, pads, schedules). Data only, from ticket Part 2.
- `headless.py` - Test Contract CLI. `web/index.html` - renders + reads keys only, runs `game/sim.py` via Pyodide (`web_new/web_step/web_map`).
- `game.contract.json` - `tuning` must equal `sim.TUNING` (a test enforces it).
- `tests/test_sim.py` (Phase 1 rules on standard numbers), `tests/test_phase2.py` (new rules). Both are black-box: they call the CLI through `tests/blackbox.py`.
- `tests/scenarios/sNN_name.{scenario,inputs,expect}.json`. `expect.json` may set `night` and `seed` (default 1).
- Shared design decisions for Phase 2: `docs/notes/phase-2-design.md`.

## Rules
- Never put game rules in JS. Web and headless must share `game/sim.py`.
- The per-tick processing order in the ticket is mandatory. Win/lose is judged at the end of the tick.
- Contract text is exact: event names, field names, shade states, exit codes (malformed file -> 2), tick model, 3-decimal rounding.
- Counters are integer ticks, decremented in step 2: set n at tick t -> active t..t+n-1.
- Radius checks use `<= r + EPS` (float accumulation once shifted a pickup by 1 tick).
- Expected values in `*.expect.json` are computed by hand from the rules (write `_why`), never copied from output.
- When tests and code disagree, the ticket text decides (then `phase-2-design.md`). Fix whichever is wrong and say why.
- When a ticket changes a rule: update the test (comment `# Ticket-NN: ...`), record it in `tests/CHANGES-phase-N.md` and `docs/notes/phase-N.md`; never delete tests silently.
- Creative extras must not change headless output (visual/sound only, or disabled in headless).
- Do not edit `docs/lab/` (instructor files).
