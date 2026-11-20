# Bằng chứng Phase 1 (tag `phase-1`)

Chạy lại tất cả: `python3 tools/check.py` (cần đạt hết). Lưu lại bằng chứng: `PHASE=phase-1 python3 tools/check.py --save`.

- Kết quả kịch bản headless: [scenario_report.md](scenario_report.md). Output thật ở [runs/](runs/), mỗi kịch bản chạy 2 lần và phải giống hệt từng byte.
- Bản web: [web/web_check.json](web/web_check.json) và ảnh chụp trong [web/](web/), tạo bằng `python tools/web_check.py` (Playwright điều khiển trình duyệt thật).
- Tiêu chí nghiệm thu R1–R13 và giả định A1–A18: [docs/notes/phase-1.md](../../notes/phase-1.md).

## Truy vết yêu cầu → bằng chứng

| # | Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|---|
| R1 | Đi lại, camera 3D | Unit test tốc độ + xoay theo yaw + chuẩn hóa vector chéo + bờ đảo. Ảnh chụp camera góc thứ ba | `Movement.*` trong [test_sim.py](../../../tests/test_sim.py), [02_playing_hud.png](web/02_playing_hud.png) | ĐẠT |
| R2 | Nhảy | Unit test y tăng rồi về 0 | `Movement.test_jump_rises_and_lands` | ĐẠT |
| R3 | Đom đóm rải rác, nhặt được | Biên bán kính 1.0 / 1.01 m, giới hạn mang 5. Màn mặc định có 40 con | `Motes.*`, `Determinism.test_default_level`, kịch bản s01, s05 | ĐẠT |
| R4 | Nạp ánh sáng thắp đèn | Nạp một phần rồi thắp. Ngoài tầm thì không nạp. Giữ phím chỉ kích hoạt 1 lần | `Lanterns.*`, s05. Trình duyệt thắp L1: [03_lantern_lit.png](web/03_lantern_lit.png) | ĐẠT |
| R5 | Thắng + điểm | Thắp đèn cuối → `won all_lit`, điểm 848 tính tay | s02, `Lanterns.test_win_all_lit_with_bonus` | ĐẠT |
| R6 | Bóng Mực xuất hiện, đuổi | Tốc độ 3.5 m/s. `shade_spawned` S1 ở tick 300. Không vào vùng an toàn của đèn đã thắp | `Shades.test_chase_speed`, `test_safe_radius_of_lit_lantern`, `test_unlit_lantern_is_not_safe` | ĐẠT |
| R7 | Bị chạm mất máu, thua | Mất lửa, rơi đom đóm, miễn sát thương 120 tick, `lost no_flames` | `Shades.test_hit_drop_invuln_and_lose`, s03 | ĐẠT |
| R8 | Tỏa sáng xua Bóng Mực | Biên 6 / 6.5 m, đẩy 4 m, choáng đúng 180 tick, tốn 1 đom đóm, hồi 60 tick, cần có đom đóm | `Pulse.*`, s01 | ĐẠT |
| R9 | Hết đêm | `lost dawn` đúng tick 120 khi còn 2 s | s04, `TickModel.test_dawn` | ĐẠT |
| R10 | Test Contract | Mô hình tick, `snapshot-every`, dòng `end` cuối, kiểm tra định dạng mọi dòng, mã thoát 2 khi file sai, `tuning` khớp code | `TickModel.*`, `Cli.*`, `ContractFile`, kiểm tra định dạng trong `tools/check.py` | ĐẠT |
| R11 | Tất định | Mọi kịch bản chạy 2 lần so từng byte. Màn mặc định seed 42 chạy 3000 tick | [scenario_report.md](scenario_report.md), `Determinism.*` | ĐẠT |
| R12 | HUD, thắng/thua, chơi lại | Playwright: bắt đầu → đi → thắp đèn → hết giờ → Enter → ván mới (điểm 0, 300 s) | [web_check.json](web/web_check.json): `replay_resets: true`, [04_game_over.png](web/04_game_over.png) | ĐẠT |
| R13 | Phong cách | Ảnh chụp: đêm tím tối, đèn vàng cam, Mây đội nón lá có đèn nhỏ, đảo sáng lên khi thắp đèn | [01_start.png](web/01_start.png), [02](web/02_playing_hud.png), [03](web/03_lantern_lit.png) | ĐẠT (đánh giá bằng mắt) |
| — | Web và headless cùng luật | Cùng seed 42 và 900 frame input: trạng thái trong trình duyệt == Python | `parity_browser_vs_python: true` | ĐẠT |

