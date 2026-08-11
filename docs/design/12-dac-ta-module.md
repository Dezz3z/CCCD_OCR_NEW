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
| **Phương thức** | ⭐ `execute(front_image: bytes, back_image: bytes, doc_types: Sequence[DocumentTypeSpec], progress: ProgressCallback, *, profile, known_province_codes, force_full_ocr) -> ExtractionResult` |
| **Tiền điều kiện** | Hai ảnh đã qua kiểm định S1; `doc_types` không rỗng, mọi phần tử `is_active`, phần tử đầu là thế hệ **phiên đã khai báo** |
| **Hậu điều kiện** | `ExtractionResult` luôn có đủ 6 khoá trong `fields` (giá trị có thể `None`); `channel_summary` phản ánh đúng nguồn thắng cuộc; `validation_report` đã chạy đủ 23 quy tắc |
| **Bất biến** | ⭐ **Không bao giờ ném ngoại lệ ra ngoài** — mọi lỗi gói vào `ExtractionResult.error_code` và `status`. Lý do: pipeline chạy trong job nền; ngoại lệ lọt ra sẽ làm chết worker |
| **Bất biến** | `progress` được gọi ít nhất một lần mỗi chặng với `(percent, message_vi)`. ⭐ Callback ném lỗi **không** làm hỏng lần trích xuất đã thành công |
| **Bất biến** | `error_code` khác `None` **khi và chỉ khi** `status is FAILED`; `status` luôn thuộc 5 giá trị pipeline sinh ra được (`COMPLETED`, `COMPLETED_WITH_WARNINGS`, `NEEDS_REUPLOAD`, `NEEDS_MANUAL_ASSIGN`, `FAILED`) — 6 giá trị còn lại của `OcrSessionStatus` thuộc vòng đời phiên, không thuộc pipeline |
| **Xử lý lỗi từng chặng** | Phân loại `SUY_GIẢM` / `CẦN_NGƯỜI_DÙNG` / `CHÍ_MẠNG` — xem [07-module-ocr.md §7.7](07-module-ocr.md) |
| **Không được làm** | ❌ Ghi CSDL (Use Case làm) · ❌ Ghi file · ❌ Biết về HTTP |
| **Đầu ra** | `ExtractionResult{ status, fields{6}, channel_summary, validation_report, diagnostics, overall_confidence, auto_swapped, duration_ms, error_code, card_generation, detected_sides }` |

> ⭐ **Vì sao `doc_types` là danh sách chứ không phải một `doc_type`** (khác bản D2.0 gốc): người dùng **không thể biết** thẻ mình đang cầm thuộc thế hệ nào, mà hai thế hệ đang lưu hành song song và có `zone_map` khác nhau. Truyền một phần tử duy nhất cho đúng hành vi cũ; truyền nhiều thì `IDocumentTypeSelector` (§12.19.1) chọn từ chính chữ S7 đã đọc. Xem §12.3.1.

### ⭐ 12.3.1. Ba đòn bẩy thời gian, và cái nào thực sự trả tiền

Đo 2026-08-11 trên 15 thẻ thật, máy 4 nhân / 4 GB:

| # | Đòn bẩy | Cơ chế | Đo được |
|---|---|---|---|
| 1 | **Tối đa một lượt quét toàn thẻ mỗi ảnh** | Thế hệ suy từ chính `regions` của lượt đó (Port 19), không quét lần hai | Lượt hai từng tốn 28–45 s/ảnh, gấp 5–7 lần lượt đầu chứ không phải gấp đôi |
| 2 | ⭐ **Bỏ hẳn lượt quét của mặt không còn gì để đóng góp** | `_sides_worth_reading` đọc `zone_map` để biết mặt nào in trường nào, rồi so với những gì QR/MRZ đã cho | **1.00 lượt/cặp thay vì 2 — cắt đúng 50% công nhận dạng**, 15/15 thẻ vẫn đủ 6/6 trường |
| 3 | Chuẩn bị hai ảnh song song | `asyncio.gather` cho giải mã/tiền xử lý/QR; mọi thứ chạm bộ nhận dạng bị khoá tuần tự | Nhỏ nhất trong ba. Có mặt vì ngân sách tính theo **cặp** còn mọi phép đo trước tính theo **ảnh** |

