# Phase 2: Ticket-02 "Ba hòn đảo" + Test Contract v1.1

Nguồn: [docs/lab/ticket-02.txt](../lab/ticket-02.txt). Thiết kế chung (chốt trước khi chia việc): [phase-2-design.md](phase-2-design.md). Bằng chứng: [docs/proof/phase-2/README.md](../proof/phase-2/README.md).

## 1. Thay đổi so với Phase 1

| Thay đổi | Lý do |
|---|---|
| Thay mọi số tự chọn bằng số chuẩn (mang 10, đèn 10, nạp 2.0 m, vùng an toàn 6 m, Tỏa Sáng 3 / 5 m / 3 s, choáng 120 tick, bất tử 90 tick, Bóng Mực 4.0 m/s…) | Ticket Phần 1 bắt buộc, để mọi bản cho cảm giác giống nhau |
| Thêm `game/maps.py`: hình học, đèn, điểm sinh, lịch sinh của 3 Đêm; `ground_height(night, x, z)` trả `None` ở biển mây | Tách bản đồ khỏi luật chơi. Web và headless cùng đọc một nguồn (`web_map(night)`) |
| Bỏ bờ chắn vô hình. Đảo Bến bán kính 40 m, ra ngoài thì rơi (`fall_enabled: true`) | Ticket Phần 1 (rơi khỏi đảo) và Phần 2 |
| Viết lại vòng tick theo đúng 12 bước của ticket. Thắng/thua xét **cuối tick** (Phase 1 thắng ngay lúc `lantern_lit`) | Ticket ghi thứ tự là bắt buộc; thắng đúng tick hết giờ vẫn là thắng |
| Điểm đom đóm tính **khi nạp**, không tính khi nhặt. +5 mỗi Bóng Mực trúng Tỏa Sáng | Ticket chuẩn hóa điểm |
| Đom đóm rơi khi bị đánh nằm lại trên đất (vành 1.5–2.5 m, TTL 480 tick), không mất hẳn | Ticket Phần 1 |
| Bóng Mực có 5 trạng thái `spawning/wander/chase/recoil/stunned`, phát hiện 12 m, bỏ đuổi 18 m | Contract v1.1 bắt buộc đúng tên trạng thái |
| Thêm Lướt, Pause, Gió Lạc, Bùa Gió, gió mạnh, bục nhảy, địa hình 3 tầng | Ticket Phần 1–3 |
| Contract v1.1: `--night 1/2/3`, snapshot và scenario thêm trường, sự kiện mới | Ticket Phần 4 |
| Test đi qua CLI (`tests/blackbox.py`) thay vì gọi thẳng `game.sim.Game` | Lõi bị viết lại; test hộp đen không phụ thuộc chi tiết bên trong |
| Web: menu → giới thiệu Đêm → chơi → kết quả → Đêm kế → Bình Minh; HUD mới; tắt khử răng cưa mặc định (`?hq` để bật) | Ticket Phần 3; DoD ≥ 30 FPS ở 1280×720 |

## 2. Giả định

Toàn bộ ở [phase-2-design.md](phase-2-design.md) (mục 2–6). Những giả định quan trọng nhất:

| # | Chỗ ticket chưa rõ | Giả định |
|---|---|---|
| B1 | Góc trên mặt XZ | `x = r·cosθ, z = r·sinθ` (để tầng 1 Đêm 3 "nửa z > 0" chứa các điểm 20°…160°) |
| B2 | Bộ đếm kéo dài bao lâu | Đếm bằng tick nguyên, giảm ở bước 2. Đặt `n` tick ở tick t thì có hiệu lực t … t+n−1 |
| B3 | "Tăng tốc/dừng ≤ 0.1 s" | Vận tốc ngang đổi ngay (0 tick). Trên không giống trên đất |
| B4 | Vách và dốc | Mặt đất mới cao hơn chân quá 0.3 m thì bị chặn (thử trượt từng trục). Thấp hơn ≤ 0.3 m thì bám đất, thấp hơn nữa thì rơi |
| B5 | Lướt | 12 tick, hướng chốt lúc bắt đầu, `vy = 0`, không trọng lực, vách vẫn chặn |
| B6 | Xuất phát Đêm 3 | (0,0,−30), vì tâm đảo là tháp chuông |
| B7 | Gió | Bắt đầu ở tick 1800·k, dài 300 tick. Hướng chọn bằng rng ở tick báo trước (−120 tick) |
| B8 | Trần 30 đom đóm | Tính cả đom đóm rơi |
| B9 | Bóng Mực mới sinh | `spawning` 60 tick vô hại, rồi `wander` 1.5 m/s quanh điểm gốc |
| B10 | Gió Lạc sinh ở đâu | Trên điểm sinh Bóng Mực, cách Mây ≥ 15 m, y = mặt đất + 1.5 |
| B11 | Pause | Cạnh lên `pause` khi đang chơi thì dừng bước. Khi đang pause thì `resumed` rồi chạy tiếp tick đó. Nút khác bị bỏ. Dòng `end` khi đang pause ghi `playing` |
| B12 | Tổng điểm game | Chỉ có ở bản web (headless chạy một Đêm) |

