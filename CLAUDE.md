# COCAS — Chỉ dẫn phát triển

Hệ thống Desktop tự động tạo hợp đồng từ ảnh CCCD, chạy hoàn toàn cục bộ trên Windows.

---

## 📘 TÀI LIỆU THIẾT KẾ GỐC

> **`docs/design/` là nguồn chân lý duy nhất.** Mọi quyết định triển khai phải truy vết ngược được về một mục trong đó.
>
> **Nếu thực tế bắt buộc làm khác thiết kế → SỬA TÀI LIỆU TRƯỚC, VIẾT CODE SAU.**

Bắt đầu từ [`docs/design/README.md`](docs/design/README.md) — mục lục 14 tài liệu, phiên bản **D2.0**.

| Khi làm việc với | Đọc |
|---|---|
| Kiến trúc, ADR, tầng, DI | `01-kien-truc-tong-the.md` |
| Sơ đồ, luồng, máy trạng thái | `02-so-do-he-thong.md` · `03-luong-du-lieu.md` |
| Bảng, cột, quan hệ, migration, mã hoá | `04-co-so-du-lieu.md` |
| Endpoint, request/response, mã lỗi | `05-thiet-ke-api.md` |
| Màn hình, component, phím tắt | `06-giao-dien.md` |
| Pipeline OCR, QR/MRZ, fusion | `07-module-ocr.md` |
| Regex, quy tắc validation | `08-validation.md` |
| Template, DOCX, PDF, tên file | `09-template-va-tai-lieu.md` |
| Bảo mật, logging, nhật ký | `10-bao-mat-va-logging.md` |
| Cây thư mục, thư viện | `11-cau-truc-va-thu-vien.md` |
| Interface, tiền/hậu điều kiện, bất biến | `12-dac-ta-module.md` |
| Test, CI, đóng gói | `13-kiem-thu-va-dong-goi.md` |
| Kế hoạch, rủi ro, cải tiến | `14-roadmap-va-tuong-lai.md` |

---

## 🔒 13 nguyên tắc bất biến

Vi phạm = phải sửa, không phải tranh luận.

| Mã | Nguyên tắc |
|---|---|
| **P-01** | **Offline-First** — không chỉ "không gọi Internet" mà **không có khả năng** gọi |
| **P-02** | **Dependency Rule** — Presentation → Application → Domain. Domain không import gì bên ngoài |
| **P-03** | **Replaceable Engines** — OCR/Storage/Render/PDF/Queue đều là Port |
| **P-04** | **Extraction ≠ OCR** — hợp nhất 3 kênh QR/MRZ/OCR |
| **P-05** | **Data Minimization** — xoá ảnh gốc sau khi sinh hợp đồng |
| **P-06** | **Template-Driven** — thêm mẫu = upload `.docx` + khai báo, không sửa code |
| **P-07** | **Everything is Logged** |
| **P-08** | **Fail Loud, Degrade Gracefully** — OCR chết vẫn nhập tay được; PDF chết vẫn có DOCX |
| **P-09** | **Deterministic** — snapshot bất biến, in lại sau 5 năm giống bản gốc |
| **P-10** | **Radical Simplicity** — không xây cho quy mô không tồn tại |
| **P-11** | **Windows là lớp xác thực** — không có đăng nhập, không mật khẩu ứng dụng |
| **P-12** | **Template điều khiển quy trình**, không chỉ nội dung |
| **P-13** | **Bảo mật đúng một mục tiêu: dữ liệu không rời khỏi máy** |

---

## ⚠️ Bảy điều dễ làm sai nhất

| # | Điều dễ sai | Đúng phải là |
|---|---|---|
| 1 | Tạo `asyncio.Queue` cho job | ⭐ **Bảng `job` LÀ hàng đợi duy nhất.** JobRunner polling `SELECT … FOR UPDATE SKIP LOCKED` mỗi 500 ms |
| 2 | Regex tên tiếng Việt dùng dải `À-Ỹ` | ⭐ Dùng **tập ký tự tường minh** (89 chữ hoa). NFC **trước**, UPPERCASE **sau** |
| 3 | Giả định PaddleOCR giới hạn được bộ ký tự | ⭐ **Không hỗ trợ.** `charset_hint` chỉ là **bộ lọc hậu xử lý** cho MRZ |
| 4 | Tầng Application tạo `docxtpl.RichText` | ⭐ Application tạo `StyledValue`; **`DocxContextAdapter` (Infrastructure)** chuyển thành `RichText` |
| 5 | Thêm cột `version` cho mọi bảng | ⭐ **Chỉ `contract`** có khoá lạc quan |
| 6 | Trả `*_masked` trong API response | ⭐ Trả **PII đầy đủ** (D1.6 bỏ che). Cột `_masked` chỉ dùng cho log và bảng danh sách |
| 7 | Đưa đối tượng ORM/Settings vào render context | ⭐ Chỉ kiểu nguyên thuỷ + `StyledValue` — **phòng thủ SSTI lớp cuối** |