⚠️ **Khoá bộ nhận dạng là bắt buộc, không phải thận trọng thừa.** Hai lượt PaddleOCR đồng thời trên máy 4 GB sinh `Insufficient memory` **từ trong OpenCV** — nó hiện ra như lỗi giải mã ảnh, không phải như hết bộ nhớ.

⚠️ **Mọi lời gọi Port đi qua `asyncio.to_thread`, và thứ tự lượng giá đối số quan trọng.** `PreprocessedImageSet` dựng biến thể **khi truy cập thuộc tính** (§12.4), nên `to_thread(engine.recognize, image_set.v3, …)` sẽ dựng `v3` **trên event loop** rồi mới đưa mảng đã xong cho luồng. Truy cập lười phải nằm *bên trong* luồng.

**Kết quả đo (15 thẻ, một lần chạy):** 6/6 trường trên **15/15** thẻ · 0 ô phải review · độ tin cậy tổng trung bình 0.99 · 0 lỗi validation. **Thời gian: trung bình 9.5 s/cặp, p95 12.4 s/cặp — 🔴 vẫn vượt ngân sách 9 s.** Đòn bẩy 2 đã cắt từ ~15.4 s (2 × 7.7 s/ảnh) xuống 9.5 s; phần còn lại nằm ở bản thân lượt quét.

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

## 12.5. `IssuePlaceNormalizer` — Chuẩn hoá 5 tầng

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain Service |
| **Trách nhiệm** | Đưa chuỗi thô về đúng 1 trong 2 giá trị chuẩn, hoặc `None` |
| **Phương thức** | `normalize(raw: str) -> NormalizationOutcome` |
| **Phụ thuộc** | `alias_repository: IAliasRepository` (nạp `normalization_alias`, có cache) |
| **Tiền điều kiện** | `raw` là chuỗi (có thể rỗng) — ⭐ và là **văn bản của vùng nơi cấp**, không phải văn bản bất kỳ (xem tầng 5) |
| **Hậu điều kiện** | `outcome.value ∈ {"BỘ CÔNG AN", "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI", None}` |
| **Bất biến** | ⭐ **Không tồn tại đường nào trả về giá trị thứ ba.** Đây là bất biến quan trọng nhất của module |
| **Thuật toán** | Tầng 0 tiền chuẩn hoá → Tầng 1 khớp chính xác (bỏ dấu) → Tầng 2 tra alias → ⭐ **Tầng 5 hình dạng (chữ đầu)** → Tầng 3 fuzzy `token_set_ratio` → Tầng 4 từ khoá → `None` |
| **Đầu ra** | `NormalizationOutcome{ value, confidence, tier (0..5), matched_alias_id }` |
| **Bảng confidence** | Tầng 1 → 1.00 · Tầng 2 → theo `alias.assigned_confidence` · ⭐ Tầng 5 → 0.92 (có độ dài từ đầu xác nhận) / 0.85 (chỉ chữ đầu) · Tầng 3 ≥85 → 0.90, 70–85 → 0.65 · Tầng 4 → 0.60 · Không khớp → 0.00 |
| **Test bắt buộc** | ⭐ Property test: với **mọi** chuỗi đầu vào bất kỳ, kết quả luôn thuộc tập 3 giá trị cho phép |

### ⭐ 12.5.1. Tầng 5 — phân biệt bằng chữ đầu (`issue_place_shape.py`)

> Bổ sung 2026-08-11 sau khi đo trên 46 ảnh thật. **Số tầng là nhãn nguồn gốc, không phải thứ tự chạy:** tầng 5 chạy **trước** tầng 3 và 4, giữ số 5 để không phải đánh số lại 4 tầng cũ trong mã nguồn, test và tài liệu.

