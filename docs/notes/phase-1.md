# Phase 1: PRD-0 + Test Contract v1.0

## Quyết định kiến trúc

- **Python thuần cho luật chơi** ([game/sim.py](../../game/sim.py)): không cần thư viện, máy chấm chạy được ngay trên macOS/Linux, dễ đảm bảo tất định.
- **Bản 3D là trang web** (Three.js). Trang này chạy **cùng file `sim.py`** qua Pyodide, nên luật chơi chỉ có một bản, không thể lệch giữa lúc chơi và headless. Bản web cũng giải quyết yêu cầu "dùng Windows thì phải có cách chạy cho macOS/Linux".
- Bỏ Ursina: nếu dùng thì phải cài Panda3D, nặng và dễ lỗi trên máy chấm.

## Giả định (chỗ PRD-0 chưa nói rõ)

| # | Chỗ mơ hồ | Giả định của tôi |
|---|---|---|
| A1 | "Máu" là gì | `flames` = 3 ngọn lửa. Mỗi lần bị chạm mất 1 |
| A2 | Tỏa sáng "tốn ánh sáng" | Tốn `pulse_cost` = 1 đom đóm đang mang. Không có đom đóm thì không tỏa sáng được và không ghi sự kiện. Đang hồi chiêu cũng vậy |
| A3 | Đom đóm bị rơi khi trúng đòn | Rơi `floor(carried × 0.5)` con và **mất hẳn** (bay đi), không rơi xuống đất |
| A4 | "Bóng Mực sợ đèn" | Chỉ **đèn đã thắp** mới có vùng an toàn `safe_radius` 4 m. Bóng Mực bị đẩy ra mép vùng. Đèn chưa thắp không bảo vệ |
| A5 | Nạp đèn | Nhấn `interact` trong 2.5 m của đèn chưa thắp gần nhất (bằng nhau thì chọn id nhỏ hơn). Nạp `min(carried, cost - deposited)`. Nạp nhiều lần được |
| A6 | Nhặt đom đóm | Tự nhặt khi ở trong 1 m. Đầy 5 con thì đom đóm nằm lại |
| A7 | Rơi khỏi đảo | Không có: bờ chắn vô hình ở bán kính 30 m, nên `fall_enabled: false`. Bờ chỉ chặn bước đi **ra ngoài**. Vị trí scenario đặt ngoài 30 m được giữ nguyên, không bị kéo vào |
| A8 | Bóng Mực bị choáng | Không di chuyển và không gây sát thương trong đúng 180 tick. Choáng ở tick t thì trạng thái `stunned` kéo dài các tick t … t+179 |
| A9 | Miễn sát thương, hồi chiêu | Tính bằng tick: trúng đòn ở tick t thì bị trúng lại sớm nhất ở tick t+120. Tỏa sáng ở tick t thì dùng lại được từ tick t+60 |
| A10 | Điểm thời gian | Chỉ cộng khi thắng: `per_second_left × floor(time_left_s)` và `per_flame_left × flames` |
| A11 | Màn mặc định | 5 đèn trên vòng tròn bán kính 18 m (L1 ở (0,0,18), cách nhau 72°). 40 đom đóm ngẫu nhiên, cứ 4 s thêm 1 con nếu dưới 40. Bóng Mực: con đầu ở tick 300, sau đó mỗi 1200 tick, tối đa 6, xuất hiện ở mép đảo cách người chơi ≥ 12 m. Lúc dựng màn chưa có Bóng Mực nào |
| A12 | Nhảy | Vận tốc ban đầu 7 m/s, trọng lực 20 m/s². Chỉ để hiển thị. Va chạm đo theo mặt phẳng XZ nên nhảy không né được Bóng Mực |
| A13 | Thứ tự xử lý trong một tick | input → di chuyển/nhảy → nhặt → nạp đèn (có thể thắng) → tỏa sáng → Bóng Mực di chuyển → va chạm (có thể thua) → sinh thêm → kiểm tra bình minh |
| A14 | Snapshot | Chỉ ghi ở các tick chia hết cho `--snapshot-every`. Khi game kết thúc giữa chừng thì không thêm snapshot riêng; dòng `end` vẫn luôn có |
| A15 | `move` vượt [-1, 1] | Kẹp về [-1, 1]. Sai kiểu dữ liệu (không phải số, thiếu phần tử) thì báo sai định dạng, thoát mã 2 |
| A16 | Scenario đặt `lit: true` mà không có `deposited` | `deposited` = `lantern_cost` |
| A17 | Bóng Mực trong scenario | Giữ nguyên y được cho. Bóng Mực tự sinh có y = 1.0 (tâm). Id tự sinh (S1, S2…) bỏ qua các id scenario đã dùng |
| A18 | So bán kính | `≤ r + 1e-6` để sai số cộng dồn số thực không làm lệch 1 tick |
| A19 | Scenario đặt sẵn cả 5 đèn `lit: true` | Không tự thắng: dựng scenario không phát sự kiện, và thắng chỉ xảy ra khi có `lantern_lit` |
| A20 | `time_left_s: 0` | Game kết thúc ở bước đầu tiên (tick 1, `lost dawn`), vì snapshot tick 0 là trạng thái trước mọi xử lý |
| A21 | Số nguyên ghi dạng `2.0` | Chấp nhận như `2`. File scenario không phải object JSON (`[]`, `null`) thì báo sai định dạng, thoát mã 2 |

