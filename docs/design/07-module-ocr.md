# 07 — Thiết kế module OCR

[← Mục lục](README.md)

**Pipeline 3 kênh QR / MRZ / OCR · PaddleOCR PP-OCRv4 · Hoàn toàn offline**

---

## 7.1. Tuyên bố kiến trúc

Module OCR là phần **có giá trị kỹ thuật cao nhất** và cũng **dễ lỗi thời nhất**. Nó được thiết kế quanh một mệnh đề duy nhất:

> **Trích xuất thông tin từ CCCD không phải bài toán OCR. Đó là bài toán hợp nhất nhiều nguồn bằng chứng, trong đó OCR là nguồn kém tin cậy nhất.**

| Hạng | Nguồn | Bản chất | Độ chính xác | Trường phủ được |
|---|---|---|---|---|
| **A** | **Mã QR** (mặt trước) | Dữ liệu số hoá trực tiếp từ CSDL dân cư — *không phải nhận dạng ảnh* | **100%** khi giải mã được | Họ tên, số CCCD, ngày sinh, giới tính, địa chỉ, ngày cấp |
| **B** | **Vùng MRZ** (mặt sau) | Chuỗi ICAO 9303 TD1, **có ký tự kiểm tra tự xác thực** | **98%** khi checksum hợp lệ | Số CCCD, ngày sinh, **ngày hết hạn**, giới tính |
| **C** | **OCR văn bản** | Nhận dạng ảnh — có thể sai | 85–95% | Tất cả, đặc biệt **nơi cấp** (nguồn duy nhất) |

**Hệ quả:** với ảnh CCCD chụp bình thường, hệ thống đạt **5/6 trường chính xác tuyệt đối** trước khi OCR nói được câu nào. OCR chỉ phải lo "Nơi cấp" — mà trường này chỉ có 2 giá trị hợp lệ, nên chuẩn hoá mờ gần như luôn đúng.

⭐ **Đây là lý do NFR-01 (≥99%) khả thi mà không cần cloud AI.**

---

## 7.2. Sơ đồ thành phần

```mermaid
graph TB
    subgraph PORTS["🟢 DOMAIN — PORTS (interface thuần)"]
        P1["IImagePreprocessor"]
        P2["ICardSideClassifier"]
        P3["IQrDecoder"]
        P4["IMrzReader"]
        P5["IRegionRecognizer"]
        P5b["IOcrEngine<br/>(kế thừa IRegionRecognizer)"]
        P6["IFieldExtractor"]
    end

    subgraph DOMSVC["🟢 DOMAIN — SERVICES (logic thuần, không I/O)"]
        D1["FieldNormalizer"]
        D2["IssuePlaceNormalizer<br/>4 tầng khớp"]
        D3["FieldFusionService<br/>8 quy tắc hợp nhất"]
        D4["ConfidenceCalculator"]
        D5["CardValidityPolicy"]
    end

    subgraph ORCH["🟣 APPLICATION"]
        O1["<b>ExtractionPipeline</b><br/>điều phối 9 chặng<br/>KHÔNG BAO GIỜ ném ngoại lệ ra ngoài"]
        O2["RunOcrUseCase"]
    end

    subgraph ADAPTERS["🟠 INFRASTRUCTURE — ADAPTERS (thay thế được)"]
        A1["OpenCvPreprocessor<br/>biến thể TẠO LƯỜI"]
        A2["HeuristicSideClassifier"]
        A3["OpenCvQrDecoder<br/>+ PyzbarFallback · 3 lần thử"]
        A4["Td1MrzReader<br/>post-filter charset"]
        A5["<b>PaddleOcrAdapter</b>"]
        A5b["TesseractAdapter (dự phòng)"]
        A5c["NullOcrAdapter (khi engine chết)"]
        A6["ZoneAndAnchorExtractor"]
    end

    subgraph DATA["📦 DỮ LIỆU CẤU HÌNH (trong CSDL, sửa qua UI)"]
        C1["document_type.zone_map"]
        C2["document_type.anchor_patterns"]
        C3["normalization_alias"]
        C4["system_setting.ocr.* / preproc.*"]
    end

    O2 --> O1
    O1 --> P1 & P2 & P3 & P4 & P5b & P6
    O1 --> D1 & D3
    D1 --> D2
    D3 --> D4 & D5
    P4 --> P5

    A1 -.->|implements| P1
    A2 -.->|implements| P2
    A3 -.->|implements| P3
    A4 -.->|implements| P4
    A5 & A5b & A5c -.->|implements| P5b
    A6 -.->|implements| P6

    C1 & C2 --> A6
    C3 --> D2
    C4 --> O1

    style PORTS fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style DOMSVC fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style ORCH fill:#f3e5f5,stroke:#6a1b9a
    style ADAPTERS fill:#ffe0b2,stroke:#ef6c00
    style DATA fill:#fff9c4,stroke:#f57f17
    style A5 fill:#ff9800,color:#fff
```