**Vì sao cần một tầng nữa.** `issue_place` là trường **duy nhất không kênh chính xác nào đọc được** — QR trả 4 trường (`id_number`, `full_name`, `date_of_birth`, `issue_date`), MRZ TD1 trả 3 (`id_number`, `date_of_birth`, `expiry_date`), không kênh nào mang tên cơ quan cấp. Nó phụ thuộc 100% vào OCR, là kênh yếu nhất.

**Ý tưởng.** Trường này là **chọn 1 trong 2**, không phải chuỗi cần đọc. Bốn tầng cũ đều so khớp **toàn bộ** chuỗi với một danh mục cách viết — đúng cho trường mở, sai cho trường đóng: nó khiến câu trả lời phụ thuộc vào việc bộ nhận dạng đọc đúng bao nhiêu phần của một tên cơ quan 23 ký tự, trong khi chỉ cần **phần mở đầu**.

| Giá trị chuẩn | Thẻ in ra | 3 chữ đầu |
|---|---|---|
| `BỘ CÔNG AN` | `BỘ CÔNG AN` (Căn cước 2024) | `BOC` |
| `CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI` | `CỤC TRƯỞNG CỤC CẢNH SÁT…` (CCCD 2021) | `CUC` |

**Đo 2026-08-11 trên 46 ảnh thật (22 ảnh có trường này):**

| Tầng | Đúng | Confidence |
|---|---|---|
| 3 (fuzzy toàn chuỗi) | 13/22 | 0.65 · 1 ca 0.90 |
| 4 (từ khoá) | 1/22 | 0.60 |
| **cả hai đều im lặng — không ra giá trị nào** | **8/22** | — |
| ⭐ **5 (hình dạng)** | **22/22** | **0.92** |

⚠️ **Tầng 3 và 4 không phải hai đường dự phòng độc lập — chúng hỏng cùng một chỗ.** Bộ nhận dạng dính chữ (`CUCTRUONG CUCCANH SAT`), làm giao của `token_set_ratio` rỗng **và đồng thời** làm mất token `CUC` mà tầng 4 đòi có đủ. Một lỗi, hai tầng chết. Tầng 5 chỉ cần chữ đầu, phép dính chữ không đụng tới.

**Hai tín hiệu:**

1. **Chữ đầu** (quyết định) — 3 ký tự đầu, so với phần mở đầu của mỗi giá trị chuẩn cắt cùng độ dài. Bỏ token đầu ngắn hơn 2 ký tự trước khi lấy (`S CUC TRUONG…` — mảnh `S` là nhiễu; `BỘ`/`CỤC` không bao giờ dài 1 ký tự).
2. **Độ dài từ đầu tiên** (xác nhận) — `BỘ` 2 ký tự, `CỤC` 3 ký tự trở lên. Đồng thuận → 0.92; nghịch → 0.85, chữ đầu vẫn thắng.

⚠️ **Tín hiệu "độ dài toàn chuỗi" KHÔNG dùng được, dù trên giấy nó áp đảo.** Hai giá trị chuẩn chênh nhau gần 5 lần (8 ký tự / 38 ký tự). Nhưng trên văn bản **thực sự đến được** hàm này thì khoảng cách biến mất: vùng 2021 chỉ bắt được dòng đầu của tên cơ quan (`CỤC TRƯỞNG CỤC CẢNH SÁT`, 19 ký tự), còn vùng 2024 nuốt luôn dòng tiếng Anh bên dưới (`BO CONGAN MINISTRY OF PUBLIC SECURITY`, 31 ký tự). Đo được: 2021 = 19–20, 2024 = 15 và 31 — **chồng lấn, và ngược chiều**. Độ dài là thuộc tính của **vùng cắt**, không phải của trường.

