# Bằng chứng Phase 3 (Ticket-03 "Đèn cạn dầu", Contract v1.2)

Chạy lại tất cả: `python tools/check.py` (cần đạt hết). Lưu lại bằng chứng: `PHASE=phase-3 python tools/check.py --save`.

- Kết quả lần chạy `--save`: **167 unit test PASS** (58 trong `tests/test_phase3.py`, 81 trong `tests/test_phase2.py`, 28 trong `tests/test_sim.py`) và **35/35 kịch bản headless PASS**. Kịch bản mới: s24–s35. Kịch bản được cập nhật: s02, s05, s08, s09, s15, s16, s17, s19, s20. Mỗi kịch bản chạy 2 lần, file giống hệt từng byte. Chi tiết và lệnh chạy: [scenario_report.md](scenario_report.md). Output thật: [runs/](runs/).
- Bản web: [web/web_check.json](web/web_check.json) (`ok: true`, `js_errors: []`) và ảnh trong [web/](web/), tạo bằng `PHASE=phase-3 python tools/web_check.py` (Playwright, Chromium headless).
- Tiêu chí nghiệm thu: [docs/notes/phase-3.md](../../notes/phase-3.md). Quyết định: [ADR-001](../../notes/adr-001-lantern-fuel.md). Test bị đổi: [tests/CHANGES-phase-3.md](../../../tests/CHANGES-phase-3.md). Đổi phá vỡ: [CHANGELOG.md](../../../CHANGELOG.md).

## Truy vết yêu cầu → bằng chứng

Kết quả: **ĐẠT** = có kiểm tra tự động xác nhận. **ĐẠT một phần** = có kiểm tra nhưng chưa đủ phạm vi hoặc có giới hạn. **CHƯA ĐẠT** = chưa có bằng chứng.

### Phần 1: Nhiên liệu đèn

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Thắp mới (10), thắp lại (5), fuel 100 khi thắp | Unit test và kịch bản | `test_phase3`: `test_first_light_costs_10_and_reports_relight_false`, `test_relight_costs_5_scores_40_and_counts`; s26 | ĐẠT |
| Hao 1.0/giây, đơn vị nguyên 1/60 | Unit test và kịch bản | `test_decay_is_one_per_second_at_tick_resolution`, `test_decay_exactly_one_per_60_ticks_and_one_decimal`; s24 | ĐẠT |
| Châm dầu: min(mang, ceil((100−fuel)/10)) | Unit test và kịch bản | `test_example_fuel_25_5_carried_10_uses_8_and_fills`, `test_limited_by_carried`; s25 | ĐẠT |
| Đèn đầy không được chọn, không sự kiện, không điểm | Unit test | `test_nothing_to_refuel_with_empty_hands`, `test_only_one_lantern_per_press` | ĐẠT |
| Chọn gần nhất, bằng nhau thì id nhỏ | Unit test | `test_nearest_candidate_wins_*`, `test_tie_goes_to_smaller_id_both_ways` | ĐẠT |
| Hết dầu: tắt, deposited 0, `lantern_out`, `ever_lit` | Unit test và kịch bản | `test_lantern_out_tick_deposited_reset_and_ever_lit`; s24, s25 | ĐẠT |
| Thanh dầu và nhấp nháy 1 Hz khi fuel < 30 | Trình duyệt | `lit_fuel_bar_visible`, `low_fuel_blinks`, `low_fuel_blink_rate_about_1hz`, `no_blink_when_fuel_at_least_30`; ảnh [06b](web/06b_low_fuel_blink.png) | ĐẠT (trình duyệt, không phải Python) |

### Phần 2: Bóng Mực hút dầu

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Vùng an toàn chỉ khi fuel ≥ 30 (đúng 30 còn) | Unit test | `test_zone_kept_at_exactly_30_lost_below`, `test_low_fuel_lantern_gives_no_protection_from_the_start` | ĐẠT |
| Chỉ wander chọn đèn yếu; không có thì đèn tắt | Unit test | `test_wander_goes_to_weak_lantern_not_nearest_unlit`, `test_without_weak_lantern_wander_heads_for_nearest_unlit` | ĐẠT |
| Vào 2 m → drain, đứng yên, 5/giây, cộng dồn | Unit test và kịch bản | `test_wander_shade_enters_drain_stands_still_and_drains_6_per_tick`, `test_two_shades_stack_and_decay_still_applies`; s27 | ĐẠT |
| Ra khỏi drain: chase / stunned / wander | Unit test và kịch bản | `test_drain_to_chase_when_cloud_within_6m`, `test_stun_end_goes_to_wander`; s35, s31 | ĐẠT |
| `fuel_drain` mỗi 60 tick | Unit test và kịch bản | `test_fuel_drain_event_every_60_ticks`; s27, s35 | ĐẠT (mốc tick 61 là quyết định thiết kế, xem ADR-001) |
| Châm lên ≥ 30 đẩy Bóng Mực ra mép | Unit test và kịch bản | `test_refuel_above_30_expels_a_draining_shade`; s32 | ĐẠT |

