# Đảo Đèn Lồng

> **Video demo:** _(sẽ thêm ở Phase 4)_ · **Lab:** Day 12 AI SDLC · Hoàng Hải Long · 2A202603670

Game 3D góc nhìn thứ ba. Mây, người giữ đèn đội nón lá, gom đom đóm để nạp dầu và thắp các Đèn Lồng Lớn trên **3 hòn đảo trong 3 Đêm** (Đảo Bến, Đảo Cau, Đảo Chuông). Giữ đèn còn sáng tới bình minh, đồng thời né Bóng Mực tím đen (chúng hút dầu từ đèn yếu) và Gió Lạc hay cướp đom đóm.

- Luật chơi viết **một lần** bằng Python thuần ([game/sim.py](game/sim.py), bản đồ ở [game/maps.py](game/maps.py)). Chế độ headless chạy thẳng các file này.
- Bản chơi 3D chạy trên trình duyệt (Three.js). Trình duyệt chạy **chính file Python đó** qua Pyodide, nên chơi và headless luôn ra cùng kết quả (đã kiểm chứng ở Đêm 1 và Đêm 3 và kịch bản có nhiên liệu, xem [docs/proof/phase-3](docs/proof/phase-3/README.md)).

## Cài đặt và chạy (macOS / Linux / Windows)

Chỉ cần Python 3.9+. Không cần cài thư viện nào. Trình duyệt cần có Internet để tải three.js và Pyodide từ CDN.

```bash
git clone <repo-url> && cd K5-L3A-DAY12-HoangHaiLong-2A202603670-AI-SDLC-Dao-Den-Long
python3 serve.py          # mở http://127.0.0.1:8000/web/ trên trình duyệt (thêm ?hq để bật khử răng cưa)
```

Menu chính → giới thiệu Đêm → chơi → kết quả → Đêm kế tiếp. Thắng Đêm 3 thì hiện màn Bình Minh với tổng điểm. Thua thì chơi lại Đêm đó. Âm lượng, độ nhạy chuột và **Bảng màu dễ phân biệt** (mù màu) chỉnh trong Cài đặt, được lưu lại.

## Điều khiển

| Phím | Việc |
|---|---|
| `W A S D` | Đi lại (theo hướng camera) |
| Kéo chuột / phím mũi tên | Xoay camera (lăn chuột: thu phóng) |
| `Space` | Nhảy |
| `Shift` | Lướt (2.8 m trong 12 tick, hồi 90 tick) |
| `E` | Nạp đom đóm vào đèn chưa sáng, hoặc châm dầu cho đèn đang sáng (đứng trong 2 m) |
| `F` | Tỏa Sáng: choáng Bóng Mực trong 5 m (tốn 3 đom đóm, hồi 180 tick) |
| `Esc` / `P` | Tạm dừng (Tiếp tục / Chơi lại Đêm / Cài đặt / Về menu) |
| `F3` | Hiện FPS |
| `Enter` | Bắt đầu / xác nhận |

## Luật chơi và cách tính điểm

Số liệu theo Ticket-03 (chi tiết: [docs/notes/phase-3.md](docs/notes/phase-3.md); quyết định: [ADR-001](docs/notes/adr-001-lantern-fuel.md)).

- **Máu** = 3 Ngọn Lửa, hồi đầy mỗi Đêm. Bóng Mực chạm thì mất 1 lửa, rơi một nửa số đom đóm đang mang ra đất quanh Mây (nhặt lại được), sau đó bất tử 1.5 s. Rơi khỏi đảo: mất 1 lửa và toàn bộ đom đóm, hồi sinh ở điểm xuất phát.
- **Đom đóm**: chạm (≤ 1 m) là nhặt. Mang tối đa **10**, tăng 2 mỗi lần thắp thành công trong Đêm (tối đa 20).
- **Đèn có dầu**: đèn sáng có nhiên liệu tối đa 100, hao 1 mỗi giây. Thắp mới cần 10 đom đóm, thắp lại đèn đã từng sáng chỉ cần 5. Châm dầu bằng `E` khi đứng gần đèn đang sáng. Hết dầu thì đèn tắt. Đèn có nhiên liệu từ 30 trở lên mới tạo vùng an toàn 6 m mà Bóng Mực không vào được. Đèn dưới 30 nhấp nháy.
- **Bóng Mực** (4 m/s, Đêm 3: 4.5 m/s) đuổi khi Mây trong 12 m. Khi rảnh, Bóng Mực đi tới đèn yếu (dưới 30) gần nhất và đứng hút 5 dầu mỗi giây cho tới khi bị đuổi hoặc đèn tắt. **Gió Lạc** (Đêm 2–3) cướp 3 đom đóm khi Mây mang ≥ 5. **Bùa Gió** (Đêm 2–3): chạy 7.2 m/s, Lướt không hồi chiêu trong 10 s. Đêm 3 có gió mạnh mỗi 30 s (lá bay báo trước).
- **Thắng** một Đêm: khi trời sáng (Đêm dài **240 / 270 / 300 s** cho Đêm 1 / 2 / 3), còn Mây và số đèn đang sáng ≥ 60% tổng (Đêm 1 cần 3/5, Đêm 2 cần 4/6, Đêm 3 cần 5/7). Thắp hết đèn **không** kết thúc Đêm. **Thua**: hết lửa (kể cả đúng tick bình minh), hoặc trời sáng mà thiếu đèn.

