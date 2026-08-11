# COCAS — Chỉ dẫn phát triển

Hệ thống Desktop tự động tạo hợp đồng từ ảnh CCCD, chạy hoàn toàn cục bộ trên Windows.

---

## 📘 TÀI LIỆU THIẾT KẾ GỐC

> **`docs/design/` là nguồn chân lý duy nhất.** Mọi quyết định triển khai phải truy vết ngược được về một mục trong đó.
>
> **Nếu thực tế bắt buộc làm khác thiết kế → SỬA TÀI LIỆU TRƯỚC, VIẾT CODE SAU.**

Bắt đầu từ [`docs/design/README.md`](docs/design/README.md) — mục lục 14 tài liệu, phiên bản **D2.1**.

> ⭐ **D2.1 (2026-08-11) — KHÔNG XUẤT PDF.** `.docx` là đầu ra duy nhất; LibreOffice bị gỡ khỏi ngăn xếp, gói cài đặt và mọi cấu hình. Đảo ngược ADR-05. Lý do đầy đủ: [`09-template-va-tai-lieu.md §9.13`](docs/design/09-template-va-tai-lieu.md).

| Khi làm việc với | Đọc |
|---|---|
| Kiến trúc, ADR, tầng, DI | `01-kien-truc-tong-the.md` |
| Sơ đồ, luồng, máy trạng thái | `02-so-do-he-thong.md` · `03-luong-du-lieu.md` |
| Bảng, cột, quan hệ, migration, mã hoá | `04-co-so-du-lieu.md` |
| Endpoint, request/response, mã lỗi | `05-thiet-ke-api.md` |
| Màn hình, component, phím tắt | `06-giao-dien.md` |
| Pipeline OCR, QR/MRZ, fusion | `07-module-ocr.md` |
| Regex, quy tắc validation | `08-validation.md` |
| Template, DOCX, tên file | `09-template-va-tai-lieu.md` |
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
| **P-03** | **Replaceable Engines** — OCR/Storage/Render/Queue đều là Port |
| **P-04** | **Extraction ≠ OCR** — hợp nhất 3 kênh QR/MRZ/OCR |
| **P-05** | **Data Minimization** — xoá ảnh gốc sau khi sinh hợp đồng |
| **P-06** | **Template-Driven** — thêm mẫu = upload `.docx` + khai báo, không sửa code |
| **P-07** | **Everything is Logged** |
| **P-08** | **Fail Loud, Degrade Gracefully** — OCR chết vẫn nhập tay được |
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

## Quy mô hệ thống (D2.1)

| | Số lượng |
|---|---|
| Bảng CSDL | **19** |
| Endpoint API | ⭐ **62** *(D2.1: −2 endpoint PDF)* |
| Wireframe | **8** |
| Quy tắc validation | **56** |
| Port (interface) | ⭐ **19** *(đánh số 1–20, **khuyết 13** — `IPdfConverter` gỡ ở D2.1; `ITemplateInspector` thêm ở P3 module 3)* |
| Thư viện Python | **38** *(D2.1 bỏ `pypdf`)* |
| Wizard | **3 bước** |
| Mẫu hợp đồng | **2** (`01A_HD_GDN`, `01A_GDKQ`) |
| ⭐ Thế hệ thẻ hỗ trợ | **2** (`CCCD_CHIP` 2021, `CAN_CUOC_2024`) |

---

## Ngăn xếp công nghệ

| Tầng | Công nghệ |
|---|---|
| Desktop | Tauri (Rust) + WebView2 |
| Frontend | React 18 + TypeScript 5 + MUI v5 + TanStack Query + Zustand |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · Uvicorn (**1 worker**) |
| OCR | PaddleOCR PP-OCRv4 (CPU, offline) + OpenCV + zxing-cpp |
| CSDL | PostgreSQL 16 portable `127.0.0.1:55432` · SQLAlchemy 2.0 async · Alembic |
| Tài liệu | docxtpl (Jinja2 **sandboxed**) — ⭐ **chỉ `.docx`, không PDF** |
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

**Giai đoạn 1 (Thiết kế): ✅ HOÀN THÀNH** — tài liệu **D2.1** (D2.0 + gỡ PDF), 0 lỗi kiến trúc đã biết.

