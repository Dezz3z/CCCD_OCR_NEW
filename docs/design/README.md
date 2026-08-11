# COCAS — Tài liệu thiết kế gốc

**Contract & OCR Automation System**
Hệ thống Desktop tự động tạo hợp đồng từ ảnh CCCD, chạy hoàn toàn cục bộ.

| | |
|---|---|
| **Mã dự án** | COCAS |
| **Phiên bản tài liệu** | **D2.1** (đã hợp nhất D1.1 → D1.6 + Architecture Review + ⭐ gỡ PDF/LibreOffice) |
| **Trạng thái** | ✅ Đóng băng — đây là tài liệu thiết kế gốc |
| **Ngày** | 08/08/2026 |

> ⚠️ **Tài liệu này là nguồn chân lý duy nhất cho toàn bộ quá trình phát triển.**
> Mọi quyết định triển khai phải truy vết ngược được về một mục trong đây.
> Nếu thực tế bắt buộc phải làm khác, **sửa tài liệu trước, viết code sau**.

---

## Mục lục

| # | Tài liệu | Nội dung |
|---|---|---|
| 01 | [Kiến trúc tổng thể](01-kien-truc-tong-the.md) | Nguyên tắc · Ràng buộc · NFR · Triển khai · Clean Architecture · DI · 15 ADR |
| 02 | [Sơ đồ hệ thống](02-so-do-he-thong.md) | C4 Context/Container/Component · Sequence · State machine · DFD · Deployment |
| 03 | [Luồng xử lý dữ liệu](03-luong-du-lieu.md) | Pipeline 13 chặng · Luồng thay thế · Idempotency · Vòng đời dữ liệu |
| 04 | [Cơ sở dữ liệu](04-co-so-du-lieu.md) | **19 bảng** · ERD · Quan hệ · Chỉ mục · Mã hoá · Migration |
| 05 | [Thiết kế API](05-thiet-ke-api.md) | **64 endpoint** · Quy ước · Mã lỗi · Request/Response |
| 06 | [Thiết kế giao diện](06-giao-dien.md) | Design system · **8 wireframe** · Component · Phím tắt · Kiến trúc FE |
| 07 | [Module OCR](07-module-ocr.md) | Pipeline 3 kênh QR/MRZ/OCR · Tiền xử lý · Fusion · Đo lường |
| 08 | [Module Validation](08-validation.md) | 4 tầng · 10 bảng Regex · 56 quy tắc · Thông điệp lỗi |
| 09 | [Template Engine & Sinh tài liệu](09-template-va-tai-lieu.md) | Quét biến · Phiên bản · Context Builder · DOCX · Đặt tên file |
| 10 | [Bảo mật & Logging](10-bao-mat-va-logging.md) | Mô hình đe doạ · 4 biện pháp · Loguru · Che PII · Nhật ký hoạt động |
| 11 | [Cấu trúc & Thư viện](11-cau-truc-va-thu-vien.md) | Cây thư mục · 39 thư viện Python · Chính sách phiên bản |
| 12 | [Đặc tả hợp đồng module](12-dac-ta-module.md) | 13 module: trách nhiệm · tiền/hậu điều kiện · bất biến |
| 13 | [Kiểm thử & Đóng gói](13-kiem-thu-va-dong-goi.md) | Kim tự tháp test · Golden Set · PyInstaller · NSIS · Nâng cấp |
| 14 | [Roadmap & Cải tiến tương lai](14-roadmap-va-tuong-lai.md) | 12.5 tuần / 7 giai đoạn · Sổ rủi ro · 26 đề xuất nâng cấp |

---

## Tóm tắt điều hành

### Mục tiêu

```
Ảnh CCCD (trước + sau)  →  OCR offline  →  Trích xuất  →  Validation
    →  Form bổ sung  →  Sinh hợp đồng DOCX  →  Lưu CSDL
```

Toàn bộ chạy **trên một máy tính Windows**, **không có Internet**, **không gửi dữ liệu ra ngoài**.

### Phạm vi v1.0

| Có | Không có |
|---|---|
| ✅ 1 máy tính, 1 người dùng | ❌ Mạng LAN, nhiều người dùng |
| ✅ CCCD gắn chip 12 số | ❌ CMND 9 số, GPLX, Hộ chiếu, GPKD |
| ✅ 2 mẫu hợp đồng: `01A/HĐ-GĐN`, `01A/GDKQ` | ❌ Mẫu cho tổ chức |
| ✅ 1 bên tham gia (cá nhân) | ❌ Nhiều bên (đã chừa bản lề) |
| ✅ Sinh DOCX | ❌ ⭐ Xuất PDF *(D2.1 — §9.13)* |
| ✅ Sao lưu / khôi phục | ❌ Đăng nhập, mật khẩu, phân quyền |

---

## 🔒 13 nguyên tắc bất biến

Mọi dòng code phải tuân thủ. Vi phạm = phải sửa, không phải tranh luận.

