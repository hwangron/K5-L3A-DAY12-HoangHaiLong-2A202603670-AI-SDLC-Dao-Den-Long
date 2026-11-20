# Phase 4: Ticket-04 "Bình minh v1.0.0" + Test Contract v1.3

Nguồn: [docs/lab/ticket-04.txt](../lab/ticket-04.txt). Thiết kế chung: [phase-4-design.md](phase-4-design.md). Bằng chứng: [docs/proof/phase-4/README.md](../proof/phase-4/README.md). Đổi phá vỡ: [CHANGELOG.md](../../CHANGELOG.md). Test bị đổi: [tests/CHANGES-phase-4.md](../../tests/CHANGES-phase-4.md).

Ticket thắng nếu mâu thuẫn với thiết kế. Luật chơi v1.0–v1.2 giữ nguyên.

## 1. Thay đổi so với Phase 3

| Thay đổi | Lý do |
|---|---|
| Chế độ benchmark trong sim (`bench=True`) và trang `?bench=1` | Ticket Phần 1. Mọi bài đo cùng một cảnh chuẩn |
| `bench.py` (đo FPS bản web, ghi `bench.json`) và `game/benchstats.py` | Ticket Phần 1 |
| `soak.py` (10 Đêm liên tiếp headless) và `game/procmem.py` (RSS) | Ticket Phần 2 |
| Bảng xếp hạng cục bộ: `game/leaderboard.py`, API trong `serve.py`, màn hình trên web | Ticket Phần 3 |
| Đổi phím, phụ đề, giảm chuyển động, chữ lớn (chỉ web) | Ticket Phần 4 |
| `tools/fetch_vendor.py`, `tools/make_release.py` (zip chạy offline) | Ticket Phần 5 |
| Contract v1.3: `bench_cmd`, `soak_cmd`, `build_cmd` | Ticket Phần 6 |

## 2. Giả định và quyết định

Toàn bộ ở [phase-4-design.md](phase-4-design.md). Các điểm ticket không nói rõ và đã được chốt:

| # | Chỗ ticket chưa rõ | Giả định |
|---|---|---|
| D1 | Vị trí 200 Bóng Mực trong bench | `random.Random(seed)`, bán kính `38·sqrt(u)`, góc đều, y = mặt đất + 1 |
| D2 | Phân vị 95 của dt | Nearest-rank: `sorted(dt)[ceil(0.95·N) − 1]` |
| D3 | Số khung `p1_low_fps` | k = max(1, ceil(0.01·N)) giá trị dt lớn nhất, `1000 / trung bình` |
| D4 | Tên hợp lệ | Sau NFC, khớp `^\w{3,12}$` (chữ Unicode, chữ số, `_`) |
| D5 | Ai đặt `achieved_at` | Server, không nhận giá trị từ client |
| D6 | Bảng xếp hạng khi không có server (bản single-file) | localStorage |
| D7 | Bench khi không tìm được Chrome/Edge/Chromium | Mở trình duyệt mặc định, ghi `vsync_off: false` và README nói rõ |
| D8 | `peak_mem_mb` trên web | `null` (trình duyệt không cho đọc RSS từ trang), soak đo RSS thay |
| D9 | Input của soak | `random.Random(seed + i)` riêng cho mỗi Đêm; 10% đứng yên khi chọn hướng |
| D10 | Đêm thứ i của soak | Đêm `((i−1) mod 3) + 1`, seed `7 + i`, tối đa 21600 tick |
| D11 | Cài đặt trợ năng | Lưu localStorage (chỉ web), mặc định đều tắt |
| D12 | Chữ lớn | ×1.25 áp cho mọi chữ UI, ngưỡng 18 px kiểm trên 133 phần tử |

## 3. Tiêu chí nghiệm thu (làm A thì thấy B)

### Phần 1: Benchmark

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| M1 | Lệnh | `python3 bench.py --seed 42 --duration 30 --out bench.json` ra file đủ trường, `contract_version "1.3"` |
| M2 | Cảnh chuẩn | Canvas 1280×720. 200 Bóng Mực `wander`, 100 đom đóm, L1–L3 sáng fuel 100, không menu, không input |
| M3 | Tắt trong bench | Không sinh thêm, không sát thương, không nhặt, không hao dầu, không kết thúc Đêm. Bóng Mực vẫn `wander` |
| M4 | Camera | `pos = (30cos(2πt/15), 15, 30sin(2πt/15))`, nhìn (0,0,0) |
| M5 | Thời gian đo | Bỏ 3 s đầu, đo đúng `--duration` giây, tự thoát mã 0 |
| M6 | Công thức | `avg_fps`, `p1_low_fps`, `frame_ms_p95`, `frames` đúng định nghĩa ticket; N = 0 báo lỗi |
| M7 | Đầu ra | `load_ms = first_frame − t0`; `peak_mem_mb: null` có giải thích; `vsync_off`, `renderer`, `os` điền đủ |
| M8 | Vsync | Trình duyệt có cờ `--disable-gpu-vsync --disable-frame-rate-limit`, `vsync_off: true`. Không tắt được thì README ghi rõ |
| M9 | Ngưỡng | Trên máy chấm: `avg_fps ≥ 60`, `p1_low_fps ≥ 30`, `load_ms ≤ 10000` |

