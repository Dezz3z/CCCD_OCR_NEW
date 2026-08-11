# 02 — Sơ đồ hệ thống

[← Mục lục](README.md)

---

## 2.1. C4 Level 1 — Sơ đồ ngữ cảnh

```mermaid
graph TB
    subgraph BOUNDARY["🔒 MỘT MÁY TÍNH WINDOWS — KHÔNG MẠNG, KHÔNG INTERNET"]
        SYS["<b>COCAS</b><br/>Hệ thống sinh hợp đồng từ ảnh CCCD<br/><i>Ứng dụng Desktop đơn máy</i>"]
        FS[("Ổ đĩa cục bộ<br/>File Vault — mã hoá<br/>ảnh · docx · template")]
        DB[("PostgreSQL portable<br/>127.0.0.1:55432")]
        PP["PaddleOCR<br/>model offline"]
        BK[("Thư mục sao lưu<br/>*.cocasbak")]
    end

    OP["👤 <b>Nhân viên nghiệp vụ</b><br/>Làm trọn quy trình: chọn mẫu → ảnh → OCR<br/>→ bổ sung → hợp đồng .docx<br/><b>Không cần đăng nhập, không cần ai duyệt</b>"]

    OP ==>|"Toàn bộ nghiệp vụ"| SYS

    SYS --> FS
    SYS --> DB
    SYS -->|"CLI convert"| LO
    SYS -->|"inference cục bộ"| PP
    SYS -->|"tự động hàng ngày"| BK

    NET(["🌐 Internet"])
    LAN(["🖧 Mạng LAN"])
    SYS -. "❌ KHÔNG kết nối<br/>(không có HTTP client ra ngoài)" .-x NET
    SYS -. "❌ KHÔNG lắng nghe<br/>(chỉ bind 127.0.0.1)" .-x LAN

    style BOUNDARY fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px
    style SYS fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:3px
    style OP fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    style NET fill:#ffcdd2,stroke:#c62828,stroke-dasharray: 5 5
    style LAN fill:#ffcdd2,stroke:#c62828,stroke-dasharray: 5 5
```

---

## 2.2. C4 Level 2 — Sơ đồ Container

```mermaid
graph TB
    USER["👤 Người dùng"]

    subgraph PROC1["🪟 Tiến trình 1 — ContractSystem.exe (Tauri)"]
        SHELL["<b>Tauri Shell</b> · Rust<br/>• Cửa sổ, menu, khay hệ thống<br/>• <b>Supervisor</b>: spawn/giám sát/restart<br/>• Hộp thoại file & thư mục (native)<br/>• In ấn, mở Explorer<br/>• Sinh Local Handshake Token<br/>• Single-instance mutex"]
        WEBVIEW["<b>SPA</b> · React 18 + TS + MUI v5<br/>CSP: connect-src chỉ 127.0.0.1:&lt;port&gt;<br/>Asset nhúng 100%, không CDN"]
    end

    subgraph PROC2["🐍 Tiến trình 2 — cocas-backend.exe (PyInstaller onedir)"]
        API["<b>Presentation</b> · FastAPI<br/>Routers · Middlewares · Pydantic Schemas"]
        APP["<b>Application</b><br/>Use Cases · UnitOfWork · EventBus · ActivityLog"]
        DOM["<b>Domain ★</b><br/>Entities · Value Objects · Ports<br/>Domain Services · Business Rules"]
        INFRA["<b>Infrastructure</b><br/>Repos · OCR Pipeline · Renderer<br/>Vault · Crypto · JobRunner"]
        RUNNER["<b>JobRunner</b><br/>polling bảng `job` mỗi 500ms<br/>đồng thời = 1"]
        OCRMEM["<b>PaddleOCR</b><br/>singleton, nạp nền sau khi UI hiện"]
    end

    subgraph PROC3["🐘 Tiến trình 3 — postgres.exe (portable)"]
        PG[("PostgreSQL 16<br/>127.0.0.1:55432<br/>pgdata trong %LOCALAPPDATA%")]
    end

    subgraph DISK["💾 Ổ đĩa cục bộ"]
        VAULT[("File Vault · AES-256-GCM<br/>images / contracts / thumbnails")]
        TPL[("Template Store<br/>*.docx có phiên bản")]
        MODEL[("OCR Models<br/>det · rec · cls — chỉ đọc")]
        KEYS[("keys/master.key.dpapi<br/>KEK bọc bằng Windows DPAPI")]
        LOGS[("Logs — xoay vòng 30 ngày<br/>PII đã được che")]
        BKP[("Backups — *.cocasbak")]
    end

    USER ==> SHELL
    SHELL <-->|"IPC: cổng + token"| WEBVIEW
    WEBVIEW ==>|"HTTP/JSON · loopback<br/>X-Local-Token: &lt;handshake&gt;"| API
    SHELL -.->|"spawn · health probe 5s · restart ×3"| PROC2
    SHELL -.->|"pg_ctl start/stop"| PROC3

    API --> APP --> DOM
    INFRA -.->|"triển khai Port"| DOM
    APP --> INFRA
    APP -->|"INSERT job"| PG
    RUNNER -->|"SELECT FOR UPDATE SKIP LOCKED"| PG
    RUNNER --> INFRA
    INFRA --> OCRMEM

    INFRA --> PG
    INFRA --> VAULT
    INFRA --> TPL
    INFRA --> KEYS
    INFRA --> LOGS
    INFRA --> BKP
    OCRMEM --> MODEL

    style PROC1 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style PROC2 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style PROC3 fill:#e0f2f1,stroke:#00695c,stroke-width:2px
    style DISK fill:#fafafa,stroke:#616161
    style DOM fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
```

