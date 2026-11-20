# Bằng chứng Phase 4 (Ticket-04 "Bình minh v1.0.0", Contract v1.3)

Chạy lại kiểm chứng: `python3 tools/check.py` (cần đạt hết). Lưu bằng chứng: `PHASE=phase-4 python3 tools/check.py --save`.

- Kết quả `tools/check.py`: **223 unit test PASS** và **35/35 kịch bản headless PASS**. Mỗi kịch bản chạy 2 lần, file đầu ra giống hệt nhau. Test mới: [tests/test_phase4.py](../../../tests/test_phase4.py). Test đổi số phiên bản: [tests/CHANGES-phase-4.md](../../../tests/CHANGES-phase-4.md).
- Benchmark: [bench.json](bench.json), đo bằng `python3 bench.py --seed 42 --duration 30 --out bench.json`.
- Soak: [soak.json](soak.json), đo bằng `python3 soak.py --seed 7 --nights 10 --out soak.json`.
- Bản web: [web/web_check.json](web/web_check.json) (`ok: true`, `js_errors: []`) và ảnh trong [web/](web/). Tạo bằng `PHASE=phase-4 python3 tools/web_check.py` (Playwright, Chromium headless).
- Tiêu chí nghiệm thu: [docs/notes/phase-4.md](../../notes/phase-4.md). Thiết kế: [phase-4-design.md](../../notes/phase-4-design.md).

Kết quả: **ĐẠT** = có kiểm tra tự động xác nhận. **ĐẠT một phần** = có kiểm tra nhưng chưa đủ phạm vi hoặc có giới hạn. **CHƯA ĐẠT** = chưa có bằng chứng hoặc chưa làm.

## Số đo

### Benchmark (bench.json, máy phát triển)

| Trường | Giá trị | Ngưỡng ticket (máy chấm) | Kết quả trên máy này |
|---|---|---|---|
| `avg_fps` | 618.4 | ≥ 60 | Đạt |
| `p1_low_fps` | 157.2 | ≥ 30 | Đạt |
| `frame_ms_p95` | 5.6 ms | (không có ngưỡng) | |
| `frames` | 18551 (30 s đo) | | |
| `load_ms` | 2463 | ≤ 10000 | Đạt |
| `peak_mem_mb` | null | null được phép nếu giải thích | Xem bên dưới |
| `vsync_off` | true | | |
| `renderer` | three.js r128 WebGL · ANGLE (AMD, AMD Radeon(TM) Graphics, D3D11) · Chrome 157 | | |
| `os` | Windows-11-10.0.26200-SP0 | | |

Ghi chú:
- Số trên là của máy phát triển, dùng để tham khảo. Máy chấm của giảng viên sẽ cho số khác. Ticket nói mọi bài đo trên cùng một máy chấm.
- `avg_fps` khớp với công thức: 18551 khung / 30 s ≈ 618.4. Với 618 fps, không thể là vsync 60 Hz đang giới hạn khung hình, nên xác nhận vsync đã tắt. Đây là suy luận, không phải đo trực tiếp.
- `peak_mem_mb: null`: bản web chạy trong trình duyệt. Mã JavaScript trên trang không đọc được RSS của tiến trình trình duyệt, nên bench không có số đo đáng tin. Ticket cho phép ghi `null` kèm giải thích. Bộ nhớ được đo ở soak (Python, RSS thật).
- Cảnh bench (200 Bóng Mực, 100 đom đóm, camera vòng tròn) được kiểm trong `web_check.json`: `bench_200_shades_100_motes_instanced`, `bench_scene_from_sim`, `bench_camera_circle_r30_y15`, `bench_measured_exactly_duration`, `bench_canvas_1280x720`, `bench_ignores_input`: tất cả `true`.

### Soak (soak.json)