## Tiêu chí nghiệm thu (mỗi dòng kiểm tra được)

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| R1 | Đi lại, camera | `move [0,1]`, yaw 90°, 60 tick → pos = (6, 0, 0). Vector chéo được chuẩn hóa về tốc độ 6 m/s |
| R2 | Nhảy | Nhấn jump → y > 0.5 ở tick 20 → y = 0 ở tick 60 |
| R3 | Nhặt đom đóm | Đom đóm cách đúng 1.0 m thì nhặt, 1.01 m thì không. Đầy 5 con thì không nhặt thêm |
| R4 | Nạp, thắp đèn | Nạp 3 thì chưa sáng; nạp đủ 5 → sự kiện `lantern_lit`, +100 điểm |
| R5 | Thắng | Đèn cuối được thắp → `game_over won all_lit`, điểm có cộng thưởng (848 trong s02) |
| R6 | Bóng Mực đuổi | Đi 3.5 m/s về phía người chơi. Không vào vòng 4 m quanh đèn đã thắp |
| R7 | Trúng đòn, thua | Mất 1 lửa, rơi floor(carried/2) đom đóm, miễn sát thương 120 tick. Hết lửa → `lost no_flames` |
| R8 | Tỏa sáng | Tốn 1 đom đóm. Choáng các Bóng Mực trong ≤ 6 m trong 180 tick, đẩy lùi 4 m, +20 điểm mỗi con. Hồi 60 tick |
| R9 | Bình minh | Hết `time_left_s` → `lost dawn` |
| R10 | Contract | Đúng mô hình tick, định dạng JSONL, dòng `end` cuối, làm tròn 3 chữ số, mã thoát 2 khi file sai định dạng |
| R11 | Tất định | Cùng seed, scenario và input → file đầu ra giống hệt từng byte |
| R12 | HUD, chơi lại | HUD hiện lửa, đom đóm, số đèn, thời gian, điểm, trạng thái tỏa sáng. Hết game nhấn Enter → ván mới, điểm 0 |
| R13 | Phong cách | Đêm tím tối, ánh sáng vàng cam là thứ tốt, Bóng Mực tím đen, Mây đội nón lá có đèn nhỏ, đảo sáng dần |

Bằng chứng cho từng dòng: [docs/proof/phase-1/README.md](../proof/phase-1/README.md).

## Đánh giá Phase 1

Xem phần cuối của [docs/proof/phase-1/README.md](../proof/phase-1/README.md).
