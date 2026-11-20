# Đảo Đèn Lồng v1.0.0

Game 3D góc nhìn thứ ba: gom đom đóm, thắp và giữ sáng các Đèn Lồng Lớn trên ba hòn đảo trong ba Đêm, né Bóng Mực và Gió Lạc. Chi tiết luật: [README](../README.md).

**Video demo:** [docs/demo/demo.mp4](demo/demo.mp4) (sẽ được đính kèm khi quay xong).

## Có gì trong bản này

- Ba Đêm (Đảo Bến, Đảo Cau, Đảo Chuông), Lướt, Tỏa Sáng, đèn có dầu, Bóng Mực hút dầu, Gió Lạc, Bùa Gió, gió mạnh Đêm 3.
- **Bảng xếp hạng cục bộ**: top 10, lưu trên máy bạn. Xuất ra JSON bằng `python3 serve.py --export-leaderboard out.json`.
- **Trợ năng**: đổi phím (có báo trùng và khôi phục mặc định), phụ đề và chỉ báo hình ảnh, giảm chuyển động, chữ lớn ×1,25, bảng màu dễ phân biệt.
- **Luật chơi dùng chung**: một file Python (`game/sim.py`) chạy cả trên trình duyệt lẫn headless. Test: 223 unit test và 35 kịch bản headless, đều đạt.
- **Test Contract v1.3**: thêm `bench_cmd` và `soak_cmd`.

## Cách chạy

**Cách 1: từ mã nguồn** (cần Internet lần đầu để tải three.js và Pyodide)

```bash
python3 serve.py
```

Mở http://127.0.0.1:8000/web/ nếu trình duyệt không tự mở. Cần Python 3.9+.

**Cách 2: file zip Release** (chạy offline, đã kèm three.js và Pyodide)

1. Giải nén `dao-den-long-v1.0.0.zip`.
2. Mở thư mục đã giải nén rồi chạy `python3 serve.py`.

Xem thêm `START-HERE.txt` trong zip.

## Số đo (máy phát triển: Windows 11, AMD Radeon đồ họa tích hợp, Chrome 157)

| Đo | Kết quả |
|---|---|
| FPS trung bình (bench, 30 s, vsync tắt) | 618.4 |
| FPS 1% khung chậm nhất | 157.2 |
| Thời gian khung p95 | 5.6 ms |
| Thời gian tải đến khung đầu | 2.46 s |
| Soak: 10 Đêm headless, không crash | 0 crash, RSS 20.4 MB → 20.4 MB |

Số này là của một máy. Máy chấm của giảng viên sẽ cho số khác. Trình duyệt không đo được bộ nhớ của chính nó nên `peak_mem_mb` là `null`; bộ nhớ được đo ở soak. Chi tiết: [bằng chứng Phase 4](proof/phase-4/README.md).

## Yêu cầu

- Python 3.9+ (chỉ thư viện chuẩn).
- Chrome, Edge hoặc Chromium để chơi. Bench cần Chrome, Edge hoặc Chromium.

## Ghi chú

- Cài đặt và phím đã đổi được lưu trên trình duyệt (localStorage). Bảng xếp hạng lưu ở `~/.dao-den-long/leaderboard.json`.
- Bản đã biết giới hạn: chưa có kiểm tra tự động cho âm thanh và cảm giác chơi trên GPU thật. Xem [CHANGELOG](../CHANGELOG.md) và [CREDITS](../CREDITS.md).
