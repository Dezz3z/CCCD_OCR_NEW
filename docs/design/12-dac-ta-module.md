# 12 — Đặc tả hợp đồng module

[← Mục lục](README.md)

**13 module cốt lõi · Hợp đồng interface đủ để hiện thực 1-1**

---

## 12.1. Quy ước đọc bảng

| Mục | Ý nghĩa |
|---|---|
| **Tiền điều kiện** | Điều kiện phải đúng **trước khi** gọi. Vi phạm = lỗi lập trình, không phải lỗi người dùng |
| **Hậu điều kiện** | Điều kiện được đảm bảo **sau khi** gọi thành công |
| **Bất biến** | Luôn đúng, ở mọi thời điểm |
| **Ném ra** | Ngoại lệ có thể xảy ra — đã dịch sang ngoại lệ Domain |
| **Không được làm** | Ranh giới trách nhiệm — vi phạm = rò rỉ kiến trúc |

---

## 12.2. `IOcrEngine` / `IRegionRecognizer` — Port thay thế engine

### `IRegionRecognizer` (port hẹp)

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) |
| **Trách nhiệm** | Nhận dạng văn bản trong **một vùng** của ảnh |
| **Phương thức** | `recognize_region(image: ImageData, bbox: RelativeBox, charset_hint: str \| None) -> TextRegion \| None` |
| **Vì sao tách riêng** | ⭐ `MrzReader` chỉ cần phương thức này — không nên phụ thuộc toàn bộ `IOcrEngine` (nguyên tắc ISP) |

### `IOcrEngine` (kế thừa `IRegionRecognizer`)

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) |
| **Trách nhiệm** | Nhận dạng văn bản trong ảnh. **Chỉ vậy** |
| **Phương thức 1** | `recognize(image: ImageData, options: OcrOptions) -> list[TextRegion]` |
| **Phương thức 2** | *(kế thừa)* `recognize_region(...)` |
| **Phương thức 3** | `warm_up() -> None` — nạp model |
| **Phương thức 4** | `get_info() -> EngineInfo` |
| **Tiền điều kiện** | `image` giải mã được, cạnh ngắn ≥ 320 px; `warm_up()` đã gọi thành công |
| **Hậu điều kiện** | Mọi `TextRegion.text` chuẩn hoá Unicode **NFC**; `bbox` là toạ độ **tương đối 0..1**; danh sách sắp xếp theo thứ tự đọc (trên→dưới, trái→phải) |
| **Bất biến** | ⭐ Không bao giờ trả `None` từ `recognize()` — không nhận được gì thì trả **danh sách rỗng** |
| **Bất biến** | ⚠️ `charset_hint` là **gợi ý cho hậu xử lý**, KHÔNG phải ràng buộc giải mã (PaddleOCR không hỗ trợ) |
| **Ném ra** | `OcrEngineUnavailableError` · `OcrTimeoutError` · `ImageDecodeError` |
| **Không được làm** | ❌ Biết khái niệm "họ tên"/"số CCCD"/"nơi cấp" · ❌ Ghi file · ❌ Truy cập CSDL · ❌ Đọc cấu hình toàn cục (nhận qua constructor) |
| **Hiện thực** | `PaddleOcrAdapter` (mặc định) · `TesseractAdapter` (dự phòng) · `NullOcrAdapter` (khi engine chết) |
| **Điểm test** | ⭐ Toàn bộ test tầng trên phải chạy được với `FakeOcrEngine` trả dữ liệu cố định |

**Kiểu dữ liệu:**

| Kiểu | Trường |
|---|---|
| `TextRegion` | `bbox: RelativeBox` · `text: str` · `confidence: float (0..1)` |
| `RelativeBox` | `x, y, w, h: float (0..1)` |
| `OcrOptions` | `use_angle_cls: bool` · `charset_hint: str \| None` · `min_confidence: float` |
| `EngineInfo` | `name` · `version` · `languages: list[str]` · `is_ready: bool` · `model_path: str` |

---

## 12.3. `ExtractionPipeline` — Bộ điều phối 9 chặng

