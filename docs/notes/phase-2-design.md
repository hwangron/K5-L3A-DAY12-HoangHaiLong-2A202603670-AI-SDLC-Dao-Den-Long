# Phase 2 — Thiết kế chung (Ticket-02, Contract v1.1)

Nguồn yêu cầu: [docs/lab/ticket-02.txt](../lab/ticket-02.txt). File này chốt mọi chỗ ticket chưa nói rõ và giao diện giữa các phần, để các agent làm song song không lệch nhau. **Ticket thắng file này nếu mâu thuẫn.**

## 1. Phân công file (mỗi agent chỉ sửa file của mình)

| Agent | Sở hữu |
|---|---|
| core | `game/sim.py`, `game/maps.py` (mới), `headless.py`, `game.contract.json` |
| test | `tests/**`, `tools/check.py` |
| web | `web/index.html`, `tools/web_check.py`, `tools/build_web.py` |
| docs | `README.md`, `AGENTS.md`, `.claude/skills/**`, `docs/notes/phase-2.md`, `docs/notes/ai-log.md`, `docs/proof/phase-2/**` |

## 2. Quy ước chung

- 60 tick/s. Góc θ đo từ +X: **x = r·cosθ, z = r·sinθ** (để tầng 1 của Đêm 3 ở "nửa z > 0" chứa các điểm 20°…160°).
- Mọi bộ đếm lưu bằng **tick nguyên**. Snapshot đổi ra giây: `ticks/60`, làm tròn 3 chữ số.
- **Bộ đếm giảm ở bước 2.** Một hiệu ứng đặt `n` tick ở tick t thì kéo dài các tick t … t+n−1 và hết ở tick t+n. Ví dụ: choáng 120 tick đặt ở tick 100 → snapshot tick 100…219 là `stunned`; ở tick 220 Bóng Mực di chuyển lại. Bất tử 90 tick: bị đánh ở t thì từ t+90 bị đánh lại được. Hồi Lướt 90 tick, hồi Tỏa Sáng 180 tick, bùa 600 tick, TTL đom đóm rơi 480 tick, hồi bùa 2700 tick, chờ hồi sinh 60 tick, recoil 60 tick, bị đẩy khỏi vùng an toàn tối đa 30 tick, Gió Lạc flee 240 tick (hoặc 120 tick sau khi thả đồ).
- So bán kính dùng `≤ r + EPS` (EPS = 1e-6).
- Điểm `--night` mặc định là 1. Tick model giữ như v1.0, cộng thêm pause.

## 3. Luật chi tiết (bổ sung cho ticket)

**Số liệu** (`TUNING`): player_speed 6.0, carry_capacity 10, lantern_cost 10, lantern_count_night1 5, pickup_radius 1.0, interact_radius 2.0, pulse_cost 3, pulse_radius 5.0, night1/2/3_duration_s 300/330/360, flames 3, invuln_s 1.5, hit_drop_ratio 0.5, pulse_stun_s 2.0, pulse_push_m 4.0, pulse_cooldown_s 3.0, safe_radius 6.0, shade_speed 4.0, shade_hit_radius 1.0, fall_enabled true, dash_speed 14.0, dash_duration_s 0.2, dash_cooldown_s 1.5. score: per_mote 10 (**tính khi nạp**, không tính khi nhặt), per_lantern 100, per_stun 5, per_second_left 2, per_flame_left 50.

**Di chuyển**
- Vận tốc ngang đổi **ngay lập tức** (0 tick, thỏa "≤ 0.1 s"); điều khiển trên không giống trên đất.
- Hướng mặt (`facing`) ban đầu là +Z, cập nhật theo hướng di chuyển thế giới khi có input.
- Mỗi tick thử bước ngang. Nếu mặt đất tại điểm mới cao hơn chân hiện tại quá 0.3 m (vách, tháp) thì bị chặn. Khi đó thử trượt từng trục (chỉ x, rồi chỉ z).
- Đang đứng trên đất mà mặt đất mới thấp hơn ≤ 0.3 m (đi xuống dốc) thì bám theo mặt đất. Thấp hơn nữa, hoặc không còn đất, thì rơi tự do.
- Trọng lực theo Euler như Phase 1: `y += vy·dt; vy -= 20·dt`. Chạm đất khi `y ≤ ground` và `vy ≤ 0`.
- Nhảy chỉ khi đang chạm đất, `vy = 7`.

**Lướt**
- Kéo dài 12 tick ở 14 m/s theo hướng input (đứng yên thì theo `facing`). Hướng được chốt lúc bắt đầu lướt.
- Trong lúc lướt: bỏ qua input di chuyển, `vy = 0` và không có trọng lực (giữ độ cao). Vách vẫn chặn.
- Hồi chiêu 90 tick tính từ tick bắt đầu. Nhấn lúc đang lướt bị bỏ qua. Có bùa thì không có hồi chiêu.
- Sự kiện `dash {}`.