## 3. Tiêu chí nghiệm thu (làm A thì thấy B)

### Phần 1–2, Phần 4 (luật chơi và contract)

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| P1 | Số liệu chuẩn | `game.contract.json` có `contract_version "1.1"`, `tuning` = `sim.TUNING` = số trong ticket (gồm `dash_*`, `night2/3_duration_s`) |
| P2 | Chạy, nhảy | `move [0,1]` 60 tick → đi 6 m. Nhảy vy 7, trọng lực −20, chỉ nhảy khi chạm đất |
| P3 | Lướt | Đứng yên nhấn dash → đi 2.8 m theo hướng mặt trong 12 tick. Nhấn lại trước 90 tick (tính từ lúc bắt đầu) → không lướt. Lướt trên không giữ nguyên y. Bị chạm lúc lướt vẫn mất lửa |
| P4 | Nhặt | Đom đóm cách XZ 1.0 m và chênh cao ≤ 1.5 m → nhặt; chênh 1.6 m → không. Nhặt không cộng điểm |
| P5 | Bị đánh | −1 lửa, rơi floor(mang/2) con ra vành 1.5–2.5 m (sống 480 tick, nhặt lại được từ tick sau), bất tử 90 tick, Bóng lùi 2 m trong 60 tick (`recoil`) |
| P6 | Vùng an toàn | Đèn vừa thắp khi Bóng ở trong 6 m → Bóng bị đẩy ra mép trong ≤ 30 tick, không gây hit |
| P7 | Tỏa Sáng | Tâm = chân + 0.8 m, khoảng cách 3D 4.994 m → choáng, 5.004 m → trượt. Choáng đúng 120 tick, đẩy 4 m trong 15 tick, tốn 3, hồi 180 tick, +5 mỗi con |
| P8 | Lịch sinh | Đêm 1: Bóng ở tick 300 (2 con), 780, 1260… tối đa 6. Đêm 2/3: mỗi 420/360 tick, tối đa 8/10. Đom đóm: 20 lúc đầu, +1 mỗi 240 tick, trần 30 |
| P9 | Rơi khỏi đảo | Ra ngoài bán kính 40 m → y < −10 → `player_hit {by:"fall", lost:n}`, mất hết đom đóm, chờ 60 tick, hồi sinh ở điểm xuất phát với bất tử 90 tick. Hết lửa → thua ngay |
| P10 | Thắng/thua | Thắp đèn cuối đúng tick hết giờ → `won`. Hết lửa cùng tick thắp đèn cuối → `lost no_flames`. Thắp đèn cuối rồi Tỏa Sáng cùng tick vẫn được tính điểm |
| P11 | 3 bản đồ | `--night 1/2/3` cho đúng số đèn 5/6/7 và vị trí đèn, điểm xuất phát, bùa, thời gian 300/330/360 s (tên đảo hiện ở bản web). Đêm 2: đi qua cầu, bục nhảy đưa từ đảo A sang B (bỏ qua phím di chuyển). Đêm 3: đi lên dốc 30° tới tầng 1; đi thẳng vào vách thì bị chặn; bục (0,3,13) đưa lên tầng 2; tháp chặn |
| P12 | Pause (headless) | Cạnh lên `pause` → `paused {}`, sim_tick, thời gian, hồi chiêu, spawn đứng yên, snapshot `state: "paused"`. Cạnh lên tiếp → `resumed {}` |
| P13 | Contract v1.1 | Snapshot có `night`, `wind`, `player.{vel, grounded, invuln, dash_cd_s, pulse_cd_s, charm_s}`, `motes`, `drifters`, `charms`. Sự kiện đúng tên và đúng khóa. Sai định dạng → thoát mã 2 |
| P14 | Tất định | Cùng seed, Đêm, scenario, input → file ra giống hệt từng byte |
| P15 | Hiệu năng | Một Đêm 3 đầy đủ 21600 tick chạy xong ≤ 30 s |
| P16 | FPS | Bản web ở 1280×720 đạt ≥ 30 FPS trung bình |

### Phần 3 (tính năng mới)

