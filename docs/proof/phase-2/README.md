# Bằng chứng Phase 2 (tag `phase-2`, Ticket-02, Contract v1.1)

Chạy lại tất cả: `python tools/check.py` (cần đạt hết). Lưu lại bằng chứng: `PHASE=phase-2 python tools/check.py --save` (phải ghi `PHASE`, mặc định của script vẫn là `phase-1`).

- Kết quả lần chạy `--save`: **108 unit test PASS, 23/23 kịch bản headless PASS**, mỗi kịch bản chạy 2 lần giống hệt từng byte. Chi tiết và lệnh chạy từng kịch bản: [scenario_report.md](scenario_report.md). Output thật: [runs/](runs/).
- Bản web: [web/web_check.json](web/web_check.json) (`ok: true`, không có lỗi JS) và ảnh trong [web/](web/), tạo bằng `PHASE=phase-2 python tools/web_check.py` (Playwright, Chromium headless).
- Tiêu chí nghiệm thu P1–P16, F1–F9 và giả định: [docs/notes/phase-2.md](../../notes/phase-2.md). Test bị đổi do ticket: [tests/CHANGES-phase-2.md](../../../tests/CHANGES-phase-2.md).

Unit test: `tests/test_sim.py` (test Phase 1 đã chỉnh theo số chuẩn) và `tests/test_phase2.py` (luật mới). Cả hai gọi CLI qua `tests/blackbox.py`.

## Truy vết yêu cầu → bằng chứng

### Luật chơi và contract (Phần 1, 2, 4)

| # | Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|---|
| P1 | Số liệu chuẩn, contract 1.1 | So `tuning` với số viết tay từ ticket và với `sim.TUNING` | `ContractV11.test_version_tuning_equal_and_standard`, `ContractFile.test_contract_matches_game` | ĐẠT |
| P2 | Chạy 6 m/s, nhảy | Tốc độ, xoay theo yaw, chuẩn hóa vector chéo, nhảy lên rồi đáp | `Movement.*` | ĐẠT |
| P3 | Lướt | 2.8 m trong 12 tick theo hướng mặt, hồi 90 tick từ lúc bắt đầu, giữ độ cao trên không, không bất tử | `Dash.*`, s07 | ĐẠT |
| P4 | Nhặt (XZ ≤ 1.0, chênh cao ≤ 1.5), mang 10 | Biên bán kính và độ cao. Nhặt không cộng điểm | `Pickup.*`, `Motes.*`, s01, s05 | ĐẠT |
| P5 | Bị đánh, đom đóm rơi | floor(mang/2) ra vành 1.5–2.5 m, TTL 480, nhặt lại được, bất tử 90, recoil 60 tick / 2 m, tối đa 1 hit mỗi tick theo id | `DroppedMotes.*`, `ShadesV11.*`, s08, s03 | ĐẠT |
| P6 | Vùng an toàn 6 m, đẩy Bóng ra | Đèn thắp khi Bóng ở 0.5 m: bị đẩy ra mép, không gây hit | `SafeZone.*`, `Shades.test_safe_radius_of_lit_lantern`, s09 | ĐẠT |
| P7 | Tỏa Sáng v1.1 | Biên 3D 4.994 / 5.004 m, choáng đúng 120 tick, đẩy 4 m trong 15 tick, hồi 180, tốn 3, +5 kể cả con đang choáng | `PulseV11.*`, `Pulse.*`, s10, s01 | ĐẠT |
| P8 | Lịch sinh Bóng Mực, đom đóm | Tick 300 (2 con), +480/420/360, tối đa 6/8/10; đom đóm 20, +1 mỗi 240, trần 30; id bỏ qua id scenario | `Schedules.*`, s21 | ĐẠT |
| P9 | Rơi khỏi đảo | −1 lửa, mất hết đom đóm (`lost`), chờ 60 tick không nhặt / không bị chạm, hồi sinh với bất tử 90, bỏ qua bất tử khi rơi, hết lửa thua ngay | `Fall.*`, `Movement.test_island_edge_falls`, s11 | ĐẠT |
| P10 | Thắng/thua cuối tick | Thắng đúng tick hết giờ; hết lửa thắng thắp đèn; các bước còn lại vẫn chạy sau khi thắp đèn cuối | `WinLose.*`, s19, s20, s04 | ĐẠT |
| P11 | 3 bản đồ | Đèn, xuất phát, bùa, thời gian từng Đêm; cầu; bục nhảy Đêm 2 (A→B, B→A) và Đêm 3 (lên tầng 2); dốc; vách; tháp; bước ra mép tầng thì rơi xuống | `ContractV11.test_night_defaults_from_map`, `JumpPads.*`, `Night3Terrain.*`, s16, s17, s18, s22, s23. Ảnh: [08](web/08_night2_map.png), [09](web/09_night2_bridge.png), [10](web/10_night3_map.png), [10b](web/10b_night3_tiers.png) | ĐẠT |
| P12 | Pause (headless) | sim_tick, thời gian, hồi chiêu đứng yên, nút khác bị bỏ, `state: "paused"`, dòng `end` ghi `playing` | `Pause.*`, s12 | ĐẠT |
| P13 | Contract v1.1 | `tools/check.py` kiểm khóa snapshot, khóa từng phần tử, tên trạng thái, tên sự kiện và đúng khóa dữ liệu, làm tròn 3 chữ số; sai định dạng → mã 2 | `SnapshotV11.*`, `CliV11.test_malformed_v11_fields_exit_2`, `Cli.*`, [scenario_report.md](scenario_report.md) | ĐẠT |
| P14 | Tất định | Mọi kịch bản chạy 2 lần so từng byte; màn mặc định 3 Đêm | `Determinism.*`, s06, s22, s23 | ĐẠT |
| P15 | Một Đêm đầy đủ ≤ 30 s | Đo thời gian chạy Đêm 3 21600 tick (xem Số đo) | `Performance.test_full_night3_under_30s` + đo tay | ĐẠT (1.8–4.6 s) |
| P16 | ≥ 30 FPS ở 1280×720 | Playwright đếm khung hình 5 s khi đang chạy và xoay camera | Lần chạy cuối (sau khi sửa theo review): `fps_night1_avg_5s: 34.4`, `fps_night3_avg_5s: 29.3`. Lần trước: 39.2 / 36.7 | ĐẠT một phần: chỉ đo được trên GL phần mềm (cận dưới), Đêm 3 dao động quanh 30. Cần đo trên GPU thật bằng `?fps` |
| — | Web và headless cùng luật | Cùng seed 42 và cùng chuỗi input: trạng thái Pyodide == CPython | `parity_night1_browser_vs_python` (900 tick), `parity_night3_browser_vs_python` (1300 tick) | ĐẠT |
| — | Regression Phase 1 | Test Phase 1 chạy lại với số chuẩn (đã chỉnh theo ticket, không xóa im lặng) | `tests/test_sim.py`, s01–s06, [CHANGES-phase-2.md](../../../tests/CHANGES-phase-2.md) | ĐẠT |

### Tính năng mới (Phần 3)