**Độ chính xác của ngưỡng.** `fuzz.ratio` trên 3 ký tự chỉ trả về được {0, 33.3, 66.7, 100}, nên ngưỡng 80 trên thực tế nghĩa là "chữ đầu khớp chính xác". Giữ dạng ngưỡng thay vì so bằng để `HEAD_LEN` còn chỉnh được. Quét **752 dòng còn lại** của 46 ảnh qua đúng phép thử này: **0 dòng ra phán quyết**. Ca sát nhất là dòng quê quán `Bố Trạch, Quảng Bình` → `BOT` được 66.7 điểm với `BOC` — đây chính là con số mà ngưỡng 80 phải nằm trên.

⚠️ **Tầng 5 cố ý cả tin:** nó giả định văn bản nhận được **là** nơi cấp và chỉ quyết định *cái nào*. Đó là lý do tiền điều kiện của module nói rõ đầu vào phải là văn bản vùng nơi cấp.

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

## 12.6a. `FieldNormalizer` — Chuẩn hoá S9

> Bổ sung khi triển khai P2 tuần 4. §7.2 luôn liệt kê service này (D1) nhưng §12 chưa có ô đặc tả; đánh số `12.6a` thay vì dồn số để không phá mọi tham chiếu `§12.7`–`§12.19` đang có trong mã nguồn.

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain Service |
| **Trách nhiệm** | Đưa mỗi giá trị thô của từng kênh về **một dạng chuẩn duy nhất** để hợp nhất so sánh được |
| **Phương thức** | `normalize(key, text, confidence) -> NormalizedValue` · `normalize_channel(fields, confidence) -> dict[FieldKey, NormalizedValue]` |
| **Phụ thuộc** | `IssuePlaceNormalizer` |
| **Tiền điều kiện** | không có — `text` có thể là `None`, rỗng, hoặc rác |
| **Hậu điều kiện** | `value` là dạng chuẩn của §S9 hoặc `None`; `value is None ⇒ confidence == 0.0` |
| **Bất biến** | ⭐ **Không bao giờ ném ngoại lệ** |
| **Bất biến** | ⭐ Không cho giá trị thô lọt qua khi chuẩn hoá thất bại |
| **Đầu ra** | `NormalizedValue{ value, confidence, flags, tier }` — `tier` chỉ dùng cho `issue_place` (`ocr_field.normalization_tier`) |
| **Cờ** | `DATE_REPAIRED` · `NO_EXPIRY` · `ISSUE_PLACE_UNRECOGNIZED` · `UNPARSEABLE` |
| **Không được làm** | ❌ Quyết định trường nào bắt buộc (Validation) · ❌ Chọn giữa các kênh (Fusion) |

---

## 12.6b. `ConfidenceCalculator` — Quy tắc 7 của Fusion

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain Service |
| **Trách nhiệm** | Từ 6 trường đã hợp nhất tính **một** điểm cho cả thẻ |
| **Phương thức** | `overall(fields) -> float` · `needs_retake(fields) -> bool` |
| **Hậu điều kiện** | `overall ∈ [0, 1]`; trường `value is None` đóng góp **0** |
| **Bất biến** | ⭐ Bảng trọng số cộng lại đúng **1.00** — được `assert` lúc nạp module, không phải tin suông |
| **Dùng ở đâu** | Băng trạng thái ở màn hình xác nhận · ngưỡng `overall < 0.40` của ALT-03 ("chụp lại") |
| **Không được làm** | ❌ Loại trường thiếu khỏi mẫu số — thẻ đọc được đúng 1/6 trường sẽ chấm 1.00 |

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