| Mục | Nội dung |
|---|---|
| **Tầng** | Application |
| **Trách nhiệm** | Chạy tuần tự S3→S11, xử lý lỗi từng chặng, gom kết quả |
| **Phương thức** | `execute(front_image: bytes, back_image: bytes, doc_type: DocumentTypeSpec, progress: ProgressCallback) -> ExtractionResult` |
| **Tiền điều kiện** | Hai ảnh đã qua kiểm định S1; `doc_type` tồn tại và `is_active` |
| **Hậu điều kiện** | `ExtractionResult` luôn có đủ 6 khoá trong `fields` (giá trị có thể `None`); `channel_summary` phản ánh đúng nguồn thắng cuộc; `validation_report` đã chạy đủ 23 quy tắc |
| **Bất biến** | ⭐ **Không bao giờ ném ngoại lệ ra ngoài** — mọi lỗi gói vào `ExtractionResult.error_code` và `status`. Lý do: pipeline chạy trong job nền; ngoại lệ lọt ra sẽ làm chết worker |
| **Bất biến** | `progress` được gọi ít nhất một lần mỗi chặng với `(percent, message_vi)` |
| **Xử lý lỗi từng chặng** | Phân loại `SUY_GIẢM` / `CẦN_NGƯỜI_DÙNG` / `CHÍ_MẠNG` — xem [07-module-ocr.md §7.7](07-module-ocr.md) |
| **Không được làm** | ❌ Ghi CSDL (Use Case làm) · ❌ Ghi file · ❌ Biết về HTTP |
| **Đầu ra** | `ExtractionResult{ status, fields{6}, channel_summary, validation_report, diagnostics, overall_confidence, auto_swapped, duration_ms, error_code }` |

---

## 12.4. `IImagePreprocessor`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) · hiện thực `OpenCvPreprocessor` (Infrastructure) |
| **Trách nhiệm** | Biến ảnh thô thành **tập biến thể** tối ưu cho từng kênh |
| **Phương thức** | `prepare(image_bytes: bytes, exif_orientation: int \| None, profile: PreprocessProfile) -> PreprocessedImageSet` |
| **Đầu ra** | `PreprocessedImageSet` — truy cập biến thể qua thuộc tính `.v0 .v1 .v2 .v3 .v4` · `transform_matrix` · `warp_succeeded: bool` · `quality: ImageQuality` |
| **Tiền điều kiện** | `image_bytes` không rỗng |
| **Hậu điều kiện** | `.v0` luôn khả dụng; các biến thể khác dựng được khi truy cập |
| **Bất biến** | ⭐ Biến thể **chỉ tạo khi truy cập lần đầu**, sau đó cache trong phạm vi đối tượng |
| **Bất biến** | Không bao giờ sửa `v0`. Mọi biến thể giữ được ma trận biến đổi để ánh xạ ngược `bbox` về ảnh gốc |
| **Ném ra** | `ImageDecodeError` · `ImageTooSmallError` |
| **Không được làm** | ❌ Ghi file · ❌ Truy cập CSDL · ❌ Phụ thuộc cấu hình toàn cục |

---

## 12.5. `IssuePlaceNormalizer` — Chuẩn hoá 4 tầng

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain Service |
| **Trách nhiệm** | Đưa chuỗi thô về đúng 1 trong 2 giá trị chuẩn, hoặc `None` |
| **Phương thức** | `normalize(raw: str) -> NormalizationOutcome` |
| **Phụ thuộc** | `alias_repository: IAliasRepository` (nạp `normalization_alias`, có cache) |
| **Tiền điều kiện** | `raw` là chuỗi (có thể rỗng) |
| **Hậu điều kiện** | `outcome.value ∈ {"BỘ CÔNG AN", "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI", None}` |
| **Bất biến** | ⭐ **Không tồn tại đường nào trả về giá trị thứ ba.** Đây là bất biến quan trọng nhất của module |
| **Thuật toán** | Tầng 0 tiền chuẩn hoá → Tầng 1 khớp chính xác (bỏ dấu) → Tầng 2 tra alias → Tầng 3 fuzzy `token_set_ratio` → Tầng 4 từ khoá → `None` |
| **Đầu ra** | `NormalizationOutcome{ value, confidence, tier (0..4), matched_alias_id }` |
| **Bảng confidence** | Tầng 1 → 1.00 · Tầng 2 → theo `alias.assigned_confidence` · Tầng 3 ≥85 → 0.90, 70–85 → 0.65 · Tầng 4 → 0.60 · Không khớp → 0.00 |
| **Test bắt buộc** | ⭐ Property test: với **mọi** chuỗi đầu vào bất kỳ, kết quả luôn thuộc tập 3 giá trị cho phép |

