# Changelog

## [v1.0.0 / phase-4] Contract v1.3

Ticket: [ticket-04](docs/lab/ticket-04.txt). Thiết kế: [phase-4-design](docs/notes/phase-4-design.md). Không đổi luật chơi: đổi phá vỡ chỉ ở công cụ và số phiên bản.

- `contract_version` là `"1.3"`. `game.contract.json` thêm `bench_cmd`, `soak_cmd`, `build_cmd`. Các test cũ chỉ đổi số phiên bản (xem [tests/CHANGES-phase-4.md](tests/CHANGES-phase-4.md)).
- Chế độ benchmark trong sim: `Game(..., bench=True)` với 200 Bóng Mực và 100 đom đóm, tắt sinh thêm, sát thương, nhặt, hao dầu và kết thúc. Chế độ thường không đổi (có test).
- Lệnh mới: `python3 bench.py --seed 42 --duration 30 --out bench.json` (đo FPS trên bản web, ghi `bench.json` với `peak_mem_mb: null`), `python3 soak.py --seed 7 --nights 10 --out soak.json` (10 Đêm liên tiếp headless, đo RSS).
- Bảng xếp hạng cục bộ: top 10, lưu ở `~/.dao-den-long/leaderboard.json` (đổi bằng `DDL_LEADERBOARD`). API `GET/POST /api/leaderboard`. Xuất: `python3 serve.py --export-leaderboard out.json`.
- Dễ tiếp cận (web, lưu localStorage): đổi phím cho mọi hành động, báo trùng, khôi phục mặc định; phụ đề và chỉ báo hình ảnh; giảm chuyển động; chữ UI tối thiểu 18 px, tùy chọn chữ lớn ×1.25.
- Đóng gói: `tools/fetch_vendor.py` tải three.js r128 và Pyodide 0.27.2 vào `web/vendor/`. `tools/make_release.py` tạo `dist/dao-den-long-v1.0.0.zip`, chạy offline.

## [phase-3] Contract v1.2 — Breaking changes

Quyết định chi tiết: [ADR-001](docs/notes/adr-001-lantern-fuel.md). Ticket: [ticket-03](docs/lab/ticket-03.txt).

- `contract_version` là `"1.2"`. Thời gian Đêm 1 / 2 / 3 là 240 / 270 / 300 s (trước: 300 / 330 / 360).
- `game_over.reason`: bỏ `all_lit`, thêm `dawn_survived`. Thua vẫn là `dawn` hoặc `no_flames`.
- Không còn thắng sớm. Thắp hết đèn không kết thúc Đêm. Thắng khi hết giờ với số đèn đang sáng ≥ ceil(0.6 × tổng): Đêm 1 cần 3/5, Đêm 2 cần 4/6, Đêm 3 cần 5/7.
- Đèn có nhiên liệu: tối đa 100, hao 1.0/giây, lưu bằng đơn vị nguyên ×60. Thắp mới cần 10 đom đóm, thắp lại cần 5. Hết dầu thì tắt (`lantern_out`).
- Vùng an toàn của đèn chỉ có khi fuel ≥ 30.
- Bóng Mực có trạng thái mới `drain`: đứng yên bên đèn yếu, hút 5 dầu/giây.
- Bóng Mực hết choáng thì về `wander` (trước: `chase` nếu trong 12 m).
- Công thức điểm mới, thay toàn bộ bảng cũ: nạp mỗi đom đóm +5, thắp lần đầu +100, thắp lại +40, Tỏa Sáng +5 mỗi con (+15 nếu con đó đang `drain`). Khi thắng: mỗi đèn sáng +50 + floor(fuel), mỗi Ngọn Lửa còn lại +50. Bỏ thưởng thời gian.
- Sự kiện mới: `refuel {lantern_id, amount, fuel}`, `lantern_out {lantern_id}`, `fuel_drain {lantern_id, shade_id, fuel}` (ghi mỗi 60 tick đang hút). `lantern_lit` thêm `relight: true|false`.
- Snapshot: mỗi đèn thêm `fuel`, `ever_lit`, `relit_count`. `player` thêm `capacity`. Bóng Mực có thêm trạng thái `drain`.
- Scenario: mỗi đèn thêm `fuel`, `ever_lit`; `player` thêm `successful_lights`; `shades[]` thêm `target_lantern_id`. Đèn đặt `lit: true` mà không có `fuel` thì mặc định 100.
- Sức chứa: 10 + 2 × số lần thắp thành công trong Đêm, tối đa 20. Đặt lại mỗi Đêm.
- Chế độ mù màu (cài đặt web): viền và mắt Bóng Mực đổi sang `#00B3FF`, cảnh báo đổi sang `#FFFFFF` kèm ⚠, đèn tắt bị xẹp và có vết rách.

## [phase-2] Contract v1.1

Thêm ba bản đồ (Đảo Bến, Đảo Cau, Đảo Chuông) với đèn 5 / 6 / 7, cầu, bục nhảy, địa hình 3 tầng, vách và dốc. Đảo có bán kính 40 m, ra ngoài thì rơi. Thêm Lướt, Pause, Gió Lạc, Bùa Gió và gió mạnh ở Đêm 3. Bóng Mực có 5 trạng thái `spawning`, `wander`, `chase`, `recoil`, `stunned`. Số liệu chuẩn: mang 10, đèn cần 10, nạp 2.0 m, vùng an toàn 6 m, Tỏa Sáng tốn 3 trong 5 m (3D) và choáng 120 tick. Thắng hoặc thua được xét cuối tick. Đom đóm rơi nằm lại trên đất. Chi tiết: [docs/notes/phase-2.md](docs/notes/phase-2.md).

## [phase-1] Contract v1.0

Luật chơi bằng Python thuần trong `game/sim.py`, chạy headless qua `headless.py` và được web chạy lại qua Pyodide. Đảo một đêm, 5 đèn, mang 5 đom đóm, nạp 2.5 m. Đèn đã sáng không nhận thêm đom đóm. Thắng ngay khi thắp đèn cuối. Điểm tính khi nhặt. Bờ chắn 30 m, không rơi khỏi đảo.
