# Phase 3: Ticket-03 "Đèn cạn dầu" + Test Contract v1.2

Nguồn: [docs/lab/ticket-03.txt](../lab/ticket-03.txt). Thiết kế chung: [phase-3-design.md](phase-3-design.md). Quyết định kiến trúc: [ADR-001](adr-001-lantern-fuel.md). Bằng chứng: [docs/proof/phase-3/README.md](../proof/phase-3/README.md). Đổi phá vỡ: [CHANGELOG.md](../../CHANGELOG.md).

## 1. Thay đổi so với Phase 2

| Thay đổi | Lý do |
|---|---|
| Đèn có nhiên liệu (0–100), hao 1/giây, châm dầu bằng Tương tác, hết dầu thì tắt | Ticket Phần 1. Người chơi giỏi không còn thắp hết đèn rồi kết thúc sớm |
| Thắp lại đèn đã từng sáng chỉ tốn 5 đom đóm (`ever_lit`) | Ticket Phần 1. Thưởng cho việc giữ đèn sống, không chỉ thắp lần đầu |
| Bóng Mực có trạng thái `drain`: tìm đèn yếu (fuel < 30) và hút dầu | Ticket Phần 2. Tạo áp lực lên đèn đang yếu |
| Vùng an toàn chỉ khi fuel ≥ 30 | Ticket Phần 2. Đèn yếu không còn che chở |
| Bỏ thắng sớm `all_lit`. Thắng xét lúc bình minh với ≥ 60% đèn đang sáng | Ticket Phần 3. Đúng mục tiêu "giữ đảo sáng tới bình minh" |
| Điểm theo công thức mới, bỏ thưởng thời gian | Ticket Phần 5 |
| Sức chứa tăng theo số lần thắp (10 → tối đa 20) | Ticket Phần 4 |
| Cài đặt "Bảng màu dễ phân biệt" (được lưu) | Ticket Phần 6 |
| Thời gian Đêm 240 / 270 / 300 s | Ticket Phần 3 |

Luật Phase 2 không bị ticket thay thì vẫn giữ ([phase-2-design.md](phase-2-design.md), [phase-2.md](phase-2.md)).

## 2. Giả định và quyết định

Toàn bộ ở [phase-3-design.md](phase-3-design.md). Các quyết định chính nằm trong [ADR-001](adr-001-lantern-fuel.md): đơn vị nguyên ×60, mô hình trạng thái đèn, luật thắng ở bình minh.

## 3. Tiêu chí nghiệm thu (làm A thì thấy B)

### Phần 1: Nhiên liệu đèn

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| N1 | Thắp mới | Đèn chưa sáng nhận đủ 10 đom đóm → `lantern_lit {relight: false}`, fuel 100.0, +100 điểm và +5 mỗi đom đóm |
| N2 | Hao dầu | Đèn sáng không ai chạm: sau 60 tick fuel giảm đúng 1.0 (99.0), không sai số |
| N3 | Châm dầu | Đèn sáng ở fuel 25.5, mang 10 → dùng 8 đom đóm, fuel 100.0, còn 2 đom đóm, `refuel {amount: 8}`, +40 |
| N4 | Đèn đầy không được chọn | Đèn đầy dầu, mang 0 đom đóm → không có sự kiện, không cộng điểm |
| N5 | Hết dầu | Đèn ở fuel 1.0 tắt đúng tick 60: `lantern_out`, deposited 0, `ever_lit: true` |
| N6 | Thắp lại | Đèn đã từng sáng, tắt rồi, nạp 8 đom đóm → chỉ dùng 5, `lantern_lit {relight: true}`, +40 |
| N7 | Hiển thị (web) | Đèn sáng có thanh dầu. Fuel < 30 thì đèn và thanh dầu nhấp nháy khoảng 1 Hz. Fuel ≥ 30 thì không nhấp nháy |

### Phần 2: Bóng Mực hút dầu

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| S1 | Vùng an toàn | Đèn fuel 29.9 không có vùng an toàn; đúng 30.0 vẫn còn |
| S2 | Chọn đèn yếu | Bóng Mực wander đi tới đèn sáng fuel < 30 gần nhất, bằng nhau thì id nhỏ hơn. Không có thì đi tới đèn tắt gần nhất |
| S3 | Drain | Bóng Mực vào trong 2 m của đèn yếu → `drain`, đứng yên, đèn mất thêm 5/giây. Hai con cộng dồn |
| S4 | Ra khỏi drain | Mây vào trong 6 m → `chase`. Trúng Tỏa Sáng → `stunned`. Đèn tắt, hoặc fuel lên ≥ 30, hoặc cách > 2 m → `wander` |
| S5 | Sự kiện hút | Bóng Mực hút liên tục 60 tick → `fuel_drain` (tick 61 nếu bắt đầu ở tick 1), rồi mỗi 60 tick |
| S6 | Đẩy khỏi vùng an toàn | Châm đèn lên ≥ 30 khi Bóng Mực đang hút → Bóng Mực bị đẩy ra mép trong ≤ 30 tick, không gây sát thương |