---

## 12.6. `FieldFusionService` — Hợp nhất 3 nguồn

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain Service |
| **Trách nhiệm** | Từ nhiều ứng viên chọn ra giá trị cuối và tính độ tin cậy |
| **Phương thức** | `fuse(candidates: dict[FieldKey, list[Candidate]], context: FusionContext) -> dict[FieldKey, FusedField]` |
| **Tiền điều kiện** | Mỗi `Candidate` đã qua chuẩn hoá |
| **Hậu điều kiện** | Kết quả có đủ 6 khoá; mỗi `FusedField.source ∈ {QR, MRZ, OCR, MANUAL, NONE}` |
| **Bất biến** | ⭐ `confidence ∈ [0, 1]` tuyệt đối · nếu `value is None` thì `confidence = 0` và `source = NONE` |
| **8 quy tắc** | Ưu tiên nguồn · thưởng đồng thuận · phát hiện xung đột · kiểm tra khớp thẻ (`CARD_MISMATCH`) · suy luận từ mã số · tính điểm tổng · gắn cờ `needs_review` |
| **Không được làm** | ❌ Quyết định chặn hay không chặn (việc của Validation) · ❌ Sửa giá trị |

---

## 12.7. `ValidationEngine`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain |
| **Trách nhiệm** | Chạy tập quy tắc trên một đối tượng, trả báo cáo |
| **Phương thức** | `validate(target: Any, rule_set: RuleSetKey, context: RuleContext) -> ValidationReport` |
| **Tập quy tắc** | `OCR_RESULT` (23) · `CUSTOMER_FORM` (15) · `CONTRACT_GENERATION` (10) · `TEMPLATE_REGISTRATION` (8) |
| **Tiền điều kiện** | `rule_set` tồn tại trong registry |
| **Hậu điều kiện** | ⭐ **Chạy hết tất cả quy tắc**, không dừng ở lỗi đầu tiên — người dùng cần thấy toàn bộ vấn đề trong một lần |
| **Bất biến** | `report.is_valid == (len(report.errors) == 0)` |
| **Đầu ra** | `ValidationReport{ is_valid, errors[], warnings[], infos[] }` — mỗi mục `{code, field, message_vi, hint, severity}` |
| **Không được làm** | ❌ Sửa dữ liệu · ❌ Truy cập CSDL trực tiếp (quy tắc cần tra CSDL nhận repository qua `RuleContext`) |
| **Mở rộng** | Thêm quy tắc = thêm một đối tượng Rule vào registry, **không sửa engine** |

---

## 12.8. `TemplateInspector`

| Mục | Nội dung |
|---|---|
| **Tầng** | Infrastructure |
| **Trách nhiệm** | Mở file `.docx`, quét biến bằng **AST Jinja2**, đối chiếu từ điển |
| **Phương thức** | `inspect(file_bytes: bytes, party_schema: PartySchema) -> TemplateInspection` |
| **Tiền điều kiện** | `file_bytes` không rỗng |
| **Hậu điều kiện** | `inspection.status ∈ {VALID, WARNING, INVALID}`; nếu `INVALID` thì `diagnostics` có ít nhất một mục mức ERROR |
| **Bất biến** | ⭐ **Không bao giờ render** trong lúc kiểm tra — chỉ phân tích cú pháp. Render là việc của `DocxRenderer` |
| **Bất biến** | ⭐ Dùng **AST Jinja2**, không dùng regex quét text |
| **Ném ra** | `NotADocxFileError` · `TemplateSyntaxError(line, detail)` |
| **Kiểm tra bảo mật** | ⭐ Quét mẫu nguy hiểm (`__`, `class`, `mro`, `globals`, `import`, `eval`, `lipsum`, …) → `COCAS-6014` |
| **Kiểm tra phạm vi** | ⭐ `party_schema` chỉ dùng tính năng v1.0 (`entity_type=INDIVIDUAL`, `min=max=1`) → `COCAS-6016` |
| **Đầu ra** | `TemplateInspection{ status, declared[], required[], optional[], unknown[], richtext_vars[], has_loops, has_conditionals, diagnostics[] }` |

---

## 12.9. `RenderContextBuilder` (Application)