**Giai đoạn 2 (Triển khai): P0 ✅ + P1 ✅ HOÀN THÀNH (2026-08-09). P2 (OCR) mã nguồn ✅ xong 2026-08-11 — tuần 1 (tiền xử lý ảnh) + tuần 2 (kênh QR/MRZ) + tuần 3 (engine + phân loại mặt + trích trường) + tuần 3b (thế hệ thẻ thứ hai) + tuần 4 (chuẩn hoá + hợp nhất + validation) + tầng 5 `issue_place`. Còn lại của P2 là Golden Set.**

⭐ **P3 (Nghiệp vụ) ĐANG LÀM — module 3/6 xong 2026-08-11.** Module 1 `ExtractionPipeline`; module 2 alias/document-type/ocr-result repository + `ProcessOcrSessionUseCase`; ⭐ module 3 `DocxTemplateInspector` (**Port 20**, AST Jinja2, 10 mã chẩn đoán, chặn SSTI). ⭐ **D2.1 gỡ hẳn module 5 (PDF/LibreOffice) khỏi kế hoạch.** **1325 test xanh.**
Chi tiết đầy đủ từng module — xem [progress.md](progress.md) (cập nhật theo từng module, không rút gọn).

### Kiến trúc đã triển khai (P0 + P1 + P2 + P3 module 1–3)