| Sự kiện | Điểm |
|---|---|
| Nạp 1 đom đóm (thắp mới, thắp lại, châm dầu) | +5 |
| Thắp lần đầu | +100 |
| Thắp lại | +40 |
| Mỗi Bóng Mực trúng Tỏa Sáng | +5 (+15 nếu con đó đang hút dầu) |
| Khi thắng: mỗi đèn đang sáng | +50 + nhiên liệu còn lại (làm tròn xuống) |
| Khi thắng: mỗi ngọn lửa còn lại | +50 |

Tổng điểm game = tổng điểm các Đêm đã thắng. Thời gian còn lại không còn được tính điểm.

## Chế độ headless (Test Contract v1.2)

```bash
python3 headless.py --seed 1 --night 3 --ticks 18000 --out out.jsonl     [--scenario tests/scenarios/s17_night3_terrain.scenario.json] [--inputs file.json] [--snapshot-every 10]
```

- `--night` nhận 1, 2, 3 (mặc định 1). Khai báo đầy đủ trong [game.contract.json](game.contract.json) (`contract_version: "1.2"`). Phần `tuning` được một test so khớp với số thật trong code.
- `fall_enabled: true`: ra khỏi đảo thì rơi (`player_hit` với `by: "fall"` và `lost`). Có `dash` và `pause` trong input.
- Snapshot có `night`, `wind`, `motes`, `drifters`, `charms`. Đèn có `fuel`, `ever_lit`, `relit_count`; người chơi có `capacity`. Trạng thái Bóng Mực: `spawning`, `wander`, `chase`, `recoil`, `stunned`, `drain`. Sự kiện mới: `refuel`, `lantern_out`, `fuel_drain`.
- Mã thoát: `0` chạy xong; `2` file scenario/inputs sai định dạng; `1` lỗi khác (ví dụ thiếu tham số). Lỗi in ra stderr.
- Một Đêm 3 đầy đủ chạy trong vài giây (giới hạn 30 s).

## Kiểm chứng

```bash
python3 tools/check.py      # 167 unit test + 35 kịch bản headless, mỗi kịch bản chạy 2 lần để so tính tất định
```

- Bằng chứng, truy vết yêu cầu, số đo và ảnh chụp: [docs/proof/phase-3/README.md](docs/proof/phase-3/README.md). Phase 2: [docs/proof/phase-2](docs/proof/phase-2/README.md). Phase 1: [docs/proof/phase-1](docs/proof/phase-1/README.md).
- Đổi phá vỡ theo từng phase: [CHANGELOG.md](CHANGELOG.md). Quyết định kiến trúc: [ADR-001](docs/notes/adr-001-lantern-fuel.md). Giả định và tiêu chí nghiệm thu: [docs/notes/phase-3.md](docs/notes/phase-3.md), [phase-3-design.md](docs/notes/phase-3-design.md) · Nhật ký dùng AI: [docs/notes/ai-log.md](docs/notes/ai-log.md)
- CI chạy `tools/check.py` mỗi lần push ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Harness AI

- [AGENTS.md](AGENTS.md) (CLAUDE.md trỏ tới): lệnh, cấu trúc, quy tắc cho agent.
- Hook `Stop` trong [.claude/settings.json](.claude/settings.json): chạy `tools/check.py`. Nếu còn đỏ thì agent không được kết thúc.
- Skill [.claude/skills/verify](.claude/skills/verify/SKILL.md): quy trình kiểm chứng và lưu bằng chứng cho mỗi phase.
- Phase 3 chia việc cho subagent (coder, tester, docs) theo file sở hữu, dùng Sonnet và Haiku thay vì Opus. Không có lượt review độc lập riêng (xem nhật ký AI).

## Sáng tạo của tôi

Chỉ có trong phần hiển thị ([web/index.html](web/index.html)), không đụng tới luật chơi nên không đổi đầu ra headless (headless không chạy file này; `tools/check.py` vẫn đạt toàn bộ). Các mục từ Phase 1 vẫn giữ:

1. **Sương đen lùi dần**: mỗi đèn thắp làm sương mỏng đi (ánh sáng nền theo công thức chuẩn của ticket, nay theo số đèn đang sáng).
2. **Âm thanh tự tổng hợp** bằng WebAudio, không dùng file asset: tiếng "ting" cao dần theo số đom đóm đang mang, nhạc nền khác nhau mỗi Đêm.
3. **Đèn hiện tiến độ**: đèn chưa thắp sáng dần theo số đom đóm đã nạp. Đèn đã thắp có vòng sáng cho thấy vùng an toàn 6 m.

Thêm ở Phase 2: lời Ông Đăng ở màn giới thiệu / kết quả, lá bay báo gió, đom đóm rơi nhấp nháy trước khi biến mất. Thêm ở Phase 3: thanh dầu trên đèn, Bóng Mực hút dầu có tia nối tới đèn, và chế độ mù màu (viền Bóng Mực xanh dương, đèn tắt có vết rách).

Bằng chứng: [web_check.json](docs/proof/phase-3/web/web_check.json) cho thấy trình duyệt và Python ra **cùng trạng thái** với cùng seed và input (Đêm 1: 900 tick, Đêm 3: 1300 tick, kịch bản có nhiên liệu).

## Cấu trúc

```
game/sim.py          luật chơi (dùng chung)      headless.py   CLI Test Contract
game/maps.py         bản đồ 3 Đêm
web/index.html       bản chơi 3D                 serve.py      mở game
tests/               unit test + scenarios       tools/        check, web_check, build_web
docs/notes/          ADR, giả định, nhật ký AI   docs/proof/   bằng chứng từng phase
docs/lab/            tài liệu gốc của lab
CHANGELOG.md         đổi phá vỡ theo phase
```