---

## 7.3. Đặc tả Port

### `IImagePreprocessor`

| Mục | Nội dung |
|---|---|
| **Trách nhiệm** | Biến ảnh thô thành **tập biến thể** tối ưu cho từng kênh |
| **Đầu vào** | `image_bytes: bytes` · `exif_orientation: int \| None` · `profile: PreprocessProfile` |
| **Đầu ra** | `PreprocessedImageSet` — truy cập biến thể **theo yêu cầu (lazy)** qua `.v0 .v1 .v2 .v3 .v4` · `transform_matrix` · `warp_succeeded: bool` · `quality: ImageQuality` |
| **Ném ra** | `ImageDecodeError`, `ImageTooSmallError` |
| **Bất biến** | Không bao giờ sửa `v0`. Mọi biến thể giữ được ma trận biến đổi để ánh xạ ngược `bbox` về ảnh gốc |
| **Bất biến** | ⭐ Biến thể **chỉ được tạo khi truy cập lần đầu**, sau đó cache trong phạm vi đối tượng |
| **Không được làm** | Ghi file · truy cập CSDL · phụ thuộc cấu hình toàn cục |

### `ICardSideClassifier`

| Mục | Nội dung |
|---|---|
| **Trách nhiệm** | Quyết định ảnh nào là mặt trước, ảnh nào là mặt sau |
| **Đầu vào** | `image_a`, `image_b: PreprocessedImageSet` · `doc_type: DocumentTypeSpec` |
| **Đầu ra** | `SideClassification` — `front_index`, `back_index`, `confidence_a`, `confidence_b`, `swapped: bool`, `verdict: RESOLVED \| DUPLICATE_SIDE \| AMBIGUOUS`, `signals: dict` |
| **Bất biến** | Không bao giờ trả `verdict=RESOLVED` khi cả hai ảnh có `confidence < 0.60` |

### `IQrDecoder`

| Mục | Nội dung |
|---|---|
| **Trách nhiệm** | Tìm và giải mã QR, phân tách thành các trường |
| **Đầu vào** | `image_set: PreprocessedImageSet` |
| **Đầu ra** | `QrExtractionResult` — `available: bool`, `raw_payload: str \| None`, `fields: dict[FieldKey, str]`, `layout_recognized: bool`, `attempts: int` |
| **Ném ra** | ⭐ **Không ném** — QR thất bại là **bình thường**, trả `available=False` |
| **Bất biến** | Bố cục payload không khớp mẫu → `layout_recognized=False`, `fields={}`, ghi log cảnh báo với payload **đã che PII**. Thiết kế chống vỡ khi phôi thẻ thay đổi |

### `IRegionRecognizer` ⭐ Port hẹp

| Mục | Nội dung |
|---|---|
| **Trách nhiệm** | Nhận dạng văn bản trong **một vùng** của ảnh |
| **Phương thức** | `recognize_region(image, bbox, charset_hint) -> TextRegion \| None` |
| **Vì sao tách riêng** | `MrzReader` chỉ cần phương thức này — không nên phụ thuộc toàn bộ `IOcrEngine` (nguyên tắc ISP) |

### `IOcrEngine` ⭐ Port quan trọng nhất — điểm thay thế engine

| Mục | Nội dung |
|---|---|
| **Kế thừa** | `IRegionRecognizer` |
| **Trách nhiệm** | Nhận dạng văn bản trong ảnh. **Chỉ vậy** |
| **Phương thức 1** | `recognize(image, options) -> list[TextRegion]` |
| **Phương thức 2** | *(kế thừa)* `recognize_region(image, bbox, charset_hint) -> TextRegion \| None` |
| **Phương thức 3** | `warm_up() -> None` — nạp model |
| **Phương thức 4** | `get_info() -> EngineInfo` |
| **Tiền điều kiện** | `image` giải mã được, cạnh ngắn ≥ 320 px; `warm_up()` đã gọi thành công |
| **Hậu điều kiện** | Mọi `TextRegion.text` chuẩn hoá Unicode **NFC**; `bbox` là toạ độ **tương đối 0..1**; danh sách sắp xếp theo thứ tự đọc |
| **Bất biến** | ⭐ Không bao giờ trả `None` từ `recognize()` — không nhận được gì thì trả **danh sách rỗng** |
| **Ném ra** | `OcrEngineUnavailableError`, `OcrTimeoutError`, `ImageDecodeError` |
| **Không được làm** | ❌ Biết khái niệm "họ tên", "số CCCD", "nơi cấp" · ❌ Ghi file · ❌ Truy cập CSDL · ❌ Đọc cấu hình toàn cục |