| Tầng | Trạng thái |
|---|---|
| `domain/` | ✅ Đầy đủ — 10 Value Object · 14 enum · 8 Entity · **7 Domain Service** (⭐ `IssuePlaceNormalizer` **5 tầng** với `issue_place_shape.py`) + ⭐ **từ điển 28 biến template** (`template_variables.py`) · ⭐ **19 Port** (+ fake/null cho mỗi Port; đánh số 1–20 khuyết 13) · cây ngoại lệ · ⭐ **`validation/`**: `ValidationEngine` + registry 4 tập quy tắc + **23 quy tắc `V-OCR-*`** (3 tập còn lại đăng ký **rỗng**, không phải thiếu — xem ghi chú trong `engine.py`) |
| `infrastructure/` | Một phần — **persistence** (19 bảng, **10 migration**, 7/8 repository + UnitOfWork; `Contract` repo **hoãn có chủ đích** vì phụ thuộc `RenderContextBuilder` chưa tồn tại) · **security** (DPAPI thật + AES-256-GCM + blind index) · **logging** (Loguru 3 sink + PII filter 2 lớp) · **system** · ⭐ **ocr đầy đủ 8/8 Port OCR**: `preprocessing` · `channels` (`ZxingQrDecoder`, `Td1MrzReader`) · `engines` (`PaddleOcrAdapter`) · `classification` (`HeuristicSideClassifier`, ⭐ `MarkerDocumentTypeSelector`) · `extraction` · `text_matching.py` · ⭐ **documents**: `DocxTemplateInspector` (Port 20). Chưa có: storage, queue, `DocxRenderer`, `DocxContextAdapter` |
| `application/` | ⭐ Một phần — `dto/extraction.py` · `pipelines/extraction_pipeline.py` (9 chặng S3→S11) · ⭐ **`use_cases/ocr/process_ocr_session.py`** (2 transaction kẹp lượt OCR — ngoại lệ §12.14.1). Use Case khác vẫn rỗng |
| `presentation/` | Một phần — middlewares (CORS, security headers, correlation-id, local token) · chưa có router/endpoint nào (⭐ 62 endpoint là việc P3 module 7) |
| `container.py` | ✅ Composition Root — ⭐ **đã nối trọn chuỗi OCR**: 8 adapter P2 + `ExtractionPipeline` + `process_ocr_session_use_case()` + ⭐ `template_inspector`. ⚠️ `warm_up()` cố ý không gọi ở đây |

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
- ⭐ **`lang='vi'` của PaddleOCR không cho model tiếng Việt, cũng không cho PP-OCRv4** (đo 2026-08-10). Nó gộp về `latin_PP-OCRv3_rec` với `latin_dict.txt` — phủ **4/42** chữ hoa có dấu tiếng Việt. `vi_dict.txt` phủ 42/42 nhưng không bao giờ được chọn, và **không tồn tại** model khớp nó (404). Hệ quả: `FULL_NAME` từ OCR **mất dấu chứ không sai chữ**; QR là nguồn chính.
- ⭐ **`charset_hint` KHÔNG được xoá ký tự.** Mọi bên gọi làm số học theo vị trí trên kết quả, nên xoá một ký tự nhận nhầm đẩy lệch mọi trường phía sau → sáu giá trị sai đầy tự tin. Adapter chỉ chuyển hoa; việc ánh xạ là của kênh biết định dạng.
- ⭐ **Toạ độ `zone_map` gieo sẵn lệch ~0.2 theo y ở mọi trường mặt trước** — đã hiệu chỉnh bằng chân lý từ QR/MRZ (2026-08-10). Ô `full_name` cũ trỏ vào dòng `Citizen Identity Card` và giao nó cho hợp nhất như tên khách hàng. Kèm **danh sách chữ in sẵn** làm lớp chặn độc lập với độ chính xác toạ độ.
- ⭐ **Kênh MRZ đọc `v3` trước, `v4` dự phòng** — giả định "nhị phân hoá tốt hơn hẳn cho MRZ" sai với PaddleOCR (v4 mất 8/20 khối). Dải quét cũng đã hiệu chỉnh: **y 0.62–0.98**, không phải 0.82–0.98.
- ⭐ **4 số kiểm nhóm là cổng chặn, số kiểm tổng là nhân chứng** — bắt buộc cả 5 làm rớt 64% khối đúng. ⚠️ Nhưng khối **đã sửa lỗi** phải được số kiểm tổng xác nhận, nếu không `_repair` sẽ tự chế ra "hợp lệ" từ nhiễu. Và số kiểm tổng **không** làm chứng cho nhóm số tài liệu dòng 1 (cùng pha trọng số).
- ⭐ **Tín hiệu "đếm vùng text ở 0° vs 180°" không tồn tại** — 17.7 vs 15.8 vùng, conf 0.911 vs 0.904. PaddleOCR lật từng dòng nên thẻ lộn ngược vẫn ra chữ đầy đủ và tự tin, 74% sai. Thay bằng **dấu vân chữ in sẵn ở dải TRÊN** (phải là cụm chỉ có ở phần ba trên — dùng cụm ở đáy thẻ thì gọi sai 6/46).
- ⭐ **`partial_ratio` không an toàn với chuỗi ngắn** — mảnh 2 ký tự `ON` đạt 100 điểm với `CỘNG HÒA XÃ HỘI…`. Mọi so khớp phải nhân điểm với `min(1, len(text)/len(anchor))`, và phải **bỏ hẳn khoảng trắng** vì bộ nhận dạng nuốt dấu cách có hệ thống.
- ⭐ **Chuẩn hoá (S9) tồn tại vì HỢP NHẤT, không vì lưu trữ.** Ngày phải ra **ISO `YYYY-MM-DD`** ở cả 3 kênh: QR trả `13031987`, MRZ trả `13031987`, bộ trích trường trả `13/03/1987`. Không quy về một dạng thì quy tắc 3 (thưởng đồng thuận) chết hẳn và quy tắc 4 báo **xung đột giả trên mọi thẻ**. Cùng lý do, `KHÔNG THỜI HẠN` là **hằng số giá trị**, không phải `None` — `None` nghĩa là "không đọc được", khác hẳn.
- ⭐ **Sửa lỗi ngày chỉ được đổi MỘT chữ số và KHÔNG BAO GIỜ đổi năm.** Quét toàn bộ 8 chữ số như đặc tả gốc biến `29/02/2023` (ca biên **bắt buộc phải bị từ chối** theo §8.11) thành `2028-02-29` — cách đọc tự nhất quán duy nhất trong không gian tìm kiếm. Và cho phép 2 phép thế biến `00/00/1990` thành "duy nhất" `06/06/1990`. Giới hạn 1 phép thế đưa không gian từ 256 xuống 4 ứng viên, tức là "duy nhất" mới có nghĩa.
- ⭐ **Trong chuẩn hoá tên: SỬA chữ số trước, LỌC ký tự sau.** Lọc trước thì `H0ANG` mất số `0` vì ngoài bộ ký tự và thành `HANG` — một cái tên trông hợp lý nhưng không phải cái in trên thẻ. Thứ tự này lộ ra chỉ khi có test, không lộ khi đọc code.
- ⭐ **QR + MRZ trên cùng một ảnh không phải thế hoà mà là quan sát quyết định nhất** — trọng số 0.80 → BACK. Coi chúng là hai lá phiếu độc lập thì triệt tiêu đúng 0.40–0.40 và **mọi** cặp Căn cước 2024 ra `AMBIGUOUS` (đo: 0/10). Sau khi sửa: **10/10 đúng**, và **rẻ hơn 26%** vì không còn phải đọc dải tiêu đề.
- ⭐⭐ **`issue_place` là trường đóng 2 giá trị, nên hãy PHÂN LOẠI nó, đừng ĐỌC nó.** Bốn tầng đầu của `IssuePlaceNormalizer` đều so khớp **toàn bộ** chuỗi — đúng cho trường mở, sai cho trường đóng. Thêm **tầng 5**: lấy **3 chữ đầu** (`BOC` / `CUC`), xác nhận bằng **độ dài từ đầu tiên** (`BỘ` 2 ký tự / `CỤC` ≥3). Đo **22/22 đúng ở 0.92**, và quét 752 dòng còn lại của cùng bộ ảnh ra **0 phán quyết sai**.
  - ⚠️ **Tầng 3 và 4 không phải hai đường dự phòng độc lập — chúng chết cùng một lúc.** Bộ nhận dạng dính chữ (`CUCTRUONG CUCCANH SAT`) làm giao của `token_set_ratio` rỗng **và đồng thời** làm mất token `CUC` mà tầng 4 đòi. Kết quả: **8/22 ảnh không ra giá trị nào** — tệ hơn "độ tin cậy thấp".
  - ⚠️ **Tín hiệu "độ dài" hấp dẫn trên giấy nhưng sai trên máy.** Hai giá trị chuẩn chênh gần 5 lần (8 / 38 ký tự), nhưng văn bản thật tới nơi thì 2021 = 19–20 ký tự (vùng cắt cụt tên cơ quan) và 2024 = 15 và 31 (vùng nuốt thêm dòng tiếng Anh) — **chồng lấn và ngược chiều**. Độ dài là thuộc tính của **vùng cắt**, không phải của trường. Chỉ độ dài **từ đầu tiên** là dùng được.
  - ⚠️ **Script đo từng gieo 2 dòng alias trong khi bản seed thật có 19** — và 2 dòng đó đều tầng 4, nên tầng 3 **không có gì để so** và không thể kích hoạt. Con số "0.60 phẳng" trước đây là hiện vật của fixture, không phải tính chất của trường. Khi một trường trông yếu đều, hãy kiểm tra fixture trước.
