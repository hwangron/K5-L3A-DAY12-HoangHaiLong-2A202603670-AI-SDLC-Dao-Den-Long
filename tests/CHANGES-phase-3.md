# Test changes for Phase 3 (Ticket-03 "Den can dau", contract v1.2)

Ticket-03 replaced several rules (the `[THAY THE]` items): lit lanterns take fuel and can be refuelled, a lantern needs
fuel >= 30 for a safe zone, the night is won only at dawn with enough lit lanterns (`all_lit` is gone), the score
formula is new, the night lengths are 240 / 270 / 300 s, and a stunned shade returns to `wander`.
Every changed test carries a `# Ticket-03: ...` comment. Nothing was skipped; removed tests are listed below with their
replacements. Expected values were recomputed by hand from the ticket (arithmetic is in the comments / `_why`), never
copied from program output.

Effects that touch many tests:
- Score is now +5 per mote **deposited or refuelled** (was +10). `tests/blackbox.py`: `PER_MOTE 10 -> 5`,
  `PER_SEC 2 -> 0`, new `PER_RELIGHT 40`, `PER_DRAIN_STUN 15`, `PER_LIT_DAWN 50`, helper `lantern(snap, id)`.
- `lantern_lit` now carries `relight` (`false` for a first light): every scenario/unit test that lists it was updated.
- Lighting the last lantern no longer ends the night.

## `tests/test_sim.py`

| Test | Status | Why |
|---|---|---|
| `ContractFile.test_contract_matches_game` | changed | contract_version "1.1" -> "1.2" |
| `Lanterns.test_deposit_partial_then_lit` | changed | +5 per mote (3 -> 15; 7 + first light -> 135), `lantern_lit` has `relight: false` |
| `Lanterns.test_win_all_lit_with_bonus` | **removed, replaced** | "win as soon as all lanterns are lit" no longer exists |
| `Lanterns.test_all_lit_does_not_end_the_night` | new (replacement) | lighting the 5th lantern at tick 1: no `game_over`, state `playing`, score only 10*5 + 100 = 150 |
| `Lanterns.test_win_at_dawn_with_bonus` | new (replacement) | 5 lit, dawn at tick 60: won `dawn_survived`; 10*5 + 100 + 5*(50+99) + 2*50 = 995 (old bonus 2 x seconds left is gone) |
| `Pulse.test_pulse_stun_push_cost_score` | comment only | stun end -> `wander`; the shade is 8.99 m <= 12 m from the player so the wander->chase check fires in the same tick: still `chase` at tick 121 |
| `TickModel.*`, `Movement.*`, `Motes.*`, `Shades.*` (all), `Pulse.test_pulse_needs_light_and_cooldown`, `Determinism.*`, `Cli.*`, `Lanterns.test_out_of_range_no_deposit`, `test_held_button_triggers_once`, `test_prelit_lantern_gives_no_score` | unchanged | rechecked against the ticket; `TickModel.test_dawn` (0 lit -> `lost dawn` at 60) and `Shades.test_safe_radius_of_lit_lantern` (fuel 100 -> 90 after 600 ticks, still >= 30) still hold |

## `tests/test_phase2.py`

