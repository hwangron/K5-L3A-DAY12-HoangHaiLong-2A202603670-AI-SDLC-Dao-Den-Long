# Phase 3 — Thiết kế chung (Ticket-03 "Đèn cạn dầu", Contract v1.2)

Nguồn: [docs/lab/ticket-03.txt](../lab/ticket-03.txt). Ticket thắng file này nếu mâu thuẫn. Mọi luật Phase 2 không bị ticket thay vẫn giữ ([phase-2-design.md](phase-2-design.md)).

## Phân công file
| Agent | Sở hữu |
|---|---|
| coder (sim) | `game/sim.py`, `game/maps.py`, `headless.py`, `game.contract.json` |
| tester | `tests/**`, `tools/check.py` |
| coder (web) | `web/index.html`, `tools/web_check.py` |
| docs-writer | `README.md`, `CHANGELOG.md`, `docs/notes/adr-001-lantern-fuel.md`, `docs/notes/phase-3.md`, `docs/proof/phase-3/**`, `docs/notes/ai-log.md`, `AGENTS.md` |

## Quyết định

**Dầu**
- Lưu bằng **đơn vị nguyên = fuel × 60**: tối đa 6000, mỗi tick tự hao 1 đơn vị, mỗi Bóng Mực đang `drain` hút 5 đơn vị/tick.
- Snapshot ghi `fuel = round(units/60, 1)`. Đèn tắt ghi 0.
- Bước 2 (giảm bộ đếm) trừ dầu: tự hao + bị hút bởi các Bóng Mực đang `drain` từ tick trước. Ngay sau bước 2, đèn có units ≤ 0 thì tắt:
  - `lit = false`, `deposited = 0`, `ever_lit = true`, units = 0, sự kiện `lantern_out {lantern_id}`.
  - Bóng Mực đang hút đèn đó chuyển về `wander` ở bước di chuyển.
- `fuel_drain {lantern_id, shade_id, fuel}`: ghi khi một Bóng Mực đã hút liên tục đủ 60, 120, … tick (đếm từ tick nó vào `drain`), sau khi trừ dầu ở bước 2. `fuel` là dầu sau khi trừ, 1 chữ số thập phân.

**Tương tác**
- Ứng viên là đèn trong 2.0 m (XZ) và:
  - chưa sáng; hoặc
  - đang sáng có `used = min(carried, ceil((6000 − units)/600)) > 0`.
- Chọn gần nhất, bằng nhau thì id nhỏ hơn. Không mang gì thì không có ứng viên.
- **Đèn chưa sáng:** nạp như cũ với chi phí 10 (chưa từng sáng) hoặc `relight_cost` 5 (`ever_lit`).
  - Mỗi đom đóm +5.
  - Đủ chi phí thì sáng: units = 6000, `successful_lights += 1`, `lantern_lit {lantern_id, relight}`.
  - Thắp lần đầu +100. Thắp lại +40 và `relit_count += 1`.
- **Đèn đang sáng:** châm dầu, units = min(6000, units + 600·used), trừ `used` đom đóm, mỗi đom đóm +5, sự kiện `refuel {lantern_id, amount: used, fuel}`.

**Vùng an toàn**
- Chỉ đèn đang sáng có units ≥ 1800 (fuel ≥ 30) mới có vùng an toàn. Đúng 30 vẫn còn.
- Bước 6: đèn nào có vùng an toàn thì đẩy Bóng Mực đang ở trong ra mép (30 tick, vô hại), như Phase 2. Nhờ vậy đèn vừa thắp hoặc vừa được châm lên ≥ 30 tự đẩy Bóng Mực ra.
- Bóng Mực đang `drain` bị đẩy thì về `wander`.

**Bóng Mực**
- Trạng thái: `spawning, wander, chase, recoil, stunned, drain`.
- `wander` chọn mục tiêu mỗi tick, theo thứ tự ưu tiên:
  1. Đèn đang sáng có fuel < 30 gần nhất (bằng nhau thì id nhỏ hơn).
  2. Nếu không có: đèn đang tắt gần nhất. Đi tới cách đèn 4 m rồi lượn quanh như wander cũ (điểm ngẫu nhiên trong 6 m quanh đèn đó).
  3. Nếu không có đèn tắt nào: wander cũ quanh vị trí gốc.
- Tốc độ wander 1.5 m/s.
- `target_lantern_id` trong scenario: đặt mục tiêu ban đầu nếu đèn đó hợp lệ.
- Ưu tiên chuyển trạng thái giữ như Phase 2: `wander` → `chase` khi Mây ≤ 12 m (kiểm tra trước). Không chase mà cách đèn yếu mục tiêu ≤ 2 m (XZ) thì → `drain` (đứng yên, bắt đầu hút từ bước 2 của tick sau).
- Từ `drain`:
  - → `chase` nếu Mây ≤ 6 m (XZ);
  - → `wander` nếu đèn tắt, fuel ≥ 30, cách > 2 m, hoặc bị đẩy khỏi vùng an toàn.
  - Bóng đang `drain` vẫn gây sát thương khi chạm như `wander`/`chase`.
- Hết `stunned` → **`wander`** (thay luật Phase 2 "về chase/wander theo khoảng cách"). Hết `recoil` giữ như Phase 2.

**Tỏa Sáng**
- +5 mỗi con. Con đang `drain` ngay trước khi trúng thì tổng +15.

**Thắng/thua** (bước cuối của tick)
1. Hết lửa → `lost no_flames`.
2. Còn lại, hết giờ (time_left ≤ 0):
   - số đèn đang sáng ≥ ceil(0.6 × tổng) → `won dawn_survived`;
   - ngược lại → `lost dawn`.
- Không còn thắng sớm, không còn `all_lit`.
- Khi thắng cộng: mỗi đèn đang sáng +50 + floor(fuel), mỗi lửa +50. Bỏ thưởng thời gian.

**Sức chứa**
- `capacity = min(20, 10 + 2·successful_lights)`. Đếm cả thắp lại. Đèn đặt sẵn bằng scenario không tính.
- Scenario có `player.successful_lights`. Snapshot có `player.capacity`.

**Số liệu (TUNING)**
- Đổi: night1/2/3_duration_s = 240/270/300.
- Thêm: fuel_max 100, fuel_decay_per_s 1.0, fuel_per_mote 10, relight_cost 5, win_ratio 0.6, drain_per_s 5, low_fuel_threshold 30, capacity_max 20.
- `carry_capacity` = 10 (sức chứa gốc).
- score: per_mote 5, per_lantern 100, per_stun 5, per_second_left 0, per_flame_left 50. Thêm per_relight 40, per_drain_stun 15, per_lit_lantern_dawn 50.

**Scenario đèn**
- `lit`, `fuel`, `ever_lit`, `deposited`.
- `lit: true` mà không có `fuel` → 100. `ever_lit` mặc định = `lit`.
- `relit_count` mặc định 0.

**Snapshot đèn:** `id, pos, lit, deposited, fuel, ever_lit, relit_count`.

**Web glue:** không đổi giao diện. Snapshot có thêm trường mới. Bản web tự tính `needed = ceil(0.6 × tổng)` để hiện trên HUD.
