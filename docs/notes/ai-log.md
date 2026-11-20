# Nhật ký dùng AI

Công cụ: **Claude Code** (VS Code extension), model Claude Opus 5.5. Phase 1: một agent chính (điều phối + viết code) và một **subagent review độc lập** không viết code. Phase 2: một agent điều phối và nhiều subagent song song (xem dưới).

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

## Phase 2

### Cách làm
1. **Điều phối viên** (agent chính) đọc Ticket-02 một lần, lưu bản text gọn ở `docs/lab/ticket-02.txt`, rồi viết [phase-2-design.md](phase-2-design.md): chốt mọi chỗ ticket chưa rõ (góc, bộ đếm, vách/dốc, pause…), giao diện headless v1.1, glue web (`web_new/web_step/web_map`) và **bảng sở hữu file**. Viết file này trước để các agent làm song song không lệch nhau.
2. **3 subagent chạy song song**, mỗi agent chỉ sửa file của mình:
   - **core**: `game/sim.py`, `game/maps.py` (mới), `headless.py`, `game.contract.json`.
   - **test**: `tests/**`, `tools/check.py`. Viết test **hộp đen** qua CLI từ chính văn bản ticket, không đọc code core.
   - **web**: `web/index.html`, `tools/web_check.py`, `tools/build_web.py`.
3. **Phân xử**: điều phối viên chạy `tools/check.py`, so chỗ test và code lệch nhau với văn bản ticket, giao lại cho agent sai. Quy tắc: ticket quyết định.
4. **Review độc lập** (subagent không viết code) và **docs agent** (README, AGENTS.md, skill, ghi chú, bằng chứng).

### Lỗi của AI và cách phát hiện

| # | Lỗi | Phát hiện bằng | Sửa và chỉnh harness |
|---|---|---|---|
| E5 | Core agent cho Gió Lạc **chỉ cướp khi đang `chase`**. Ticket chỉ nói "chạm (XZ ≤ 1.2 m) thì cướp", nên Gió Lạc đang `idle` mà chạm Mây cũng phải cướp | Test agent viết test hộp đen từ ticket **độc lập** với core, nên test đỏ. Điều phối viên đọc lại ticket và xác nhận test đúng | Giao core agent sửa (2,045 token). Thêm quy tắc "test và code lệch nhau thì ticket quyết định" vào `AGENTS.md` |
| E6 | Web agent cần `game/maps.py` để vẽ bản đồ, nhưng file này do core agent viết song song, chưa có | Core agent báo phụ thuộc trong báo cáo | Điều phối viên chuyển giao diện `web_map(night)` (đã chốt trong design) cho web agent. Bài học: chốt giao diện giữa các agent **trước** khi chia việc |
| E7 | Web agent tắt khử răng cưa (MSAA) để đạt ≥ 30 FPS trong Chromium GL phần mềm | Đọc diff `web/index.html` lúc review | Chấp nhận, nhưng ghi rõ: FPS đo là cận dưới, bật lại bằng `?hq`. Ghi trong bằng chứng để không ai tưởng đó là số trên GPU thật |

### Token và chi phí

| Agent | Token | Ghi chú |
|---|---|---|
| core | 164,554 (gồm 2 lần sửa: drifter +2,045, theo review +8,650) | Số đo thật từ harness |
| test | 248,125 | Số đo thật. Nhiều nhất vì phải tính tay kỳ vọng cho 108 unit test và 23 kịch bản |
| web | 176,279 | Số đo thật |
| reviewer | 121,803 | Số đo thật. 5 mutation test + nhiều kịch bản biên |
| docs | 127,310 | Số đo thật |
| điều phối viên | _ước tính, sẽ thay bằng số từ `/cost`_ | Đọc ticket, viết design, phân xử |

Cách tiết kiệm:
- Viết `phase-2-design.md` một lần, mọi subagent đọc chung thay vì mỗi agent tự suy luận lại ticket.
- Sở hữu file rõ ràng: không có hai agent sửa cùng một file, nên không phải hòa trộn hay chạy lại.
- Chạy nặng (`check.py --save`, `web_check.py`, đo hiệu năng) chỉ một lần cho bằng chứng.
