# Test changes for Phase 2 (Ticket-02, contract v1.1)

Ticket-02 replaced several Phase-1 rules with standard numbers. Tests that checked a replaced rule were
updated (not deleted). Each changed unit test has a `# Ticket-02: ...` comment. Expected values were
recomputed by hand from the ticket (arithmetic is in the comments / `_why`).

Two changes affect almost every test:
- `night_start {night}` is now emitted at tick 0, so "no events" checks look at game events only, and every
  scenario `events` list starts with `[0, "night_start", {"night": N}]`.
- Score is +10 per **deposited** mote (Phase 1: per picked-up mote).

Tests now go through the CLI (`headless.main(argv)` in-process, `tests/blackbox.py`) instead of `game.sim.Game` /
`parse_inputs`, so they do not depend on the internals being rewritten. Expected numbers are written out from
the ticket instead of read from `TUNING` (only the contract-equality test reads `TUNING`).

## Unit tests in `tests/test_sim.py`

| Test | Status | Why |
|---|---|---|
| `ContractFile.test_contract_matches_game` | changed | contract_version "1.0" -> "1.1" |
| `TickModel.test_snapshot0_before_input_and_event_tick` | changed | end score 10 -> 0 (pickup no longer scores) |
| `TickModel.test_time_left_and_snapshot_every`, `test_dawn` | unchanged | |
| `Movement.test_island_edge_clamp` | **removed, replaced** by `test_island_edge_falls` | The invisible shore at 30 m is gone: island radius is 40 m and walking off falls (fall_enabled true). Clamping can no longer be tested. |
| `Movement.test_scenario_position_outside_edge_not_moved` | unchanged | x=40 is now exactly the island edge (still land), so the review finding still holds |
| `Movement.test_speed_and_yaw`, `test_diagonal_normalised`, `test_jump_rises_and_lands` | unchanged | speed 6, jump 7, gravity 20 are the same |
| `Motes.test_pickup_radius_inclusive` | unchanged | pickup radius still 1.0 |
| `Motes.test_capacity` | changed | carry 5 -> 10 |
| `Lanterns.test_deposit_partial_then_lit` | changed | cost 5 -> 10, interact 2.5 -> 2.0, score per deposited mote (3 -> 30; 7 + lit -> 170) |
| `Lanterns.test_out_of_range_no_deposit` | changed | radius 2.0; ignore `night_start` |
| `Lanterns.test_held_button_triggers_once` | unchanged | |
| `Lanterns.test_win_all_lit_with_bonus` | changed | carried 10, score 100 + 100 + 99*2 + 2*50 = 498 |
| `Lanterns.test_prelit_lantern_gives_no_score` | changed | ignore `night_start` |
| `Shades.test_chase_speed` | changed | speed 3.5 -> 4.0, and a shade at 20 m now only wanders (detect 12 m): moved to 10 m -> x 6.0 |
| `Shades.test_hit_drop_invuln_and_lose` | changed | invuln 120 -> 90 ticks (second hit at 91) |
| `Shades.test_safe_radius_of_lit_lantern` | changed | safe radius 4 -> 6 |
| `Shades.test_unlit_lantern_is_not_safe` | unchanged | |
| `Pulse.test_pulse_stun_push_cost_score` | changed | cost 1 -> 3, radius 6 (2D) -> 5 (3D from feet+0.8), stun 180 -> 120, push instant -> over 15 ticks, +20 -> +5 |
| `Pulse.test_pulse_needs_light_and_cooldown` | changed | cooldown 60 -> 180, cost 3 (carried 6 for two pulses, 2 is not enough) |
| `Determinism.test_same_seed_same_output_default_level` | unchanged | |
| `Determinism.test_default_level` | changed | 40 -> 20 motes at start; player snapshot has extra v1.1 keys (checked by subset) |
| `Cli.*` | unchanged | |

## Phase-1 scenarios (names kept)

| Scenario | Change |
|---|---|
| `s01_contract_example` | Rebuilt on v1.1 numbers: the old shade (10,0,0) would now follow a pursuit curve that cannot be computed by hand, and one mote cannot pay a 3-mote pulse. Shade now chases head-on along Z (`state: chase`), player starts with 2 motes, pulse at input 80. Events: pickup 40, pulse 81 (S1), hit 241; score 5. |
| `s02_win` | Player moved to (0,0,23) (L1 is now at (0,0,25), interact 2.0), carries 10. Score 948. |
| `s03_lose_shade` | Shade speed 4.0 -> hit at tick 30 (was 35). |
| `s04_dawn` | Only the `night_start` event added. |
| `s05_partial_deposit` | L1 is at (0,0,25): walk to z=23, deposit at tick 231; score 30 now comes from the deposit. |
| `s06_default_level` | Determinism/format only; `night: 1` written out. |

## New

- `tests/test_phase2.py`: unit tests for every new rule (contract 1.1, nights, snapshot fields, dash, pickup
  height, dropped motes, safe zone, pulse v1.1, shade states/hits, schedules, fall, win/lose order, pause,
  drifters, charm, wind, jump pads, night-3 terrain, performance, malformed v1.1 input).
- `tests/blackbox.py`: shared CLI helpers (not a test module).
- Scenarios `s07`–`s23` (dash, dropped motes, safe-zone expel, pulse v1.1, fall + respawn, pause, drifter steal,
  charm, wind, jump pad, night-3 ramp, night-3 cliff, win on dawn tick, win at end of tick, shade schedule,
  default nights 2 and 3).
- `tools/check.py`: reads optional `night`/`seed`, checks v1.1 snapshot keys, item keys, state names, event
  names and exact event data keys, 3-decimal rounding.
- Review: shade `spawning` now lasts 1 tick (spawn tick only, acts from t+1); `test_spawn_points_states_and_id_skip` checks tick 301 = `wander` instead of 359 = `spawning`.