| Trường | Giá trị | Ngưỡng | Kết quả |
|---|---|---|---|
| `nights` | 10 | 10 | |
| `crashes` | 0 | = 0 | Đạt |
| `mem_start_mb` / `mem_end_mb` | 20.4 / 20.4 | `mem_end ≤ 1.2 × start` (≤ 24.48) | Đạt |
| `duration_s` | 2.0 | | |
| `results` | 10 × `lost` | | Xem ghi chú |
| `seed` | 7 | | Đêm i dùng seed 7+i (8 … 17), Đêm xoay 1 → 2 → 3 |
| `ticks` theo Đêm | 5601, 1548, 2254, 2147, 3217, 2865, 1626, 1796, 8235, 2418 (tổng 31707) | | |

Ghi chú:
- Input ngẫu nhiên nên cả 10 Đêm đều `lost`. Soak không kiểm tra đường thắng. Đường thắng được kiểm bằng unit test và kịch bản headless.
- Đo RSS trong soak là đo tiến trình Python (headless), không phải trình duyệt. Đó là lý do soak có số RSS còn bench thì không.

### Bản web trong Chromium headless (web_check.json)

Môi trường này dùng SwiftShader (GL phần mềm, vẽ bằng CPU). Các số dưới đây là **cận dưới**, không đại diện cho GPU.

| Đo | Giá trị |
|---|---|
| FPS Đêm 1 (5 s trung bình) | 35.2 |
| FPS Đêm 3 (5 s trung bình) | 27.4 |
| Bench trong headless | 18.9 fps trung bình, 57 khung (không đại diện) |
| `font_check_elements` | 133, vi phạm 18 px ở mặc định: 0; ở chữ lớn (22.5 px): 0 |

## Truy vết yêu cầu → bằng chứng

### Phần 1: Benchmark

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Lệnh chạy và file đầu ra đủ trường, `contract_version "1.3"` | Chạy lệnh, đọc file | [bench.json](bench.json) | ĐẠT |
| Canvas 1280×720, không menu, không input | Trình duyệt | `bench_canvas_1280x720`, `bench_no_ui`, `bench_ignores_input` | ĐẠT (headless; chưa kiểm cửa sổ của lần đo thật) |
| 200 Bóng Mực wander, 100 đom đóm, L1–L3 sáng | Unit test + trình duyệt | `BenchScene` trong `test_phase4.py`; `bench_200_shades_100_motes_instanced`, `bench_scene_from_sim` | ĐẠT |
| Tắt sinh thêm, sát thương, nhặt, hao dầu, kết thúc | Unit test | `BenchScene` (14401 bước vẫn `playing`, không sinh, không trúng, không nhặt, không hao) | ĐẠT |
| Camera vòng tròn r 30, y 15, nhìn tâm | Trình duyệt | `bench_camera_circle_r30_y15` | ĐẠT (headless) |
| Bỏ 3 s, đo đúng `--duration`, tự thoát mã 0 | Trình duyệt | `bench_measured_exactly_duration`; mã thoát 0 khi chạy thành công | ĐẠT một phần: nhánh lỗi (quá `duration + 120` s, thoát mã 1) chưa có kiểm chứng riêng |
| Công thức avg, p1_low, p95, frames | Unit test | `BenchStats` (k tại N = 1, 2, 3, 100, 101, 200, 201, 1000, 1001; nearest-rank; N = 0 báo lỗi); `bench_stats_computable` | ĐẠT |
| `load_ms`, `vsync_off`, `renderer`, `os` | Đọc file | [bench.json](bench.json) | ĐẠT |
| `peak_mem_mb` null có giải thích | Đọc file và README | [bench.json](bench.json), [README](../../../README.md) (mục Benchmark) | ĐẠT |
| Ngưỡng: avg ≥ 60, p1 ≥ 30, load ≤ 10000 | Đo trên máy này | 618.4 / 157.2 / 2463 | ĐẠT trên máy phát triển; **CHƯA ĐẠT** chưa đo trên máy chấm (máy chấm chưa công bố) |