| Mục | Nội dung |
|---|---|
| **Tầng** | ⭐ **Application** |
| **Trách nhiệm** | Biến dữ liệu CSDL thành từ điển chỉ chứa kiểu nguyên thuỷ |
| **Phương thức** | `build(contract_draft: ContractDraft, template: TemplateVersion) -> RenderContext` |
| **8 bước** | Nạp bên → dựng cây → **làm phẳng nếu 1 bên** → biến hệ thống → biến bổ sung → định dạng theo kiểu → **bọc `StyledValue`** → **áp `suppressed_variables`** |
| **Tiền điều kiện** | Mọi bên đã có chủ thể; KEK đã nạp được |
| **Hậu điều kiện** | ⭐ Ngữ cảnh **chỉ chứa** `str`, `int`, `float`, `bool`, `list`, `dict`, `StyledValue`. **KHÔNG có đối tượng ORM, KHÔNG `Settings`, KHÔNG `docxtpl.RichText`, KHÔNG bất kỳ đối tượng nào có phương thức** |
| **Bất biến** | ⭐ Giá trị `None` **luôn** thành chuỗi rỗng — không bao giờ thành `"None"` hay `"null"` |
| **Bất biến** | Với mẫu 1 bên, cả `full_name` và `holder.full_name` đều tồn tại và bằng nhau |
| **Bất biến** | Biến trong `template.suppressed_variables` luôn là chuỗi rỗng |
| **Không được làm** | ❌ Import `docxtpl` · ❌ Đưa đối tượng có phương thức vào ngữ cảnh (**phòng thủ SSTI lớp cuối**) |

---

## 12.10. `DocxContextAdapter` (Infrastructure)

| Mục | Nội dung |
|---|---|
| **Tầng** | ⭐ **Infrastructure** |
| **Trách nhiệm** | Chuyển `StyledValue` → `docxtpl.RichText` ngay trước khi render |
| **Phương thức** | `adapt(context: RenderContext) -> dict[str, Any]` |
| **Tiền điều kiện** | `context` chỉ chứa kiểu nguyên thuỷ và `StyledValue` |
| **Hậu điều kiện** | Mọi `StyledValue` đã thành `RichText` với thuộc tính tương ứng (`bold`, `italic`, `underline`, `color`, `size`, `font`) |
| **Bất biến** | Duyệt đệ quy qua `dict` và `list` — không bỏ sót `StyledValue` lồng sâu |
| **Vì sao tồn tại** | ⭐ Giữ tầng Application không phụ thuộc `docxtpl` (P-02). Đổi sang thư viện render khác chỉ cần đổi adapter |

---

## 12.11. `DocxRenderer`

| Mục | Nội dung |
|---|---|
| **Tầng** | Infrastructure |
| **Phương thức** | `render(template_path: Path, context: dict, output_path: Path) -> RenderResult` |
| **Tiền điều kiện** | File mẫu tồn tại · SHA-256 khớp CSDL · thư mục đích ghi được · còn ≥ 100 MB đĩa |
| **Hậu điều kiện** | File tại `output_path` tồn tại, mở được bằng `python-docx`, SHA-256 khớp `RenderResult.sha256` |
| **Bất biến** | ⭐ Mẫu *write-temp → verify → rename*. **Không bao giờ tồn tại file `.docx` dở dang ở đường dẫn đích** |
| **Môi trường Jinja2** | ⭐ `SandboxedEnvironment` · danh sách trắng 10 bộ lọc · `undefined` trả chuỗi rỗng · timeout 10s · giới hạn 1000 vòng lặp |
| **Ném ra** | `TemplateNotFoundError` · `TemplateChecksumMismatchError` · `RenderError` · `InsufficientStorageError` |
| **Luồng** | ⭐ Chạy trong `run_in_executor` — CPU-bound, không chặn event loop |
| **Đầu ra** | `RenderResult{ output_path, sha256, size_bytes, duration_ms }` |

---

## 12.12. `PdfConverter` & `LibreOfficeManager`