## 12.8. `TemplateInspector` — ⭐ Port 20 `ITemplateInspector`

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) · hiện thực `DocxTemplateInspector` (Infrastructure) |
| **Trách nhiệm** | Mở file `.docx`, quét biến bằng **AST Jinja2**, đối chiếu từ điển |
| **Phương thức** | `inspect(file_bytes, party_schema, contract_fields=()) -> TemplateInspection` |
| **Tiền điều kiện** | `file_bytes` không rỗng |
| **Hậu điều kiện** | `inspection.status ∈ {VALID, WARNING, INVALID}`; nếu `INVALID` thì `diagnostics` có ít nhất một mục mức ERROR |
| **Bất biến** | ⭐ **Không bao giờ render** trong lúc kiểm tra — chỉ phân tích cú pháp. Render là việc của `DocxRenderer` |
| **Bất biến** | ⭐ Thu thập biến bằng **AST Jinja2**, không dùng regex quét text — xem ngoại lệ đã đo ở §12.8.2 |
| **Ném ra** | `NotADocxFileError` · `TemplateSyntaxError(line, detail)` — **chỉ hai ca này**, xem §12.8.1 |
| **Kiểm tra bảo mật** | ⭐ Chặn bằng **hình dạng AST** (`Getattr` bắt đầu bằng `_`, `Call`, `Include`/`Extends`/`Import`, bộ lọc ngoài danh sách trắng, tên toàn cục Jinja2) → `COCAS-6014`. Blacklist chuỗi là lớp phụ và **chỉ quét thân thẻ Jinja2** (§9.9) |
| **Kiểm tra phạm vi** | ⭐ `party_schema` chỉ dùng tính năng v1.0 (`entity_type=INDIVIDUAL`, `min=max=1`, `collect ⊆ {contact, bank_account}`) → `COCAS-6016` |
| **Đầu ra** | `TemplateInspection{ status, declared[], required[], optional[], unknown[], richtext_vars[], has_loops, has_conditionals, diagnostics[] }` |

> ⭐ **`contract_fields` là tham số thêm ở P3 (mặc định rỗng).** `contract_template.contract_fields` khai biến cấp hợp đồng y như `party_schema[].extra_fields` khai biến cấp bên. Không truyền vào thì mọi biến khai ở đó bị báo `COCAS-6009` "không xác định" — cảnh báo sai trên chính mẫu do người dùng khai đúng. Cả 2 mẫu v1.0 đều có `contract_fields: []` nên mặc định rỗng giữ nguyên hành vi.

### ⭐ 12.8.1. Ranh giới "ném ra" và "trả về"

Bảng §9.3 liệt kê 10 mã chẩn đoán, nhưng **không phải cả 10 đều nằm trong `diagnostics[]`**:

| Nhóm | Mã | Cách báo | Vì sao |
|---|---|---|---|
| **Phân tích bất khả thi** | `COCAS-6002` · `COCAS-6003` | **Ném ngoại lệ** | Không mở được file, hoặc Jinja2 không dựng được AST ⇒ **không có gì để báo cáo**. Trả một `TemplateInspection` rỗng-nhưng-hợp-lệ sẽ khiến bên gọi tưởng đã quét xong và thấy 0 biến |
| **Phân tích được, nhưng phải từ chối** | `COCAS-6014` · `COCAS-6016` | **Trả về**, mức ERROR ⇒ `status = INVALID` | Người dùng vẫn cần thấy danh sách biến bên cạnh lý do từ chối |
| **Cảnh báo** | `6008` `6009` `6010` `6011` `6012` `6015` | **Trả về**, mức WARNING ⇒ `status = WARNING` | Không chặn đăng ký |

Use Case là bên ánh xạ sang HTTP: hai ngoại lệ → `400/422`, `status = INVALID` → `422`.

### ⭐ 12.8.2. Hai thứ AST **không** thấy được — và vì sao đó không phải lách luật

Đã đo trên `docxtpl 0.18.0` (2026-08-11):