### Phần 2: Soak

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| K1 | Lệnh | `python3 soak.py --seed 7 --nights 10 --out soak.json` ra `nights`, `crashes`, `results` (10 mục), `mem_start_mb`, `mem_end_mb`, `duration_s` |
| K2 | Thứ tự Đêm | Đêm 1 → 2 → 3 → 1 … trong cùng một tiến trình, seed `7 + i` |
| K3 | Input | Mỗi 30 tick chọn lại hướng; mỗi tick nhảy 5%, lướt 3%, tỏa sáng 2%, tương tác 10% |
| K4 | Lỗi | Exception trong một Đêm: `crashes += 1`, kết quả Đêm đó là `"crash"`, chạy tiếp |
| K5 | Ngưỡng | `crashes = 0` và `mem_end_mb ≤ 1.2 × mem_start_mb` |
| K6 | Đo RSS | Linux `/proc/self/statm`, macOS `mach task_info` (dự phòng `ru_maxrss`), Windows `GetProcessMemoryInfo` |

### Phần 3: Bảng xếp hạng

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| L1 | Thời điểm nhập | Sau màn Bình Minh, hoặc sau khi thua ở bất kỳ Đêm nào, hiện ô nhập tên |
| L2 | Tên | 3–12 ký tự. Sai thì báo lỗi và không lưu. Dấu tiếng Việt được chấp nhận. Enter trong ô là lưu, không thử lại |
| L3 | Mục | `name, score, nights_won (0–3), achieved_at (ISO 8601 có múi giờ), seed` |
| L4 | Xếp hạng | Điểm giảm dần; bằng điểm thì ai đạt trước đứng trên. Giữ top 10 |
| L5 | Lưu | Tắt và mở lại game, bảng vẫn còn (file trong `$DDL_LEADERBOARD` hoặc `~/.dao-den-long/leaderboard.json`) |
| L6 | Màn hình | Menu chính có Bảng xếp hạng; Esc đóng; nút Quay lại về đúng nơi đã vào |
| L7 | Xuất | `python3 serve.py --export-leaderboard out.json` ghi `{"entries": [...]}` đúng thứ tự, rồi thoát |
| L8 | API | `GET /api/leaderboard`; `POST` sai thì 400 kèm thông báo; đúng thì trả `{entries, rank}` |

### Phần 4: Dễ tiếp cận (web)

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| A1 | Đổi phím | Đổi được lên/xuống/trái/phải, nhảy, lướt, tương tác, tỏa sáng, tạm dừng. Trùng phím thì báo và giữ phím cũ. Có nút Khôi phục mặc định. Được lưu sau khi tải lại trang |
| A2 | Phím dành riêng | Esc, Enter, Tab, F3 và mũi tên không gán được |
| A3 | Phụ đề | Bóng Mực xuất hiện (kèm mũi tên ở mép màn hình), gió sắp thổi, 10 s cuối, đèn fuel < 30. Tắt phụ đề thì không hiện thêm chỉ báo |
| A4 | Giảm chuyển động | Bật thì không rung camera, không chớp màn hình. Tắt thì trở lại |
| A5 | Chữ | Mọi chữ UI ≥ 18 px ở 1280×720. Bật chữ lớn thì ≥ 22.5 px |
| A6 | Lưu | Cài đặt trợ năng còn sau khi tải lại trang |

### Phần 5: Đóng gói

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| G1 | Clone sạch | README có tối đa 3 lệnh đưa tới trò chơi chạy được |
| G2 | Tài liệu | README có mô tả, ảnh chụp, yêu cầu hệ thống, cài đặt, điều khiển, test, headless, bench, soak. CHANGELOG có mục cho cả 4 phase. CREDITS liệt kê tài nguyên và công cụ AI. Có LICENSE |
| G3 | Zip Release | `python3 tools/make_release.py` tạo `dist/dao-den-long-v1.0.0.zip` có `web/vendor/`; chạy được không cần Internet |
| G4 | GitHub Release | Release v1.0.0 có file chạy được (zip) và hướng dẫn |

### Phần 6: Contract v1.3

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| T1 | Số liệu | `game.contract.json` có `contract_version "1.3"`, `bench_cmd`, `soak_cmd`, `build_cmd`; `tuning` khớp `sim.TUNING` |
| T2 | Không đổi cũ | Mọi test v1.0–v1.2 vẫn đạt (sửa số phiên bản có ghi chú) |

### Phần 7: Retro và demo

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| R1 | Retro | [docs/notes/retro.md](retro.md): đánh giá 4 phase, việc hiệu quả và không hiệu quả khi làm với AI, lỗi AI và cách phát hiện, harness hữu ích nhất, token và tiết kiệm, điều đổi lần sau |
| R2 | Video | `.mp4` dưới 5 phút, đính kèm Release hoặc `docs/demo/demo.mp4`; chơi trực tiếp và cho thấy test, headless, bench |

### Định nghĩa hoàn thành (DoD)

| # | Yêu cầu | Làm A thì thấy B |
|---|---|---|
| D-a | Bằng chứng | [docs/proof/phase-4/README.md](../proof/phase-4/README.md) có truy vết từng mục |
| D-b | Tag | Tag `phase-4` và Release `v1.0.0` |
| D-c | Số đo commit | `bench.json` và `soak.json` có trong repo |
| D-d | Test ẩn Phase 1–3 | Vẫn đạt (không kiểm được hết: test ẩn không có trong repo) |
| D-e | Repo | Public, có harness AI và tài liệu theo quy định |
