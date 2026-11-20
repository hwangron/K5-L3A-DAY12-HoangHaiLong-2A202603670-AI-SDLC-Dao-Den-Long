# Retro: 4 phase làm game với AI

Tổng hợp từ bằng chứng: [phase-1](../proof/phase-1/README.md), [phase-2](../proof/phase-2/README.md), [phase-3](../proof/phase-3/README.md), [phase-4](../proof/phase-4/README.md). Nhật ký chi tiết và số token: [ai-log.md](ai-log.md).

## 1. Đánh giá 4 phase

| Phase | Nội dung | Kết quả (theo tiêu chí của chính phase) | Điểm còn thiếu |
|---|---|---|---|
| 1 | PRD-0: đảo một đêm, 5 đèn, Bóng Mực, Tỏa Sáng, contract v1.0 | Đạt R1–R13. 27 unit test, 6 kịch bản, trình duyệt khớp Python sau 900 tick | Reviewer độc lập bắt được 2 lỗi (bờ đảo kéo vị trí scenario, file `[]` được nhận) |
| 2 | Ticket-02: ba đảo, lướt, rơi, Gió Lạc, Bùa Gió, pause, contract v1.1 | Đạt P1–P16 trừ FPS và một số HUD. 108 unit test, 23 kịch bản. Reviewer không tìm được lỗi về luật | FPS chỉ đo trên GL phần mềm (cận dưới). Âm thanh và một phần HUD không có kiểm tra tự động |
| 3 | Ticket-03: đèn có dầu, Bóng Mực hút dầu, thắng ở bình minh, mù màu, contract v1.2 | Đạt phần lớn. 167 unit test, 35 kịch bản, tương đương web/Python ở 3 trường hợp | Không có reviewer (hết giới hạn sử dụng). Thắng trên web được ép bằng hàm hỗ trợ thử nghiệm (`sim._web_game`). Test ẩn Phase 1–2 không có trong repo |
| 4 | Ticket-04: bench, soak, bảng xếp hạng, trợ năng, zip Release, contract v1.3 | Bench 618 / 157 / 2463 ms, soak 0 crash và RSS 20.4 → 20.4 MB. 223 unit test, 35 kịch bản | Một máy đo, chưa có máy chấm. Chưa có video, chưa tag, chưa có GitHub Release. Không có reviewer |

Xu hướng: số test và kịch bản tăng đều, nhưng bằng chứng về trải nghiệm thật (FPS, âm thanh, cảm giác chơi) chưa bao giờ được kiểm tự động. Phase 4 là phase đầu tiên có số đo hiệu năng trên GPU thật, và đó là số đáng tin nhất trong 4 phase.

## 2. Điều hiệu quả và không hiệu quả khi làm với AI

**Hiệu quả**
- **Viết design trước khi chia việc.** `phase-2-design.md`, `phase-3-design.md`, `phase-4-design.md` chốt các chỗ ticket mơ hồ và giao diện giữa các agent. Các agent chạy song song không lệch nhau, trừ những chỗ design chưa chốt (xem mục 3).
- **Sở hữu file rõ ràng.** Mỗi agent chỉ sửa file của mình. Không có xung đột gộp file, không phải chạy lại việc của người khác.
- **Tester viết test hộp đen từ ticket, không đọc code.** Ở Phase 2 cách này bắt được lỗi Gió Lạc mà coder không thấy. Test đúng vì kỳ vọng được tính tay, không chép từ output.
- **Luật chơi viết một lần trong Python.** Pyodide chạy chính file đó trên web, nên trình duyệt và headless khớp nhau (đã kiểm ở 3 trường hợp).
- **Số đo có script.** Bench, soak, check và web_check đều là lệnh trong repo. Phase 4 có số đo mà ai cũng chạy lại được.

**Không hiệu quả**
- **Subagent dùng Opus ở Phase 2.** Các việc viết code theo design và viết test không cần Opus. Phase 3 và 4 chuyển sang Sonnet và Haiku.
- **Giới hạn sử dụng 5 giờ cắt Phase 3 giữa chừng.** Ba subagent bị dừng, Phase 3 không có reviewer, và một số kiểm tra web phải ép trạng thái thay vì chơi thật.
- **Mỗi subagent phải đọc lại ticket, design và code.** Chi phí lặp lại này lớn nhất ở Phase 2 (5 agent). Phase 4 web tốn 346,735 token, có thể vì file `web/index.html` lớn (khoảng 124 KB) bị đọc lại nhiều lần. Đây là giả thuyết, chưa đo.
- **Thiếu reviewer ở Phase 3 và 4.** Phase 3 bị cắt bởi giới hạn sử dụng. Phase 4 không có reviewer theo quyết định, và đây là sai lầm: reviewer ở Phase 1 bắt được lỗi biên mà test chưa bắt.

## 3. Lỗi của AI và cách phát hiện