### `IPdfConverter`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) · hiện thực `LibreOfficePdfConverter` |
| **Phương thức** | `convert(docx_path: Path, output_dir: Path, timeout_sec: int) -> PdfResult` |
| **Tiền điều kiện** | `soffice` tồn tại tại đường dẫn cấu hình; DOCX hợp lệ |
| **Hậu điều kiện** | PDF tại `output_dir`, 5 byte đầu là `%PDF-`, số trang > 0 |
| **Bất biến** | ⭐ Timeout **luôn** dẫn tới kill **cây tiến trình** — không để lại `soffice` mồ côi |
| **Bất biến** | Mỗi lần chạy dùng `-env:UserInstallation` trỏ hồ sơ riêng |
| **Ném ra** | `LibreOfficeUnavailableError` · `PdfConversionTimeoutError` · `InvalidPdfOutputError` |
| **Retry** | ⭐ **Không tự retry** — việc retry do `JobRunner` quyết định (tối đa 3 lần, backoff 5s/25s/125s) |
| **Đầu ra** | `PdfResult{ output_path, sha256, size_bytes, page_count, duration_ms, generator_version }` |

### `LibreOfficeManager` (vòng đời listener)

| Mục | Nội dung |
|---|---|
| **Tầng** | Infrastructure |
| **Phương thức** | `ensure_started() -> bool` · `shutdown() -> None` · `restart() -> None` · `is_alive() -> bool` |
| **Bất biến** | ⭐ **Khởi động LƯỜI** — chỉ bật khi `ensure_started()` được gọi (từ bước 1 wizard hoặc lúc convert) |
| **Bất biến** | ⭐ **Tự tắt sau `document.libreoffice_idle_shutdown_min` phút** không dùng (mặc định 20) |
| **Bất biến** | Khi ứng dụng thoát, kill toàn bộ PID `soffice` do mình tạo |
| **Đo lường** | Ghi log thời điểm bật/tắt để chẩn đoán |

---

## 12.13. `EncryptedFileVault`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port `IFileStorage`) · hiện thực `EncryptedFileVault` |
| **Phương thức** | `save(data: bytes, category: VaultCategory) -> VaultRef` · `load(ref: VaultRef) -> bytes` · `delete(ref: VaultRef) -> None` · `exists(ref) -> bool` |
| **Tiền điều kiện** | Khoá Vault đã nạp từ DPAPI |
| **Hậu điều kiện** | `VaultRef.relative_path` có dạng `{category}/{yyyy}/{mm}/{dd}/{uuid}.enc` |
| **Bất biến** | ⭐ Tên file **luôn** là UUID — không bao giờ chứa dữ liệu do người dùng kiểm soát |
| **Bất biến** | ⭐ `load()` **luôn** chuẩn hoá đường dẫn (`Path.resolve()`) và kiểm tra nằm trong gốc Vault bằng `is_relative_to()`. Ngoài → `PathTraversalError` |
| **Bất biến** | Ghi luôn theo mẫu *write-temp → rename* |
| **Ném ra** | `PathTraversalError` · `VaultFileNotFoundError` · `DecryptionError` · `InsufficientStorageError` |
| **Không được làm** | ❌ Nhận đường dẫn tuyệt đối từ tham số · ❌ Trả về đường dẫn tuyệt đối cho tầng trên |

---

## 12.14. `IReadRepository<T>` / `IWriteRepository<T>` / `IUnitOfWork`

### `IReadRepository<T>`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) |
| **Phương thức** | `get(id) -> T \| None` · `list(spec: Specification) -> Page[T]` · `exists(spec) -> bool` |
| **Hậu điều kiện** | ⭐ **Luôn trả về Domain Entity, không bao giờ trả về ORM model** |
| **Bất biến** | Giải mã PII xảy ra **trong** repository — tầng trên không biết dữ liệu từng được mã hoá |

### `IWriteRepository<T>`

| Mục | Nội dung |
|---|---|
| **Phương thức** | `add(entity) -> None` · `update(entity, expected_version: int \| None) -> None` |
| **Bất biến** | ⭐ Dịch ngoại lệ hạ tầng sang Domain: `IntegrityError` → `DuplicateEntityError`, `OperationalError` → `DatabaseUnavailableError` |
| **Bất biến** | `expected_version` chỉ được truyền cho thực thể implement `IVersionedEntity` (v1.0: chỉ `Contract`) |
| **Không được làm** | ❌ Để `IntegrityError` của psycopg rò lên Use Case |