**Bục nhảy**
- Kích hoạt khi đang chạm đất, chân trong bán kính 1 m quanh bục (XZ) và `|y − y_bục| < 0.05`. Mây được gán `vy` và vận tốc ngang cố định (Đêm 2: 14 và 24 m/s về tâm đảo kia, tính từ vị trí bục; Đêm 3: 12 và 8 m/s hướng −Z).
- Trạng thái "phóng" kéo dài tới khi chạm đất. Trong lúc phóng bỏ qua input di chuyển nhưng vẫn lướt được. Lướt tạm thay vận tốc ngang và giữ độ cao; lướt xong thì quay lại vận tốc phóng.

**Gió (Đêm 3)**
- Cơn gió bắt đầu ở tick 1800·k (k ≥ 1), kéo dài 300 tick.
- Hướng `dir_deg` chọn bằng rng ở tick bắt đầu − 120 (lúc báo trước), là số thực trong [0, 360).
- Trong lúc có gió, cộng 2 m/s theo (cos, sin) của hướng vào chuyển động ngang của Mây, cả lúc lướt hay phóng. Lúc chờ hồi sinh thì không cộng.
- Cờ scenario `wind_enabled` mặc định true ở Đêm 3, false ở Đêm 1–2.

**Rơi khỏi đảo**
- Kích hoạt khi y < −10, một lần mỗi lần rơi, bỏ qua bất tử.
- Mất 1 lửa và toàn bộ đom đóm. Sự kiện `player_hit {by:"fall", flames, dropped:0, lost:n}`.
- Sau đó chờ 60 tick: đứng yên, vận tốc 0, không nhặt, không bị chạm.
- Hồi sinh ở điểm xuất phát của Đêm, vận tốc 0, bất tử 90 tick, hướng mặt +Z.
- Hết lửa thì thua `no_flames` ngay, không hồi sinh.

**Đom đóm**
- Nhặt khi khoảng cách XZ ≤ 1.0 và `|y_Mây − y_đom_đóm| ≤ 1.5`, chưa đầy 10 con. Không cộng điểm khi nhặt.
- Mặc định: 20 con ở 20 điểm khác nhau, chọn ngẫu nhiên (rng) trong danh sách điểm sinh của Đêm.
- Ở tick 240·k, nếu **tổng số đom đóm đang có** (gồm cả đom đóm rơi) < 30 thì sinh 1 con ở một điểm sinh còn trống (chọn ngẫu nhiên). Không còn điểm trống thì bỏ lượt.
- `kind`: `random` (có `ttl_s: null`) hoặc `dropped`.
- Khi bị đánh, rơi `floor(carried/2)` con ra vành 1.5–2.5 m quanh Mây. Góc và bán kính lấy từ rng; y = mặt đất tại đó (không có đất thì lấy y của Mây). TTL 480 tick. Nhặt lại được từ tick sau.
- Scenario `motes`: nhận cả `[x,y,z]` lẫn `{pos}`, giữ đúng y được cho, kind `random`.

**Đèn**
- Nạp: nhấn E trong 2.0 m (XZ), chọn đèn chưa sáng gần nhất (bằng nhau thì id nhỏ hơn), nạp `min(carried, cost − deposited)`. Mỗi đom đóm nạp +10 điểm, thắp đèn +100.
- Vùng an toàn 6 m quanh đèn **đã sáng**. Bóng Mực ở ngoài bị chặn ở mép (chiếu ra mép như Phase 1).
- Ở bước 6, Bóng Mực nào đang ở trong vùng (d < 6) mà chưa bị đẩy thì bị đẩy ra mép. Mỗi tick đi `max((6 − d0)/30, 0)` theo hướng từ đèn ra ngoài (trùng tâm thì +X), tối đa 30 tick. Trong lúc bị đẩy thì không di chuyển bình thường và không gây sát thương. Không có tên trạng thái riêng.

**Tỏa Sáng**
- Cần ≥ 3 đom đóm và hết hồi chiêu. Tâm = chân Mây + (0, 0.8, 0).
- Mục tiêu là các Bóng Mực có khoảng cách **3D** tới tâm ≤ 5, chốt ngay ở tick kích hoạt: chuyển `stunned`, choáng 120 tick.
- Đẩy lùi tổng 4 m trong 15 tick đầu (4/15 m mỗi tick, theo hướng XZ từ Mây ra; trùng vị trí thì +X). Dừng đẩy nếu gặp tháp chuông.
- Pulse lại làm mới cả choáng lẫn đẩy. +5 điểm mỗi con, kể cả con đang choáng.
- Sự kiện `pulse {stunned_ids}` liệt kê con trúng, theo id tăng dần.