---

## 2.3. C4 Level 3 — Sơ đồ Component (Backend)

```mermaid
graph LR
    subgraph PRES["PRESENTATION"]
        R1["upload_router"]
        R2["ocr_router"]
        R3["customer_router"]
        R4["contract_router"]
        R5["template_router"]
        R6["system_router"]
        MW["Middlewares<br/>LocalToken · CorrelationId<br/>ErrorHandler · SecurityHeaders"]
    end

    subgraph APPL["APPLICATION"]
        UC1["UploadCardImageUC"]
        UC2["RunOcrUC"]
        UC3["ConfirmOcrResultUC"]
        UC4["CreateCustomerUC"]
        UC5["GenerateContractUC"]
        UC6["RegisterTemplateUC"]
        UOW["UnitOfWork"]
        BUS["DomainEventBus"]
        LOGS["ActivityLogService"]
        RCB["RenderContextBuilder<br/>→ StyledValue"]
    end

    subgraph DOMN["DOMAIN"]
        ENT["Entities<br/>Customer · Contract · ContractParty<br/>OcrSession · Template"]
        VOS["Value Objects<br/>CitizenId · Phone · IssuePlace<br/>SecuritiesAccountNumber · StyledValue"]
        DSV["Domain Services<br/>IssuePlaceNormalizer<br/>FieldFusionService<br/>CardValidityPolicy<br/>ExportNameGenerator"]
        PORT["<b>PORTS (18)</b><br/>IOcrEngine · IRegionRecognizer<br/>IQrDecoder · IMrzReader · IPreprocessor<br/>IDocumentTypeSelector<br/>IReadRepository · IWriteRepository<br/>IFileStorage · IDocumentRenderer<br/>IJobQueue · IClock · ICrypto"]
        RULE["Validation Rules (56)"]
    end

    subgraph INFR["INFRASTRUCTURE"]
        subgraph OCRPIPE["OCR Pipeline"]
            PRE["ImagePreprocessor<br/>(OpenCV, biến thể LƯỜI)"]
            CLS["CardSideClassifier"]
            QR["QrDecoder (3 lần thử)"]
            MRZ["MrzReader (post-filter charset)"]
            PADDLE["PaddleOcrAdapter"]
            EXT["ZoneAndAnchorExtractor"]
        end
        REPO["SqlAlchemy Repositories"]
        STOR["EncryptedFileVault"]
        DCA["DocxContextAdapter<br/>StyledValue → RichText"]
        REND["DocxTemplateRenderer"]
        SEC["DpapiCryptoService · BlindIndex"]
        QUE["JobRunner (polling bảng job)"]
    end

    MW --> R1 & R2 & R3 & R4 & R5 & R6
    R1 --> UC1
    R2 --> UC2 & UC3
    R3 --> UC4
    R4 --> UC5
    R5 --> UC6

    UC1 & UC2 & UC3 & UC4 & UC5 & UC6 --> UOW
    UC1 & UC2 & UC3 & UC4 & UC5 & UC6 --> LOGS
    UC2 & UC5 --> BUS
    UC5 --> RCB
    UC2 --> PORT
    UC5 --> PORT
    UC3 --> DSV
    UC4 --> ENT & VOS & RULE
    RCB --> VOS

    PRE & CLS & QR & MRZ & PADDLE & EXT -.->|implements| PORT
    REPO & STOR & REND & SEC & QUE -.->|implements| PORT
    RCB -.-> DCA --> REND

    style DOMN fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
    style PORT fill:#a5d6a7,stroke:#1b5e20,stroke-width:2px
    style OCRPIPE fill:#ffe0b2,stroke:#ef6c00
```