### Phần 3: Luật thắng

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Không thắng sớm khi đủ đèn | Unit test và kịch bản | `test_no_early_win_when_everything_is_lit`, `test_all_lit_does_not_end_the_night`; s02 | ĐẠT |
| Ngưỡng 3/5, 4/6, 5/7 | Unit test và kịch bản | `test_thresholds_3_of_5_4_of_6_5_of_7`; s28, s29 | ĐẠT |
| Đèn tắt đúng tick bình minh không được tính | Unit test và kịch bản | `test_lantern_dying_on_the_dawn_tick_does_not_count`; s29 | ĐẠT |
| Hết Ngọn Lửa đúng tick bình minh thì thua dù đủ đèn | Kịch bản | s34 | ĐẠT |
| Lý do: `dawn_survived`, `dawn`, `no_flames`. Không có `all_lit` | Unit test và kiểm tra CLI | `test_all_lit_reason_is_never_used`; `tools/check.py` từ chối `all_lit`; web `no_all_lit_win_wording` | ĐẠT |
| Màn thắng và kết quả (web) | Trình duyệt | `game_over_dawn`, `result_text_dawn`, `result_text_no_flames`, `win_reason_dawn_survived_all_nights`, `hud_lanterns_k_of_n_need_m` (4/6, 5/7) | ĐẠT một phần: thắng được ép bằng `sim._web_game` (đặt đèn sáng), không chơi thật |

### Phần 4: Sức chứa

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| 10 + 2 × lần thắp, tối đa 20 | Unit test và kịch bản | `test_formula_and_cap`, `test_relight_counts_and_max_is_20`; s30 | ĐẠT |
| Đèn đặt sẵn và châm dầu không tính | Unit test | `test_preset_lit_lanterns_do_not_count`, `test_refuel_does_not_count` | ĐẠT |
| HUD đang mang / sức chứa | Trình duyệt | `hud_carried_over_capacity_10`, `capacity_grows_after_light` | ĐẠT |

### Phần 5: Điểm

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Nạp +5, thắp 100 / 40 | Unit test và kịch bản | `test_score_table`, `test_formula_and_cap`; s05, s26 | ĐẠT |
| Tỏa Sáng +5, +15 nếu đang drain | Unit test và kịch bản | `test_pulse_on_normal_shade_is_5_on_drain_shade_15`; s31 | ĐẠT |
| Bình minh: +50 + floor(fuel) mỗi đèn, +50 mỗi lửa; thua không cộng | Unit test và kịch bản | `test_dawn_bonus_per_lantern_fuel_and_flames`, `test_no_dawn_bonus_when_lost`; s19, s20, s28 | ĐẠT |
| Tổng điểm web = tổng các Đêm thắng | Trình duyệt | `dawn_total_is_sum_of_won_nights` (won_scores 597 / 746 / 895) | ĐẠT (không đối chiếu từng điểm với Python) |

### Phần 6: Chế độ mù màu

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Cài đặt được lưu, tắt mặc định | Trình duyệt | `colorblind_toggle_default_off`, `colorblind_persists_after_reload`, `colorblind_toggle_off_restores_palette`; ảnh [05_settings](web/05_settings.png) | ĐẠT |
| Viền và mắt Bóng Mực `#00B3FF` | Trình duyệt | `cb_shade_rim_is_00B3FF`, `cb_shade_eyes_are_00B3FF`, `default_shade_rim_is_7A3CFF`; ảnh [05b](web/05b_colorblind_drain.png) | ĐẠT (kiểm tra tự động trong trình duyệt) |
| Cảnh báo `#FFFFFF` kèm ⚠ | Trình duyệt | `cb_warning_colour_is_white`, `cb_warning_icon_shown` | ĐẠT |
| Đèn tắt xẹp và rách | Trình duyệt | `cb_unlit_lantern_squashed_and_torn`, `unlit_lantern_squashed_and_torn`; ảnh [05b](web/05b_colorblind_drain.png) | ĐẠT (kiểm tra tự động trong trình duyệt) |
| Đèn sắp hết dầu nhấp nháy | Trình duyệt | `low_fuel_blinks`, `low_fuel_bar_blinks_too` | ĐẠT |

### Phần 7: Contract v1.2

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| `contract_version` 1.2, `tuning` khớp `sim.TUNING` | Unit test | `test_version_and_new_tuning_keys`, `ContractFile.test_contract_matches_game` | ĐẠT |
| Snapshot có khóa mới | Unit test và kiểm tra CLI | `SnapshotV12.*`; `tools/check.py` kiểm khóa | ĐẠT |
| Scenario có khóa mới, mặc định đúng | Unit test | `test_preset_lit_defaults_to_fuel_100`, `test_preset_ever_lit_and_unlit_fuel` | ĐẠT |
| Sự kiện mới đúng khóa | `tools/check.py` và kịch bản | s24, s25, s26, s27 | ĐẠT |
| Sai định dạng → thoát mã 2 | `tools/check.py` kiểm định dạng (fuel 0..100, 1 chữ số thập phân, `game_over` chỉ 3 lý do) | Mô tả trong [tests/CHANGES-phase-3.md](../../../tests/CHANGES-phase-3.md) (mục `tools/check.py`). Chưa có test riêng cho fuel ngoài 0..100 trong các test đã đối chiếu | ĐẠT một phần
| Tất định | `--save` chạy hai lần | Header [scenario_report.md](scenario_report.md) | ĐẠT |