1. **`{{r var }}` và `{%p … %}` biến mất trước khi Jinja2 nhìn thấy nguồn.** Chúng **không phải cú pháp Jinja2** — chúng là tiền tố tiền xử lý của docxtpl. `patch_xml()` biến `{{r securities_account_no }}` thành `{{ securities_account_no }}` rồi mới đưa cho bộ phân tích. Đo: cả 3 marker `{{r `, `{{p `, `{%p ` đều **không còn** trong nguồn đã vá.
   - ⇒ `richtext_vars[]`, `COCAS-6008` và `COCAS-6010` **bắt buộc** phải quét văn bản, không thể lấy từ AST. Bất biến "dùng AST, không dùng regex" áp cho **thu thập biến**, không áp cho **nhận diện marker của docxtpl**.
   - Cách quét đã kiểm chứng: **xoá mọi thẻ XML của phần** (`<[^>]+>`) — thao tác này tự nối lại các `run` mà Word chẻ ra — rồi tìm marker trên văn bản thu được. Đo trên `01A_HD_GDKQ.docx` thật: thấy đúng `{{r securities_account_no }}`; `01A_HD_GDN.docx`: 0 marker (đúng, mẫu này không có biến in đậm).
2. **Header và footer là các *part* riêng.** `DocxTemplate.get_xml()` chỉ trả `word/document.xml`. Cả 2 mẫu thật đều có `footer1.xml` (và `01A_HD_GDN.docx` có thêm `header1.xml`). Bỏ qua chúng thì biến đặt trong chân trang không vào `declared[]` ⇒ `COCAS-6011` báo thiếu biến **mà file có dùng**.

### ⭐ 12.8.3. "Số dòng" của `COCAS-6003` là **số thứ tự đoạn văn**

Trong `.docx` không có khái niệm dòng — dòng là do Word ngắt khi hiển thị. Thứ đếm được và người dùng chỉ vào được là **đoạn văn** (`<w:p>`).

Cách lấy: chèn `\n` trước mỗi `<w:p` trong nguồn đã vá (chính thủ thuật `render_xml_part()` của docxtpl dùng), khi đó `TemplateSyntaxError.lineno - 1` **chính là** số thứ tự `<w:p>`. Đo: lỗi đặt ở đoạn 6 → `lineno = 7`. Trích được nguyên văn đoạn đó để ghép vào `detail`.

⚠️ Số này đếm **cả đoạn nằm trong bảng**, nên nó lớn hơn `len(python-docx .paragraphs)` (mẫu `01A_HD_GDKQ.docx`: 273 đoạn so với 16 đoạn cấp cao nhất). Thông điệp phải nói "đoạn văn thứ N (tính cả đoạn trong bảng)".

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

## 12.12. ~~`PdfConverter` & `LibreOfficeManager`~~ — 🗑️ ĐÃ GỠ (D2.1)

> ⭐ **Mục này đã bị gỡ bỏ cùng toàn bộ khâu xuất PDF.** Xem §9.13 để biết lý do đầy đủ.
>
> **Số mục §12.12 được giữ nguyên chỗ trống có chủ ý** — đánh lại số từ §12.13 trở đi sẽ làm sai mọi trích dẫn `§12.1x` đang tồn tại trong mã nguồn, tài liệu khác và lịch sử commit. Cùng lý do đó, **Port số 13 để khuyết** trong bảng §12.19: ⭐ 19 Port, đánh số 1–20.

| Đã gỡ | Thay bằng |
|---|---|
| Port `IPdfConverter` + `PdfResult` | *(không có gì — `IDocumentRenderer` là điểm cuối của chuỗi sinh tài liệu)* |
| `LibreOfficePdfConverter` · `NullConverter` | — |
| `LibreOfficeManager` (vòng đời listener lười) | — |
| `LibreOfficeUnavailableError` · `PdfConversionTimeoutError` · `InvalidPdfOutputError` | — |

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
| **Bất biến** | Một Use Case = một UoW = một transaction — ⚠️ **trừ ngoại lệ dưới đây** |
| **Bất biến** | ⭐ Thao tác file **không nằm trong** transaction: *ghi tạm → commit → rename* |