**Kiểu dữ liệu:**

| Kiểu | Trường |
|---|---|
| `TextRegion` | `bbox: RelativeBox` · `text: str` · `confidence: float (0..1)` |
| `RelativeBox` | `x, y, w, h: float (0..1)` |
| `OcrOptions` | `use_angle_cls: bool` · `charset_hint: str \| None` · `min_confidence: float` |
| `EngineInfo` | `name` · `version` · `languages: list[str]` · `is_ready: bool` · `model_path: str` |

> ⭐ **Chính ranh giới này làm việc thay engine trở nên tầm thường.** `IOcrEngine` chỉ nhận ảnh, trả text + vị trí. Đổi PaddleOCR sang bất cứ gì cũng chỉ cần thoả 4 phương thức.

### `IFieldExtractor`

| Mục | Nội dung |
|---|---|
| **Trách nhiệm** | Ánh xạ `list[TextRegion]` → 6 trường nghiệp vụ |
| **Đầu vào** | `regions: list[TextRegion]` · `side: CardSide` · `doc_type: DocumentTypeSpec` · `warp_succeeded: bool` |
| **Đầu ra** | `dict[FieldKey, RawFieldValue]` với `RawFieldValue = {text, confidence, bbox, strategy}` |
| **Chiến lược** | `ZONE` (khi `warp_succeeded`) hoặc `ANCHOR`. Chạy **cả hai**, chọn kết quả có confidence cao hơn cho mỗi trường |

---

## 7.4. Đặc tả thành phần Infrastructure

### 7.4.1. `OpenCvPreprocessor` — 9 phép biến đổi

| # | Phép | Kỹ thuật cụ thể | Cấu hình | Rủi ro & cách giảm |
|---|---|---|---|---|
| 1 | Sửa hướng EXIF | Áp `Orientation` 1–8 đã lưu ở S1 | `preproc.exif_transpose` | Ảnh scan không có EXIF → bỏ qua, không lỗi |
| 2 | Giới hạn kích thước | Resize cạnh dài → 1600px. `INTER_AREA` khi thu nhỏ, `INTER_CUBIC` khi phóng | `preproc.target_long_edge` | 1600px là điểm cân bằng: dưới 1200 mất chi tiết, trên 2000 chậm gấp đôi không lợi |
| 3 | Nắn phối cảnh | Contour → lọc theo diện tích + tỉ lệ ≈1.585 → `approxPolyDP` 4 đỉnh → `getPerspectiveTransform` → khung chuẩn 1012×638 | `preproc.perspective.*` | ⭐ Tìm nhầm contour (bàn, giấy nền) sẽ cắt sai. **Bảo vệ:** tỉ lệ ∈ [1.45, 1.72] và diện tích ≥ 25% ảnh; thất bại → `warp_succeeded=False`, giữ ảnh gốc |
| 4 | Phát hiện lộn ngược 180° | 3 tín hiệu bỏ phiếu: `cls` model PaddleOCR · số vùng text đọc được ở 0° vs 180° · vị trí chân dung / MRZ | `preproc.orientation.strategy` | Ba tín hiệu ít khi cùng sai |
| 5 | Khử nghiêng | Hough Line trên cạnh ngang chủ đạo → góc trung vị → `warpAffine`. Giới hạn ±15° | `preproc.deskew.max_angle` | Xoay quá lớn làm mất góc → giới hạn góc |
| 6 | Khử nhiễu | `bilateralFilter` (nhanh, giữ cạnh — **mặc định**) hoặc `fastNlMeansDenoisingColored` (chất lượng cao, chậm 5×) | `preproc.denoise.method` | Khử nhiễu quá tay làm mờ dấu tiếng Việt → tham số bảo thủ |
| 7 | Cân bằng sáng | CLAHE trên kênh **L** của LAB (giữ màu) + gamma tự động theo độ sáng trung bình | `preproc.clahe.clip_limit` | `clip_limit` cao gây nhiễu hạt → mặc định 2.0 |
| 8 | Tăng nét | Unsharp masking, ⭐ **chỉ khi** phương sai Laplacian < ngưỡng | `preproc.sharpen.laplacian_threshold` | Áp lên ảnh đã nét làm **giảm** độ chính xác → điều kiện bắt buộc |
| 9 | Khử loá | Vùng bão hoà (V > 250 trong HSV) → `inpaint` | `preproc.deglare.enabled` | Mặc định **tắt** — chỉ bật khi biết chắc ảnh có phản quang |