---

## 2.4. Sơ đồ tuần tự — Toàn trình tạo hợp đồng

```mermaid
sequenceDiagram
    autonumber
    actor U as 👤 Nhân viên
    participant UI as React UI
    participant API as FastAPI
    participant UC as Use Cases
    participant J as Bảng `job`
    participant W as JobRunner
    participant OCR as OCR Pipeline
    participant DOM as Domain
    participant DB as PostgreSQL
    participant V as File Vault
    participant DOC as Doc Engine

    rect rgb(255, 249, 196)
    note over U,API: BƯỚC 1 — CHỌN MẪU (điều khiển toàn bộ wizard)
    U->>UI: Mở app → Dashboard → Ctrl+N
    UI->>API: GET /templates
    UI->>API: GET /templates/{id}/requirements
    API-->>UI: party_schema · contract_fields · estimated_steps
    UI->>U: Hiện "Mẫu đã chọn cần chuẩn bị"
    end

    rect rgb(232, 245, 233)
    note over UI,V: BƯỚC 2a — NẠP ẢNH
    U->>UI: Chọn ảnh mặt trước + mặt sau
    UI->>UI: Kiểm tra sơ bộ (đuôi, ≤10MB, preview)
    UI->>API: POST /upload/front (multipart)
    API->>UC: UploadCardImageUseCase
    UC->>UC: Magic bytes · MIME · kích thước · giải mã thử · RE-ENCODE
    UC->>V: Lưu ảnh (mã hoá, tên = UUID)
    UC->>DB: INSERT card_image (sha256, side_hint)
    API-->>UI: 201 {image_id, quality_score, quality_flags}
    UI->>API: POST /upload/back
    API-->>UI: 201
    end

    rect rgb(255, 243, 224)
    note over UI,DB: BƯỚC 2b — OCR BẤT ĐỒNG BỘ
    UI->>API: POST /ocr {front_image_id, back_image_id, party_key}
    API->>UC: CreateOcrSessionUseCase
    UC->>DB: INSERT ocr_session (status=QUEUED)
    UC->>J: INSERT job (type=OCR)
    API-->>UI: 202 {session_id, poll_url}

    W->>J: SELECT FOR UPDATE SKIP LOCKED
    W->>DB: UPDATE status=PROCESSING
    W->>V: Đọc 2 ảnh

    W->>OCR: S3 Tiền xử lý (biến thể tạo LƯỜI)
    W->>OCR: S4 Phân loại mặt
    alt Tải nhầm thứ tự
        OCR-->>W: swapped = true → tự hoán đổi + cờ
    else Trùng mặt / không rõ
        OCR-->>W: NEEDS_REUPLOAD / NEEDS_MANUAL_ASSIGN
    end
    W->>OCR: S5 Giải mã QR (3 lần thử) → 5-6 trường, conf 1.00
    W->>OCR: S6 Đọc MRZ + checksum → ngày hết hạn, conf 0.98
    W->>OCR: S7 PaddleOCR toàn ảnh
    W->>OCR: S8 Trích xuất trường (zone + anchor)
    W->>DOM: S9 Chuẩn hoá (4 tầng cho Nơi cấp)
    W->>DOM: S10 Fusion 3 nguồn + confidence + cờ
    W->>DOM: S11 Validation (23 quy tắc)
    W->>DB: INSERT ocr_result + 6 × ocr_field
    W->>DB: UPDATE status=COMPLETED[_WITH_WARNINGS]
    end

    loop Poll mỗi 800ms
        UI->>API: GET /ocr/{id}/progress
        API-->>UI: {status, progress_percent, progress_message}
    end

    rect rgb(227, 242, 253)
    note over U,DB: BƯỚC 2c — XÁC NHẬN & BỔ SUNG (bố cục CHIA ĐÔI)
    UI->>API: GET /ocr/{id}
    API-->>UI: 6 trường + confidence + bbox + next_actions
    UI->>U: Ảnh bên trái ⟷ Dữ liệu bên phải<br/>Bấm ô → vùng trên ảnh sáng lên
    U->>UI: Sửa trường sai · nhập SĐT/Email/Địa chỉ<br/>+ [Ngân hàng] hoặc [STK chứng khoán] tuỳ mẫu
    UI->>API: PATCH /ocr/{id}/fields
    UI->>API: POST /ocr/{id}/confirm
    UI->>API: POST /customers {...}
    UC->>DOM: Dựng Value Objects (tự validate)
    UC->>DB: Kiểm trùng theo id_number_bidx
    UC->>DB: INSERT customer + bank_account (PII mã hoá)
    UC->>DB: INSERT activity_log
    API-->>UI: 201 {customer_id}
    end

    rect rgb(243, 229, 245)
    note over U,LO: BƯỚC 3 — SINH HỢP ĐỒNG
    UI->>API: POST /contracts/generate {customer_id, template_code, parties[]}
    API->>UC: GenerateContractUseCase
    UC->>DB: Nạp customer + template_version (active) + kiểm SHA-256
    UC->>DOM: Sinh contract_no + export_name
    UC->>UC: RenderContextBuilder → dict + StyledValue
    alt Thiếu biến bắt buộc
        API-->>UI: 422 COCAS-7002 + danh sách biến thiếu
    end
    UC->>DB: INSERT contract (GENERATING, render_snapshot_enc)
    UC->>DOC: DocxContextAdapter (StyledValue→RichText) → render
    DOC->>V: Ghi .tmp → verify SHA-256 → rename .docx
    UC->>DB: UPDATE status=COMPLETED
    API-->>UI: 201 {contract_id, docx ready}
    end

    UI->>API: GET /contracts/{id}/documents/docx
    API->>V: Đọc file · kiểm SHA-256 · giải mã · stream
    UI->>U: Tải "Mẫu 01A - NGUYỄN VĂN A.docx"

    rect rgb(255, 235, 238)
    note over UC,V: DỌN DẸP THEO CHÍNH SÁCH
    UC->>V: Xoá ảnh gốc (retention = DELETE_AFTER_CONTRACT)
    UC->>DB: UPDATE card_image SET purged_at
    UC->>DB: INSERT activity_log (IMAGE_PURGED)
    end
```