#### ⭐ 12.14.1. Ngoại lệ: Use Case có công việc dài chạy ở giữa

`ProcessOcrSessionUseCase` (P3 module 2) dùng **hai transaction ngắn kẹp lấy lượt OCR**, không phải một. Đây là ngoại lệ được ghi nhận, không phải vi phạm bị bỏ sót.

| | |
|---|---|
| **Transaction 1** | Nạp `ocr_session` → chuyển `PROCESSING` → commit |
| **(ngoài transaction)** | Chạy `ExtractionPipeline` — đo được **~9.5 s/cặp** (§7.4.6) |
| **Transaction 2** | Ghi `ocr_result` + 6 `ocr_field` → cập nhật `ocr_session` → commit |

**Vì sao không gộp làm một:**

1. Một transaction bao trọn 9.5 giây sẽ **giữ một kết nối trong pool suốt 9.5 giây mà không dùng đến nó**. Với 1 worker Uvicorn và JobRunner polling bảng `job` mỗi 500 ms, đó chính là pool kết nối.
2. Sự cố giữa chừng sẽ **rollback cả trạng thái `PROCESSING`**: phiên quay về `QUEUED`, endpoint tiến độ (§5.3.5) báo "chưa bắt đầu" trong khi log của worker đã chết nói ngược lại.

⚠️ **Cái giá phải trả, nói rõ ra:** sự cố **giữa hai transaction** để lại phiên `PROCESSING` vĩnh viễn. Đó đúng là việc của cơ chế phục hồi job treo (§12.15), và mọi công việc chạy dài trong hệ thống đều trả cái giá này.

> **Quy tắc chung rút ra:** một Use Case được phép nhiều hơn một transaction **khi và chỉ khi** giữa chúng là công việc ngoài cơ sở dữ liệu tính bằng giây. Nhiều transaction vì "cho gọn code" thì không.

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
| **Độ trễ** | Nhận job ≤ 500 ms — không đáng kể so với OCR 4s |

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

## 12.19. Bảng tra cứu nhanh — ⭐ 19 Port *(đánh số 1–20, khuyết 13)*

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
| ~~13~~ | 🗑️ ~~`IPdfConverter`~~ | — | **Đã gỡ ở D2.1** (§12.12) — số thứ tự để khuyết có chủ ý |
| 14 | `IUnitOfWork` | Infrastructure | `SqlAlchemyUnitOfWork` |
| 15 | `IJobQueue` | Infrastructure | `JobRunner` (polling bảng `job`) |
| 16 | `IClock` | Infrastructure | `SystemClock` · `FrozenClock` (test) |
| 17 | `IIdGenerator` | Infrastructure | `Uuid7Generator` · `SequentialIdGenerator` (test) |
| 18 | `ICryptoService` | Infrastructure | `DpapiCryptoService` · `NullCryptoService` (dev) |
| ⭐ 19 | `IDocumentTypeSelector` | Infrastructure | `MarkerDocumentTypeSelector` |
| ⭐ 20 | `ITemplateInspector` | Infrastructure | `DocxTemplateInspector` |

> ⭐ **Mỗi Port phải có ít nhất một hiện thực fake/null dùng trong test.** Đây là tiêu chí nghiệm thu kiến trúc.

### ⭐ 12.19.1. Vì sao có Port thứ 19 (thêm ở P3)