| # | Yêu cầu | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|---|
| F1 | Gió Lạc | Đuổi khi mang ≥ 5 và ≤ 15 m, cướp min(3, mang) ở XZ ≤ 1.2, flee 240 tick rồi biến mất, bất tử / vùng an toàn không chặn, Tỏa Sáng lúc chase / flee, lịch sinh tối đa 2, không có ở Đêm 1 | `Drifters.*`, s13 | ĐẠT |
| F2 | Bùa Gió | Nhặt → 600 tick, 7.2 m/s, Lướt không hồi chiêu, nhấn khi đang lướt bị bỏ, xuất hiện lại sau 2700, nhặt lại làm mới, vị trí mặc định | `Charm.*`, s14 | ĐẠT |
| F3 | Chuỗi 3 Đêm | Menu → giới thiệu "Đảo Bến" → chơi → kết quả → Đêm 2 → Đêm 3 → Bình Minh; tổng điểm = 748 + 808 + 868; thua → chơi lại Đêm đó | `intro_after_start`, `next_goes_to_night2/3`, `dawn_total_is_sum_of_won_nights`, `replay_resets`. Ảnh: [01](web/01_menu.png), [02](web/02_intro_night1.png), [12](web/12_result_won_night1.png), [13](web/13_dawn.png), [07](web/07_game_over.png) | ĐẠT một phần: chuyển màn là thật, nhưng việc **thắng** mỗi Đêm được ép bằng cách đặt đèn sáng qua `sim._web_game`, không phải chơi thật |
| F4 | Tạm dừng (Esc/P) | Nhấn Esc: menu hiện, tick logic không đổi trong 1 s dù giữ W; Tiếp tục: tick tăng lại; P mở lại menu | `pause_menu_shown`, `pause_freezes_sim`, `resume_continues`, [04_pause.png](web/04_pause.png) | ĐẠT (nút "Chơi lại Đêm" / "Về menu" chỉ thấy trong ảnh, không bấm tự động) |
| F5 | Cài đặt lưu giữa các lần mở | Đổi âm lượng 37, độ nhạy 155, tải lại trang → vẫn 37 / 155 | `settings_back_to_pause`, `settings_persist_after_reload`, [05_settings.png](web/05_settings.png) | ĐẠT |
| F6 | Âm thanh | Đọc mã: WebAudio tự tổng hợp, nhạc nền mỗi Đêm, tiếng cho đủ 10 sự kiện ticket (gắn vào sự kiện của sim) | `web/index.html` (phần `sound`, hàm xử lý sự kiện) | ĐẠT một phần: **không kiểm tự động** được âm thanh, chỉ đọc mã và nghe thử bằng tay |
| F7 | HUD đầy đủ | Playwright: HUD hiện, đồng hồ dạng mm:ss, nhắc "Nạp ánh sáng" khi đứng gần L1. Ảnh: lửa trên trái, đồng hồ giữa, đèn/điểm trên phải, thanh 10 ô, biểu tượng Lướt / Tỏa Sáng | `hud_visible`, `interact_prompt_shown`, [03_play_hud.png](web/03_play_hud.png), [06_lantern_lit.png](web/06_lantern_lit.png) | ĐẠT một phần: đồng hồ đỏ nhấp nháy ≤ 30 s và mũi tên chỉ đèn chỉ kiểm bằng đọc mã, không có kiểm tra tự động |
| F8 | Bảng màu chuẩn | Đọc mã: biến CSS và vật liệu dùng đúng hex trong ticket; so bằng mắt trên ảnh | `web/index.html` (`:root`, `const M`), các ảnh trong [web/](web/) | ĐẠT (kiểm bằng đọc mã + mắt) |
| F9 | Ánh sáng môi trường | Thắp 1/5 đèn → `ambient.intensity` = 0.26 | `ambient_follows_progress` | ĐẠT |
| — | Gió mạnh báo trước (Đêm 3) | Headless: cơn gió tick 1800 dài 300 tick, 2 m/s. Web: lá bay + thông báo ở 120 tick trước cơn gió | `Wind.*`, s15, `wind_warning_shown`, [11_night3_wind_warning.png](web/11_night3_wind_warning.png) | ĐẠT (web: tua tới tick 1690 qua `sim._web_game`) |

## Số đo

- **Headless, một Đêm 3 đầy đủ 21600 tick** (10 Bóng Mực, 2 Gió Lạc, gió bật, `flames: 1000` trong scenario để người chơi sống tới bình minh): **1.78 s** với `--snapshot-every 10`, **4.56 s** với `--snapshot-every 1` (file 76 MB). Giới hạn ticket: 30 s. Test `Performance.test_full_night3_under_30s` cũng chạy mỗi lần check.
- Máy: Windows 11 (10.0.26200), AMD64 Family 25 Model 80 (AMD Ryzen), 16 luồng, Python 3.14.7.
- **FPS web ở 1280×720** (trung bình 5 s, vừa đi vừa xoay camera): lần đầu Đêm 1 **39.2**, Đêm 3 **36.7**. Lần chạy cuối Đêm 1 **34.4**, Đêm 3 **29.3**. Con số dao động theo tải CPU của máy lúc đo.
  - Đo trong Chromium headless dùng SwiftShader (GL phần mềm, CPU vẽ), nên đây là **cận dưới**. GPU thật nhanh hơn nhiều.
  - Để đạt mức này, khử răng cưa (MSAA) tắt mặc định. Bật lại bằng `?hq` trên URL.

