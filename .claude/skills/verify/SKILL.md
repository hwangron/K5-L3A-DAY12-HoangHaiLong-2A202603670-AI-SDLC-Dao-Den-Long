---
name: verify
description: Run the game's full verification and save proof for the current phase (unit tests, headless scenarios, determinism, browser screenshots). Use before tagging a phase or after changing game rules.
---

Current phase: `phase-2` (Ticket-02, contract v1.1). Always set `PHASE`; `tools/check.py` defaults to phase-1.

1. `python3 tools/check.py` - must print all PASS (exit 0). If not, fix the code, not the expectation, unless the ticket changed the rule (then add `# Ticket-NN: ...` to the test and note why in `tests/CHANGES-phase-N.md` + `docs/notes/phase-N.md`). If test and code disagree, the ticket text decides.
2. New rule? Add `tests/scenarios/sNN_name.scenario.json` (+ `.inputs.json`) and `sNN_name.expect.json` with `ticks`, optional `night` (1/2/3) and `seed` (default 1), exact `events` `[[tick, name, data], ...]` starting with `[0, "night_start", {"night": N}]`, `end`, and a `_why` explaining the hand calculation.
3. Save proof: `PHASE=phase-2 python3 tools/check.py --save` -> `docs/proof/phase-2/runs/*.jsonl` + `scenario_report.md`.
4. Browser proof (if playwright installed): `PHASE=phase-2 python tools/web_check.py` -> screenshots + `web_check.json` in `docs/proof/phase-2/web/` (browser-vs-python parity for nights 1 and 3, pause, settings, night chain, FPS at 1280x720).
5. Update the traceability table in `docs/proof/phase-N/README.md` (requirement -> how -> evidence -> ĐẠT / ĐẠT một phần / CHƯA ĐẠT, with honest notes).