| # | Lỗi | Phát hiện bằng | Ghi chú |
|---|---|---|---|
| E1 | So bán kính bằng `<=` với số thực: đom đóm cách đúng 1 m bị nhặt trễ 1 tick | Kịch bản tự viết `s05_partial_deposit` (tính tay tick 60, chạy ra 61) | Sửa bằng `EPS = 1e-6`. Thành quy tắc trong AGENTS.md |
| E4 | Bờ đảo kéo vị trí scenario đặt ngoài 30 m vào trong | **Reviewer độc lập** (Phase 1) | Người review khác người viết bắt được lỗi biên mà người viết không nghĩ tới |
| E5 | Gió Lạc chỉ cướp khi đang đuổi. Ticket nói chạm là cướp | **Tester viết test từ ticket**, test đỏ. Điều phối viên đọc lại ticket và xác nhận | Bằng chứng cho cách tách coder và tester |
| E6 | Web agent cần `game/maps.py` chưa có, vì core agent viết song song | Báo cáo của core agent | Chốt giao diện giữa agent trước khi chia việc |
| E7 | Web tắt MSAA để đạt 30 FPS trên GL phần mềm | Đọc diff lúc review | Ghi rõ FPS là cận dưới |
| — | Phase 3: một số quyết định mô phỏng ticket không nói rõ (tick 61 cho `fuel_drain` đầu tiên, thứ tự drain) | Ghi trong [ADR-001](adr-001-lantern-fuel.md) | Quyết định được ghi lại, không giấu |

Mẫu chung của các lỗi: AI thường sai ở chỗ biên (đúng bằng r, đúng bằng 30 m, một tick) và chỗ ticket viết ngắn. Cách bắt hiệu quả nhất là test kỳ vọng tính tay, và một người (agent) không viết code đọc lại.

## 4. Harness nào giúp nhiều nhất

1. **`tools/check.py` + hook Stop.** Hook chặn agent kết thúc khi check còn đỏ. Đây là lưới an toàn rẻ nhất và đã bắt lỗi nhiều lần.
2. **`AGENTS.md`.** Các quy tắc như "ticket quyết định", "tính tay kỳ vọng", "radius dùng EPS" được thêm sau mỗi lỗi. Giữ dưới 45 dòng để agent đọc hết.
3. **Design doc trước khi chia việc** (`docs/notes/*-design.md`) cùng bảng sở hữu file.
4. **Subagent có định nghĩa trong `.claude/agents/`** với model cố định (coder, tester: Sonnet; docs-writer: Haiku). Không dùng `general-purpose`.
5. **Skill `verify`** chuẩn hóa việc lưu bằng chứng cho từng phase.

## 5. Token và chi phí

Số subagent là số đo thật. Số agent chính chỉ là ước tính.

| Phase | Subagent (đo) | Agent chính |
|---|---|---|
| 1 | 67,687 | Không tách riêng |
| 2 | 838,071 (Opus) | Ước tính khoảng 630k đến hết Phase 2 |
| 3 | 764,580 (Sonnet, Haiku) | Xem `/usage` |
| 4 | 706,256 (Sonnet, Haiku), chưa gồm docs lượt này | Xem `/usage` |
| **Tổng** | **2,376,594** | **Ít nhất 630k** (chưa đủ Phase 3–4) |

Cách tiết kiệm đã dùng: viết design một lần để mọi agent đọc chung; mỗi agent chỉ sửa file của mình; chạy các lệnh nặng (`--save`, `web_check`, bench) một lần cho bằng chứng; đổi model xuống Sonnet và Haiku từ Phase 3.

Lưu ý: token không đồng giá. Phase 2 dùng Opus cho subagent, nên cùng số token thì chi phí cao hơn Phase 3 (Sonnet, Haiku). Repo không có đơn giá nên không tính được chi phí bằng tiền.

## 6. Nếu làm lại thì đổi gì

1. **Giữ reviewer độc lập cho mọi phase.** Bỏ reviewer ở Phase 3 và 4 là lỗi lớn nhất. Trước khi tag, reviewer chạy mutation test và kịch bản biên.
2. **Chọn model khi tạo subagent, không để mặc định.** Ghi model trong định nghĩa agent và kiểm trong ai-log sau mỗi phase.
3. **Tách `web/index.html` thành nhiều file** (bench, trợ năng, bảng xếp hạng, HUD). Agent đọc được từng phần và tốn ít token hơn.
4. **Ghi số token ngay khi subagent kết thúc** vào ai-log, không đợi cuối phase. Phase 3 và 4 còn thiếu số agent chính vì không ghi kịp.
5. **Chạy bench trên máy chấm và quay video trước khi tag.** Phase 4 có số đo trên máy phát triển, nhưng video, tag và Release đều chưa xong.
6. **Thêm bài kiểm âm thanh và FPS trên GPU thật** vào web_check (hiện chỉ đọc mã và nghe tay).
7. **Viết ticket và design cho Phase sau với giao diện được chốt** giữa các agent (như E6 đã dạy), kể cả khi phần còn lại của phase chưa xong.