## Số đo

- Một đêm đầy đủ 18000 tick (6 Bóng Mực, 40 đom đóm), headless: **0.64 s**. Máy: Windows 11, AMD Ryzen (Family 25 Model 80), 16 luồng, Python 3.14.7.
- Trình duyệt chưa đo FPS. Phase 1 không yêu cầu, sẽ đo nếu ticket sau yêu cầu.

## Chưa đạt / giới hạn đã biết

- Bản web cần Internet để tải three.js và Pyodide từ CDN. Lần mở đầu mất vài giây để tải Pyodide.
- Phần "phong cách" chỉ đánh giá bằng mắt qua ảnh chụp, không có test tự động.

## Review độc lập

Một subagent **không viết code** đọc contract, thử phá bằng kịch bản tự tạo (ngoài repo) và chạy mutation test trên bản sao repo.

- **Mutation test:** cài 3 lỗi cố ý (đổi pickup `<=` thành `<`, kết thúc choáng lệch 1 tick, bỏ đếm ngược thời gian). Cả 3 đều bị `tools/check.py` bắt, chứng tỏ test không phải loại "luôn đạt".
- **Lỗi tìm được, đã sửa:**
  1. *Major*: bờ đảo kéo vị trí scenario đặt ngoài 30 m vào trong, kể cả khi đứng yên (đom đóm ở x = 40 không nhặt được). Sửa: bờ chỉ chặn bước đi ra ngoài. Có test hồi quy `test_scenario_position_outside_edge_not_moved`.
  2. *Minor*: file scenario `[]` hoặc `null` được chấp nhận, đúng ra phải thoát mã 2. Đã sửa và thêm vào `Cli.test_malformed_exit_2`.
- **Điểm mơ hồ reviewer nêu:** đã ghi giả định A4, A10, A19–A21 trong [phase-1.md](../../notes/phase-1.md).
- Reviewer xác nhận khớp contract: mô hình tick, `--ticks 0`, `snapshot-every` không chia hết, input giữ giá trị và kích hoạt theo cạnh lên, công thức yaw, biên bán kính, nhiều sự kiện trong cùng một tick, dòng `end` cuối.

## Đánh giá Phase 1

- **Đạt:** toàn bộ R1–R13. Kiểm chứng tự động: 27 unit test, 6 kịch bản headless, kiểm tra tất định, kiểm tra trình duyệt bằng Playwright.
- **Phase trước:** không có (phase đầu tiên).
- **AI sai ở đâu:** lỗi biên số thực (E1), script test nhấn phím quá nhanh (E2), bờ đảo kéo vị trí scenario (reviewer bắt được). Chi tiết ở [ai-log.md](../../notes/ai-log.md).
- **Chỉnh harness:** thêm quy tắc EPS và "kỳ vọng phải tính tay" vào `AGENTS.md`. Hook Stop chặn agent kết thúc khi check còn đỏ. Thêm skill `verify`.
- **Rủi ro còn lại:** những chỗ contract không nói rõ (A4 vùng an toàn chỉ cho đèn đã thắp, A2 tỏa sáng cần đom đóm). Sẽ hỏi trợ giảng hoặc điều chỉnh nếu ticket sau làm rõ.