### Chiến lược đa biến thể — TẠO LƯỜI ⭐

| Biến thể | Tạo bằng | Dùng cho | Vì sao |
|---|---|---|---|
| `v0` | Ảnh gốc đã re-encode | Dự phòng cuối | Không mất thông tin |
| `v1` | + EXIF + resize | **Kênh QR** | ⭐ QR chịu nhiễu tốt nhưng **rất nhạy với khử nhiễu** — làm mượt có thể phá cấu trúc module |
| `v2` | v1 + nắn phối cảnh | Cơ sở cho v3, v4 | |
| `v3` | v2 + khử nhiễu + CLAHE + tăng nét | **Kênh OCR văn bản** | Tối ưu cho chữ có dấu |
| `v4` | v2 → xám → nhị phân adaptive | **Kênh MRZ** | MRZ là chữ đơn cách đen trắng — nhị phân hoá cho kết quả tốt hơn hẳn ảnh màu |

> ⭐ **Tạo lười:** biến thể chỉ dựng khi kênh tương ứng truy cập lần đầu, sau đó cache. Nếu QR đọc được ngay ở `v1`, biến thể `v3`/`v4` của mặt trước **không bao giờ được tạo**.
> **Tiết kiệm:** ~15% RAM đỉnh (62 MB → 40 MB) và ~15% thời gian xử lý.

**Retry đa biến thể:** kênh thất bại trên biến thể ưu tiên → thử biến thể dự phòng theo thứ tự đã định.

---

### 7.4.2. `HeuristicSideClassifier`

| Tín hiệu | Trọng số | Cách phát hiện | Chỉ định |
|---|---|---|---|
| Có QR giải mã được | **0.40** | Payload khớp `^\d{12}\|` | → FRONT |
| Có vùng MRZ | **0.40** | 20% đáy ảnh, ≥3 dòng, mật độ ký tự `<` > 15% | → BACK |
| Anchor text mặt trước | 0.15 | Fuzzy ≥80% với "CĂN CƯỚC CÔNG DÂN", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Số / No.", "Họ và tên / Full name" | → FRONT |
| Anchor text mặt sau | 0.15 | Fuzzy với "Đặc điểm nhân dạng", "Ngày, tháng, năm", "CỤC TRƯỞNG", "Personal identification" | → BACK |
| Vùng chân dung góc trái-dưới | 0.10 | Haar cascade hoặc phân tích độ phức tạp texture | → FRONT |
| Vùng vân tay góc trái | 0.10 | Texture pattern tần số cao có hướng | → BACK |

**Ngưỡng:** ≥ 0.60 chấp nhận · 0.35–0.60 cần bằng chứng thứ hai · < 0.35 → `AMBIGUOUS`.

**Bốn kết cục:** đúng thứ tự → tiếp tục · ngược thứ tự → tự hoán đổi + cờ `auto_swapped` · trùng mặt → `DUPLICATE_SIDE` chặn · không rõ → `AMBIGUOUS`, cho người dùng gán tay.

---

### 7.4.3. `OpenCvQrDecoder`

**Chuỗi thử (3 lần, dừng ở lần đầu thành công):**

| Lần | Ảnh | Kỹ thuật |
|---|---|---|
| 1 | `v1` toàn ảnh | `cv2.wechat_qrcode.WeChatQRCode` — mạnh nhất với QR mờ/nghiêng |
| 2 | `v1` toàn ảnh | `pyzbar.decode` — thuật toán khác, bắt được ca WeChat trượt |
| 3 | `v1` góc phải-trên phóng 2× | QR trên CCCD nằm ở góc này |

> ⭐ **Rút từ 5 xuống 3 lần.** Hai lần cuối trong thiết kế cũ (quét 4 góc phần tư) có lợi ích biên rất thấp nhưng tốn ~0.8 giây ở ca xấu. Nếu 3 lần đều trượt thì QR thực sự không đọc được, và kênh MRZ đã đủ bù.

**Phân tích payload:** tách theo `|`, ánh xạ theo vị trí sang các trường: số CCCD, số CMND cũ, họ tên, ngày sinh, giới tính, địa chỉ thường trú, ngày cấp.

**Kiểm tra hợp lý bắt buộc** trước khi chấp nhận: phần tử đầu phải là 12 chữ số; các trường ngày phải parse được `ddmmyyyy`. Không khớp → `layout_recognized=False`.