**Bóng Mực**
- Trạng thái: `spawning`, `wander`, `chase`, `recoil`, `stunned`.
- Sinh ra ở `spawning` đúng 1 tick (chính tick sinh): đứng yên, vô hại. Từ tick sau thì sang `wander`/`chase`. Ban đầu chọn 60 tick; sau review đổi về 1 tick để khớp câu trong ticket "thực thể mới chỉ tương tác được từ tick sau".
- Bóng Mực trong scenario giữ đúng y được cho cho tới khi nó di chuyển, vì máy chấm tính khoảng cách 3D theo tọa độ họ đặt.
- `wander`: bay 1.5 m/s tới một điểm ngẫu nhiên (rng) trong 6 m quanh vị trí gốc (vị trí sinh hoặc vị trí trong scenario). Chọn điểm mới khi tới nơi hoặc sau mỗi 180 tick.
- `wander` → `chase` khi khoảng cách XZ tới Mây ≤ 12. `chase` → `wander` khi > 18. Kiểm tra ở bước di chuyển của Bóng Mực, rồi di chuyển ngay trong tick đó.
- `chase` đi thẳng về phía Mây theo XZ, tốc độ 4.0 (Đêm 3: 4.5). Bay qua được vách và biển mây. y = mặt đất dưới nó + 1.0 (biển mây coi như mặt đất 0). Tháp chuông chặn (đẩy ra ngoài r = 2).
- Chạm: XZ ≤ 1.0 và `|y_Mây − y_Bóng| ≤ 1.5`; Bóng đang `chase` hoặc `wander`, không đang bị đẩy khỏi vùng an toàn; Mây không bất tử và không chờ hồi sinh. Xét theo thứ tự id tăng dần (số trong `S<n>`), tối đa 1 lần mỗi tick.
- Bóng gây hit chuyển `recoil` 60 tick: lùi tổng 2 m theo hướng ra xa Mây, vô hại. Hết `stunned`/`recoil` thì về `chase` hoặc `wander` tùy khoảng cách (≤ 18 là `chase`).
- Lịch sinh: 2 con ở tick 300, sau đó 1 con ở tick 300 + T·k (T = 480/420/360 tick cho Đêm 1/2/3), tối đa 6/8/10 con. Chọn ngẫu nhiên trong các điểm sinh cách Mây ≥ 15 m (XZ). Không có điểm hợp lệ thì bỏ lượt. Id `S1`, `S2`… theo thứ tự sinh, bỏ qua id scenario đã dùng.
- Scenario `shades[]` không có `state` thì mặc định `wander` (nên tick đầu chuyển `chase` nếu ≤ 12 m). `state_ticks_left` dùng cho `spawning`, `stunned`, `recoil`.

**Gió Lạc** (Đêm 2–3; cờ `random_drifters` mặc định true ở Đêm 2–3, false ở Đêm 1)
- Sinh ở tick 1200·k nếu đang có < 2 con, tại một điểm sinh Bóng Mực chọn ngẫu nhiên (cách Mây ≥ 15 m). y = mặt đất + 1.5. Id D1, D2…
- `idle`: lượn 2 m/s tới điểm ngẫu nhiên trong 8 m quanh vị trí gốc.
- `idle` → `chase` (bay 7 m/s về phía Mây) khi Mây mang ≥ 5 đom đóm và cách ≤ 15 m (XZ). Điều kiện mất thì về `idle`.
- Chạm XZ ≤ 1.2 (không xét độ cao, không bị bất tử chặn): cướp `min(3, carried)`, sự kiện `drifter_steal`, chuyển `flee` 240 tick (bay ra xa Mây 7 m/s). Hết 240 tick thì biến mất khỏi mảng `drifters`.
- Trúng Tỏa Sáng (3D ≤ 5 tới tâm pulse): đang `chase` → `flee` không cướp (`stolen` 0). Đang `flee` mà có đồ → thả hết tại vị trí nó (thành đom đóm rơi, y = mặt đất), sự kiện `drifter_drop`, `stolen` = 0, biến mất sau 120 tick.
- Vùng an toàn không chặn Gió Lạc. Gió Lạc không làm mất lửa.

**Bùa Gió**
- Vị trí mặc định: Đêm 2 C1 (35,0,0); Đêm 3 C1 (30,0,25), C2 (−30,0,25). Đêm 1 không có.
- Nhặt theo luật như đom đóm, không bị giới hạn sức chứa. Hiệu lực 600 tick (nhặt lại thì làm mới): tốc độ 7.2, Lướt không hồi chiêu.
- Bùa biến mất, 2700 tick sau xuất hiện lại. Sự kiện `charm_picked {charm_id, charm_ticks: 600}`.

**Pause**
- Ở bước 1, cạnh lên của `pause`:
  - Đang chơi → `paused`, sự kiện `paused {}`, dừng bước (tick vẫn tăng, sim_tick không tăng).
  - Đang pause → sự kiện `resumed {}`, rồi chạy tiếp các bước còn lại của tick đó.
