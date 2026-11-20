---
name: verify
description: Run the game's full verification and save proof for the current phase (unit tests, headless scenarios, determinism, browser screenshots). Use before tagging a phase or after changing game rules.
---

1. `python3 tools/check.py` - must print all PASS (exit 0). If not, fix the code, not the expectation, unless the ticket changed the rule (then note why in `docs/notes/phase-N.md`).
2. New rule? Add `tests/scenarios/NAME.scenario.json` (+ `.inputs.json`) and `NAME.expect.json` with `ticks`, exact `events` `[[tick, name, data], ...]`, `end`, and a `_why` explaining the hand calculation.
3. Save proof: `PHASE=phase-N python3 tools/check.py --save` -> `docs/proof/phase-N/runs/*.jsonl` + `scenario_report.md`.
4. Browser proof (if playwright installed): `PHASE=phase-N python tools/web_check.py` -> screenshots + `web_check.json` (includes browser-vs-python parity).
5. Update the traceability table in `docs/proof/phase-N/README.md` (requirement -> how -> evidence -> PASS/NOT MET).
