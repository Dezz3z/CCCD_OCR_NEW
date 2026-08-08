# PROGRESS — Checkpoint dự án COCAS

> File này ghi lại **trạng thái tiến độ thực tế**, dùng làm context nhanh cho các phiên Claude Code tiếp theo. Khác với `CLAUDE.md` (chỉ dẫn ổn định) và `docs/design/` (đặc tả kỹ thuật đầy đủ), file này trả lời câu hỏi: **"Đang ở đâu, làm gì tiếp theo, còn thiếu gì?"**

Cập nhật lần cuối: sau khi hoàn thành Giai đoạn 1 (Thiết kế), trước khi bắt đầu Giai đoạn 2 (Triển khai).

---

## 🎯 Trạng thái tổng quan

| Giai đoạn | Trạng thái |
|---|---|
| **Giai đoạn 1 — Thiết kế** | ✅ **HOÀN THÀNH** — tài liệu D2.0 đã đóng băng, đã qua Architecture Review, 0 lỗi kiến trúc đã biết |
| **Giai đoạn 2 — Triển khai** | ⬜ **CHƯA BẮT ĐẦU** |

**Việc tiếp theo:** bắt đầu **P0 — khung dự án, CI, import-linter** (xem [docs/design/14-roadmap-va-tuong-lai.md](docs/design/14-roadmap-va-tuong-lai.md)).

---

## 📚 Đã có gì

### Tài liệu thiết kế — `docs/design/` (15 file, ~470 KB, phiên bản D2.0)

Bắt đầu từ [`docs/design/README.md`](docs/design/README.md). Đây là **nguồn chân lý duy nhất** — mọi quyết định triển khai phải truy vết ngược về một mục trong đó. Nếu thực tế bắt buộc làm khác thiết kế → **sửa tài liệu trước, viết code sau**.

Lịch sử rút gọn: thiết kế ban đầu (D1.0, 19 chương) → 6 lần sửa đổi lớn (D1.1–D1.6: rút về đơn máy, đơn giản hoá wizard, đưa chọn mẫu lên đầu, khai báo 2 mẫu hợp đồng thật, bỏ toàn bộ xác thực) → Architecture Review toàn diện → hợp nhất thành **D2.0** (sửa 7 lỗi kiến trúc, áp 6 cải thiện, cắt/giữ bản lề theo quyết định người dùng). Nội dung trong `docs/design/` hiện tại **là bản D2.0 cuối cùng**, không phải nhật ký các lần sửa.

### Chỉ dẫn phát triển — `CLAUDE.md` (gốc dự án)

Tự nạp mỗi phiên. Chứa: bảng tra cứu "đọc file nào khi làm gì", 13 nguyên tắc bất biến (P-01 → P-13), và đặc biệt **bảng "Bảy điều dễ làm sai nhất"** — 7 lỗi kiến trúc đã tự phát hiện và sửa trong review, chốt lại để không tái phạm khi viết code thật.

---

## 🔑 Tóm tắt kiến trúc (để không phải đọc lại toàn bộ)

**Là gì:** Desktop app Windows, 1 máy, 1 người dùng, offline hoàn toàn — chuyển ảnh CCCD (mặt trước + sau) thành hợp đồng DOCX/PDF qua OCR 3 kênh (QR + MRZ + nhận dạng ảnh).

**Ngăn xếp:** Tauri (Rust) + React 18/TS/MUI ⟷ FastAPI (1 worker) ⟷ PostgreSQL portable. OCR bằng PaddleOCR CPU-only. Sinh tài liệu bằng docxtpl (Jinja2 sandboxed) + LibreOffice headless. Không JWT, không đăng nhập — Windows là lớp xác thực (P-11).

**Quy mô:** 18 bảng CSDL · 64 endpoint API · 8 wireframe · 56 quy tắc validation · 18 Port (interface) · 39 thư viện Python · wizard 3 bước · 2 mẫu hợp đồng thật (`01A_HD_GDN`, `01A_GDKQ`).

**13 nguyên tắc bất biến** (chi tiết trong `CLAUDE.md`): Offline-First tuyệt đối · Dependency Rule (Clean Architecture) · Replaceable Engines (Ports & Adapters) · Extraction ≠ OCR (3 kênh) · Data Minimization · Template-Driven Zero-Code · Everything is Logged · Fail Loud Degrade Gracefully · Deterministic/Reproducible · Radical Simplicity · Windows là lớp xác thực · Template điều khiển quy trình · Bảo mật chỉ nhằm một mục tiêu (dữ liệu không rời máy).

**Ba bản lề cố ý giữ lại** (rẻ bây giờ, đắt nếu thêm sau): bảng `contract_party` (cho phép hợp đồng nhiều bên sau này không cần di trú), cơ chế khoá lạc quan chung (hiện chỉ áp `contract`, mở rộng dễ), endpoint export nhật ký hoạt động (cho lưu trữ lạnh sau này).