> ⭐ **Nguyên tắc chống vỡ:** nếu bố cục QR thay đổi trong tương lai, hệ thống **không sinh dữ liệu sai** — nó chỉ tắt kênh QR và rơi về MRZ + OCR. Người dùng thấy nhiều ô vàng hơn, admin thấy cảnh báo trong log. **Không có im lặng hỏng.**

---

### 7.4.4. `Td1MrzReader`

| Bước | Nội dung |
|---|---|
| 1. Định vị | Quét 20% đáy `v4`, tìm dải ngang có mật độ ký tự `<` cao. Nếu `warp_succeeded` → dùng thẳng toạ độ cố định từ `zone_map` |
| 2. Đọc | Gọi `recognize_region()` trên biến thể `v4` (nhị phân) |
| 3. ⭐ **Ánh xạ cưỡng bức hậu xử lý** | PaddleOCR **không hỗ trợ giới hạn bộ ký tự lúc giải mã** — mọi ký tự ngoài `[A-Z0-9<]` được ánh xạ về ký tự gần nhất theo bảng nhầm lẫn hình dạng: `O,o,Q,D→0` · `I,l,\|→1` · `S,s→5` · `B→8` · `Z,z→2` · `G→6` · `T→7` · `A→4` · `«,‹→<` · chữ thường→hoa · không ánh xạ được → `<` |
| 4. Chuẩn hoá cấu trúc | Ép mỗi dòng về đúng 30 ký tự (đệm/cắt `<`); ghép 3 dòng |
| 5. Phân tích TD1 | Dòng 1: loại tài liệu + `VNM` + số tài liệu + check digit. Dòng 2: ngày sinh + check + giới tính + **ngày hết hạn** + check + check tổng. Dòng 3: họ tên (không dấu) |
| 6. **Xác thực checksum** | Thuật toán trọng số 7-3-1 của ICAO cho từng nhóm và toàn khối |
| 7. Sửa lỗi có kiểm soát | Nếu checksum sai, thử hoán vị nhầm lẫn phổ biến — ⭐ **tối đa 3 vị trí** (nâng từ 2 để bù việc mất ràng buộc giải mã) |
| 8. Chấm điểm | Đúng ngay → 0.98 · đúng sau sửa → 0.90 · không bao giờ đúng → 0.50 + cờ `MRZ_CHECKSUM_FAILED` |

> ⭐ **Chỉ tiêu: MRZ checksum hợp lệ ≥ 75%** (đã điều chỉnh từ 85% sau khi xác định PaddleOCR không hỗ trợ charset whitelist). **Cần kiểm chứng bằng Golden Set ngay ở P2 tuần 2** — nếu thấp hơn, phải điều chỉnh chiến lược trước khi đi tiếp.

> **Vì sao MRZ đáng công sức này:** nó là **nguồn duy nhất ngoài OCR** cho trường "Ngày hết hạn" — trường QR không chứa. Không có MRZ, ngày hết hạn phụ thuộc hoàn toàn OCR với độ chính xác ~88%. Có MRZ, con số đó lên 95%+.

---

### 7.4.5. `PaddleOcrAdapter`

| Mục | Thiết kế |
|---|---|
| Model | PP-OCRv4: `det` (phát hiện vùng) + `rec` (nhận dạng, `lang='vi'`) + `cls` (phân loại góc 0/180) |
| Đóng gói | ⭐ Model tải sẵn vào `app/ocr-models/`, **không bao giờ tải từ mạng lúc chạy** (P-01). Adapter **phải** chỉ định `det_model_dir`, `rec_model_dir`, `cls_model_dir` tường minh |
| Vòng đời | **Singleton**, nạp ở **luồng nền sau khi UI hiện** qua `warm_up()`. Chiếm ~150 MB RAM thường trú |
| Luồng | ⭐ Chạy trong `run_in_executor` (thread pool) — PaddleOCR là **CPU-bound và blocking**; gọi thẳng sẽ chặn event loop và treo toàn bộ API (ADR-06) |
| Giới hạn CPU | `ocr.cpu_threads` cấu hình được (mặc định = số nhân / 2) để không chiếm hết máy |
| Chuẩn hoá đầu ra | `bbox` pixel → tương đối (0..1). Text → Unicode **NFC**. Sắp xếp vùng theo thứ tự đọc (trên→dưới, trái→phải) |
| Xử lý lỗi | Model không nạp được → `warm_up()` ném `OcrEngineUnavailableError`, health check báo `DEGRADED`, hệ thống **vẫn dùng được ở chế độ nhập tay** (P-08) |
| ⚠️ Giới hạn kỹ thuật | **Không hỗ trợ charset whitelist lúc giải mã** — `charset_hint` chỉ dùng làm gợi ý cho bộ lọc hậu xử lý |