| Test | Status | Why |
|---|---|---|
| module docstring | changed | mentions Ticket-03 |
| `ContractV11.test_version_tuning_equal_and_standard` | changed | "1.2"; durations 240/270/300; the old `score` table (per_mote 10, per_second_left 2) removed from the standard dict (checked as the new table in `test_phase3.ContractV12.test_score_table`) |
| `ContractV11.test_night_defaults_from_map` | changed | default `time_left_s` 240 / 270 / 300 (was 300 / 330 / 360) |
| `Pause.test_pause_freezes_sim` | changed | night 1 is 14400 ticks: `time_left_s` = (14400 - 10)/60 = 239.833 (was 18000-based) |
| `SafeZone.test_lit_lantern_expels_shade_harmlessly` | changed | score 10*5 + 100 = 150 (constants); behaviour unchanged |
| `PulseV11.test_stun_120_exact_push_4m_over_15_ticks` | comment only | stun end -> wander -> chase in the same tick (7 m <= 12 m); same observable result |
| `WinLose.test_win_on_the_dawn_tick` | rewritten (same name) | was "light the last lantern on tick 60 -> won all_lit (350)". Now: L1 lit by deposit on the dawn tick, 5/5 lit -> won `dawn_survived`, score 150 + 150 + 596 + 150 = 1046 |
| `WinLose.test_no_flames_beats_win` | **renamed** `test_no_flames_beats_dawn`, rewritten | was fall + last lantern lit; now the last flame is lost by a shade hit on the dawn tick (tick 60) while 3/5 lanterns are lit -> `lost no_flames`, score 0. Control: invulnerable -> `won dawn_survived`, 3*149 + 1*50 = 497 |
| `WinLose.test_rest_of_tick_runs_after_last_lantern` | **renamed** `test_rest_of_tick_runs_before_dawn_verdict`, rewritten | the verdict is still after the whole tick, now the dawn tick: deposit, lantern_lit, pulse, then `game_over won dawn_survived`; score 1016 |
| `Performance.test_full_night3_under_30s` | changed | night 3 is 18000 ticks (was 21600) and standing in a lit lantern no longer protects to dawn (fuel runs out at tick 6000). The player is now invulnerable for 18000 ticks; the night ends `lost dawn` at tick 18000 (no lantern lit); still must finish in < 30 s |
| everything else (dash, motes, dropped motes, pulse, shades, schedules, fall, pause, drifters, charm, wind, jump pads, terrain, CLI) | unchanged | |

## Scenarios (`tests/scenarios/`)

| Scenario | Status | Change |
|---|---|---|
| `s01_contract_example`, `s03`, `s04`, `s06`, `s07`, `s10`, `s11`, `s12`, `s13`, `s14`, `s18`, `s21`, `s22`, `s23` | unchanged | rechecked (stun end -> wander -> chase in s01/s10/s11 happens within 12 m, same events; s21 lit lantern keeps fuel >= 30 for 2800 ticks) |
| `s02_win` | **changed** | all 5 lit on tick 1 no longer wins. Scenario `time_left_s: 5`; win at dawn tick 300 `dawn_survived`, score 1025; snapshot checks added |
| `s05_partial_deposit` | changed | score 3*5 = 15 (was 30) |
| `s08_dropped_motes` | changed | `lantern_lit.relight false`; score 5*5 + 100 = 125 (was 150) |
| `s09_safe_zone_expel` | changed | `relight false`; score 150 (was 200) |
| `s15_wind` | changed | `relight false`; score 125 (was 150) |
| `s16_jump_pad` | changed | `relight false`; score 150 (was 200) |
| `s17_night3_terrain` | changed | `relight false`; score 150 (was 200) |
| `s19_win_on_dawn_tick` | **changed** | now `won dawn_survived` on the dawn tick, score 1046 (was `all_lit`, 350) |
| `s20_win_end_of_tick` | **changed** | action moved to the dawn tick (inputs at 59, `time_left_s: 1`, S1 preset stunned so it stays put); events at tick 60, `won dawn_survived`, score 1016 |

New scenarios (all hand computed, with `_why`): `s24_fuel_decay_out`, `s25_refuel`, `s26_relight`, `s27_drain`,
`s28_win_dawn`, `s29_lose_dawn_ratio`, `s30_capacity_growth`, `s31_drain_pulse15`, `s32_refuel_expels_drainer`,
`s33_stun_end_wander`, `s34_no_flames_beats_dawn`, `s35_drain_to_chase`.

## New