---

## 2.5. Sơ đồ tuần tự — Xử lý tải nhầm thứ tự mặt

```mermaid
sequenceDiagram
    autonumber
    participant W as JobRunner
    participant CLS as CardSideClassifier
    participant QR as QrDecoder
    participant MRZ as MrzReader
    participant DB as PostgreSQL
    participant UI as React UI

    W->>CLS: classify(image_A), classify(image_B)

    Note over CLS: 6 tín hiệu bỏ phiếu có trọng số:<br/>QR (0.40 → FRONT) · MRZ (0.40 → BACK)<br/>Anchor mặt trước (0.15) · Anchor mặt sau (0.15)<br/>Vùng chân dung (0.10) · Vùng vân tay (0.10)

    CLS-->>W: A: {side: BACK, 0.94} · B: {side: FRONT, 0.97}

    alt Cả 2 rõ ràng, ĐÚNG thứ tự
        W->>W: Tiếp tục bình thường
    else Cả 2 rõ ràng, NGƯỢC thứ tự
        W->>W: Hoán đổi tự động
        W->>DB: ocr_session.auto_swapped = true
        W->>UI: Cảnh báo mềm: "Đã tự hoán đổi mặt trước/sau" [Hoàn tác]
    else Hai ảnh cùng một mặt
        W->>DB: status = NEEDS_REUPLOAD · error = DUPLICATE_SIDE
        W->>UI: "Bạn đã tải 2 ảnh cùng một mặt" + hướng dẫn có hình
    else Một ảnh score < 0.60
        W->>QR: Thử giải QR trên cả 2 ảnh
        W->>MRZ: Thử đọc MRZ trên cả 2 ảnh
        alt Có bằng chứng quyết định
            W->>W: Gán mặt theo bằng chứng
        else Không có bằng chứng
            W->>DB: status = NEEDS_MANUAL_ASSIGN
            W->>UI: Hiển thị 2 ảnh, cho người dùng bấm chọn mặt
        end
    end
```