- ⭐⭐ **`ExtractionPipeline` nhận DANH SÁCH `document_type`, không phải một cái** (P3 module 1, khác §12.3 bản gốc). Người dùng **không thể biết** thẻ mình cầm thuộc thế hệ nào, hai thế hệ lưu hành song song, và một phiên khai nhầm sẽ trích mọi trường qua sai `zone_map` — tức là sinh giá trị **sai đầy tự tin**, đúng thứ §7.9 chặn phát hành. Truyền một phần tử = hành vi cũ.
  - ⚠️ Bản đồ "mặt nào in trường nào" (dùng cho đòn bẩy bỏ lượt quét) phải lấy **hợp của mọi thế hệ ứng viên**, vì hai thế hệ in `expiry_date` ở hai mặt khác nhau. Dùng thế hệ đã khai báo sẽ khiến phiên khai nhầm bỏ đúng lượt quét lẽ ra nhận ra nó là thế hệ kia.
- ⭐ **S9 chạy TRƯỚC S7 cho hai kênh chính xác.** Không phải để đẹp thứ tự: đòn bẩy "bỏ lượt quét" cần biết trường nào còn thiếu, mà muốn biết thì QR/MRZ phải chuẩn hoá xong trước.
- ⭐⭐ **D2.1 — gỡ PDF thì phải gỡ luôn hai trạng thái trung gian.** `DOCX_READY` chỉ có nghĩa "đã có DOCX, chưa có PDF"; sau khi bỏ PDF, khoảng đó bằng không nên `GENERATING` đi thẳng `COMPLETED`, và `mark_docx_ready()` nhập vào `mark_completed(snapshot_sha256, now)`. Giữ lại `DOCX_READY` là giữ một trạng thái **không thao tác nào quan sát được**.
  - ⭐ **Số Port 13 và mã lỗi `COCAS-7004`/`7005` để KHUYẾT, không đánh lại và không tái sử dụng.** Đánh lại số làm sai mọi trích dẫn `§12.1x` trong mã, tài liệu và lịch sử commit — rẻ hôm nay, sai từ ngày mai.
  - ⚠️ **Migration `011` CHUYỂN dữ liệu chứ không xoá:** hợp đồng kẹt ở `DOCX_READY`/`PDF_CONVERTING`/`PDF_FAILED` đều nghĩa là `.docx` đã ghi xong ⇒ `COMPLETED`. Xoá chúng là huỷ chứng từ pháp lý để làm vừa một CHECK. Riêng job `PDF_CONVERT` đang xếp hàng thì xoá — chúng mô tả việc không còn tồn tại.
  - ⚠️ **Seed migration `007` sửa tại chỗ (28→25 khoá), không để `011` xoá bù** — CSDL seed *sau* D2.1 không được sinh ra dòng mà `011` tồn tại để xoá.
  - ⭐ **Con số dẫn xuất lạc hậu ngay:** "xoá ảnh giảm dung lượng 9 lần" thành **~20 lần**. Cắt phạm vi làm phần "không phải ảnh" nhỏ đi ⇒ tỉ lệ này **lớn lên**, ngược trực giác.