> ⭐ **Vì sao tách đôi (ISP):** `IActivityLogRepository` = `IReadRepository` + `append()` — **không có `update`**, vì bảng `activity_log` cấm UPDATE ở tầng ứng dụng.

### `IUnitOfWork`

| Mục | Nội dung |
|---|---|
| **Phương thức** | `__aenter__` / `__aexit__` · `commit()` · `rollback()` · thuộc tính truy cập từng repository |
| **Bất biến** | ⭐ Thoát khối `async with` mà chưa `commit()` → **tự động rollback** |
| **Bất biến** | Một Use Case = một UoW = một transaction |
| **Bất biến** | ⭐ Thao tác file **không nằm trong** transaction: *ghi tạm → commit → rename* |

---

## 12.15. `JobRunner`

| Mục | Nội dung |
|---|---|
| **Tầng** | Infrastructure (hiện thực Port `IJobQueue`) |
| **Phương thức** | `enqueue(job_type, target, payload, priority) -> JobId` · `cancel(job_id) -> bool` · `get_status(job_id) -> JobStatus` · `start()` · `stop(graceful_timeout)` |
| ⭐ **Nguồn job** | **Bảng `job` LÀ hàng đợi duy nhất.** `enqueue()` chỉ thực hiện `INSERT` — **không có `asyncio.Queue`** |
| ⭐ **Vòng lặp** | Mỗi 500 ms: `SELECT … FROM job WHERE status='QUEUED' ORDER BY priority, created_at FOR UPDATE SKIP LOCKED LIMIT 1` |
| **Đồng thời** | ⭐ **1** — máy đơn, một người dùng |
| **Bất biến** | Cập nhật `heartbeat_at` mỗi 10 giây khi đang chạy |
| **Bất biến** | ⭐ Ngoại lệ trong handler **không bao giờ** làm chết worker — được bắt, ghi vào `job.error_detail`, chuyển `FAILED` |
| **Phục hồi** | Lúc khởi động: job `RUNNING` với `heartbeat_at` cũ hơn 5 phút → `FAILED` với `STALE_JOB_RECOVERED` |
| **Retry** | Backoff luỹ thừa 5s/25s/125s, tối đa 3 lần, ⭐ **chỉ với lỗi `is_retryable_error = true`** |
| **Độ trễ** | Nhận job ≤ 500 ms — không đáng kể so với OCR 4s và PDF 3s |

---

## 12.16. `BackupService`

| Mục | Nội dung |
|---|---|
| **Tầng** | Application + Infrastructure |
| **Phương thức** | `create(target_dir, passphrase, trigger) -> BackupResult` · `verify(file_path, passphrase) -> VerifyResult` · `restore(file_path, passphrase) -> RestoreResult` |
| **Nội dung backup** | `manifest.json` · `kek.wrapped` · `database.dump` (pg_dump custom) · `vault/` · `templates/` |
| **Mã hoá** | `Argon2id(passphrase, salt)` với `time_cost=4, memory_cost=131072` → AES-256-GCM toàn file |
| **Bất biến** | ⭐ `restore()` **luôn** tạo backup hiện trạng trước (`trigger = PRE_RESTORE`) |
| **Bất biến** | ⭐ Từ chối khôi phục nếu `schema_version` trong backup **mới hơn** ứng dụng → `COCAS-8008` |
| **Bất biến** | ⭐ KEK trong backup được bọc bằng khoá dẫn từ passphrase, **không** bằng DPAPI — để khôi phục được trên máy khác |
| **Ném ra** | `WrongPassphraseError` · `CorruptedBackupError` · `SchemaVersionMismatchError` · `InsufficientStorageError` |

---

## 12.17. `CryptoService` & `BlindIndex`