| Mã | Nguyên tắc |
|---|---|
| **P-01** | **Offline-First / Air-Gap by Design** — không chỉ "không gọi Internet" mà **không có khả năng** gọi |
| **P-02** | **Dependency Rule** — Presentation → Application → Domain. Domain không import gì bên ngoài |
| **P-03** | **Replaceable Engines** — OCR/Storage/Render/Queue đều là Port, đổi adapter không đổi gì khác |
| **P-04** | **Extraction ≠ OCR** — trích xuất là hợp nhất 3 kênh QR/MRZ/OCR, không phải chỉ OCR |
| **P-05** | **Data Minimization** — xoá ảnh gốc sau khi sinh hợp đồng thành công |
| **P-06** | **Template-Driven, Zero-Code Extension** — thêm mẫu = upload `.docx` + khai báo, không sửa code |
| **P-07** | **Everything is Logged** — mọi thao tác chạm PII hoặc sinh tài liệu đều ghi nhật ký |
| **P-08** | **Fail Loud, Degrade Gracefully** — OCR chết vẫn nhập tay được |
| **P-09** | **Deterministic & Reproducible** — snapshot bất biến, in lại sau 5 năm giống bản gốc |
| **P-10** | **Radical Simplicity** — không xây cho quy mô không tồn tại |
| **P-11** | **Windows là lớp xác thực** — ứng dụng không dựng lại lớp đó |
| **P-12** | **Template điều khiển quy trình**, không chỉ nội dung |
| **P-13** | **Bảo mật đúng một mục tiêu: dữ liệu không rời khỏi máy** |

---

## 🎯 6 quyết định định hình hệ thống

| # | Quyết định | Vì sao quan trọng |
|---|---|---|
| **1** | **QR + MRZ là nguồn chính, OCR là phụ** | Mã QR mặt trước chứa dữ liệu số hoá gốc (100% chính xác), MRZ mặt sau có checksum tự kiểm. 5/6 trường chính xác **trước khi** OCR nói gì. Đây là lý do đạt ≥99% mà không cần cloud AI |
| **2** | **Mẫu hợp đồng điều khiển quy trình** | `party_schema` khai báo cần giấy tờ gì, thông tin gì → wizard tự sinh các bước. Thêm mẫu mới không sửa một dòng code |
| **3** | **`contract` trỏ tới `template_version`, không phải `template`** | Cập nhật mẫu không làm sai lệch hợp đồng cũ. Bắt buộc trong môi trường tài chính |
| **4** | **Windows là lớp xác thực** | Không mật khẩu ứng dụng. Bảo mật tập trung vào **4 con đường thoát dữ liệu** thay vì rải đều |
| **5** | **`ocr_field` lưu cả máy đoán lẫn người sửa** | Hệ thống tự đo được độ chính xác thật và tự cải thiện — trên chính máy khách hàng, không gửi đi đâu |
| **6** | **Ảnh bị xoá mặc định, không nhúng vào hợp đồng** | Vừa an toàn, vừa giảm dung lượng 8 lần (29 GB → 3.5 GB ở 10.000 hợp đồng) |

---

## Ngăn xếp công nghệ

| Tầng | Công nghệ |
|---|---|
| Desktop | **Tauri** (Rust) + WebView2 |
| Frontend | **React 18** + TypeScript 5 + MUI v5 + TanStack Query + Zustand |
| Backend | **Python 3.11+** + FastAPI + Pydantic v2 + Uvicorn (1 worker) |
| OCR | **PaddleOCR** PP-OCRv4 (CPU, offline) + OpenCV + zxing-cpp |
| CSDL | **PostgreSQL 16** portable (127.0.0.1:55432) + SQLAlchemy 2.0 + Alembic |
| Tài liệu | **docxtpl** (Jinja2 sandboxed) — ⭐ chỉ `.docx` |
| Logging | **Loguru** (JSON có cấu trúc, che PII bắt buộc) |
| Mã hoá | **cryptography** (AES-256-GCM) + Windows DPAPI |
| Đóng gói | PyInstaller (onedir) + NSIS |

---

## Chỉ số then chốt

| Chỉ số | Mục tiêu |
|---|---|
| Độ chính xác trường (có QR/MRZ) | ≥ 99% |
| Độ chính xác trường (OCR thuần) | ≥ 95% |
| Độ chính xác toàn thẻ (6/6 đúng) | ≥ 92% |
| ⭐ **False Confidence** (conf ≥ 0.95 nhưng sai) | **≤ 0.5%** — chỉ số chặn phát hành |
| Thời gian OCR 1 cặp ảnh (p95) | ≤ 9 giây |
| Sinh DOCX (p95) | ≤ 800 ms |
| Khởi động ứng dụng | p50 ≤ 10s · p95 ≤ 15s |
| RAM lúc nghỉ / đỉnh | ~460 MB / ~850 MB |
| Coverage Domain / Application | ≥ 95% / ≥ 85% |

---

## Quy mô hệ thống