- ⭐⭐ **Repository phục vụ singleton phải nhận session FACTORY, không nhận session** (P3 module 2). `SqlAlchemyAliasRepository`/`SqlAlchemyDocumentTypeRepository` phục vụ `IssuePlaceNormalizer` — Domain Service sống suốt vòng đời tiến trình bên trong pipeline. Gắn session vào sẽ hoặc ghim singleton vào một session mà Use Case sẽ đóng dưới chân nó, hoặc kéo lượt đọc 19 dòng dữ liệu tham chiếu vào transaction nghiệp vụ.
  - ⚠️ **`find_by_alias` KHÔNG được là truy vấn riêng** — nó đọc chính cache của `list_active`. Hai đường SQL tới cùng một bảng là cách tầng 2 và tầng 3 bắt đầu bất đồng ý về việc *có những dòng nào*.
  - ⚠️ **Dòng tầng 4 có `alias_normalized` NULL.** Tra chuỗi rỗng mà khớp NULL sẽ trả về một dòng từ khoá và gán giá trị chuẩn ở **độ tin cậy đầy đủ**.
- ⭐⭐ **Infrastructure KHÔNG được import `ExtractionResult`** — nó là DTO tầng Application, mà `infrastructure` nằm **dưới** `application` trong hợp đồng import-linter. Vì thế có `OcrResultSnapshot`/`OcrFieldSnapshot` (từ vựng Domain) và **Use Case là bên dịch**. Không cần thêm Port: nó khớp `IWriteRepository[T]` (Port 9).
- ⭐ **Use Case có công việc dài ở giữa được dùng HAI transaction** (ngoại lệ §12.14.1, đã ghi vào tài liệu). Một transaction bao trọn 9.5 s giữ nguyên một kết nối pool không dùng đến, và sự cố giữa chừng rollback cả `PROCESSING` → phiên về `QUEUED` trong khi log nói ngược lại. Giá phải trả: sự cố **giữa** hai transaction để lại phiên `PROCESSING` vĩnh viễn (việc của §12.15).
- ⚠️ **`mrz_corrections_applied`: `NULL` ≠ `0`.** `NULL` = không có MRZ để đọc; `0` = đọc được, không phải sửa. Tỉ lệ sửa lỗi §7.5 chia cho vế thứ hai. Cùng loại: phiên `FAILED` **không có dòng `ocr_result`** — ghi dòng toàn NULL sẽ khiến "chạy không ra gì" giống hệt "thẻ trắng".
- ⚠️ **AAD của `ocr_field` gắn vào `id` của chính dòng đó**, không gắn vào phiên hay tên trường — nếu không, ciphertext dời được giữa 6 dòng cùng kết quả và `dob` dán đè `id_number` vẫn giải mã sạch.
- ⭐ **Chỉ 9/23 quy tắc `V-OCR-*` chặn cứng.** Thẻ hết hạn, tuổi bất thường, mã tỉnh lạ đều là 🟡 — chặn vì nghi ngờ là để người dùng không lập được hợp đồng cho khách đang ngồi trước mặt (P-08). Và trường **trống** chỉ do `V-OCR-017` báo: các quy tắc hình dạng (003/005/006/007/016) chỉ chạy khi trường **có giá trị nhưng sai dạng**, nếu không một ô hỏng sẽ nhận hai lỗi.
- 🔴🔴 **Quét blacklist chuỗi trên XML thô là một cổng chặn LUÔN ĐÓNG** (P3 module 3). §9.9 biện pháp #3 bản D2.0 từ chối file chứa `open` — và `open` nằm trong `http://schemas.openxmlformats.org/…`, không gian tên **bắt buộc của chính định dạng `.docx`**. Đo: 101 lần khớp trong `01A_HD_GDN.docx`, 15 trong `01A_HD_GDKQ.docx` ⇒ **từ chối 100% file sạch**. Sửa: chốt chặn chính là **hình dạng AST** (5 luật §9.9.1), blacklist chỉ quét **thân thẻ `{{ }}`/`{% %}`** (đo lại: 0 khớp).
  - ⚠️ **Luật AST phải soi `Getattr.attr`, không soi tên biến.** `{{ ''.__class__ }}` **không có nút `Name` nào** — gốc của nó là hằng chuỗi rỗng. Bộ quét chỉ nhìn tên biến cho payload này qua thẳng.
  - ⚠️ **Bộ phân tích cú pháp không cứu được gì:** cả 12 payload SSTI trong bộ test đều **phân tích sạch**. Nếu không quét thì chúng đi thẳng tới sandbox.