---

## Quy mô hệ thống (D2.0)

| | Số lượng |
|---|---|
| Bảng CSDL | **18** |
| Endpoint API | **64** |
| Wireframe | **8** |
| Quy tắc validation | **56** |
| Port (interface) | **18** |
| Thư viện Python | **39** |
| Wizard | **3 bước** |
| Mẫu hợp đồng | **2** (`01A_HD_GDN`, `01A_GDKQ`) |

---

## Ngăn xếp công nghệ

| Tầng | Công nghệ |
|---|---|
| Desktop | Tauri (Rust) + WebView2 |
| Frontend | React 18 + TypeScript 5 + MUI v5 + TanStack Query + Zustand |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · Uvicorn (**1 worker**) |
| OCR | PaddleOCR PP-OCRv4 (CPU, offline) + OpenCV + pyzbar |
| CSDL | PostgreSQL 16 portable `127.0.0.1:55432` · SQLAlchemy 2.0 async · Alembic |
| Tài liệu | docxtpl (Jinja2 **sandboxed**) + LibreOffice headless CLI |
| Logging | Loguru (JSON có cấu trúc, **che PII bắt buộc**) |
| Mã hoá | cryptography (AES-256-GCM) + Windows DPAPI |
| Đóng gói | PyInstaller (**onedir**) + NSIS |

---

## Quy ước mã nguồn

- **PEP 8** · type hints đầy đủ · docstring cho mọi public API · xử lý ngoại lệ tường minh.
- Tên bảng/cột: `snake_case`, **số ít**, tiếng Anh. Định danh mã nguồn: tiếng Anh.
- Thông điệp cho người dùng cuối: **tiếng Việt**. Log: **tiếng Anh**.
- Ghim tuyệt đối: `paddlepaddle`, `paddleocr`, `numpy` (`>=1.26,<2.0`).
- Mọi thao tác file: **write-temp → verify SHA-256 → rename**.
- Mọi Port phải có ít nhất một hiện thực fake/null dùng trong test.

## Kiểm tra bắt buộc trong CI

| Kiểm tra | Ngưỡng |
|---|---|
| `import-linter` — Dependency Rule | 0 vi phạm (ngoại lệ duy nhất: `container.py`) |
| `mypy --strict` cho `domain/` + `application/` | 0 lỗi |
| Coverage `domain/` | ≥ 95% |
| Coverage `application/` | ≥ 85% |
| ⭐ Test chạy trong VM **ngắt mạng** | Toàn luồng phải hoàn tất |
| ⭐ `grep` PII trong log | **0 kết quả** |
| ⭐ **False Confidence** (OCR) | **≤ 0.5%** — chặn phát hành |
| Build `.exe` (từ P1) | Chạy được trên VM sạch |

---

## Trạng thái hiện tại

**Giai đoạn 1 (Thiết kế): ✅ HOÀN THÀNH** — tài liệu D2.0 đã đóng băng, 0 lỗi kiến trúc đã biết.

**Giai đoạn 2 (Triển khai): CHƯA BẮT ĐẦU.**
Bước tiếp theo: **P0 — khung dự án, CI, import-linter** (song song với việc thu thập Golden Set).

### Ba việc cần người dùng cung cấp

1. ⭐ **Golden Set 200 cặp ảnh CCCD đã gán nhãn** — đường găng dài nhất, quyết định cả P2.
2. ⭐ **2 file `.docx` thật** — để quét tên biến chính xác.
3. ⭐ **Xác nhận tên file xuất cho `01A/GDKQ`** — hiện tạm để `Mẫu 01A-GDKQ - {full_name}` vì trùng số hiệu 01A.

### Quy trình làm việc Giai đoạn 2

Mỗi lần làm **một module hoàn chỉnh**: cấu trúc thư mục → mã nguồn → giải thích → cách chạy → cách kiểm thử. Chỉ chuyển module tiếp theo khi module hiện tại đã xong và test xanh.
