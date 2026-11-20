# Phase 4 — Thiết kế chung (Ticket-04 "Bình minh v1.0.0", Contract v1.3)

Nguồn: [docs/lab/ticket-04.txt](../lab/ticket-04.txt). Ticket thắng nếu mâu thuẫn. Luật chơi v1.0–v1.2 giữ nguyên.

## Phân công file
| Agent | Sở hữu |
|---|---|
| coder (python) | `game/sim.py` (chỉ thêm chế độ bench), `game/benchstats.py`, `game/leaderboard.py`, `game/procmem.py`, `bench.py`, `soak.py`, `serve.py`, `tools/fetch_vendor.py`, `tools/make_release.py`, `game.contract.json`, `.gitignore` |
| coder (web) | `web/index.html`, `tools/web_check.py`, `tools/build_web.py` |
| tester | `tests/**`, `tools/check.py` |
| docs-writer | `README.md`, `CHANGELOG.md`, `CREDITS.md`, `AGENTS.md`, `docs/notes/phase-4.md`, `docs/notes/retro.md`, `docs/notes/ai-log.md`, `docs/proof/phase-4/README.md`, `docs/release-notes-v1.0.0.md` |

## 1. Benchmark

**Chế độ bench trong sim**
- `Game(seed, scenario=None, night=1, bench=True)`, kèm glue `web_bench_new(seed)` trả về cùng dạng với `web_new`.
- Bench luôn là Đêm 1. Mây đứng yên tại (0,0,0).
- **200 Bóng Mực** id S1…S200, trạng thái `wander`. Vị trí lấy từ `random.Random(seed)`: bán kính `r = 38·sqrt(u)`, góc đều. y = mặt đất + 1. Vị trí gốc của mỗi con là chỗ nó được sinh.
- **100 đom đóm** kind `random`, rải đều theo cùng cách với r ≤ 38. Được vượt trần 30.
- L1–L3 đang sáng, fuel 100, `ever_lit`. L4–L5 tắt.
- **Tắt trong bench:**
  - sinh thêm mọi thứ (Bóng Mực, đom đóm, Gió Lạc, bùa, gió);
  - sát thương, nhặt đom đóm, hao dầu và bị hút dầu;
  - mọi điều kiện kết thúc, và thời gian đứng yên.
- Bóng Mực vẫn `wander` theo luật bình thường.

**`game/benchstats.py`**: `compute(dts_ms: list[float]) -> {frames, avg_fps, p1_low_fps, frame_ms_p95}`.
- `avg_fps = 1000·N/Σdt`.
- `p1_low_fps`: k = max(1, ceil(0.01·N)), lấy k giá trị dt lớn nhất, `1000 / trung bình của chúng`.
- `frame_ms_p95`: phân vị 95 theo nearest-rank, tức `sorted(dt)[ceil(0.95·N) − 1]`.
- Làm tròn 1 chữ số. N = 0 thì báo lỗi.

**`bench.py --seed 42 --duration 30 --out bench.json [--browser PATH] [--port P]`**
- Ghi `t0` (epoch ms) ngay khi tiến trình bắt đầu.
- Chạy server của `serve.py` (hàm `make_server`) ở cổng trống.
- Tìm trình duyệt theo thứ tự: `--browser`, biến `BENCH_BROWSER`, Chrome/Chromium/Edge ở các đường dẫn chuẩn của macOS/Linux/Windows và trên PATH, rồi Chromium của Playwright nếu có.
- Mở trình duyệt với các cờ:
  ```
  --app=URL --window-size=1280,720 --user-data-dir=<tmp> --no-first-run
  --disable-gpu-vsync --disable-frame-rate-limit
  ```
  Có các cờ này thì `vsync_off: true`. Nếu phải dùng `webbrowser.open` thì `vsync_off: false` và README ghi rõ lý do.
- URL: `/web/index.html?bench=1&seed=42&duration=30`.
- Trang POST về `/api/bench` JSON `{first_frame_epoch_ms, dts_ms:[...], renderer, warmup_s: 3}`.
- `load_ms = first_frame_epoch_ms − t0`.
- Ghi `bench.json` với các trường:
  - `contract_version: "1.3"`, các số từ benchstats, `load_ms`;
  - `peak_mem_mb: null` (bản web không đo được RSS của trình duyệt; README giải thích);
  - `vsync_off`;
  - `renderer`: "three.js r128 WebGL · <GPU string> · <browser>";
  - `os: platform.platform()`.
- Đóng trình duyệt, thoát mã 0. Quá `duration + 120` s thì in lỗi ra stderr và thoát mã 1.

**Trang ở chế độ bench (`?bench=1`)**
- Canvas cố định 1280×720, hiệu ứng và ánh sáng đầy đủ như lúc chơi, không menu, không input.
- Camera: `pos = (30·cos(2πt/15), 15, 30·sin(2πt/15))`, luôn nhìn (0,0,0), t tính từ khung đầu tiên.
- Bỏ 3 s đầu, sau đó ghi `dt` của từng khung (theo timestamp của `requestAnimationFrame`) trong đúng `duration` giây, rồi POST.
- Sim vẫn bước 60 tick/s như lúc chơi.
- Nên dùng `InstancedMesh` cho Bóng Mực và đom đóm để giữ FPS.