- ⭐⭐ **`{{r var }}` và `{%p … %}` KHÔNG phải cú pháp Jinja2 — chúng biến mất trước khi AST hình thành.** `patch_xml()` của docxtpl đổi `{{r x }}` thành `{{ x }}` rồi mới đưa cho bộ phân tích. Nên `richtext_vars`, `COCAS-6008` và `COCAS-6010` **bắt buộc** quét văn bản; bất biến "dùng AST, không dùng regex" chỉ áp cho **thu thập biến**. Cách quét đã kiểm chứng: **xoá mọi thẻ XML** (`<[^>]+>`) — thao tác đó tự nối lại các `run` mà Word chẻ ra, nên không cần logic gộp run riêng.
- ⭐ **`.docx` không có "dòng" — `COCAS-6003` phải báo SỐ THỨ TỰ ĐOẠN VĂN.** Chèn `\n` trước mỗi `<w:p` thì `TemplateSyntaxError.lineno - 1` **chính là** số thứ tự đoạn (đo: lỗi ở đoạn 6 → lineno 7). ⚠️ Số này đếm cả đoạn trong bảng nên lớn hơn `len(python-docx .paragraphs)` (mẫu GDKQ: 273 so với 16).
- ⚠️ **Header/footer là các *part* riêng.** `DocxTemplate.get_xml()` chỉ trả `word/document.xml`; cả 2 mẫu thật đều có chân trang. Bỏ qua ⇒ biến trong chân trang bị coi là "khai báo nhưng không dùng" (`COCAS-6011`) — cảnh báo sai trên file đúng.
- ⭐ **Chỉ 8/10 mã chẩn đoán nằm trong `diagnostics[]`.** `COCAS-6002`/`6003` được **ném**, vì hai ca đó không phân tích được gì — trả về một `TemplateInspection` rỗng-nhưng-hợp-lệ sẽ khiến bên gọi tưởng đã quét xong và thấy 0 biến (§12.8.1).
- ⚠️ **Không tự thêm lý do từ chối cho `party_schema`.** §4.5 liệt kê đúng **ba** giới hạn v1.0 (`entity_type`, `min`/`max`, `collect`). Thêm "nhiều bên" thành lý do thứ tư sẽ chặn mẫu mà `RenderContextBuilder` §12.9 bước 2 vốn dựng được.

### Ràng buộc cần biết khi làm tiếp P2

0. ⭐ **Model OCR không nằm trong Git.** Chạy `python backend/scripts/fetch_ocr_models.py` một lần để tải 16 MB về `backend/resources/ocr-models/`. Thiếu nó thì `PaddleOcrAdapter.warm_up()` **ném lỗi chứ không tải** (P-01), và các test trong `tests/security/test_ocr_offline.py` tự bỏ qua.