### Định nghĩa hoàn thành (DoD)

| Yêu cầu | Bằng chứng | Kết quả |
|---|---|---|
| Có bằng chứng game chạy đúng | Bảng trên, [runs/](runs/), [web/](web/) | ĐẠT một phần (xem Đánh giá) |
| Có ghi chú quyết định | [ADR-001](../../notes/adr-001-lantern-fuel.md), [phase-3-design.md](../../notes/phase-3-design.md) | ĐẠT |
| Test cũ được sửa hoặc xóa có lý do, không skip âm thầm | [tests/CHANGES-phase-3.md](../../../tests/CHANGES-phase-3.md). Tìm `skip` trong `tests/*.py` chỉ thấy tên và chú thích, không có `@skip` | ĐẠT |
| Có changelog các đổi phá vỡ | [CHANGELOG.md](../../../CHANGELOG.md) | ĐẠT |
| Test ẩn Phase 1–2 không bị thay vẫn đạt | Test ẩn của giảng viên không có trong repo nên không chạy được. Bộ hồi quy của chúng tôi: 28 test Phase 1 + 81 test Phase 2 (những test bị luật mới thay đã sửa có lý do trong [CHANGES-phase-3.md](../../../tests/CHANGES-phase-3.md)) | ĐẠT một phần (chỉ có bộ hồi quy của chúng tôi) |

### Hiệu năng và tương đương web/Python

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Web và Python cùng trạng thái, Đêm 1 (900 tick) | So trạng thái Pyodide với CPython | `parity_night1_browser_vs_python: true` | ĐẠT |
| Web và Python cùng trạng thái, Đêm 3 (1300 tick) | Như trên | `parity_night3_browser_vs_python: true` | ĐẠT |
| Web và Python cùng trạng thái, kịch bản có nhiên liệu | Như trên, có sự kiện fuel | `parity_fuel_scenario_browser_vs_python`, `parity_fuel_scenario_has_fuel_events`, `parity_fuel_scenario_snapshot_has_fuel`: true | ĐẠT |
| Một Đêm đầy đủ ≤ 30 s | Test tự động + đo thời gian | `Performance.test_full_night3_under_30s`. Đo: Đêm 1 / 2 / 3 = 1.28 / 1.93 / 2.73 s ([perf.txt](perf.txt)) | ĐẠT |
| FPS ≥ 30 ở 1280×720 | Playwright đếm 5 s | `fps_night1_avg_5s: 36.7`, `fps_night3_avg_5s: 35.1`. Chỉ đo được trên GL phần mềm (SwiftShader), là cận dưới | ĐẠT một phần: chưa đo trên GPU thật |

## Review độc lập

Phase 3 **không có subagent review riêng**. Giới hạn sử dụng 5 giờ đã dừng giữa chừng phase, nên không có lượt review độc lập như Phase 2.

Kiểm tra độc lập duy nhất là **subagent tester** viết test hộp đen từ chính ticket, tách khỏi subagent coder. Tester không đọc code core. Các kỳ vọng được tính tay từ ticket và ghi trong `_why`, không chép từ output. Việc này không thay thế một lượt review đọc code và thử phá như Phase 2.

## Đánh giá Phase 3

- **Đạt:** luật nhiên liệu, drain, thắng ở bình minh, sức chứa, điểm mới, contract v1.2 (167 unit test, 35 kịch bản, mỗi kịch bản chạy 2 lần giống hệt từng byte). Tương đương web/Python ở Đêm 1, Đêm 3 và kịch bản có nhiên liệu. Chế độ mù màu được kiểm tra tự động trong trình duyệt.
- **Đạt một phần:** thắng trên web được ép bằng `sim._web_game`. FPS chỉ đo trên GL phần mềm. Lỗi thoát mã 2 mới chỉ xác nhận ở `tools/check.py`.
- **Chưa đạt / chưa có bằng chứng:** test ẩn Phase 1–2 (không có trong repo). Âm thanh (không thuộc ticket Phase 3, không có kiểm tra tự động trong `web_check.json`; đây là hồi quy từ Phase 2 chưa được kiểm lại). Thời gian chạy một Đêm đầy đủ đã đo và lưu ở [perf.txt](perf.txt).
- **Giới hạn đã biết:** bản web cần Internet để tải three.js và Pyodide từ CDN.
