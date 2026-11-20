# ADR-001: Đèn có nhiên liệu và luật thắng lúc bình minh

- Trạng thái: Đã chấp nhận (Phase 3, Contract v1.2)
- Nguồn: [docs/lab/ticket-03.txt](../lab/ticket-03.txt). Thiết kế chi tiết: [phase-3-design.md](phase-3-design.md). Kết quả: [phase-3.md](phase-3.md).

## Bối cảnh

Phase 2 có đèn chỉ có hai trạng thái: `{chưa sáng, sáng mãi mãi}`. Người chơi giỏi thắp hết đèn trong khoảng 2 phút, game kết thúc ngay (`all_lit`), nên cuối Đêm thiếu căng thẳng. Ticket-03 đổi mục tiêu thành "giữ đảo sáng tới bình minh".

## Quyết định

1. **Mô hình trạng thái đèn** đổi từ `{unlit, lit forever}` sang `{unlit, lit(fuel), out → ever_lit}`:
   - Fuel lưu bằng đơn vị nguyên, 1 fuel = 60 đơn vị (tối đa 6000). Snapshot ghi số thực 1 chữ số. Lý do: tránh sai số số thực khi hao 1/60 mỗi tick.
   - Đèn hao 1 đơn vị mỗi tick. Bóng Mực đang `drain` hút 5 đơn vị mỗi tick. Hết dầu thì tắt (`lantern_out`) và nhớ `ever_lit`.
   - Thắp lại đèn đã từng sáng chỉ tốn 5 đom đóm (`relight_cost`), đèn chưa từng sáng tốn 10.
   - Châm dầu bằng Tương tác trên đèn đang sáng chưa đầy.
2. **Vùng an toàn** chỉ có khi fuel ≥ 30 (đúng 30 vẫn có).
3. **Bóng Mực có trạng thái `drain`**: đứng yên bên đèn yếu (fuel < 30) gần nhất trong 2 m và hút dầu. Đây là trạng thái mới, không có trong ticket.
4. **Luật thắng**: bỏ thắng sớm `all_lit`. Chỉ xét ở cuối tick bình minh: còn Mây, và số đèn đang sáng ≥ ceil(0.6·N). Hết Ngọn Lửa luôn thua `no_flames`, kể cả cùng tick bình minh.

Các quyết định triển khai do agent mô phỏng (sim) báo lại, ticket không nói rõ:

- Drain bắt đầu từ tick **sau** khi Bóng Mực vào trong 2 m (kiểm tra trước khi di chuyển).
- Sự kiện `fuel_drain` đầu tiên ghi khi đủ 60 tick đang hút. Nếu drain bắt đầu ở tick 1 thì sự kiện đầu ở tick 61, sau đó 121, 181.
- Scenario có đèn `fuel > 0` nhưng `lit: false` thì đèn được coi là sáng.
- Fuel nằm ngoài 0..100 trong scenario → thoát mã 2.
- `target_lantern_id` chỉ áp dụng cho lựa chọn wander đầu tiên.
- Hao dầu chạy ở bước 2, trước tương tác. Đèn ở 100 fuel sẽ mất 1 đom đóm ở tick kế tiếp (không phải 0).
- Wander đi tới đèn tắt gần nhất cho đến khi cách 4 m, rồi lượn quanh đèn.

## Hệ quả

- Người chơi phải quay lại châm đèn trong Đêm. Trận đấu kéo dài và căng hơn.
- Test cũ về "thắp hết đèn là thắng" và điểm cũ bị thay thế. Danh sách ở [tests/CHANGES-phase-3.md](../../tests/CHANGES-phase-3.md).
- Các số trong `tuning` (`relight_cost`, `drain_per_s`, `win_ratio`, ...) được test so khớp với `game.contract.json`.
- Tên khóa điểm (`per_relight`, `per_drain_stun`, `per_lit_lantern_dawn`) do thiết kế đặt, vì ticket chỉ cho số điểm. Ghi rõ trong CHANGES.
- Sức chứa tăng theo số lần thắp thành công (tối đa 20). Đèn đặt sẵn bằng scenario không tính.

## Phương án đã cân nhắc

- **Giữ float cho fuel**: bị loại. Hao 1/60 mỗi tick cộng dồn sai số, làm lệch thời điểm hết dầu và vùng an toàn ở biên (ví dụ đúng 30).
- **Giữ thắng sớm `all_lit` và chỉ thêm dầu**: bị loại. Ticket yêu cầu bỏ thắng sớm, nên người chơi vẫn thắp hết trong 2 phút.
- **Thắng khi đủ đèn ngay tại thời điểm bất kỳ trong Đêm**: bị loại. Ticket yêu cầu xét ở bình minh, vì người chơi phải giữ được đèn tới cuối.
- **Drain ngay trong tick Bóng Mực vào trong 2 m**: bị loại. Thứ tự tick của ticket xử lý trạng thái ở bước 8 và hút dầu ở bước 2, nên hiệu lực chỉ tới tick sau.