### Phần 2: Soak

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| 10 Đêm liên tiếp trong một tiến trình, Đêm xoay vòng, seed 7+i | Đọc `per_night`, unit test | [soak.json](soak.json); `SoakCLI` | ĐẠT |
| Input theo seed (30 tick, 5/3/2/10%) | Unit test | `SoakCLI` (chạy 3 Đêm hai lần, kết quả giống nhau) | ĐẠT |
| Exception một Đêm: `crashes += 1`, kết quả `crash`, chạy tiếp | Đọc mã | `soak.py` | ĐẠT một phần: chưa có kịch bản cố ý gây lỗi để kiểm chứng |
| `crashes = 0`, `mem_end ≤ 1.2 × mem_start` | Đo | `crashes 0`; 20.4 ≤ 24.48 | ĐẠT |
| RSS trên Windows (`GetProcessMemoryInfo`), macOS, Linux | Đo trên Windows | 20.4 MB đo được | ĐẠT trên Windows; **CHƯA KIỂM** macOS, Linux |

### Phần 3: Bảng xếp hạng

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Hỏi tên sau Bình Minh và sau khi thua | Trình duyệt | `dawn_name_form_in_dawn_card`, `loss_name_form_in_result_card`, [13b](web/13b_dawn_name_form.png), [07c](web/07c_loss_name_form.png) | ĐẠT |
| Tên 3–12 ký tự; sai thì không lưu; có dấu được | Unit test + trình duyệt | `LeaderboardNames`; `name_validation_messages`, `name_not_saved_when_invalid`, `vietnamese_nfd_name_is_longer_raw`, [13c](web/13c_name_error.png) | ĐẠT |
| Enter trong ô lưu, không thử lại | Trình duyệt | `enter_in_name_box_saves_not_retry` | ĐẠT |
| Mục đủ trường; `achieved_at` do server đặt | Unit test | `LeaderboardOrdering`, `LeaderboardPersistence`; `lb_source_is_server` | ĐẠT |
| Sắp điểm giảm dần, bằng điểm thì đến trước đứng trên, top 10 | Unit test + trình duyệt | `LeaderboardOrdering`; `lb_order_score_desc_then_earlier_first`, `lb_ranks_reported` | ĐẠT |
| Lưu đĩa, còn sau khi tắt và mở lại | Unit test + trình duyệt | `LeaderboardPersistence`; `lb_file_persisted` | ĐẠT |
| Màn Bảng xếp hạng từ menu | Trình duyệt | `lb_screen_from_dawn`, `lb_back_returns_to_dawn`, `lb_back_returns_to_menu`, `lb_escape_closes`; [14](web/14_leaderboard.png), [14b](web/14b_leaderboard_local.png) | ĐẠT |
| `--export-leaderboard out.json` đúng thứ tự | Unit test | `LeaderboardExport` | ĐẠT |
| API `GET`/`POST`, 400 khi sai | Unit test | `LeaderboardNames`, `LeaderboardPersistence` | ĐẠT |
| Không có API thì localStorage | Trình duyệt | `lb_fallback_local_storage_used`, `lb_fallback_ties_keep_time_order`, `lb_fallback_persists_after_reload`, `lb_fallback_did_not_touch_server_file` | ĐẠT |

