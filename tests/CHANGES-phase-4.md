# Tests changed or added for Ticket-04 ("Binh minh v1.0.0", contract v1.3)

## Existing tests that changed (nothing deleted)

| File | Change | Why |
|---|---|---|
| `test_sim.py` `ContractFile` | `contract_version` expected `"1.3"` (was `"1.2"`) | Ticket-04 part 6: contract v1.3 |
| `test_phase2.py` `test_version_tuning_equal_and_standard` | same | same |
| `test_phase3.py` `ContractV12.test_version_and_new_tuning_keys` | same; the tuning assertions are untouched | v1.3 adds only `bench_cmd` / `soak_cmd`, the v1.2 tuning stays |

## New: `test_phase4.py` (all black-box, expected numbers hand-computed in the comments)

`ContractV13`, `BenchStats` (hand-made dt lists, k = max(1, ceil(0.01 N)) at N = 1, 2, 3, 100, 101, 200, 201, 1000, 1001,
nearest-rank p95, N = 0 raises), `BenchScene` (200 wander shades, 100 motes, L1-L3 lit fuel 100, nothing spawns / hits /
picks up / burns / ends, 14401 steps still `playing`, same seed identical, other seed different), `NormalModeUnchanged`,
`SoakCLI` (3 nights twice for determinism, 10 nights when 3 nights are fast), `LeaderboardNames`, `LeaderboardOrdering`,
`LeaderboardPersistence`, `LeaderboardExport`, `CommittedProof` (skips until `bench.json` / `soak.json` are committed in
the repo root or `docs/proof/phase-4/`).

## Expectations that depend on `docs/notes/phase-4-design.md` (the ticket is silent)

If the design changes, these move with it. Every one is in a test whose name or comment says `DESIGN`.

1. `compute()` rounds to 1 decimal, p95 is nearest-rank `sorted(dt)[ceil(0.95 N) - 1]`, N = 0 raises (any exception).
2. Bench shades have ids `S1..S200`; shades and motes lie within 38 m of the origin; `web_bench_new(seed)` returns
   `{events, snap, extra}` like `web_new`.
3. `soak.py` writes `per_night` rows `{night, seed, ...}` with night `((i-1) mod 3)+1` and seed `7+i`; the first 3
   results of a 10-night run equal a 3-night run.
4. The leaderboard is reached through `python serve.py <port> --no-browser` (`GET`/`POST /api/leaderboard`, 400 +
   `{"error": ...}` for a bad entry, `entries` in the POST response); `achieved_at` is set by the server (a client value
   is ignored); names are NFC-normalised before the 3-12 check; `nights_won` outside 0-3 is rejected.
5. `game.contract.json` `bench_cmd` / `soak_cmd` end with `bench.py` / `soak.py`.

## Not tested here (needs a browser)

Camera path, window size, vsync flags, `bench.py` itself, accessibility, packaging: covered by `tools/web_check.py`
and the checklist in the Phase 4 proof notes.