| | Số lượng |
|---|---|
| Bảng CSDL | **19** |
| Endpoint API | ⭐ **62** *(D2.1: −2 endpoint PDF)* |
| Wireframe | **8** |
| Quy tắc validation | **56** |
| Port (interface) | ⭐ **19** *(đánh số 1–20, **khuyết 13**)* — `IDocumentTypeSelector` §12.19.1 và `ITemplateInspector` §12.19.2 thêm ở P3; `IPdfConverter` gỡ ở D2.1 |
| Use Case | **41** |
| Thư viện Python | **38** *(D2.1 bỏ `pypdf`)* |
| Ước tính công | **12.5 tuần** (2 người) |

---

## Lịch sử sửa đổi

| Bản | Nội dung |
|---|---|
| D1.0 | Bản thiết kế đầu tiên — 19 chương |
| D1.1 | **Chỉ giữ chế độ đơn máy** — bỏ LAN, bỏ Redis, bỏ reverse proxy, bỏ phê duyệt nhiều cấp |
| D1.2 | Bỏ wireframe đăng nhập · gộp bước "Bổ sung thông tin" vào màn hình kiểm tra OCR · đơn giản hoá giao diện |
| D1.3 | **Đưa bước chọn mẫu lên đầu** · bổ sung mô hình Bên tham gia (`party_schema`) |
| D1.4 | Khai báo chính thức 2 mẫu hợp đồng thật · biến `securities_account_no` · không nhúng ảnh |
| D1.5 | STK chứng khoán in đậm · tách số HĐ nội bộ ⟷ tên file xuất · ngày HĐ và chữ ký để trống |
| D1.6 | **Bỏ toàn bộ xác thực** — không mật khẩu, không JWT, không phân quyền |
| D2.0 | **Architecture Review** — sửa 7 lỗi, 6 cải thiện, cắt 5 mục, cắt một phần 3 mục |
| **D2.1** | ⭐ **Gỡ toàn bộ khâu xuất PDF và LibreOffice** — đầu ra duy nhất là `.docx`. Đảo ngược ADR-05. Kéo theo: 19→18 Port · 64→62 endpoint · ContractStatus 9→6 · JobType 6→5 · DocType 2→1 · 28→25 khoá cấu hình · đóng rủi ro font tiếng Việt. Lý do đầy đủ: [§9.13](09-template-va-tai-lieu.md) |

**Sửa trong lúc triển khai** *(không đổi số bản — chỉ chỉnh cho khớp thứ đo được)*

| Ngày | Nội dung |
|---|---|
| 2026-08-11 | ⭐ **Port 20 `ITemplateInspector`** (§12.19.2) — 18→**19 Port**, đánh số 1–20 khuyết 13 |
| 2026-08-11 | ⭐ §9.9 biện pháp #3: blacklist chuỗi **chỉ quét thân thẻ Jinja2**. Quét XML thô như bản cũ từ chối **mọi** `.docx` vì `openxmlformats.org` chứa `open` — đo trên 2 mẫu thật ([§9.9.1](09-template-va-tai-lieu.md)) |
| 2026-08-11 | ⭐ §9.5 từ điển biến: **25 → 28 biến** (đếm lại từng dòng; dòng `day/month/year` khai 3 biến) |
| 2026-08-11 | ⭐ `COCAS-6003` báo **số thứ tự đoạn văn**, không phải "số dòng" — `.docx` không có dòng ([§12.8.3](12-dac-ta-module.md)) |

### Tóm tắt kết quả D2.0

**7 lỗi đã sửa:** hàng đợi hai nguồn chân lý · regex tên tiếng Việt sai · giả định sai về PaddleOCR charset · tầng Application tạo đối tượng docxtpl · mâu thuẫn `contract_date` · endpoint chết · ví dụ API lỗi thời.

**6 cải thiện:** tách `IReadRepository`/`IWriteRepository` · ~~LibreOffice khởi động lười~~ *(D2.1 gỡ)* · biến thể ảnh tạo lười · QR thử 3 lần · nới NFR khởi động · nói đúng mức về Local Token.

**Đã cắt:** bộ sinh mã Zod/Pydantic · bảng `idempotency_record` · bảng `perf_metric` · 14 endpoint · 3 wireframe · bảng `organization`.

**3 bản lề giữ lại** cho nâng cấp sau (rẻ bây giờ, đắt về sau):
1. Bảng **`contract_party`** — thêm bên thứ hai sau này không phải di trú dữ liệu
2. **Cơ chế khoá lạc quan chung** — áp cho thực thể mới chỉ cần thêm cột
3. Endpoint **`GET /activity-logs/export`** — lưu trữ lạnh sau này chỉ là "xuất rồi xoá"

---

## 3 việc cần làm trước Giai đoạn 2

| # | Việc | Vì sao |
|---|---|---|
| 1 | ⭐ **Thu thập & gán nhãn Golden Set 200 cặp ảnh CCCD** | Đường găng dài nhất. Chỉ tiêu MRZ 75% chỉ kiểm chứng được bằng ảnh thật |
| 2 | ⭐ **Cung cấp 2 file `.docx` thật** | Để quét tên biến chính xác và xác nhận vị trí `{{r securities_account_no }}` |
| 3 | ⭐ **Xác nhận tên file xuất cho `01A/GDKQ`** | Đang tạm để `Mẫu 01A-GDKQ - {full_name}` vì cả hai mẫu đều mang số hiệu 01A |
