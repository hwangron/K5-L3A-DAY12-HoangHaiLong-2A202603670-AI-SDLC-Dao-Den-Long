# Nhật ký dùng AI

Công cụ: **Claude Code** (VS Code extension), model Claude Opus 5.5. Một agent chính (điều phối + viết code) và một **subagent review độc lập** không viết code.

## Phase 1

### Cách làm
1. Agent đọc tài liệu lab và PRD-0 (lab board), tóm tắt và đề xuất công nghệ. Tôi chọn: Python thuần cho luật chơi, web (Pyodide + Three.js) cho bản chơi, để luật chơi chỉ có một bản.
2. Agent viết `game/sim.py` + `headless.py`, rồi chạy thử ví dụ trong PRD. Kết quả khớp: tick 120 ở z = 12.0, đúng như ví dụ snapshot.
3. Viết 26 unit test và 6 kịch bản headless. Giá trị mong đợi được **tính tay từ luật** (trường `_why`), không chép từ output.
4. Viết bản web, dùng Playwright tự chơi và chụp ảnh. So sánh trạng thái trình duyệt với Python sau 900 tick: giống hệt nhau.
5. Harness: `AGENTS.md`, hook Stop (`tools/check.py` đỏ thì chặn agent kết thúc), skill `verify`, CI GitHub Actions.
6. Subagent review độc lập: đọc contract, thử phá bằng kịch bản tự tạo, chạy mutation test (xem kết quả trong proof).

### Lỗi của AI và cách phát hiện

| # | Lỗi | Phát hiện bằng | Sửa và chỉnh harness |
|---|---|---|---|
| E1 | So bán kính bằng `<=` số thực: đi 60 bước × 0.1 m ra 5.9999999 thay vì 6, nên đom đóm cách đúng 1 m bị nhặt **trễ 1 tick**. Test ẩn đặt vật ở đúng mép bán kính sẽ trượt | Kịch bản tự viết `s05_partial_deposit` (kỳ vọng tính tay tick 60, chạy ra 61) | Thêm `EPS = 1e-6` cho mọi phép so bán kính. Ghi quy tắc vào `AGENTS.md` |
| E2 | Script kiểm tra web nhấn phím E rồi nhả ngay trong cùng một khung hình, nên game không nhận | `web_check.json` báo `lantern_L1_lit_in_browser: false` | Giữ phím 120 ms (giống người chơi thật). Lỗi nằm ở script test, không phải ở game |
| E3 | `tools/check.py`: không tìm được test (thư mục `tests` không phải package); `relpath` lỗi khi khác ổ đĩa; chuỗi `\n` bị chèn hỏng | Chạy script, đọc traceback | Sửa từng lỗi. Script bị crash cũng trả mã 2 để hook vẫn chặn được |
| E4 | Bờ đảo kéo vị trí scenario đặt ngoài 30 m vào trong. Chấp nhận file scenario `[]` | **Subagent review độc lập** thử phá bằng kịch bản biên | Sửa code, thêm 2 test hồi quy. Bài học: người review khác người viết bắt được lỗi người viết không nghĩ tới |

### Token và chi phí (ước tính)

| Phase | Ước tính | Ghi chú |
|---|---|---|
| 1 | Agent chính: khoảng 350k token vào (phần lớn là cache), 60k token ra. Subagent review: **67.7k token** (số đo thật từ harness), 7 lần gọi công cụ | Số chính xác: gõ `/cost` trong Claude Code rồi điền vào đây |

Cách tiết kiệm:
- Đọc PRD **một lần** và lưu bản text gọn (10 KB thay vì trang HTML 180 KB).
- Một agent viết toàn bộ luật chơi trong một file thay vì chia nhiều agent (đỡ phải nạp lại ngữ cảnh).
- Chỉ dùng **một** subagent, cho việc review độc lập (rubric yêu cầu người đánh giá khác người viết).
- Sửa file bằng script nhỏ và chỉ chạy lại phần cần thiết. `AGENTS.md` giữ dưới 30 dòng.
