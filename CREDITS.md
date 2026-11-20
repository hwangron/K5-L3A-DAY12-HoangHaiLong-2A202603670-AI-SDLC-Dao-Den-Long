# Credits

## Nội dung và âm thanh

- Nhân vật, bối cảnh và tên (Mây, Đảo Đèn Lồng, Bóng Mực): tài liệu gốc của lab Day 12 AI SDLC.
- Mọi hình 3D được dựng từ hình học nguyên thủy trong code. Không có ảnh, mô hình hay file âm thanh bên ngoài.
- Mọi âm thanh (tiếng nhặt, thắp đèn, nhạc nền) được tổng hợp bằng WebAudio lúc chạy. Không có file âm thanh.

## Thư viện bên thứ ba

- [three.js](https://threejs.org) r128. **MIT License**. Bản chơi tải từ cdnjs; `tools/fetch_vendor.py` tải về `web/vendor/three.min.js` để chạy offline, và bản này nằm trong file zip Release.
- [Pyodide](https://pyodide.org) 0.27.2. **MPL-2.0**. Chạy `game/sim.py` trong trình duyệt. Bản chơi tải từ jsdelivr; `tools/fetch_vendor.py` tải các file lõi (`pyodide.js`, `pyodide.asm.js`, `pyodide.asm.wasm`, `python_stdlib.zip`, `pyodide-lock.json`) vào `web/vendor/pyodide/`, và các file này nằm trong file zip Release.- [Playwright](https://playwright.dev). **Apache-2.0**. Chỉ dùng để kiểm tra trình duyệt và chụp ảnh (`tools/web_check.py`). Không có trong bản phát hành.

## Công cụ AI

- Mã nguồn, test và tài liệu được viết với sự hỗ trợ của **Claude Code** (Anthropic). Điều phối viên là Claude Opus 5.5; các subagent chạy Claude Sonnet 5.5 (coder, tester) và Claude Haiku 5.5 (docs-writer). Quy trình và kết quả kiểm chứng: [docs/notes/ai-log.md](docs/notes/ai-log.md).