### Phần 3: Luật thắng

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| W1 | Không thắng sớm | Thắp hết 5/5 đèn ở tick 1 → không kết thúc Đêm, điểm chỉ gồm đèn và nạp |
| W2 | Ngưỡng | Đêm 1 với 3/5 đèn sáng lúc bình minh → thắng. Với 2/5 → thua `dawn`. Đêm 2 cần 4/6, Đêm 3 cần 5/7 |
| W3 | Thứ tự trong tick | Đèn có fuel về 0 đúng tick bình minh thì không được tính là sáng |
| W4 | Hết Ngọn Lửa trước | Hết Ngọn Lửa đúng tick bình minh, dù đủ đèn → `lost no_flames` |
| W5 | Lý do kết thúc | Thắng: `dawn_survived`. Thua: `dawn` hoặc `no_flames`. Không có `all_lit` |

### Phần 4: Sức chứa

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| C1 | Công thức | Chưa thắp đèn nào: sức chứa 10. Thắp 1 đèn: 12. Thắp 5 đèn: 20. Không vượt 20 |
| C2 | Đèn đặt sẵn | Đèn `lit: true` đặt bằng scenario không làm tăng sức chứa |
| C3 | Thắp lại tính | Thắp lại đèn đã từng sáng làm tăng sức chứa. Châm dầu không làm tăng |
| C4 | HUD (web) | HUD hiện "đang mang / sức chứa", ví dụ 10/12 sau một lần thắp |

### Phần 5: Điểm

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| G1 | Nạp | Mỗi đom đóm nạp (thắp mới, thắp lại, châm dầu) +5. Nhặt không cộng điểm |
| G2 | Thắp | Thắp lần đầu +100, thắp lại +40 |
| G3 | Tỏa Sáng | Mỗi Bóng Mực trúng +5. Con đang `drain` ngay trước đó +15 |
| G4 | Bình minh (thắng) | Mỗi đèn sáng +50 + floor(fuel), mỗi Ngọn Lửa còn lại +50. Không có thưởng thời gian |
| G5 | Bình minh (thua) | Không cộng điểm bình minh |
| G6 | Tổng web | Tổng điểm chơi nhiều Đêm = tổng các Đêm thắng, không đổi so với Phase 2 |

### Phần 6: Chế độ mù màu

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| B1 | Cài đặt | Có "Bảng màu dễ phân biệt", tắt mặc định, được lưu sau khi tải lại trang |
| B2 | Màu Bóng Mực | Bật: viền và mắt `#00B3FF`. Tắt: `#7A3CFF` |
| B3 | Cảnh báo | Bật: màu cảnh báo `#FFFFFF` kèm ⚠. Tắt: `#FF5A5F` |
| B4 | Hình dạng | Đèn tắt bị xẹp 20% và có vết rách. Đèn sắp hết dầu nhấp nháy |

### Phần 7: Contract v1.2

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| T1 | Số liệu | `game.contract.json` có `contract_version "1.2"`, `tuning` khớp `sim.TUNING` với các khóa mới |
| T2 | Snapshot | Mỗi đèn có `fuel`, `ever_lit`, `relit_count`; `player` có `capacity`; Bóng Mực có `drain` |
| T3 | Scenario | Đèn có `fuel` và `ever_lit`; `player` có `successful_lights`; `shades[]` có `target_lantern_id` |
| T4 | Sự kiện | `refuel`, `lantern_out`, `fuel_drain`, `lantern_lit.relight` đúng khóa. Sai định dạng → thoát mã 2 |
| T5 | Tất định | Mọi kịch bản chạy hai lần cho file giống hệt từng byte |

## 4. Xử lý thay đổi yêu cầu

Ticket thắng giả định Phase 2. Test cũ bị luật mới làm sai được **sửa, không xóa im lặng**. Mỗi test đổi có chú thích `# Ticket-03: ...`. Chi tiết từng test và các kỳ vọng phụ thuộc quyết định thiết kế: [tests/CHANGES-phase-3.md](../../tests/CHANGES-phase-3.md).

Ticket không nói rõ một số chi tiết (thời điểm `fuel_drain` đầu tiên, tên khóa điểm, mục tiêu wander khi không có đèn yếu). Những chỗ này do [phase-3-design.md](phase-3-design.md) quyết định và được ghi trong [ADR-001](adr-001-lantern-fuel.md).