---

## 2.6. Máy trạng thái — Phiên OCR

```mermaid
stateDiagram-v2
    [*] --> CREATED: Tạo phiên
    CREATED --> QUEUED: Đủ 2 ảnh, INSERT job
    CREATED --> CANCELLED: Người dùng huỷ

    QUEUED --> PROCESSING: JobRunner nhận job
    QUEUED --> CANCELLED: Huỷ trước khi chạy

    PROCESSING --> COMPLETED: Đủ 6 trường, mọi conf ≥ ngưỡng
    PROCESSING --> COMPLETED_WITH_WARNINGS: Có trường conf thấp<br/>hoặc validation cảnh báo
    PROCESSING --> NEEDS_REUPLOAD: Ảnh sai mặt / trùng mặt /<br/>chất lượng quá kém
    PROCESSING --> NEEDS_MANUAL_ASSIGN: Không phân loại được mặt
    PROCESSING --> FAILED: Lỗi kỹ thuật (engine crash, hết bộ nhớ)

    NEEDS_MANUAL_ASSIGN --> QUEUED: Người dùng gán mặt thủ công
    NEEDS_REUPLOAD --> CREATED: Người dùng tải ảnh mới
    FAILED --> QUEUED: Thử lại (tối đa 3 lần)

    COMPLETED --> CONFIRMED: Người dùng xác nhận/sửa
    COMPLETED_WITH_WARNINGS --> CONFIRMED: Người dùng xác nhận/sửa

    CONFIRMED --> CONSUMED: Đã dùng để tạo Customer
    CONSUMED --> [*]
    CANCELLED --> [*]

    note right of COMPLETED_WITH_WARNINGS
        Trạng thái phổ biến nhất trong thực tế.
        UI làm nổi bật trường cần kiểm tra
        bằng màu vàng + biểu tượng ⚠️ + % cụ thể.
        Trường đạt ngưỡng chỉ hiện ✅ (UX-07).
    end note
```

---

## 2.7. Máy trạng thái — Hợp đồng

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Tạo bản nháp
    DRAFT --> GENERATING: Yêu cầu sinh tài liệu
    GENERATING --> COMPLETED: docxtpl render xong + hash khớp
    GENERATING --> GENERATION_FAILED: Lỗi template/biến

    GENERATION_FAILED --> GENERATING: Sửa dữ liệu rồi thử lại

    COMPLETED --> SUPERSEDED: Sinh lại bản mới (giữ bản cũ)
    COMPLETED --> VOIDED: Huỷ hợp đồng (soft, có lý do)
    DRAFT --> VOIDED
    GENERATING --> VOIDED
    GENERATION_FAILED --> VOIDED

    SUPERSEDED --> [*]
    VOIDED --> [*]

    note right of COMPLETED
        ⭐ D2.1: sau khi bỏ PDF, GENERATING đi
        thẳng tới COMPLETED. DOCX_READY /
        PDF_CONVERTING / PDF_FAILED đã bị gỡ:
        chúng chỉ tồn tại để mô tả khoảng thời
        gian giữa "có DOCX" và "có PDF", khoảng
        đó nay bằng không.
    end note

    note right of SUPERSEDED
        Không bao giờ xoá hợp đồng cũ.
        Mỗi lần sinh lại tạo bản ghi mới
        với revision_no+1 và liên kết supersedes_id.
    end note