### `ICryptoService`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) · hiện thực `DpapiCryptoService` |
| **Phương thức** | `encrypt(plaintext: bytes, aad: AadContext) -> bytes` · `decrypt(ciphertext: bytes, aad: AadContext) -> bytes` · `blind_index(value: str, field: BidxField) -> bytes` |
| **Tiền điều kiện** | KEK đã nạp từ DPAPI lúc khởi động |
| **Hậu điều kiện** | Định dạng ô: `version(1) ‖ nonce(12) ‖ ciphertext ‖ tag(16)` |
| **Bất biến** | ⭐ Nonce ngẫu nhiên **mỗi lần** mã hoá — không bao giờ tái sử dụng |
| **Bất biến** | ⭐ AAD = `entity_id ‖ table_name ‖ column_name` — chống tấn công hoán vị ô |
| **Bất biến** | `blind_index` = `HMAC-SHA256(PEPPER, field_name ‖ normalize(value))[0:16]` — tất định. ⭐ Trộn `field_name` vào thông điệp (sửa 2026-08-09) để chống đụng độ chéo cột/chéo bảng khi hai trường khác nhau tình cờ cùng chuỗi giá trị đã chuẩn hoá — xem docs/design/04-co-so-du-lieu.md §4.8.4 |
| **Ném ra** | `DecryptionError` (khi tag không khớp) · `KeyUnavailableError` |
| **Không được làm** | ❌ Ghi khoá vào log · ❌ Trả khoá qua API · ❌ Lưu khoá ra đĩa dạng rõ |

---

## 12.18. `ExportNameGenerator`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain Service |
| **Trách nhiệm** | Sinh tên file xuất an toàn trên Windows |
| **Phương thức** | `generate(pattern: str, context: dict, existing_names: set[str]) -> str` |
| **Tiền điều kiện** | `pattern` không rỗng |
| **Hậu điều kiện** | ⭐ Kết quả là tên file **hợp lệ trên Windows**: không chứa `\ / : * ? " < > \|`, không phải tên dành riêng, ≤ 180 ký tự, không trùng trong `existing_names` |
| **Bất biến** | ⭐ Giữ nguyên dấu tiếng Việt trừ khi `export.strip_diacritics = true` |
| **Bất biến** | Trùng tên → thêm hậu tố ` (2)`, ` (3)`… theo kiểu Windows |
| **Test bắt buộc** | Property test: với **mọi** họ tên đầu vào, kết quả luôn là tên file hợp lệ trên Windows |

---

## 12.19. Bảng tra cứu nhanh — 18 Port

| # | Port | Tầng hiện thực | Hiện thực chính |
|---|---|---|---|
| 1 | `IOcrEngine` | Infrastructure | `PaddleOcrAdapter` · `TesseractAdapter` · `NullOcrAdapter` |
| 2 | `IRegionRecognizer` | Infrastructure | *(kế thừa bởi `IOcrEngine`)* |
| 3 | `IImagePreprocessor` | Infrastructure | `OpenCvPreprocessor` |
| 4 | `ICardSideClassifier` | Infrastructure | `HeuristicSideClassifier` |
| 5 | `IQrDecoder` | Infrastructure | `OpenCvQrDecoder` |
| 6 | `IMrzReader` | Infrastructure | `Td1MrzReader` |
| 7 | `IFieldExtractor` | Infrastructure | `ZoneAndAnchorExtractor` |
| 8 | `IReadRepository<T>` | Infrastructure | `SqlAlchemy*ReadRepository` |
| 9 | `IWriteRepository<T>` | Infrastructure | `SqlAlchemy*WriteRepository` |
| 10 | `IAliasRepository` | Infrastructure | `SqlAlchemyAliasRepository` (có cache) |
| 11 | `IFileStorage` | Infrastructure | `EncryptedFileVault` · `PlainFileVault` (dev) |
| 12 | `IDocumentRenderer` | Infrastructure | `DocxRenderer` |
| 13 | `IPdfConverter` | Infrastructure | `LibreOfficePdfConverter` · `NullConverter` |
| 14 | `IUnitOfWork` | Infrastructure | `SqlAlchemyUnitOfWork` |
| 15 | `IJobQueue` | Infrastructure | `JobRunner` (polling bảng `job`) |
| 16 | `IClock` | Infrastructure | `SystemClock` · `FrozenClock` (test) |
| 17 | `IIdGenerator` | Infrastructure | `Uuid7Generator` · `SequentialIdGenerator` (test) |
| 18 | `ICryptoService` | Infrastructure | `DpapiCryptoService` · `NullCryptoService` (dev) |

> ⭐ **Mỗi Port phải có ít nhất một hiện thực fake/null dùng trong test.** Đây là tiêu chí nghiệm thu kiến trúc.

---

[← 11 — Cấu trúc & Thư viện](11-cau-truc-va-thu-vien.md) · [Mục lục](README.md) · [Tiếp: 13 — Kiểm thử & Đóng gói →](13-kiem-thu-va-dong-goi.md)
