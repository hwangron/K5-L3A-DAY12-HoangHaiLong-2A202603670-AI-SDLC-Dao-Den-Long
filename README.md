# Đảo Đèn Lồng

> **Video demo:** _(sẽ thêm ở Phase 4)_ · **Lab:** Day 12 AI SDLC · Hoàng Hải Long · 2A202603670

Game 3D góc nhìn thứ ba. Mây, người giữ đèn đội nón lá, gom đom đóm để thắp lại 5 Đèn Lồng Lớn của **Đảo Bến** trước bình minh, đồng thời né những con Bóng Mực tím đen trong sương.

- Luật chơi viết **một lần** bằng Python thuần ([game/sim.py](game/sim.py)). Chế độ headless chạy thẳng file này.
- Bản chơi 3D chạy trên trình duyệt (Three.js). Trình duyệt chạy **chính file Python đó** qua Pyodide, nên chơi và headless luôn ra cùng kết quả (đã kiểm chứng, xem [docs/proof/phase-1](docs/proof/phase-1/README.md)).

## Cài đặt và chạy (macOS / Linux / Windows)

Chỉ cần Python 3.9+. Không cần cài thư viện nào. Trình duyệt cần có Internet để tải three.js và Pyodide từ CDN.

```bash
git clone <repo-url> && cd K5-L3A-DAY12-HoangHaiLong-2A202603670-AI-SDLC-Dao-Den-Long
python3 serve.py          # mở http://127.0.0.1:8000/web/ trên trình duyệt
```

## Điều khiển

| Phím | Việc |
|---|---|
| `W A S D` | Đi lại (theo hướng camera) |
| Kéo chuột / `←` `→` | Xoay camera |
| `Space` | Nhảy |
| `E` | Nạp đom đóm vào đèn (đứng trong 2.5 m) |
| `F` | Tỏa sáng: xua Bóng Mực trong 6 m (tốn 1 đom đóm, hồi 1 s) |
| `Enter` / `R` | Bắt đầu / chơi lại |

## Luật chơi và cách tính điểm

- **Máu** = 3 ngọn lửa. Bóng Mực chạm (≤ 1 m) thì mất 1 lửa và rơi mất một nửa số đom đóm đang mang (làm tròn xuống). Sau đó được miễn sát thương 2 s.
- **Đom đóm**: chạm (≤ 1 m) là nhặt, mang tối đa 5 con. Mỗi đèn cần 5 đom đóm, nạp nhiều lần cũng được.
- **Bóng Mực**: con đầu xuất hiện ở giây thứ 5, sau đó cứ 20 s thêm một con (tối đa 6). Chúng đuổi theo với tốc độ 3.5 m/s (Mây chạy 6 m/s) và **không vào được vòng 4 m quanh đèn đã thắp**.
- **Tỏa sáng**: choáng 3 s và đẩy lùi 4 m mọi Bóng Mực trong 6 m.
- **Thắng**: thắp đủ 5 đèn. **Thua**: hết lửa, hoặc trời sáng (đêm dài 5 phút).

| Sự kiện | Điểm |
|---|---|
| Nhặt 1 đom đóm | +10 |
| Thắp 1 đèn | +100 |
| Mỗi Bóng Mực bị choáng | +20 |
| Khi thắng: mỗi giây còn lại (làm tròn xuống) | +2 |
| Khi thắng: mỗi ngọn lửa còn lại | +50 |

## Chế độ headless (Test Contract v1.0)

```bash
python3 headless.py --seed 1 --night 1 --ticks 600 --out out.jsonl \
    [--scenario tests/scenarios/s02_win.scenario.json] [--inputs file.json] [--snapshot-every 10]
```

- Khai báo đầy đủ trong [game.contract.json](game.contract.json). Phần `tuning` được một test so khớp với số thật trong code.
- `fall_enabled: false`: đảo có bờ chắn vô hình (bán kính 30 m), không rơi được nên không có sự kiện `player_hit` với `by: "fall"`.
- Không có `dash`. Không có trường nào để `null`.
- Mã thoát: `0` chạy xong; `2` file scenario/inputs sai định dạng; `1` lỗi khác (ví dụ thiếu tham số). Lỗi in ra stderr.
- Snapshot có thêm mảng `motes` (khuyến nghị của v1.0). Trạng thái Bóng Mực: `chase` và `stunned`.

## Kiểm chứng

```bash
python3 tools/check.py      # 27 unit test + 6 kịch bản headless, mỗi kịch bản chạy 2 lần để so tính tất định
```

- Bằng chứng, truy vết yêu cầu và ảnh chụp: [docs/proof/phase-1/README.md](docs/proof/phase-1/README.md)
- Giả định và tiêu chí nghiệm thu: [docs/notes/phase-1.md](docs/notes/phase-1.md) · Nhật ký dùng AI: [docs/notes/ai-log.md](docs/notes/ai-log.md)
- CI chạy `tools/check.py` mỗi lần push ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Harness AI

- [AGENTS.md](AGENTS.md) (CLAUDE.md trỏ tới): lệnh, cấu trúc, quy tắc cho agent.
- Hook `Stop` trong [.claude/settings.json](.claude/settings.json): chạy `tools/check.py`. Nếu còn đỏ thì agent không được kết thúc.
- Skill [.claude/skills/verify](.claude/skills/verify/SKILL.md): quy trình kiểm chứng và lưu bằng chứng cho mỗi phase.
- Người review là một subagent riêng, không phải agent đã viết code (xem nhật ký AI).

## Sáng tạo của tôi

Chỉ có trong phần hiển thị ([web/index.html](web/index.html)), không đụng tới luật chơi nên không đổi đầu ra headless.

1. **Đảo sáng dần, sương đen lùi dần**: mỗi đèn thắp làm ánh sáng nền mạnh lên và sương mỏng đi. Đủ 5 đèn thì bầu trời chuyển sang xanh đêm.
2. **Âm thanh tự tổng hợp** bằng WebAudio, không dùng file asset: tiếng "ting" cao dần theo số đom đóm đang mang, hợp âm khi thắp đèn, tiếng trầm khi Bóng Mực xuất hiện.
3. **Đèn hiện tiến độ**: đèn chưa thắp sáng dần theo số đom đóm đã nạp. Đèn đã thắp có vòng vàng cho thấy vùng an toàn 4 m.

Bằng chứng phần cũ vẫn đúng: `tools/check.py` đạt toàn bộ, và [web_check.json](docs/proof/phase-1/web/web_check.json) cho thấy trình duyệt và Python ra **cùng trạng thái** sau 900 tick với cùng seed và input.

## Cấu trúc

```
game/sim.py          luật chơi (dùng chung)      headless.py   CLI Test Contract
web/index.html       bản chơi 3D                 serve.py      mở game
tests/               unit test + scenarios       tools/        check, web_check, build_web
docs/notes/          giả định, nhật ký AI        docs/proof/   bằng chứng từng phase
docs/lab/            tài liệu gốc của lab
```