### Phần 4: Dễ tiếp cận

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Đổi phím cho mọi hành động | Trình duyệt | `remap_up_to_I`, `remap_space_binds_cleanly`, `remap_all_set`, `remapped_key_moves_player`, `remapped_pause_key_pauses`, `remap_old_keys_dead`, [15b](web/15b_keys_remapped.png) | ĐẠT |
| Trùng phím báo và giữ phím cũ; phím dành riêng bị từ chối | Trình duyệt | `remap_duplicate_warns_and_keeps_old_key`, `remap_reserved_key_warns`, `remap_escape_cancels`; [15](web/15_keys_duplicate_warning.png) | ĐẠT |
| Khôi phục mặc định, lưu | Trình duyệt | `keys_reset_to_defaults_and_saved`; [15c](web/15c_keys_reset.png) | ĐẠT |
| Phím đổi được lưu sau khi tải lại | Trình duyệt | `remap_persists_after_reload`, `remap_menu_help_shows_new_keys`, `remap_hud_key_labels` | ĐẠT |
| Phụ đề: Bóng Mực xuất hiện, mũi tên mép, gió sắp thổi, 10 s cuối, fuel < 30 | Trình duyệt | `cue_shade_spawn_caption`, `cue_shade_edge_arrow_on_screen_edge`, `cue_wind_soon_caption`, `cue_last_10s_caption`, `cue_low_fuel_caption`; [16](web/16_cues_shade_spawn.png), [16b](web/16b_cue_last_10s.png) | ĐẠT |
| Tắt phụ đề thì không hiện thêm | Trình duyệt | `captions_off_clears_cues`, `captions_off_no_new_cues`, `captions_back_on` | ĐẠT |
| Giảm chuyển động: không rung, không chớp | Trình duyệt | `reduced_motion_no_camera_shake_no_flash`, `reduced_spread_vignette` [0, 0], `motion_returns_when_reduced_off` | ĐẠT |
| Chữ ≥ 18 px; chữ lớn ×1.25 | Trình duyệt | `font_min_18px_default` (133 phần tử, 0 vi phạm), `font_min_22_5px_large` (0 vi phạm); [17](web/17_settings_large_text.png), [17b](web/17b_hud_large_text.png) | ĐẠT |
| Tùy chọn trợ năng được lưu | Trình duyệt | `reduced_and_large_persist_after_reload`, `a11y_saved_in_localstorage`, `a11y_defaults_off` | ĐẠT |

### Phần 5: Đóng gói và tài liệu

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| Clone sạch, làm theo README tối đa 3 lệnh, chơi được | Chạy trên máy sạch | Chưa làm | **CHƯA KIỂM** |
| README đủ mục (mô tả, ảnh, yêu cầu, cài đặt, điều khiển, test, headless, bench, soak) | Đọc | [README](../../../README.md) | ĐẠT |
| CHANGELOG có mục cho cả 4 phase | Đọc | [CHANGELOG](../../../CHANGELOG.md) | ĐẠT |
| CREDITS liệt kê tài nguyên và công cụ AI | Đọc | [CREDITS](../../../CREDITS.md) | ĐẠT một phần: chưa kiểm tra giấy phép bản quyền có được giữ nguyên trong `three.min.js` và các file Pyodide |
| LICENSE | Có file | [LICENSE](../../../LICENSE) | ĐẠT |
| Zip Release chạy offline | Kiểm tra file | `dist/dao-den-long-v1.0.0.zip` (6.08 MB, có `web/vendor/three.min.js` và `web/vendor/pyodide/`, `START-HERE.txt`) | ĐẠT một phần: **CHƯA KIỂM** chạy zip trên máy không có Internet |
| Bản một file | Build | `dist/dao-den-long.html` (191 KB) | ĐẠT (có file; chưa chạy kiểm tra riêng) |
| GitHub Release v1.0.0 có bản chạy được | Trên GitHub | Chưa có | **CHƯA ĐẠT** (chưa tạo Release) |
| CI | Đọc | [ci.yml](../../../.github/workflows/ci.yml) chạy `tools/check.py` và smoke headless | ĐẠT (cấu hình); lần chạy trên GitHub: chưa ghi |

### Phần 6: Contract v1.3

| Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|
| `contract_version "1.3"`, `bench_cmd`, `soak_cmd`, `build_cmd` | Unit test | `ContractV13`; [game.contract.json](../../../game.contract.json) | ĐẠT |
| `tuning` khớp `sim.TUNING` | Unit test | `ContractFile.test_contract_matches_game` | ĐẠT |
| Mọi yêu cầu v1.0–v1.2 vẫn đạt | `tools/check.py` | 223 unit test + 35 kịch bản PASS; `parity_night1_browser_vs_python`, `parity_night3_browser_vs_python`, `parity_fuel_scenario_browser_vs_python`: `true` | ĐẠT một phần: test ẩn của giảng viên không có trong repo |