- `tests/test_phase3.py` (58 tests): contract v1.2 keys and values; snapshot keys and defaults; fuel decay table and
  1-decimal rounding; `lantern_out` tick, `deposited` reset, `ever_lit`; first light 10 vs relight 5, `relight` flag,
  `relit_count`, two relights of one lantern; refuel formula and event (25.5 / carried 10 -> 8 -> 100), decay before
  interaction, empty hands, reach; candidate selection (nearest, tie -> smaller id, unlit vs weak lit); safe zone lost
  below 30 and kept at exactly 30, refuel to >= 30 expels harmlessly; drain (enter, stand still, 6 units per tick,
  stacking, `fuel_drain` every 60 ticks, exits to chase / wander, `lantern_out` ends it); wander targets (weak lantern,
  nearest weak, tie, nearest unlit, strong lantern ignored); stun end -> wander; pulse +5 vs +15; win thresholds 3/5,
  4/6, 5/7 and one short; no early win; lantern dying on the dawn tick; dawn bonus per lantern and per flame; no bonus
  when lost; capacity formula, cap 20, pickups, relights count, preset lanterns do not count, refuel does not count.
- `tools/check.py`: accepts events `refuel`, `lantern_out`, `fuel_drain` and `lantern_lit.relight`; shade state `drain`;
  new snapshot keys (lantern `fuel` / `ever_lit` / `relit_count`, `player.capacity`); lantern fuel must be a number in
  [0, 100] with at most 1 decimal (0 when unlit), lit implies `ever_lit`, capacity an even integer in [10, 20];
  `refuel.fuel` / `fuel_drain.fuel` 1 decimal; `game_over` only `won dawn_survived`, `lost dawn`, `lost no_flames`
  (`all_lit` rejected). `expect.json` may now carry `snapshots` (partial match of the 10-tick snapshots, items by id).

## Expectations that depend on a design-doc decision (not on the ticket text)

The ticket is silent here; `docs/notes/phase-3-design.md` decides. If the design changes, these tests move with it.

1. `fuel_drain` phase: first event on tick 61 (60 drain ticks counted from the tick the shade enters drain), then 121,
   181 (`Drain.test_fuel_drain_phase_design_decision`, `s27_drain`, `s35_drain_to_chase`). The generic test only asserts
   "every 60 ticks" and that `fuel` equals the snapshot fuel.
2. A shade that enters `drain` in step 8 of tick t starts draining in step 2 of tick t+1 (follows from the ticket's
   step order, but the exact units per tick in the tables above depend on it).
3. A scenario shade may be preset to `state: "drain"` with `target_lantern_id` (`Drain.test_refuel_above_30_*`,
   `Drain.test_target_lantern_id_*`, `StunAndPulse.test_pulse_on_normal_shade_*`, `s31`, `s32`). A draining shade cannot
   be pulsed or refuelled over naturally (it is always > 6 m from the player, interact reach is 2 m).
4. State label right after a refuel to >= 30 expels a draining shade: asserted as "not drain, wander or chase"
   (the ticket lists both `wander` and, because the player is within 6 m, `chase`).
5. `ever_lit` defaults to `lit` for a scenario-preset lit lantern (`SnapshotV12.test_preset_lit_lantern_has_ever_lit`).
6. `tuning.score` key names and values (`per_mote 5`, `per_relight 40`, `per_drain_stun 15`, `per_lit_lantern_dawn 50`,
   `per_second_left 0`): the ticket gives the points, not the key names (`ContractV12.test_score_table`).
7. A wander shade with no weak lantern walks straight to the nearest unlit lantern until 4 m (ticket: "di ve den tat
   gan nhat"; the 4 m / circling detail is from the design doc).

## Consequences of the tick order worth knowing (derived from the ticket, tested)

- Decay (step 2) comes before interaction (step 5), so a lantern preset at fuel 80 already holds 79.98 when pressed on
  tick 1 and takes 3 motes, not 2 (`Refuel.test_decay_comes_before_interaction_in_the_same_tick`).
- A lantern is only "full" inside the tick in which it was filled. The next tick it has lost 1 unit and a press takes 1
  mote. "Full lantern is not selected / no event" is therefore only observable with `carried = 0` (used = 0), which is
  what the tests check.