- Trong lúc pause, các cạnh lên của nút khác bị bỏ.
- Snapshot ghi `state: "paused"`. Dòng `end` khi đang pause ghi `state: "playing"`. `time_left_s` tính theo sim_tick.

**Thắng/thua** (bước 12, sau mọi xử lý của tick): hết lửa → `lost no_flames`; còn sống mà mọi đèn đã sáng → `won all_lit` (kể cả đúng tick hết giờ); còn lại mà `time_left ≤ 0` → `lost dawn`. Khi thắng cộng `floor(giây còn lại)·2 + 50·lửa`. Điểm trong snapshot là điểm của Đêm đang chơi. Tổng điểm game (chỉ cộng các Đêm thắng) chỉ có ở bản web.

**`night_start {night}`**: ghi ở tick 0, ngay sau snapshot tick 0.

**Điểm xuất phát**: Đêm 1 và 2 ở (0,0,0). Đêm 3 ở (0,0,−30) (tâm đảo là tháp chuông nên không đứng được). Hướng mặt +Z.

## 4. Bản đồ (`game/maps.py`)

`ground_height(night, x, z) -> float | None` (None = biển mây):
- **Đêm 1**: r ≤ 40 → 0.
- **Đêm 2**: trong đảo A (tâm 0,0, r 28), đảo B (tâm 70,0, r 28), hoặc cầu (x ∈ [26,44], z ∈ [−2,2]) → 0.
- **Đêm 3**: r > 45 → None; r < 2 → 14 (tháp, đóng vai bức tường); r ≤ 8 → 6; 12 ≤ r ≤ 24 và z > 0 → 3; trong dải dốc → 3·(30 − s)/6; còn lại → 0. Dốc ở góc θ ∈ {30°, 150°}: u = (cosθ, sinθ), s = x·ux + z·uz, d = |−x·uz + z·ux|, nằm trong dải khi 24 ≤ s ≤ 30 và d ≤ 1.5.

Các hàm khác: `mote_points`, `shade_points` (y = mặt đất), `lanterns`, `charms`, `start`, `jump_pads`, `shade_interval_ticks`, `shade_max`, `duration_ticks`, `has_drifters`, `has_wind`, `island_name`. Tất cả lấy từ ticket Phần 2.

## 5. Giao diện headless (contract v1.1)

- Snapshot thêm: `night`, `wind {active, dir_deg}` (dir_deg = 0 khi chưa từng có gió).
- `player` thêm: `vel [x,y,z]`, `grounded`, `invuln` (boolean), `dash_cd_s`, `pulse_cd_s`, `charm_s`.
- Thêm các mảng:
  - `motes[{id, pos, kind, ttl_s}]`
  - `drifters[{id, pos, state, stolen}]`
  - `charms[{id, available, respawn_s}]`
- Scenario thêm:
  - `player.{invuln_ticks, dash_cd_ticks, pulse_cd_ticks, charm_ticks}`
  - `shades[].{state, state_ticks_left}`
  - `drifters[{id?, pos, state?, stolen?}]`
  - `charms[{id, pos?, available?, respawn_ticks?}]`
  - cờ `random_drifters`, `wind_enabled`
- Mảng `drifters` và `charms` trong scenario thay hẳn danh sách mặc định. Bỏ trống thì dùng mặc định của Đêm.
- Sai định dạng → thoát mã 2.

## 6. Giao diện web (glue trong `game/sim.py`)

- `web_new(seed, night)` → JSON `{"events": [...], "snap": {...}, "extra": {...}}`. Ván mới dùng cờ mặc định của Đêm.
- `web_step(frame_json)` → JSON cùng dạng. `frame` = toàn bộ input của tick (move, cam_yaw_deg, jump, interact, pulse, dash).
- `extra = {"dash_ready": bool, "pulse_ready": bool, "wind_warning": dir_deg|null (trong 120 tick trước cơn gió), "respawning": bool}`.
- `web_map(night)` → JSON mô tả hình học để vẽ:
  ```
  {night, name, islands:[{center:[x,z], radius, y}], bridges:[{x:[a,b], z:[c,d], y}],
   tiers:[{kind:"annulus", r:[12,24], half:"z>0", y:3}, {kind:"disk", r:8, y:6}],
   ramps:[{angle_deg, s:[24,30], width:3, y:[0,3]}], pads:[{pos:[x,y,z], radius:1}],
   tower:{pos:[0,6,0], radius:2, height:8} | null, lanterns:[{id, pos}], charms:[{id, pos}],
   start:[x,y,z], mote_points:[[x,y,z],...], shade_points:[[x,y,z],...]}
  ```
- Pause trên web: web ngừng gọi `web_step` (logic đứng yên hoàn toàn).