## Chưa đạt / giới hạn đã biết

- Một số kiểm tra web đặt trạng thái trực tiếp qua `sim._web_game` (dịch chuyển người chơi, đặt đèn sáng, giảm thời gian, tua tới tick 1690) thay vì chơi thật. Phần được kiểm là giao diện phản ứng đúng với trạng thái; luật chơi thì đã được kiểm ở headless.
- Âm thanh, bảng màu, đồng hồ nhấp nháy, mũi tên chỉ đèn: không có kiểm tra tự động.
- FPS chỉ đo trên GL phần mềm, chưa đo trên máy có GPU.
- Bản web vẫn cần Internet để tải three.js và Pyodide từ CDN.

## Review độc lập

Một subagent **không viết code** đối chiếu code với từng mục Ticket-02 (Phần 1–4), thử phá bằng kịch bản tự tạo ngoài repo, và chạy mutation test trên bản sao repo.

- **Mutation test:** cài 5 lỗi cố ý (pulse 3D → XZ, choáng 120 → 119, cộng điểm lúc nhặt thay vì lúc nạp, cho lướt lại khi đang lướt, bỏ kiểm tra bất tử). Cả 5 đều làm `tools/check.py` đỏ (5 đến 28 test fail mỗi lỗi).
- **Không có lỗi blocker hay major về luật.** Reviewer thử: nhặt ở chênh cao đúng 1.5 m, hai Bóng Mực chạm cùng tick, bị đánh khi mang số lẻ, rơi khi đang bất tử, lướt có bùa, pause ở tick 0, file scenario kiểu v1.0, cap 30 có đom đóm rơi, thắng đúng tick hết giờ. Tất cả khớp ticket.
- **Lỗi nhỏ đã sửa:** scenario bùa không có `id` bị thoát mã 2 (nay tự cấp C1, C2…). Thêm nhận `respawn_s` cho bùa và `kind: dropped` kèm `ttl_s` cho đom đóm.
- **Đổi thiết kế sau review:** `spawning` của Bóng Mực rút từ 60 tick xuống 1 tick, để khớp câu "thực thể mới chỉ tương tác được từ tick sau". Đã sửa 1 test, có ghi chú trong `tests/CHANGES-phase-2.md`.
- **Giữ nguyên có lý do:** độ cao Bóng Mực trong scenario không bị đổi, vì máy chấm tính khoảng cách 3D theo tọa độ họ đặt. Điểm xuất phát Đêm 3 là (0,0,−30) vì tâm đảo là tháp chuông. Gió Lạc biến mất khỏi mảng thay vì hiện trạng thái `removed`.

## Đánh giá Phase 2

- **Đạt:** số liệu chuẩn, 3 bản đồ, lướt, rơi + hồi sinh, Gió Lạc, Bùa Gió, gió mạnh, pause, contract v1.1, hiệu năng headless (Đêm 3 đầy đủ mất 1.78 s, giới hạn 30 s), chuỗi 3 Đêm + menu + cài đặt + HUD trên web.
- **Đạt một phần:** FPS (chỉ có số đo GL phần mềm), âm thanh và một số chi tiết HUD (chưa kiểm tra tự động).
- **Hồi quy Phase 1:** 27 test Phase 1 vẫn chạy. Test nào đổi số vì ticket thay luật đều có ghi chú `# Ticket-02:` và có trong [CHANGES-phase-2.md](../../../tests/CHANGES-phase-2.md). Không tắt test nào âm thầm.
- **AI sai ở đâu:** Gió Lạc chỉ cướp khi đang đuổi (test viết độc lập từ ticket đã bắt được). Code core cần `maps.py` mà bản web chưa nạp (điều phối viên chuyển thông tin cho agent web). Scenario bùa không có id (reviewer bắt).
- **Chỉnh harness:** `AGENTS.md` thêm quy tắc "thứ tự tick trong ticket là bắt buộc" và "test lệch code thì ticket quyết định". Mỗi agent chỉ được sửa file của mình. Có file thiết kế chung để các agent làm song song.