1. ⭐ **Vẫn thiếu Golden Set 200 cặp ảnh CCCD đã gán nhãn và 2 file `.docx` thật.** Đây giờ là thứ **duy nhất** chặn việc chốt KPI P2.
   - **MRZ ≥75%: đã đo 22/22 = 100%** (2026-08-10), 0 lần phải sửa lỗi, 2/2 ảnh có cả hai kênh cho số CCCD khớp nhau.
   - **QR ≥90%: đã đo 20/21 = 95.2%** (2026-08-10) trên các ảnh **thật sự có in QR**.
   - **Phân loại mặt ≥99%: đã đo 22/22 cặp** (12 cặp 2021 + 10 cặp 2024), đưa vào **sai thứ tự** có chủ đích.
   - ⭐ **False Confidence ≤0.5%: đã đo được 0/16 = 0.0%** (2026-08-10, đo lại 2026-08-11 vẫn 0/16). ⚠️ Proxy dùng QR/MRZ **làm nhãn** cho các trường OCR cũng đọc được, nên nó **chỉ phủ phần giao** — và `issue_place` nằm **ngoài** phần giao đó vì không kênh chính xác nào đọc trường này. Golden Set vẫn cần cho con số đầy đủ, và nó là **cách duy nhất** để kiểm chứng tầng 5.
   - ⭐ **`issue_place`: 20/20 thẻ, conf trung bình 0.89, 1 ô phải review** (2026-08-11, sau khi thêm tầng 5). Trước đó: 12/20 ở 0.60, cả 12 phải review.
   - ⭐ **Nhãn của Golden Set phải có cả trường "thế hệ thẻ"** — xem ràng buộc 7.
   - ⭐ **Pipeline thật (P3 module 1), 15 thẻ ghép đúng: 6/6 trường trên 15/15 thẻ, 0 ô review, conf tổng 0.99, 0 lỗi validation** (2026-08-11).
   - Đo lại bất cứ lúc nào: `verify_qr_mrz.py` (kênh) · `verify_side_classification.py` (phân loại mặt) · `verify_extraction.py` (từng bộ phận S3→S11) · ⭐ **`verify_pipeline.py` (toàn bộ `ExtractionPipeline`; thêm `--selector-sweep` để đo riêng Port 19)**.
   - ⚠️ **Ghép ảnh theo tên file liền nhau là SAI và đã tạo ra một bộ số hoàn toàn giả** (23/26 cặp `SOURCE_CONFLICT`, 0 thẻ 2024 nhận ra được). Ghép bằng **số CCCD** mà QR/MRZ cùng in. Xem phát hiện #35 trong `progress.md`.
   - ⚠️ **Không ghép cặp được thẻ Căn cước 2024 bằng cách đó** — mặt trước thế hệ này không có kênh chính xác nào nên không cho số CCCD. Hệ quả: **toàn chuỗi trên thẻ 2024 vẫn chưa được đo.**
2. **PyInstaller + asyncpg**: `hiddenimports = ["asyncpg.pgproto"]` không đủ — asyncpg nạp submodule Cython biên dịch sẵn không thấy được qua static analysis. Dùng `collect_submodules("asyncpg")` (đã áp dụng trong `build.spec`).
3. **`console=False` (bản production) sẽ crash lúc khởi động** — `loguru_config.configure_logging()`'s console sink gọi `logger.add(sys.stderr, ...)`, và `sys.stderr` là `None` dưới chế độ windowed của PyInstaller. Cố ý để lại cho P5/P6 (khi Supervisor đọc log qua file), **không phải bug đã sửa**.
4. ✅ ~~Sửa xoay 180° cho mặt trước~~ — **xong tuần 3.** ⚠️ Nhưng **không** bằng model `cls` như dự kiến: tín hiệu `cls`/đếm vùng text không phân biệt được hai chiều (xem quyết định ở trên). Dùng dấu vân chữ in sẵn ở dải trên; đo 44/46 đúng cả hai chiều, **0 sai**.
5. Kích thước gói `onedir` đo thật ở bản trial ~505 MB (tài liệu ước tính 180 MB cho bản cuối) — nay cộng thêm **16 MB** `resources/ocr-models` (nhẹ hơn ước tính 850 MB rất nhiều vì model PP-OCRv3 mobile nhỏ). Vẫn theo dõi ngân sách 1.5 GB (§14.5 sổ rủi ro).
6. ⭐⭐ **CÓ HAI THẾ HỆ THẺ, và bộ mẫu chứa cả hai.** Căn cước 2024 (`CAN_CUOC_2024`) in **QR ở mặt SAU** và **ngày hết hạn ở mặt SAU** — ngược với CCCD gắn chip 2021 (`CCCD_CHIP`). Tiêu đề `CĂN CƯỚC`, nhãn số thẻ `Số định danh cá nhân`, cơ quan cấp `BỘ CÔNG AN`. Mỗi thế hệ là **một dòng `document_type` riêng** với `zone_map`/`anchor_patterns` riêng — không có mã trích trường nào biết đến thế hệ. Chi tiết: `07-module-ocr.md §7.4.7`.
   - ⚠️ Điều này ẩn suốt 3 tuần vì mọi phép đo đều làm theo **tỉ lệ tổng**. Khi một tỉ lệ trông thấp, hãy mở từng ca lệch ra xem trước khi kết luận kênh yếu — lần này 19 trong 23 điểm phần trăm hụt là do **mẫu số sai**, không phải do bộ giải mã.
   - ✅ **Đã đo và đã sửa (2026-08-10):** phân loại mặt trên thẻ 2024 từng ra `AMBIGUOUS` **0/10 cặp** vì QR và MRZ triệt tiêu nhau. Sửa bằng tín hiệu tổ hợp QR+MRZ → BACK (0.80): **10/10 đúng**, đối chứng 2021 giữ 12/12. Đo lại: `python backend/scripts/verify_side_classification.py "<thư mục ảnh>"`.