```

---

## 2.8. Sơ đồ luồng dữ liệu (DFD Level 1)

```mermaid
flowchart TD
    T0[/"📋 Chọn mẫu hợp đồng"/] --> T1{{"Đọc party_schema<br/>→ sinh các bước wizard"}}
    T1 --> A

    A[/"📷 Ảnh CCCD<br/>mặt trước + sau"/] --> B{{"Cổng nạp<br/>MIME · magic bytes<br/>≤10MB · re-encode"}}
    B -->|Từ chối| X1[/"❌ 413 / 415 / 422"/]
    B -->|Chấp nhận| C[("File Vault<br/>ảnh mã hoá")]
    C --> D["Tiền xử lý ảnh<br/>9 phép biến đổi<br/>5 biến thể tạo LƯỜI"]
    D --> E{"Phân loại mặt"}
    E -->|Không rõ| X2[/"⚠️ Tải lại hoặc gán thủ công"/]
    E -->|OK| F1["Kênh 1: QR Decoder<br/>(3 lần thử)"]
    E -->|OK| F2["Kênh 2: MRZ Reader<br/>(checksum ICAO)"]
    E -->|OK| F3["Kênh 3: PaddleOCR<br/>+ Field Extractor"]

    F1 --> G["🔀 Fusion Engine<br/>QR > MRZ > OCR<br/>Đối chiếu chéo · confidence"]
    F2 --> G
    F3 --> G

    G --> H["Chuẩn hoá<br/>NFC · UPPERCASE · dd/mm/yyyy<br/>★ Nơi cấp → 1 trong 2 giá trị chuẩn"]
    H --> I{{"Validation nghiệp vụ<br/>23 quy tắc V-OCR-*"}}
    I -->|Lỗi cứng| J1["🔴 Bắt buộc người dùng sửa"]
    I -->|Cảnh báo| J2["🟡 Gắn cờ needs_review"]
    I -->|Sạch| J3["✅"]

    J1 --> K[/"📝 Bố cục CHIA ĐÔI<br/>Ảnh ⟷ 6 trường CCCD<br/>+ Liên hệ + [NH | STK CK]"/]
    J2 --> K
    J3 --> K

    K --> L{{"Validation Form<br/>15 quy tắc V-FRM-*"}}
    L -->|Lỗi| K
    L -->|OK| M[("💾 PostgreSQL<br/>customer · bank_account<br/>PII mã hoá AES-256-GCM")]

    M --> N["Nạp template_version active<br/>+ kiểm SHA-256"]
    N --> O["RenderContextBuilder<br/>→ dict + StyledValue"]
    O --> P["DocxContextAdapter<br/>StyledValue → RichText"]
    P --> Q["docxtpl render"]
    Q --> R[("📄 contract.docx<br/>trong Vault")]
    R --> V[("💾 contract<br/>+ render_snapshot_enc<br/>+ contract_party<br/>+ sha256")]
    V --> W[/"⬇️ Tải 'Mẫu 01A - NGUYỄN VĂN A.docx'"/]

    V --> Y[("📋 activity_log<br/>append-only")]
    M --> Y
    G --> Y

    V --> Z{{"Chính sách lưu trữ"}}
    Z -->|DELETE_AFTER_CONTRACT| Z1["🗑️ Xoá ảnh gốc<br/>giữ hash + thumbnail"]
    Z -->|KEEP_N_DAYS| Z2["Giữ N ngày rồi xoá"]

    style T0 fill:#fff9c4,stroke:#f57f17,stroke-width:3px
    style G fill:#fff9c4,stroke:#f57f17,stroke-width:3px
    style H fill:#fff9c4,stroke:#f57f17,stroke-width:3px
    style M fill:#c8e6c9
    style V fill:#c8e6c9
    style Y fill:#ffccbc
    style X1 fill:#ffcdd2
    style X2 fill:#ffe0b2