| # | Tính năng | Làm A thì thấy B |
|---|---|---|
| F1 | Gió Lạc | Đêm 2, Mây mang 5 con, Gió Lạc cách 10 m → `chase` 7 m/s, chạm ở XZ ≤ 1.2 m (tick 76) → `drifter_steal {amount 3}`, mang còn 2, chuyển `flee` 240 tick rồi biến mất. Mang 4 con, hoặc cách 15.5 m → vẫn `idle` (đúng 15 m → `chase`). Bất tử và vùng an toàn không chặn. Tỏa Sáng trúng lúc `chase` → `flee` không cướp; trúng lúc `flee` có đồ → `drifter_drop`, đồ thành đom đóm rơi. Đêm 1 không có Gió Lạc; Đêm 2 sinh ở tick 1200, 2400…, tối đa 2 |
| F2 | Bùa Gió | Đêm 2 đi qua (35,0,0) (hoặc bùa trong scenario) → `charm_picked {charm_ticks 600}`, tốc độ 7.2 m/s, Lướt không hồi chiêu (nhấn khi đang lướt bị bỏ). Bùa xuất hiện lại sau 2700 tick. Nhặt lại thì làm mới 600, không cộng dồn |
| F3 | Chuỗi 3 Đêm | Menu → bấm Bắt đầu → màn giới thiệu "Đảo Bến" có lời Ông Đăng → chơi. Thắng → kết quả → Đêm 2 → Đêm 3 → màn Bình Minh, tổng điểm = tổng điểm các Đêm thắng. Thua → nút chơi lại Đêm đó (điểm 0, đủ giờ) |
| F4 | Tạm dừng | Nhấn Esc hoặc P → hiện menu Tiếp tục / Chơi lại Đêm / Cài đặt / Về menu, tick logic không tăng. Tiếp tục → tick tăng lại |
| F5 | Cài đặt | Đổi âm lượng và độ nhạy chuột, tải lại trang → giá trị vẫn giữ (localStorage) |
| F6 | Âm thanh | Có nhạc nền đêm và tiếng cho: nhặt, thắp đèn, tỏa sáng, bị đánh, nhảy, lướt, thắng, thua, Bóng Mực xuất hiện, đếm ngược 10 s cuối |
| F7 | HUD | Thấy: Ngọn Lửa trên trái; đồng hồ mm:ss trên giữa, ≤ 30 s thì đỏ và nhấp nháy; đèn k/n và điểm trên phải; thanh 10 ô đom đóm dưới giữa; biểu tượng hồi Lướt (Shift) và Tỏa Sáng (F) dưới phải; đứng gần đèn hiện "E — Nạp ánh sáng (x/10)"; đèn chưa sáng gần nhất ở ngoài màn hình thì có mũi tên chỉ |
| F8 | Bảng màu | Các thành phần liệt kê trong ticket dùng đúng mã hex (lệch ≤ 10% mỗi kênh). Kiểm bằng đọc mã nguồn `web/index.html` (biến CSS, vật liệu `M`) và ảnh chụp |
| F9 | Ánh sáng môi trường | Thắp 1/5 đèn → `ambient.intensity` = 0.15 + 0.55 × 1/5 = 0.26 |

## 4. Xử lý thay đổi yêu cầu

Ticket thắng giả định Phase 1. Test cũ kiểm luật bị thay thì được **sửa, không xóa im lặng**; mỗi test đổi có chú thích `# Ticket-02: ...`. Chi tiết từng test: [tests/CHANGES-phase-2.md](../../tests/CHANGES-phase-2.md).

| Luật Phase 1 (giả định) | Thay bằng | Test bị ảnh hưởng |
|---|---|---|
| A1/A6/A5: mang 5, đèn 5, nạp 2.5 m | mang 10, đèn 10, nạp 2.0 m | `Motes.test_capacity`, `Lanterns.*`, s02, s05 |
| A2: Tỏa Sáng tốn 1, 6 m (2D), choáng 180, hồi 60, +20 | tốn 3, 5 m (3D từ chân + 0.8), choáng 120, hồi 180, +5 | `Pulse.*`, s01 (dựng lại) |
| A3: đom đóm rơi mất hẳn | nằm lại trên đất, nhặt lại được | test mới `DroppedMotes.*`, s08 |
| A4: vùng an toàn 4 m | 6 m, đẩy Bóng đang ở trong ra | `Shades.test_safe_radius_of_lit_lantern`, s09 |
| A7: bờ chắn 30 m, không rơi | đảo 40 m, rơi được | `Movement.test_island_edge_clamp` **bỏ, thay** bằng `test_island_edge_falls` |
| A9: bất tử 120 tick | 90 tick | `Shades.test_hit_drop_invuln_and_lose` |
| A11: 5 đèn bán kính 18 m, 40 đom đóm, Bóng mỗi 1200 tick | bản đồ chuẩn, 20 đom đóm, Bóng 2 con ở tick 300 rồi mỗi 480 tick | `Determinism.test_default_level`, s21 |
| A13: thắng ngay khi thắp đèn cuối | xét thắng/thua cuối tick | s19, s20 |
| Điểm khi nhặt | điểm khi nạp | `TickModel.test_snapshot0_before_input_and_event_tick`, s05 |
| Bóng Mực 3.5 m/s, luôn đuổi | 4.0 m/s, chỉ đuổi trong 12 m | `Shades.test_chase_speed`, s03 |
| Không có `night_start` | `night_start` ở tick 0 | mọi scenario thêm dòng đầu `[0, "night_start", {...}]` |

Kỳ vọng mới đều tính tay từ ticket (`_why` trong `*.expect.json` và chú thích trong test), không chép từ output.