`ExtractionPipeline` phải trả lời một câu hỏi mà không module nào trước đó gặp: **thẻ này thuộc thế hệ nào?** Không thể hỏi người dùng — cả hai thế hệ đang lưu hành, và một phiên khai báo nhầm sẽ trích **mọi trường qua sai `zone_map`**, tức là sinh ra giá trị sai đầy tự tin, đúng thứ §7.9 chặn phát hành.

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) · hiện thực `MarkerDocumentTypeSelector` (Infrastructure) |
| **Phương thức** | `select(regions: list[TextRegion], candidates: Sequence[DocumentTypeSpec]) -> DocumentTypeSpec \| None` |
| **Tiền điều kiện** | `regions` là kết quả **đã có sẵn** của S7 |
| **Bất biến** | ⭐ **Không bao giờ nhận dạng lại.** Một lượt quét thêm đắt hơn toàn bộ các chặng còn lại cộng lại (§7.4.6 phát hiện 20) |
| **Bất biến** | Hoà phiếu ⇒ trả `None`, người gọi giữ nguyên thế hệ đã khai báo. Phá hoà bằng thứ tự danh sách sẽ biến "không có bằng chứng" thành một lá phiếu ngầm |
| **Dữ liệu** | `document_type.identity_markers` — cụm từ **chỉ một thế hệ in**. ⚠️ **Không** dùng `anchor_patterns`: hai thế hệ dùng chung phần lớn nhãn (`Full name`, `Date of birth`, `BỘ CÔNG AN`), và `Ngày, tháng, năm` (2021) là tiền tố của `Ngày, tháng, năm sinh` (2024) — đúng bẫy tiền tố chung ở ràng buộc 7. Đếm nhãn khớp là đo **ảnh rõ tới đâu**, không phải đo thế hệ |
| **Ngưỡng** | 85, không phải 75 của anchor trường |
| **Đo thật** | 2026-08-11, 46 ảnh: **43/44 quyết định đúng · 0 sai · 1 từ chối trả lời** |

⚠️ **Điểm mù đã biết:** ca duy nhất từ chối là một **mặt sau Căn cước 2024** mà chữ in bị nhoè. Tín hiệu **cấu trúc** (một ảnh mang cả QR lẫn MRZ thì chỉ có thể là mặt sau 2024) sẽ quyết định được ca đó, nhưng Port 19 chỉ nhận `regions` nên không thấy tín hiệu này. Muốn vá thì phải thêm dữ liệu "thế hệ này in QR ở mặt nào" vào `document_type` — hoãn có chủ đích (P-10) cho tới khi Golden Set cho thấy tỉ lệ này đáng kể.

### ⭐ 12.19.2. Vì sao có Port thứ 20 (thêm ở P3)

`TemplateInspector` từng được xếp thuần Infrastructure (§12.8 bản D2.0) vì không ai gọi nó từ tầng trên. Đến khi hiện thực thì có **ba** Use Case gọi thẳng vào nó — `RegisterTemplateUseCase`, `ValidateTemplateUseCase`, `AddTemplateVersionUseCase` (§1 danh sách Use Case) — và hợp đồng import-linter cấm `cocas.application` import `docxtpl`. Không có Port thì hoặc tầng Application phải import thư viện render, hoặc **quyết định từ chối mẫu phải chuyển lên tầng Presentation** — tức là đưa luật nghiệp vụ ra khỏi chỗ của nó.

| Mục | Nội dung |
|---|---|
| **Tầng** | Domain (Port) · hiện thực `DocxTemplateInspector` (Infrastructure) |
| **Kiểu trả về** | `TemplateInspection` + `TemplateDiagnostic` — **từ vựng Domain**, không phải DTO Application (cùng lý do với `OcrResultSnapshot`, §12.14) |
| **Fake bắt buộc** | `FakeTemplateInspector` — trả kết quả dựng sẵn, không mở file |

⭐ **Số 13 vẫn để khuyết.** Port mới lấy số **20**, không lấp vào chỗ `IPdfConverter` đã gỡ: tái dùng số cũ sẽ khiến mọi trích dẫn "Port 13" trong lịch sử commit trỏ sang một thứ hoàn toàn khác. 19 Port, đánh số 1–20.

---

[← 11 — Cấu trúc & Thư viện](11-cau-truc-va-thu-vien.md) · [Mục lục](README.md) · [Tiếp: 13 — Kiểm thử & Đóng gói →](13-kiem-thu-va-dong-goi.md)