### Phần 7 và Định nghĩa hoàn thành

| Yêu cầu | Bằng chứng | Kết quả |
|---|---|---|
| Retro 1–2 trang | [docs/notes/retro.md](../../notes/retro.md) | ĐẠT (viết lần này) |
| Video demo dưới 5 phút (`docs/demo/demo.mp4` hoặc đính kèm Release) | Chưa có file trong repo | **CHƯA ĐẠT** |
| Có bằng chứng game chạy đúng | Trang này | ĐẠT một phần (xem các mục trên) |
| `bench.json` và `soak.json` commit trong repo | [bench.json](bench.json), [soak.json](soak.json) | ĐẠT |
| Tag `phase-4` và Release v1.0.0 | Chưa làm | **CHƯA ĐẠT** |
| Repo public, có harness AI và tài liệu | Chưa kiểm tra quyền truy cập từ bên ngoài | **CHƯA KIỂM** |

## Hiệu năng web / Python (kế thừa Phase 3)

Trạng thái Pyodide và CPython giống nhau ở Đêm 1 (900 tick), Đêm 3 (1300 tick) và kịch bản có nhiên liệu: `parity_*: true` trong `web_check.json`.

## Review độc lập

Phase 4 **không có subagent review riêng**. Kiểm tra độc lập duy nhất là subagent `tester`: viết test hộp đen từ chính ticket và thiết kế, không đọc code của `python` và `web`. Kỳ vọng được tính tay và ghi trong comment, không chép từ output. Kết quả: các test mới (`test_phase4.py`) và 35 kịch bản đều đạt.

Điều không có: lượt đọc code và thử phá như Phase 2 (mutation test, kịch bản biên do người khác viết). Đây là điểm yếu của Phase 4 và cần làm lại trước khi tag.

## Đánh giá Phase 4

- **Đạt:** benchmark đo được và vượt ngưỡng trên máy phát triển (618.4 / 157.2 / 2463 ms); soak không crash và RSS không tăng (20.4 → 20.4 MB); bảng xếp hạng đủ quy tắc; đổi phím, phụ đề, giảm chuyển động và chữ lớn đều được kiểm tự động trong trình duyệt; contract v1.3; zip Release có thư viện đi kèm; 223 unit test và 35 kịch bản đạt.
- **Đạt một phần:**
  - Benchmark chỉ đo trên một máy. Máy chấm chưa công bố nên chưa biết kết quả thật.
  - FPS trong Chromium headless (SwiftShader) là cận dưới: Đêm 3 đạt 27.4, dưới 30. Số thật trên GPU là bench 618.4.
  - Soak chỉ có `lost`, không kiểm đường thắng.
  - Zip Release chưa chạy thử offline. Phần đóng gói chưa kiểm trên máy sạch.
  - Đường lỗi của bench và soak chưa có kiểm chứng riêng.
  - Phase 4 không có review độc lập kiểu Phase 2.
- **Chưa đạt:**
  - Video demo chưa có.
  - Tag `phase-4` và GitHub Release v1.0.0 chưa tạo.
  - Chưa đo bench trên máy chấm của giảng viên.
- **Giới hạn đã biết:** bản web vẫn cần Internet lần đầu nếu không dùng zip hoặc `fetch_vendor.py`. Trình duyệt không cho đọc RSS nên `peak_mem_mb` là `null`.
- **Chi phí AI (Phase 4):** subagent đã đo: tester 138,794, web 346,735, python 220,727 (tổng 706,256). Lượt docs này chưa có số đo. Chi tiết: [nhật ký AI](../../notes/ai-log.md).