7. ⚠️ **Anchor ngắn vẫn là cái bẫy chưa hết.** Sau `Số` (2 ký tự, khớp `SOCIALIST REPUBLIC` 100 điểm) là `Số:` (3 ký tự, **80.0**) — gỡ 2026-08-10. Và hai nhãn chia nhau tiền tố dài (`Ngày, tháng, năm cấp` / `…hết hạn`) khớp chéo ở 83.9/83.3. Mọi anchor mới **phải** được chấm với dòng tiêu đề thật trước khi gieo; `tests/unit/infrastructure/ocr/extraction/test_doctype_seeds.py` làm việc đó tự động.
8. 🔴 **Ngân sách p95 ≤ 9 s/cặp VẪN BỊ VƯỢT — đo pipeline thật 2026-08-11: trung bình 9.5 s/cặp, p95 12.4 s/cặp.** Máy đo: **4 nhân / 4 GB RAM**.
   - ⭐ **Nhận dạng toàn thẻ hai lượt đắt gấp 5–7 lần chứ không phải gấp đôi** trên máy ít RAM. Gộp còn **một lượt/ảnh** đã cắt 28–45 s xuống 7.7 s/ảnh.
   - ✅ **Đòn bẩy "bỏ lượt quét mặt không còn gì để đóng góp" đã làm và đã đo: 1.00 lượt/cặp thay vì 2 — cắt đúng 50% công nhận dạng, không mất trường nào** (15/15 thẻ vẫn đủ 6/6). Từ ~15.4 s/cặp xuống 9.5 s.
   - 🎯 Ba hướng còn lại: (1) hạ `target_long_edge` rồi đo lại; (2) bỏ lượt đọc dải tiêu đề của bộ phân loại mặt khi QR/MRZ đã quyết; (3) bỏ lần giải mã QR trùng mà bộ phân loại mặt gọi thêm (~66 ms/ảnh — **đã cân nhắc và cố ý không làm**: mọi cách nhớ đệm an toàn đều phức tạp hơn 1.6% mà nó tiết kiệm).
   - ⚠️ Máy đích thực tế **chưa biết**, và p95 từng lệch **1.7 lần** giữa hai lần chạy giống hệt nhau. Đừng chốt hay bác bỏ chỉ tiêu này bằng một lần chạy.
9. ⚠️ **Đừng chạy pytest song song với script PaddleOCR** trên máy này — đã gây `OcrTimeoutError` giả hai lần trong một phiên (4 nhân / 4 GB). Cùng lý do, `ExtractionPipeline` khoá bộ nhận dạng tuần tự: hai lượt đồng thời sinh `Insufficient memory` **từ trong OpenCV**, trông như lỗi giải mã ảnh chứ không như hết bộ nhớ.
10. ⭐ **Không suy "thế hệ thẻ" từ `anchor_patterns`.** Hai thế hệ khai chung phần lớn nhãn, và `Ngày, tháng, năm` (2021) là **tiền tố** của `Ngày, tháng, năm sinh` (2024) — đếm nhãn khớp là đo ảnh rõ tới đâu. Dùng `document_type.identity_markers` (cụm chỉ một thế hệ in). Đo: **43/44 đúng, 0 sai, 1 từ chối**.
11. ⚠️ **Ràng buộc CSDL không tự đi theo tầng Domain.** `ck_ocr_field__tier_range` nằm ở 1..4 suốt một ngày sau khi tầng 5 ra đời, và tầng 5 giải 20/20 lần đọc `issue_place` — tức là ràng buộc cũ sẽ chặn gần như mọi dòng, **lúc INSERT, trong job nền**. `IssuePlaceNormalizer.MAX_TIER` + `tests/unit/migrations/test_constraint_names.py` giờ nối hai bên lại.

### Quy trình làm việc Giai đoạn 2

Mỗi lần làm **một module hoàn chỉnh**: cấu trúc thư mục → mã nguồn → giải thích → cách chạy → cách kiểm thử. Chỉ chuyển module tiếp theo khi module hiện tại đã xong và test xanh.