```

---

## 2.9. Sơ đồ triển khai

```mermaid
graph TB
    subgraph PC["💻 MÁY TÍNH WINDOWS 10/11 x64 — 8 GB RAM · 4 nhân · 3 GB trống"]
        direction TB

        subgraph INSTALL["📦 %LOCALAPPDATA%\\COCAS\\app\\ — chỉ đọc, không cần quyền Admin"]
            E1["ContractSystem.exe · 15 MB"]
            E2["cocas-backend\\ · 180 MB"]
            E3["postgres\\ · 250 MB"]
            E5["ocr-models\\ · 45 MB"]
        end

        subgraph RUNTIME["⚙️ Tiến trình lúc chạy — ⭐ 3 tiến trình · RAM nghỉ ~460 MB / đỉnh ~1.37 GB"]
            R1["ContractSystem.exe<br/>Tauri + WebView2 · ~120 MB"]
            R2["cocas-backend.exe<br/>FastAPI :&lt;cổng động&gt; · ~280 MB"]
            R3["postgres.exe<br/>:55432 · ~60 MB"]
        end

        subgraph DATA["💾 %LOCALAPPDATA%\\COCAS\\data\\ — ⭐ THỨ CẦN SAO LƯU"]
            D1[("pgdata\\")]
            D2[("vault\\ — mã hoá")]
            D3[("templates\\")]
            D4[("keys\\master.key.dpapi")]
        end

        subgraph MISC["🔧 Hỗ trợ"]
            M1[("config\\settings.toml")]
            M2[("logs\\ — 30 ngày")]
            M3[("backups\\*.cocasbak")]
        end

        R1 -.->|supervisor| R2
        R1 -.->|pg_ctl| R3
        R2 --> R3
        R2 -.->|lazy start| R4
        R2 --> DATA
        R2 --> MISC
        INSTALL -.->|nạp| RUNTIME
        DATA -->|"tự động hàng ngày<br/>+ nút Sao lưu ngay"| M3
    end

    EXT["💿 USB / Ổ đĩa ngoài"]
    M3 -.->|"người dùng chọn thư mục"| EXT

    style PC fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px
    style DATA fill:#fff9c4,stroke:#f57f17,stroke-width:3px
    style INSTALL fill:#e3f2fd,stroke:#1565c0
    style RUNTIME fill:#f3e5f5,stroke:#6a1b9a
```

---

## 2.10. Sơ đồ phụ thuộc theo tầng (kiểm chứng Dependency Rule)

```mermaid
graph RL
    subgraph L4["Presentation"]
        P1[api routers]
        P2[schemas]
        P3[middlewares]
        P4[react ui]
    end
    subgraph L3["Application"]
        A1[use_cases]
        A2[dto]
        A3[unit_of_work]
        A4[render_context_builder]
    end
    subgraph L2["Domain ★"]
        D1[entities]
        D2[value_objects]
        D3[domain_services]
        D4[ports]
        D5[exceptions]
        D6[validation rules]
    end
    subgraph L1["Infrastructure"]
        I1[persistence]
        I2[ocr]
        I3[documents]
        I4[storage]
        I5[security]
        I6[queue]
    end

    P1 --> A1
    P2 --> A2
    A1 --> D1
    A1 --> D3
    A1 --> D4
    A3 --> D4
    A4 --> D2
    I1 -.->|implements| D4
    I2 -.->|implements| D4
    I3 -.->|implements| D4
    I4 -.->|implements| D4
    I5 -.->|implements| D4
    I6 -.->|implements| D4

    CR["🔧 container.py — Composition Root<br/>(file DUY NHẤT biết cả 4 tầng)"]
    CR -.-> L1
    CR -.-> L3
    CR -.-> L4

    style L2 fill:#c8e6c9,stroke:#1b5e20,stroke-width:3px
    style CR fill:#fff9c4,stroke:#f57f17,stroke-width:2px
```

> **Kiểm chứng tự động:** `import-linter` với contract `layers` — CI đỏ nếu bất kỳ file nào trong `domain/` import từ `infrastructure/`, `application/` hay `presentation/`. Ngoại lệ duy nhất được khai báo: `container.py`.

---

[← 01 — Kiến trúc](01-kien-truc-tong-the.md) · [Mục lục](README.md) · [Tiếp: 03 — Luồng dữ liệu →](03-luong-du-lieu.md)