---

### 7.4.6. `ZoneAndAnchorExtractor`

**Chiến lược ZONE** (khi `warp_succeeded=True`) — bản đồ vùng lưu trong `document_type.zone_map` cho khung chuẩn 1012×638:

| Trường | Vùng tương đối (x, y, w, h) | Mặt |
|---|---|---|
| `id_number` | (0.38, 0.27, 0.58, 0.11) | FRONT |
| `full_name` | (0.38, 0.39, 0.61, 0.10) | FRONT |
| `date_of_birth` | (0.38, 0.50, 0.35, 0.08) | FRONT |
| `expiry_date` | (0.38, 0.80, 0.35, 0.08) | FRONT |
| `issue_place` | (0.05, 0.60, 0.90, 0.12) | BACK |
| `issue_date` | (0.05, 0.73, 0.60, 0.08) | BACK |
| `mrz` | (0.02, 0.82, 0.96, 0.16) | BACK |

> ⚠️ **Toạ độ trên là giá trị khởi tạo — PHẢI hiệu chỉnh bằng ảnh thật ở giai đoạn P2.** Lưu trong CSDL để tinh chỉnh mà không rebuild.

**Chiến lược ANCHOR** (dự phòng khi không nắn được phối cảnh):

| Trường | Anchor (fuzzy ≥75%, trên chuỗi bỏ dấu) | Quy tắc lấy giá trị |
|---|---|---|
| `id_number` | "Số", "No.", "Số / No." | Chuỗi 12 chữ số gần nhất bên phải/dòng dưới; ⭐ **ưu tiên vùng có chiều cao lớn nhất** (số CCCD in to nhất trên thẻ) |
| `full_name` | "Họ và tên", "Full name" | Chuỗi in hoa có dấu bên phải hoặc dòng kế; loại bỏ nhãn tiếng Anh |
| `date_of_birth` | "Ngày sinh", "Date of birth" | Mẫu `\d{2}/\d{2}/\d{4}` gần nhất |
| `expiry_date` | "Có giá trị đến", "Date of expiry" | Mẫu ngày **hoặc** chuỗi khớp "KHÔNG THỜI HẠN" |
| `issue_date` | "Ngày, tháng, năm", "Date, month, year" | Mẫu ngày ở nửa dưới mặt sau |
| `issue_place` | *(không có nhãn cố định)* | ⭐ Vùng in hoa nằm **phía trên** dòng ngày cấp; hoặc dòng dài nhất khớp fuzzy với 1 trong 2 giá trị chuẩn |

⭐ **Xử lý tiếng Việt bắt buộc:** mọi so khớp fuzzy thực hiện trên chuỗi đã **bỏ dấu** (NFD → lọc ký tự kết hợp) và **UPPERCASE**, để "CUC CANH SAT" khớp được "CỤC CẢNH SÁT". Không làm bước này, tỉ lệ khớp anchor giảm khoảng một nửa.

---

## 7.5. Domain Service — nơi chứa tri thức nghiệp vụ

### 7.5.1. `IssuePlaceNormalizer` — 4 tầng

