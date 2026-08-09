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
| Bảng CSDL | **19** |
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
| OCR | PaddleOCR PP-OCRv4 (CPU, offline) + OpenCV + zxing-cpp |
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

**Giai đoạn 2 (Triển khai): P0 ✅ + P1 ✅ HOÀN THÀNH (2026-08-09). P2 (OCR) đang làm — tuần 1 (tiền xử lý ảnh) ✅ + tuần 2 (kênh QR/MRZ) ✅ xong 2026-08-09.**
Chi tiết đầy đủ từng module — xem [progress.md](progress.md) (cập nhật theo từng module, không rút gọn).

### Kiến trúc đã triển khai (P0 + P1)

Backend Python (`backend/src/cocas/`) đã có đủ 3/4 tầng theo Dependency Rule, `application/` mới có khung thư mục rỗng (Use Case thật là việc của P3):

| Tầng | Trạng thái |
|---|---|
| `domain/` | ✅ Đầy đủ — 10 Value Object · 14 enum · 8 Entity · 5 Domain Service · 18 Port (+ fake/null cho mỗi Port) · cây ngoại lệ |
| `infrastructure/` | Một phần — **persistence** (19 bảng, 8 migration, 7/8 repository + UnitOfWork; `Contract` repo **hoãn có chủ đích** vì phụ thuộc `RenderContextBuilder` chưa tồn tại tới P3) · **security** (DPAPI thật + AES-256-GCM + blind index) · **logging** (Loguru 3 sink + PII filter 2 lớp) · **system** (`SystemClock`, `Uuid7Generator`) · **ocr/preprocessing** (`OpenCvPreprocessor` + 5 biến thể tạo lười — P2 tuần 1) · **ocr/channels** (`ZxingQrDecoder` + `Td1MrzReader` + `td1.py` — P2 tuần 2). Chưa có: OCR engine adapter, side classifier, field extractor, storage, documents, queue |
| `application/` | ⏳ Rỗng — chờ P3 |
| `presentation/` | Một phần — middlewares (CORS, security headers, correlation-id, local token) · chưa có router/endpoint nào (64 endpoint là việc P3) |
| `container.py` | ✅ Composition Root nối toàn bộ đồ thị phụ thuộc thật — ngoại lệ duy nhất được import-linter cho phép import cả 4 tầng |

⭐ Mốc demo M1 (roadmap §14.3) đã đạt: [`backend/scripts/demo_m1_customer.py`](backend/scripts/demo_m1_customer.py) tạo Customer giả qua Container thật, đọc lại giải mã đúng, xác nhận `id_number_enc` là nhị phân không đọc được — chạy thật trên PostgreSQL. Đã có bản build `.exe` trial đầu tiên ([`backend/build.spec`](backend/build.spec)) — khởi động và trả request thật; chưa đóng gói model OCR thật (chưa có adapter).

### Quyết định quan trọng đã chốt khi triển khai (khác/rõ hơn bản D2.0 gốc)

Mọi mục dưới đây đã đồng bộ ngược vào `docs/design/`, không chỉ nằm trong code:

- **19 bảng CSDL, không phải 18** — `04-co-so-du-lieu.md` §4.4.15 từng gộp 2 bảng dưới 1 tiêu đề. Đã sửa doc + mọi chỗ trích dẫn con số này (kể cả bảng "Quy mô hệ thống" ở trên).
- **Blind index phải trộn tên trường**: `HMAC-SHA256(PEPPER, field_name ‖ normalize(value))`, không phải `HMAC-SHA256(PEPPER, normalize(value))` như đặc tả gốc — công thức cũ khiến SĐT và số TK ngân hàng cùng chuỗi số ra cùng blind index (đụng độ chéo cột). Sửa cả `04-co-so-du-lieu.md`, `12-dac-ta-module.md` và `blind_index.py`.
- **`Container` không có "chế độ dev dùng `NullCryptoService`"** — luôn dùng `DpapiCryptoService` thật, nhất quán với P-11 (Windows là lớp xác thực duy nhất, không có triển khai thay thế). `NullCryptoService`/`FrozenClock`/`SequentialIdGenerator` chỉ tồn tại trong `tests/fixtures/fake_ports.py`.
- **Loguru cần 2 lớp phòng thủ PII, không phải 1**: sửa `record["message"]`/`record["extra"]` qua `patcher` là chưa đủ — còn phải (1) tắt `diagnose=True` mặc định (rò biến cục bộ trong traceback) và (2) tự sửa `exception.args` tại chỗ (dòng tóm tắt `str(exc)` không đi qua `record["message"]`). Cả hai đều **không lộ ra khi đọc code**, chỉ lộ khi chạy test hồi quy `grep` thật trên file log.
- **`gitleaks`/`radon` từng bị ghim sai trong `pyproject.toml`** (`gitleaks` không tồn tại trên PyPI; dải `radon>=6.1.0` chưa từng phát hành) — khiến `pip install -e ".[dev]"` fail ngay từ đầu kể từ khi 2 dòng này được thêm. Đã sửa; `ci.yml`'s bước Gitleaks đổi sang `choco install`.
- ⭐ **Bộ giải mã QR là `zxing-cpp`, không phải WeChat/pyzbar** (đổi 2026-08-09 sau khi đo thật 53 ảnh). `cv2.QRCodeDetector` chỉ đọc 1/53; `pyzbar` không chạy nổi vì `libzbar-64.dll` cần VC++ 2013 Redistributable (**máy khách cũng sẽ hỏng y hệt**); `cv2.wechat_qrcode` cần `opencv-contrib` và tốn 4060 ms/ảnh. `zxing-cpp` cùng độ chính xác WeChat, 66 ms/ảnh, wheel tự chứa. Đã đồng bộ vào `07`, `03`, `01`, `11`, `13`, `pyproject.toml`, `build.spec`.
- ⭐ **Số CCCD trong MRZ nằm ở vùng dữ liệu tuỳ chọn (dòng 1, vị trí 15–26), KHÔNG ở trường số tài liệu** (vị trí 5–13 là **CMND cũ 9 số**). Lấy nhầm sẽ khiến quy tắc hợp nhất #5 `CARD_MISMATCH` báo động giả với mọi thẻ.
- ⭐ **Ánh xạ cưỡng bức bộ ký tự MRZ phải áp theo vị trí, không toàn cục** — A–Z là ký tự hợp lệ trong TD1, nên áp `O→0 · D→0 · S→5 · B→8` toàn cục sẽ phá mọi họ tên Việt (`DO`→`00`, `HOANG`→`H0ANG`). Chỉ ép chữ→số trong các dải TD1 định nghĩa là số; dòng 3 (họ tên) không bao giờ bị ép.

### Ràng buộc cần biết trước khi bắt đầu P2

1. ⭐ **Vẫn thiếu Golden Set 200 cặp ảnh CCCD đã gán nhãn và 2 file `.docx` thật** — chặn kiểm chứng KPI P2 (QR ≥90%, MRZ ≥75%, False Confidence ≤0.5%). 53 ảnh mẫu hiện có **không gán nhãn trước/sau**, nên không tính được mẫu số cho tỉ lệ đọc QR: đo được 18/53 ảnh, tương đương một dải rộng 54–81% mặt trước. Xem "Việc cần người dùng cung cấp" trong `progress.md`.
   - **MRZ chưa đo được lần nào** — `Td1MrzReader` phụ thuộc `IRegionRecognizer`, chỉ có hiện thực thật từ tuần 3. Logic TD1 đã test kỹ bằng khối MRZ thật; phần chưa biết là engine đọc dải MRZ ra chuỗi tốt tới đâu. Dùng `backend/scripts/verify_qr_mrz.py` để đo ngay khi cắm adapter.
2. **PyInstaller + asyncpg**: `hiddenimports = ["asyncpg.pgproto"]` không đủ — asyncpg nạp submodule Cython biên dịch sẵn không thấy được qua static analysis. Dùng `collect_submodules("asyncpg")` (đã áp dụng trong `build.spec`).
3. **`console=False` (bản production) sẽ crash lúc khởi động** — `loguru_config.configure_logging()`'s console sink gọi `logger.add(sys.stderr, ...)`, và `sys.stderr` là `None` dưới chế độ windowed của PyInstaller. Cố ý để lại cho P5/P6 (khi Supervisor đọc log qua file), **không phải bug đã sửa**.
4. ⭐ **Tuần 3 phải hoàn tất khâu sửa xoay 180° cho mặt trước.** Tuần 1 chỉ xử lý được mặt sau (dựa vào vị trí khối MRZ); mặt trước không có tín hiệu nào đủ tin cậy nếu chưa có engine — dùng model `cls` của PaddleOCR khi cắm `PaddleOcrAdapter`. Xem `progress.md` mục P2 phát hiện #3, #4.
5. Kích thước gói `onedir` đo thật ở bản trial ~505 MB (tài liệu ước tính 180 MB cho bản cuối) — cần theo dõi khi thêm `resources/ocr-models` ở P5/P6, tránh vỡ ngân sách 1.5 GB (§14.5 sổ rủi ro).

### Quy trình làm việc Giai đoạn 2

Mỗi lần làm **một module hoàn chỉnh**: cấu trúc thư mục → mã nguồn → giải thích → cách chạy → cách kiểm thử. Chỉ chuyển module tiếp theo khi module hiện tại đã xong và test xanh.