---

## ⚠️ Bảy bẫy kiến trúc đã biết — đừng lặp lại khi code

| # | Bẫy | Đúng phải là |
|---|---|---|
| 1 | Tạo `asyncio.Queue` cho job | Bảng `job` trong PostgreSQL là hàng đợi duy nhất (polling `SELECT … FOR UPDATE SKIP LOCKED` mỗi 500ms) |
| 2 | Regex tên tiếng Việt dùng dải Unicode `À-Ỹ` | Dùng tập ký tự tường minh (89 chữ hoa) · chuẩn hoá NFC **trước**, UPPERCASE **sau** |
| 3 | Giả định PaddleOCR giới hạn được charset lúc decode | Không hỗ trợ — `charset_hint` chỉ dùng để **lọc hậu xử lý** |
| 4 | Tầng Application tạo `docxtpl.RichText` trực tiếp | Application tạo `StyledValue` (kiểu nguyên thuỷ) → adapter ở tầng Infra chuyển thành `RichText` |
| 5 | Thêm cột `version` cho mọi bảng | Chỉ bảng `contract` có khoá lạc quan |
| 6 | API trả field `*_masked` (che một phần) | Trả PII đầy đủ — không có khái niệm che ở app 1-người-dùng này |
| 7 | Đưa object ORM/Settings thẳng vào Jinja2 render context | Context chỉ chứa kiểu nguyên thuỷ (str/int/float/dict/list) |

---

## 🚧 Việc cần người dùng cung cấp trước khi P2 có thể hoàn tất

| # | Việc | Vì sao gấp |
|---|---|---|
| 1 | **Golden Set: 200 cặp ảnh CCCD đã gán nhãn thủ công** | Đường găng dài nhất của cả dự án — P2 (module OCR) không đo được chất lượng nếu thiếu |
| 2 | **2 file `.docx` thật** cho `01A_HD_GDN` và `01A_GDKQ` | Cần để quét đúng tên biến thay vì suy đoán |
| 3 | **Xác nhận tên file xuất cho mẫu `01A_GDKQ`** | Đang tạm đặt `Mẫu 01A-GDKQ - {full_name}` vì trùng số hiệu "01A" với mẫu kia — cần xác nhận không gây nhầm lẫn |

Nếu bắt đầu phiên mới mà 3 mục trên vẫn trống — nhắc người dùng trước khi làm sâu vào P2.

---

## 🗺️ Lộ trình Giai đoạn 2 (12.5 tuần, 2 người — xem chi tiết ở file 14)

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| **P0** | Khung dự án, CI, `import-linter` (song song thu thập Golden Set) | ⬜ **← BẮT ĐẦU TỪ ĐÂY** |
| P1 | Nền tảng: cấu trúc Clean Architecture, DB schema, migration | ⬜ |
| P2 | Module OCR: tiền xử lý ảnh, QR, MRZ, PaddleOCR, fusion | ⬜ |
| P3 | Nghiệp vụ: customer, contract, template, validation | ⬜ |
| P4 | Sinh tài liệu: DOCX/PDF render | ⬜ |
| P5 | API: 64 endpoint FastAPI | ⬜ |
| P6 | Frontend: React wizard 3 bước, 8 màn hình | ⬜ |
| P7 | Desktop: Tauri wrap, đóng gói, test tích hợp | ⬜ |

## Quy trình làm việc Giai đoạn 2

Mỗi lần làm **một module hoàn chỉnh**: cấu trúc thư mục → mã nguồn → giải thích → cách chạy → cách kiểm thử. Chỉ chuyển module tiếp theo khi module hiện tại đã xong và test xanh. **Không** viết code cho nhiều module cùng lúc.

## Kiểm tra bắt buộc trong CI (từ khi có code)

| Kiểm tra | Ngưỡng |
|---|---|
| `import-linter` — Dependency Rule | 0 vi phạm (ngoại lệ duy nhất: `container.py`) |
| `mypy --strict` cho `domain/` + `application/` | 0 lỗi |
| Coverage `domain/` | ≥ 95% |
| Coverage `application/` | ≥ 85% |
| Test chạy trong VM **ngắt mạng** | Toàn luồng phải hoàn tất (xác nhận Offline-First) |
| `grep` PII trong log | 0 kết quả |
| **False Confidence** (OCR) | ≤ 0.5% — chặn phát hành nếu vượt |
| Build `.exe` (từ P1) | Chạy được trên VM sạch |

---

## 📝 Cách dùng file này trong phiên mới

1. Đọc file này trước để biết đang ở đâu.
2. Nếu cần chi tiết kỹ thuật của phần đang làm → mở đúng file trong `docs/design/` theo bảng tra cứu ở `CLAUDE.md`.
3. Sau khi hoàn thành một module/giai đoạn → **cập nhật lại bảng lộ trình và mục "Trạng thái tổng quan" ở trên**, để phiên sau không phải hỏi lại.