Chi tiết thuật toán: xem [03-luong-du-lieu.md §S9](03-luong-du-lieu.md#s9--chuẩn-hoá).

⭐ **Cam kết bất biến:** service này **chỉ trả về `None` hoặc một trong 2 giá trị chuẩn**. Không có đường nào để giá trị thứ ba lọt ra.

**Test bắt buộc (property-based):** với **mọi** chuỗi đầu vào bất kỳ, kết quả luôn thuộc tập 3 giá trị cho phép.

### 7.5.2. `FieldFusionService` — 8 quy tắc

| # | Quy tắc | Chi tiết |
|---|---|---|
| 1 | Thu thập ứng viên | Mỗi trường có 0–3 ứng viên `(value, confidence, source)` |
| 2 | Ưu tiên nguồn | QR (1.00) > MRZ-checksum-đúng (0.98) > OCR (conf gốc × hệ số trường) > MRZ-checksum-sai (0.50) |
| 3 | **Thưởng đồng thuận** | ≥ 2 nguồn cùng giá trị → `+0.10` (trần 1.00), `agreement = true` |
| 4 | **Phát hiện xung đột** | 2 nguồn ≥ 0.90 cho giá trị **khác nhau** → chọn nguồn ưu tiên cao hơn nhưng **hạ conf xuống 0.50** + cờ `SOURCE_CONFLICT`. UI hiện cả hai cho người dùng chọn |
| 5 | ⭐ **Kiểm tra khớp thẻ** | Số CCCD từ QR ≠ từ MRZ → cờ nghiêm trọng `CARD_MISMATCH` → **chặn cứng** việc tạo Customer. Đây là dấu hiệu 2 ảnh không cùng một thẻ |
| 6 | ⭐ **Suy luận từ mã số** | 3 số đầu = mã tỉnh (tra `province_code`); số thứ 4 = giới tính + thế kỷ; số 5–6 = 2 số cuối năm sinh → **đối chiếu chéo** với ngày sinh và giới tính đã trích. Mâu thuẫn → hạ conf + cờ `ID_INCONSISTENT` |
| 7 | Tính điểm tổng | Trung bình có trọng số: `id_number` 0.30 · `full_name` 0.25 · `date_of_birth` 0.15 · `issue_date` 0.10 · `expiry_date` 0.10 · `issue_place` 0.10 |
| 8 | Gắn cờ kiểm tra | `confidence < ocr.review_threshold` (mặc định 0.85) → `needs_review = true` |

**Bất biến:** `confidence` ∈ [0, 1] tuyệt đối · nếu `value is None` thì `confidence = 0` và `source = NONE`.

**Không được làm:** quyết định chặn hay không chặn (việc của Validation) · sửa giá trị.

---

## 7.6. Chiến lược thay thế OCR Engine (kiểm chứng P-03)

**Bài kiểm tra nghiệm thu bắt buộc ở Giai đoạn 2:** thay `PaddleOcrAdapter` bằng `TesseractAdapter` và chứng minh:

| Tiêu chí | Yêu cầu |
|---|---|
| Số file phải sửa ngoài `infrastructure/ocr/` | **0** |
| Số dòng cấu hình phải đổi | **1** (`ocr.engine`) |
| Test của Domain và Application | **Vẫn xanh, không sửa** |
| Test của Fusion, Normalizer, Validation | **Vẫn xanh, không sửa** |
| Test tích hợp OCR | Chạy được với cả 2 engine bằng cách tham số hoá fixture |

> Nếu bài kiểm tra này thất bại, kiến trúc đã bị rò rỉ và **phải sửa trước khi đi tiếp**.

**Adapter dự phòng bắt buộc:** `NullOcrAdapter` — trả danh sách rỗng, `get_info().is_ready = False`. Dùng khi model không nạp được. Hệ thống chuyển sang chế độ nhập tay hoàn toàn thay vì sập.

---

## 7.7. Xử lý lỗi trong pipeline

| Chặng thất bại | Phân loại | Hành động | Ảnh hưởng người dùng |
|---|---|---|---|
| Tiền xử lý — nắn phối cảnh | **Suy giảm** | `warp_succeeded=False`, chuyển sang chiến lược ANCHOR | Không thấy gì, có thể nhiều ô vàng hơn |
| Tiền xử lý — giải mã ảnh | **Chí mạng** | `FAILED`, `IMAGE_DECODE_ERROR` | "Ảnh không đọc được, vui lòng tải ảnh khác" |
| Phân loại mặt — không rõ | **Cần người dùng** | `NEEDS_MANUAL_ASSIGN` | Màn hình cho bấm chọn mặt |
| Phân loại mặt — trùng mặt | **Cần người dùng** | `NEEDS_REUPLOAD` | Hướng dẫn có hình minh hoạ |
| Kênh QR thất bại | **Bình thường** | `qr_available=False`, tiếp tục | Không thấy gì |
| Kênh MRZ thất bại | **Bình thường** | `mrz_available=False`, tiếp tục | Ô "Ngày hết hạn" có thể vàng |
| Engine OCR chết giữa chừng | **Có thể thử lại** | Retry ×3 backoff; sau đó `FAILED` | "Xử lý thất bại. [Thử lại] hoặc [Nhập tay]" |
| Engine OCR không sẵn sàng | **Suy giảm hệ thống** | Health `DEGRADED`; wizard bỏ qua bước OCR | Banner cảnh báo, vẫn tạo được hợp đồng bằng nhập tay |
| Không trích được trường nào | **Cần người dùng** | `COMPLETED_WITH_WARNINGS`, 6 ô trống | "Không đọc được thông tin. Kiểm tra chất lượng ảnh hoặc nhập tay" |
| Hết bộ nhớ | **Chí mạng** | `FAILED`, ghi log chi tiết | "Không đủ bộ nhớ. Đóng bớt ứng dụng khác rồi thử lại" |

> ⭐ **Nguyên tắc bao trùm:** OCR thất bại **không bao giờ** chặn người dùng tạo hợp đồng. Luôn có đường nhập tay (P-08).

**`ExtractionPipeline` không bao giờ ném ngoại lệ ra ngoài** — mọi lỗi được gói vào `ExtractionResult.error_code` và `status`. Lý do: pipeline chạy trong job nền; ngoại lệ lọt ra sẽ làm chết worker.

---

## 7.8. Lộ trình nâng cao độ chính xác

Thiết kế hiện tại chừa sẵn **6 điểm cắm** để nâng cấp mà **không phá vỡ module nào**:

| # | Cải tiến | Cắm vào đâu | Ước tính cải thiện |
|---|---|---|---|
| 1 | ⭐ **Vòng lặp phản hồi** — dùng `ocr_field.user_corrected` tự động đề xuất alias mới | Job nền phân tích + gợi ý ở Cài đặt | +2–4% trên `issue_place`, `issue_date` |
| 2 | **Zone map tự học** — thống kê `bbox` thực tế của trường đọc đúng, tinh chỉnh `document_type.zone_map` | Cập nhật bản ghi CSDL | +1–3% |
| 3 | **Fine-tune model `rec`** trên phông chữ CCCD Việt Nam | Thay file model trong `ocr-models/`, không đổi adapter | +3–6% trên OCR thuần |
| 4 | **Model phát hiện thẻ chuyên dụng** (YOLO-nano ~5 MB) thay heuristic contour | Adapter mới cho `IImagePreprocessor` | Nắn phối cảnh 85% → 97% |
| 5 | ⭐ **Đọc chip NFC** qua đầu đọc thẻ | Kênh thứ tư hạng S (100% chính xác, có chữ ký số của Bộ Công an) | Đạt ~100%, xác thực được thẻ thật/giả |
| 6 | **Model phân loại mặt** thay bỏ phiếu heuristic | Adapter mới cho `ICardSideClassifier` | 96% → 99.5% |

> ⭐ Cải tiến #1 và #2 dùng **chính dữ liệu của khách hàng, trên chính máy của họ**, không gửi đi đâu. Đây là cách duy nhất "học" được mà vẫn giữ P-01.

---

## 7.9. Đánh giá & bộ dữ liệu kiểm thử

| Bộ | Số cặp ảnh | Nội dung | Dùng để |
|---|---|---|---|
| **Golden Set** | 200 | Ảnh thật, gán nhãn thủ công 6 trường, đa dạng: sáng/tối/nghiêng/mờ/loá | Đo NFR-01; chạy khi đổi engine/tham số + hàng đêm |
| **Edge Set** | 40 | Ca khó: tải nhầm thứ tự · trùng mặt · QR bị che · MRZ mờ · "KHÔNG THỜI HẠN" · ảnh xoay 180° | Test hồi quy nhánh ngoại lệ |
| **Smoke Set** | 10 | Chạy nhanh (< 60s) mỗi commit | Bắt hồi quy lớn |
| **Regression Set** | tăng dần | Mọi ảnh từng gây lỗi thật | Đảm bảo lỗi đã sửa không quay lại |

### Chỉ số theo dõi bắt buộc

| Chỉ số | Định nghĩa | Mục tiêu | Ngưỡng CI đỏ |
|---|---|---|---|
| Field Accuracy | % trường khớp chính xác nhãn vàng | ≥ 95% (OCR thuần), ≥ 99% (có QR/MRZ) | Giảm > 1% so với baseline |
| Full-Card Accuracy | % thẻ có **cả 6 trường** đúng | ≥ 92% | < 92% |
| Correction Rate | % trường người dùng phải sửa (dữ liệu thật) | ≤ 8% | — |
| ⭐ **False Confidence** | % trường có `confidence ≥ 0.95` nhưng **sai** | **≤ 0.5%** | **> 0.5%** |
| Side Classification Accuracy | % phân loại mặt đúng | ≥ 99% | < 99% |
| MRZ checksum hợp lệ | % ảnh MRZ đọc được và checksum đúng | ≥ 75% | < 70% |
| p95 Latency | Thời gian xử lý 1 cặp ảnh | ≤ 9s | > 9s |

> ⭐ **`False Confidence` là chỉ số nguy hiểm nhất và là chỉ số CHẶN PHÁT HÀNH.** Một trường sai được gắn nhãn "100% tin cậy" nguy hiểm hơn nhiều so với trường bỏ trống — vì nó lọt thẳng vào hợp đồng mà không ai nhìn. Mọi thay đổi tham số phải kiểm tra chỉ số này trước khi phát hành.

---

[← 06 — Giao diện](06-giao-dien.md) · [Mục lục](README.md) · [Tiếp: 08 — Validation →](08-validation.md)