## 2. Soak

**`soak.py --seed 7 --nights 10 --out soak.json`**, chạy trong cùng một tiến trình, không vẽ.
- Đêm thứ i (i = 1…N) là Đêm `((i − 1) mod 3) + 1`, dùng seed `7 + i`. Chạy tới khi kết thúc hoặc hết thời lượng chuẩn (tối đa 21600 tick).
- **Input:** `random.Random(seed + i)` riêng cho input.
  - Mỗi 30 tick chọn lại `move` là một vector đơn vị góc ngẫu nhiên (đôi khi đứng yên 10%).
  - Mỗi tick, các nút jump/dash/pulse/interact là `true` với xác suất 5% / 3% / 2% / 10%, còn lại `false`, nên kích hoạt theo cạnh lên.
- `game/procmem.py: rss_mb()` chỉ dùng stdlib:
  - Linux: `/proc/self/statm`;
  - macOS: `ctypes` `mach task_info`, nếu lỗi thì dùng `resource.ru_maxrss`;
  - Windows: `ctypes` `GetProcessMemoryInfo`.
- `mem_start_mb`: RSS sau khi tạo Game của Đêm đầu. `mem_end_mb`: RSS sau khi Đêm cuối kết thúc, bỏ Game, `gc.collect()`.
- Một exception trong một Đêm thì `crashes += 1`, kết quả Đêm đó ghi `"crash"`, rồi chạy tiếp.
- Output thêm `seed` và `per_night: [{night, seed, ticks, result, score}]` (ngoài các trường bắt buộc).

## 3. Bảng xếp hạng

**`game/leaderboard.py`**
- Tên hợp lệ: 3–12 ký tự, sau NFC, khớp `^\w{3,12}$` với regex Unicode. Như vậy nhận chữ tiếng Việt có dấu, chữ số và `_`; không nhận khoảng trắng hay ký tự khác.
- Mục: `{name, score, nights_won (0–3), achieved_at (ISO 8601 có múi giờ, do server đặt), seed}`.
- Sắp `score` giảm dần, bằng điểm thì `achieved_at` sớm hơn đứng trên (sort ổn định). Giữ top 10.
- File: `$DDL_LEADERBOARD`, mặc định `~/.dao-den-long/leaderboard.json`.

**`serve.py`**
- `GET /api/leaderboard` → `{"entries": [...]}`.
- `POST /api/leaderboard {name, score, nights_won, seed}`: kiểm tra hợp lệ, sai thì trả 400 kèm thông báo lỗi; đúng thì trả `{entries, rank}`.
- `POST /api/bench`: chỉ có khi bench.py chạy server.
- `python3 serve.py --export-leaderboard out.json` ghi `{"entries": [...]}` đúng thứ tự rồi thoát, không mở server.

**Trên web:** sau màn Bình Minh, hoặc sau khi thua ở bất kỳ Đêm nào, hiện ô nhập tên và lưu qua API. Không có API (bản Artifact hoặc single-file) thì lưu localStorage. Menu chính có màn Bảng xếp hạng.

## 4. Dễ tiếp cận (chỉ ở web, lưu localStorage)
- **Đổi phím** cho mọi hành động: lên/xuống/trái/phải, nhảy, lướt, tương tác, tỏa sáng, tạm dừng. Báo trùng phím, có nút "Khôi phục mặc định".
- **Phụ đề và chỉ báo:**
  - Bóng Mực xuất hiện (kèm mũi tên ở mép màn hình chỉ hướng);
  - gió sắp thổi;
  - 10 s cuối;
  - đèn có fuel < 30.
- **Giảm chuyển động:** tắt rung camera và chớp màn hình.
- **Chữ:** mọi chữ UI ≥ 18 px ở 1280×720, có tùy chọn chữ lớn ×1.25.

## 5. Đóng gói
- `tools/fetch_vendor.py` tải three.js r128 và các file lõi Pyodide 0.27.2 vào `web/vendor/` (đã gitignore).
  - Trang ưu tiên `vendor/`, không có thì dùng CDN.
  - `build_cmd = "python3 tools/fetch_vendor.py"`.
- `tools/make_release.py` tạo `dist/dao-den-long-v1.0.0.zip`: `web/` (kèm vendor), `game/`, `serve.py`, `headless.py`, `bench.py`, `soak.py`, `game.contract.json`, README, LICENSE, CREDITS, CHANGELOG. Bản này chạy offline.
- `game.contract.json`:
  ```
  contract_version "1.3"
  bench_cmd "python3 bench.py"
  soak_cmd "python3 soak.py"
  build_cmd "python3 tools/fetch_vendor.py"
  ```
