# 11 — Cấu trúc thư mục & Thư viện

[← Mục lục](README.md)

**Cây thư mục theo Clean Architecture · ⭐ 38 thư viện Python** *(D2.1 bỏ `pypdf`)*

---

# PHẦN A — CẤU TRÚC THƯ MỤC

## 11.1. Cây thư mục kho mã nguồn

```
cocas/
│
├── backend/                          # ── Python · FastAPI · Clean Architecture
│   ├── src/cocas/
│   │   │
│   │   ├── domain/                   # 🟢 TẦNG DOMAIN — zero dependency
│   │   │   ├── entities/             #    Customer · Contract · ContractParty
│   │   │   │                         #    OcrSession · Template · TemplateVersion
│   │   │   │                         #    BankAccount · CardImage
│   │   │   ├── value_objects/        #    CitizenId · VietnamesePhone · EmailAddress
│   │   │   │                         #    BankAccountNumber · SecuritiesAccountNumber
│   │   │   │                         #    IssuePlace · IdCardDates · PersonName
│   │   │   │                         #    ConfidenceScore · StyledValue
│   │   │   ├── enums/                #    ContractStatus · FieldKey · OcrSessionStatus
│   │   │   ├── services/             #    IssuePlaceNormalizer · FieldFusionService
│   │   │   │                         #    CardValidityPolicy · ContractNumberGenerator
│   │   │   │                         #    ExportNameGenerator · template_variables
│   │   │   │                         # ⭐ value_formatter — bảng định dạng §9.7
│   │   │   ├── ports/                # ⭐ 19 interface — điểm thay thế mọi hạ tầng
│   │   │   │                         #    (đánh số 1–20, khuyết 13)
│   │   │   ├── events/               #    OcrCompleted · ContractGenerated · ...
│   │   │   ├── validation/           #    Rule objects · rule registry · RuleContext
│   │   │   └── exceptions.py         #    Cây ngoại lệ nghiệp vụ
│   │   │
│   │   ├── application/              # 🟣 TẦNG APPLICATION
│   │   │   ├── use_cases/
│   │   │   │   ├── ingestion/  ocr/  customer/  bank_account/
│   │   │   │   ├── template/  contract/
│   │   │   │   └── system/  backup/  reference/
│   │   │   ├── dto/                  #    DTO vào/ra của use case
│   │   │   ├── unit_of_work.py
│   │   │   ├── event_bus.py
│   │   │   ├── activity_log_service.py
│   │   │   ├── render_context_builder.py   # ⭐ Sinh dict + StyledValue (KHÔNG RichText)
│   │   │   └── pipelines/
│   │   │       └── extraction_pipeline.py  # ⭐ Điều phối 9 chặng OCR
│   │   │
│   │   ├── infrastructure/           # 🟠 TẦNG INFRASTRUCTURE
│   │   │   ├── persistence/
│   │   │   │   ├── models/           #    Lớp ORM SQLAlchemy
│   │   │   │   ├── repositories/     #    Triển khai IReadRepository/IWriteRepository
│   │   │   │   ├── mappers/          # ⭐ ORM model ⟷ Domain entity
│   │   │   │   └── session.py
│   │   │   ├── ocr/                  # ⭐ ĐIỂM THAY THẾ ENGINE
│   │   │   │   ├── preprocessing/    #    opencv_preprocessor.py (biến thể lười)
│   │   │   │   ├── classification/   #    heuristic_side_classifier.py
│   │   │   │   ├── channels/         #    qr_decoder.py · mrz_reader.py
│   │   │   │   ├── engines/          #    paddle_adapter.py · tesseract_adapter.py
│   │   │   │   │                     #    null_adapter.py
│   │   │   │   └── extraction/       #    zone_and_anchor_extractor.py
│   │   │   ├── documents/
│   │   │   │   ├── template_inspector.py     # ⭐ Port 20 — AST Jinja2 + quét marker
│   │   │   │   ├── docx_context_adapter.py   # ⭐ StyledValue → docxtpl.RichText
│   │   │   │   ├── docx_renderer.py          # ⭐ Port 12 — hai pha, trả byte (§12.11.2)
│   │   │   ├── storage/              # ⭐ Port 11
│   │   │   │   ├── path_guard.py             #    hình dạng → resolve → is_relative_to
│   │   │   │   └── encrypted_file_vault.py   #    AES-256-GCM dưới VAULT_KEY riêng
│   │   │   ├── security/             #    dpapi.py · crypto.py · blind_index.py
│   │   │   │                         #    local_token.py
│   │   │   ├── queue/                #    job_runner.py  ⭐ polling bảng `job`
│   │   │   ├── backup/               #    backup_service.py · restore_service.py
│   │   │   └── logging/              #    loguru_config.py · pii_filter.py
│   │   │
│   │   ├── presentation/             # 🔵 TẦNG PRESENTATION
│   │   │   ├── api/v1/routers/       #    system · upload · ocr · customer
│   │   │   │                         #    bank_account · template · contract
│   │   │   │                         #    reference · settings · activity_log
│   │   │   │                         #    backup · job · dashboard
│   │   │   ├── schemas/              #    Pydantic request/response
│   │   │   ├── middlewares/          #    local_token · correlation · errors
│   │   │   │                         #    security_headers
│   │   │   ├── dependencies.py
│   │   │   └── error_handlers.py
│   │   │
│   │   ├── config/                   #    Settings (pydantic-settings) · defaults.toml
│   │   ├── container.py              # ⭐ COMPOSITION ROOT — file DUY NHẤT biết cả 4 tầng
│   │   └── main.py                   #    Điểm vào FastAPI
│   │
│   ├── migrations/                   #    Alembic
│   │   ├── versions/                 #    20260811_001_initial_schema, ...
│   │   └── seeds/                    #    document_type · alias · province
│   │                                 #    bank · setting · 2 mẫu hợp đồng
│   ├── tests/
│   │   ├── unit/          (domain · application)
│   │   ├── integration/   (repos · ocr · documents · api · backup)
│   │   ├── e2e/           (luồng đầy đủ qua API)
│   │   ├── security/      (offline · traversal · ssti · pii-in-log)
│   │   ├── chaos/         (kill process · đầy đĩa · sửa file)
│   │   └── fixtures/      (golden_set · edge_set · smoke_set · templates)
│   ├── pyproject.toml
│   ├── requirements.lock
│   └── build.spec                    #    Cấu hình PyInstaller
│
├── shared/
│   └── validation_cases.json         # ⭐ Ca kiểm thử DÙNG CHUNG cho pytest và vitest
│
├── frontend/                         # ── React · TypeScript · MUI
│   ├── src/
│   │   ├── app/                      #    router · theme · providers · error boundary
│   │   ├── shared/
│   │   │   ├── api/                  #    client · interceptor X-Local-Token · error map
│   │   │   ├── components/           #    11 component dùng chung
│   │   │   ├── hooks/                #    useDraft · useJobPolling · useKeyboard
│   │   │   │                         #    useImageHighlight
│   │   │   ├── schemas/              #    Zod (viết tay, đồng bộ qua validation_cases)
│   │   │   ├── theme/  utils/  i18n/
│   │   ├── features/
│   │   │   ├── dashboard/
│   │   │   ├── wizard/               # ⭐ Tính năng lớn nhất
│   │   │   │   ├── steps/            #    TemplateStep · PartyStep · DoneStep
│   │   │   │   ├── panels/           #    OcrVerificationPanel
│   │   │   │   │                     #    SupplementaryInfoPanel
│   │   │   │   └── store.ts          #    Zustand + tự lưu nháp localStorage
│   │   │   ├── customers/  contracts/  templates/  settings/
│   │   └── main.tsx
│   ├── tests/                        #    vitest · playwright
│   ├── package.json  ·  vite.config.ts  ·  tsconfig.json
│
├── desktop/                          # ── Tauri (Rust)
│   ├── src/
│   │   ├── main.rs
│   │   ├── sidecar.rs                # ⭐ Supervisor: spawn · health · restart ×3
│   │   ├── postgres.rs               #    pg_ctl start/stop · initdb lần đầu
│   │   ├── token.rs                  #    Sinh Local Handshake Token
│   │   ├── dialogs.rs                #    Hộp thoại file/thư mục native
│   │   └── single_instance.rs        #    Named mutex Windows
│   ├── binaries/                     #    Sidecar đã build
│   ├── icons/
│   ├── tauri.conf.json               # ⭐ CSP nghiêm ngặt
│   └── Cargo.toml
│
├── resources/                        # ── Tài nguyên đóng gói kèm (KHÔNG trong Git)
│   ├── ocr-models/                   #    PP-OCRv4: det · rec · cls  (~45 MB)
│   ├── postgres/                     #    Nhị phân portable (~250 MB)
│   ├── fonts/                        #    Inter · JetBrains Mono
│   └── webview2/                     #    Bộ cài offline (~130 MB)
│
├── installer/                        # ── Đóng gói Windows
│   ├── nsis/                         #    Script NSIS · trang tuỳ chỉnh
│   ├── bootstrap/                    #    initdb · migrate · seed lần đầu
│   └── sign.ps1                      #    Ký số
│
├── docs/
│   ├── design/                       # ⭐ TÀI LIỆU NÀY — 14 file
│   ├── api/                          #    OpenAPI đã xuất
│   ├── user-manual/                  #    Hướng dẫn tiếng Việt có ảnh
│   └── operations/                   #    Cài đặt · sao lưu · khắc phục sự cố
│
├── scripts/
│   ├── fetch_resources.ps1           #    Tải tài nguyên nhị phân từ kho nội bộ
│   ├── benchmark_ocr.py              #    Chạy Golden Set, xuất bảng chỉ số
│   ├── verify_offline.py             # ⭐ Kiểm tra không có kết nối ra ngoài
│   └── build_all.ps1
│
├── .github/workflows/                #    (hoặc CI nội bộ)
├── CLAUDE.md                         # ⭐ Chỉ dẫn cho AI agent — trỏ về docs/design
├── README.md  ·  CHANGELOG.md  ·  LICENSE
```

---

## 11.2. Vai trò từng thư mục gốc

| Thư mục | Vai trò | Ai đụng vào |
|---|---|---|
| `backend/` | Toàn bộ logic nghiệp vụ, API, OCR, sinh tài liệu | Backend dev |
| `shared/` | ⭐ File ca kiểm thử dùng chung cho cả hai phía | Cả hai |
| `frontend/` | Giao diện | Frontend dev |
| `desktop/` | Vỏ Tauri, supervisor tiến trình, tích hợp Windows | Ít thay đổi sau khi ổn định |
| `resources/` | Tài nguyên nhị phân đóng gói kèm — ⭐ **không nằm trong Git** | Release engineer |
| `installer/` | Đóng gói, ký số, bootstrap lần đầu | Release engineer |
| `docs/` | Tài liệu thiết kế, API, hướng dẫn | Cả nhóm |
| `scripts/` | Công cụ hỗ trợ phát triển và kiểm tra | Cả nhóm |

---

## 11.3. Bốn quyết định về cấu trúc

| # | Quyết định | Lý do |
|---|---|---|
| 1 | ⭐ **Backend chia theo TẦNG, frontend chia theo TÍNH NĂNG** | Backend có ràng buộc Dependency Rule cần cưỡng chế bằng cấu trúc thư mục (`import-linter` kiểm tra được). Frontend không có ràng buộc đó — chia theo tính năng giúp mọi thứ liên quan nằm cạnh nhau |
| 2 | ⭐ `resources/` **không nằm trong Git** | ~850 MB nhị phân sẽ làm kho mã không dùng được. Dùng `scripts/fetch_resources.ps1` tải từ kho nội bộ, hoặc Git LFS |
| 3 | ⭐ `shared/validation_cases.json` nằm ở **gốc kho**, không thuộc backend hay frontend | Cả hai phía đều đọc nó trong test. Đặt ở gốc thể hiện rõ nó là hợp đồng chung |
| 4 | ⭐ `container.py` là **file duy nhất** import từ cả 4 tầng | Mọi file khác chỉ import theo chiều cho phép. `import-linter` cấu hình ngoại lệ đúng một file này |

---

## 11.4. Thư mục dữ liệu lúc chạy

```
%LOCALAPPDATA%\COCAS\
├── app\        ← CHỈ ĐỌC   · installer ghi · xoá được khi gỡ cài
│   ├── ContractSystem.exe
│   ├── cocas-backend\   (PyInstaller onedir)
│   ├── ocr-models\  postgres\
├── data\       ← ĐỌC-GHI   · ⭐ ĐÂY LÀ THỨ CẦN SAO LƯU
│   ├── pgdata\
│   ├── vault\  templates\  lo-profile\
│   ├── keys\master.key.dpapi
│   ├── config\settings.toml
│   ├── logs\
│   └── backups\
└── runtime.json  ← cổng động, PID — sinh lúc chạy, tự xoá
```

> ⭐ **Tách bạch `app/` chỉ-đọc và `data/` đọc-ghi** cho phép nâng cấp phiên bản mà không đụng dữ liệu người dùng, và gỡ cài mặc định giữ lại dữ liệu.

---

## 11.5. Cưỡng chế Dependency Rule bằng `import-linter`

Cấu hình contract kiểu `layers` trong `pyproject.toml`:

```
Tầng (từ ngoài vào trong):
  cocas.presentation
  cocas.application
  cocas.domain

Contract: layered_architecture
  - `cocas.domain` KHÔNG được import từ bất kỳ tầng nào khác
  - `cocas.application` KHÔNG được import `cocas.infrastructure`
  - `cocas.infrastructure` CHỈ được import `cocas.domain` (để implement Port)

Ngoại lệ duy nhất: `cocas.container`
```

**Contract bổ sung — `forbidden`:**

| Module | Cấm import |
|---|---|
| `cocas.domain.*` | `fastapi`, `sqlalchemy`, `pydantic`, `paddleocr`, `cv2`, `docxtpl`, `loguru`, `os`, `pathlib` |
| `cocas.application.*` | `sqlalchemy`, `fastapi`, `docxtpl`, `cv2` |

⭐ **CI đỏ nếu vi phạm.** Đây là cơ chế duy nhất giữ được Clean Architecture theo thời gian.

---

# PHẦN B — THƯ VIỆN PYTHON

## 11.6. Phụ thuộc production (⭐ 38)

### Web & API (5)

| Thư viện | Phiên bản | Mục đích | Ghi chú |
|---|---|---|---|
| `fastapi` | `0.115.*` | Framework API | Async, Pydantic v2 tích hợp, OpenAPI tự sinh |
| `uvicorn[standard]` | `0.32.*` | ASGI server | ⭐ Chạy **1 worker** (ADR-06) |
| `pydantic` | `2.9.*` | Validation & serialization | v2 nhanh gấp 5–50× v1 (lõi Rust) |
| `pydantic-settings` | `2.6.*` | Cấu hình phân lớp | default → TOML → env → DB |
| `python-multipart` | `0.0.12` | Xử lý multipart upload | Bắt buộc cho FastAPI file upload |

### Cơ sở dữ liệu (4)

| Thư viện | Phiên bản | Mục đích | Ghi chú |
|---|---|---|---|
| `sqlalchemy[asyncio]` | `2.0.*` | ORM & Core | API 2.0, hỗ trợ async, typing tốt |
| `asyncpg` | `0.30.*` | Driver PostgreSQL async | Nhanh nhất cho async |
| `psycopg[binary]` | `3.2.*` | Driver đồng bộ | Cho Alembic và job nền |
| `alembic` | `1.14.*` | Migration | |

### OCR & Xử lý ảnh (6)

| Thư viện | Phiên bản | Mục đích | ⚠️ Ghi chú |
|---|---|---|---|
| `paddlepaddle` | `2.6.*` | Nền tảng suy luận | ⭐ Bản **CPU-only** — bản GPU nặng 2 GB |
| `paddleocr` | `2.9.*` | OCR | ⭐ **Ghim chặt** — API đổi thường xuyên giữa các bản |
| `opencv-python-headless` | `4.10.*` | Xử lý ảnh | ⭐ Bản `headless` — không kéo GUI Qt (~200 MB) |
| `pillow` | `11.0.*` | Đọc/ghi/re-encode ảnh | Kiểm định và làm sạch ảnh nạp vào |
| `zxing-cpp` | `3.1.*` | ⭐ Giải mã QR (kênh hạng A) | Wheel tự chứa — **không cần model, không cần DLL hệ thống**. Thay `pyzbar` từ 2026-08-09, lý do đo thật ở [`07-module-ocr.md §7.4.3`](07-module-ocr.md#743-zxingqrdecoder) |
| `numpy` | `>=1.26,<2.0` | Mảng số | ⭐ **Ghim `<2.0`** — PaddleOCR chưa tương thích NumPy 2 |

### Xử lý văn bản (2)

| Thư viện | Phiên bản | Mục đích |
|---|---|---|
| `rapidfuzz` | `3.10.*` | So khớp mờ — nhanh hơn `fuzzywuzzy` ~10×, giấy phép MIT |
| `python-dateutil` | `2.9.*` | Phân tích ngày linh hoạt |

### Sinh tài liệu (⭐ 3)

| Thư viện | Phiên bản | Mục đích | Ghi chú |
|---|---|---|---|
| `docxtpl` | `0.18.*` | Render DOCX từ template | Bao gồm `RichText` cho chữ đậm |
| `python-docx` | `1.1.*` | Thao tác DOCX cấp thấp | Phụ thuộc của docxtpl; dùng trực tiếp để kiểm thử |
| `jinja2` | `3.1.*` | Template engine | ⭐ Dùng `SandboxedEnvironment` |

### Bảo mật (4)

| Thư viện | Phiên bản | Mục đích | Ghi chú |
|---|---|---|---|
| `cryptography` | `43.*` | AES-256-GCM, HKDF | Thư viện chuẩn của Python |
| `argon2-cffi` | `23.1.*` | ⭐ Dẫn xuất khoá từ **mật khẩu backup** | *(Không dùng cho đăng nhập — hệ thống không có đăng nhập)* |
| `pywin32` | `308` | ⭐ Windows DPAPI, quản lý tiến trình, Credential Manager | Chỉ Windows |
| `python-magic-bin` | `0.4.14` | Phát hiện MIME từ magic bytes | ⭐ Bản `-bin` đã kèm `libmagic` cho Windows |

### Hạ tầng (7)

| Thư viện | Phiên bản | Mục đích | Ghi chú |
|---|---|---|---|
| `loguru` | `0.7.*` | Logging | API đơn giản, xoay vòng/nén sẵn có |
| `tenacity` | `9.0.*` | Retry có backoff | Cho job nền |
| `tomlkit` | `0.13.*` | Đọc/ghi TOML giữ định dạng | Cho `settings.toml` sửa được qua UI |
| `uuid-utils` | `0.10.*` | ⭐ UUIDv7 | `uuid` chuẩn chưa có v7 |
| `psutil` | `6.1.*` | Giám sát tiến trình, dung lượng đĩa | Health check, đo RAM/đĩa |
| `orjson` | `3.10.*` | JSON nhanh | Response lớn và log có cấu trúc |
| `anyio` | `4.6.*` | Tiện ích async (đi kèm FastAPI) | `run_in_executor` cho CPU-bound |

> **Đã bỏ so với thiết kế ban đầu:** `pyjwt[crypto]` (không có JWT), `redis`/`arq`/`hiredis` (không có Redis), `passlib` (không có đăng nhập).

---

## 11.7. Phụ thuộc phát triển

| Thư viện | Phiên bản | Mục đích |
|---|---|---|
| `pytest` · `pytest-asyncio` · `pytest-cov` · `pytest-mock` | `8.3.*` | Khung kiểm thử |
| `hypothesis` | `6.*` | Property-based testing cho Value Object |
| `factory-boy` · `faker` | | Dữ liệu thử — ⭐ dùng locale `vi_VN` |
| `httpx` | `0.27.*` | Client test API |
| `testcontainers[postgres]` | | PostgreSQL thật cho integration test |
| `ruff` | `0.8.*` | ⭐ Lint + format (thay `flake8` + `black` + `isort`) |
| `mypy` | `1.13.*` | Kiểm tra kiểu tĩnh, chế độ `strict` cho `domain/` và `application/` |
| ⭐ `import-linter` | `2.1.*` | **Cưỡng chế Dependency Rule** — CI đỏ nếu Domain import Infrastructure |
| `bandit` | `1.8.*` | Quét bảo mật mã nguồn |
| `pip-audit` | `2.7.*` | Quét CVE trong phụ thuộc |
| `detect-secrets` · `gitleaks` | | Chặn bí mật lọt vào Git |
| `radon` | | Đo độ phức tạp vòng |
| `pyinstaller` | `6.11.*` | Đóng gói `.exe` |
| `pre-commit` | | Chạy ruff/mypy/gitleaks trước mỗi commit |

---

## 11.8. ⭐ Bốn lưu ý quan trọng khi đóng gói

| # | Vấn đề | Cách xử lý |
|---|---|---|
| 1 | ⭐ **PaddleOCR tải model từ mạng lần đầu** | **Vi phạm P-01.** Bắt buộc chỉ định tường minh `det_model_dir`, `rec_model_dir`, `cls_model_dir` trỏ vào `resources/ocr-models/`. **Test bắt buộc: chạy trên máy đã ngắt mạng** |
| 2 | **PyInstaller không tự phát hiện dữ liệu của PaddleOCR/OpenCV** | Khai báo tường minh trong `build.spec`: `datas` cho model + dữ liệu `paddleocr`, `binaries` cho DLL `libmagic`, `hiddenimports` cho module nạp động |
| 3 | ⭐ **NumPy 2.0 phá vỡ PaddleOCR** | Ghim `numpy>=1.26,<2.0`. ⭐ Có **test kiểm tra phiên bản lúc khởi động** |
| 4 | **Kích thước gói** | `paddlepaddle` CPU ~600 MB khi cài, sau khi PyInstaller lọc còn ~180 MB. ⭐ Dùng UPX **nhưng loại trừ DLL của OpenCV và Paddle** — nén chúng gây crash |

---

## 11.9. Chính sách phiên bản

| Nguyên tắc | Chi tiết |
|---|---|
| **Ghim chính xác trong `requirements.lock`** | Bản build phải tái lập được |
| `pyproject.toml` dùng khoảng | `~=` cho bản vá, `>=,<` cho thư viện quan trọng |
| ⭐ **Ghim tuyệt đối** | `paddlepaddle`, `paddleocr`, `numpy` — ba thư viện phá vỡ tương thích thường xuyên nhất |
| Cập nhật phụ thuộc | Hàng quý, ⭐ **có chạy toàn bộ Golden Set** để so sánh độ chính xác OCR trước/sau |
| CVE nghiêm trọng | Cập nhật ngay, phát hành bản vá |
| ⭐ **Kiểm tra giấy phép** | Toàn bộ phụ thuộc phải là MIT / BSD / Apache-2.0. Không dùng GPL trong mã liên kết |

> ⭐ **D2.1 — mục giấy phép của LibreOffice (MPL-2.0) đã bỏ cùng chính LibreOffice.** Không còn tiến trình con nào ngoài PostgreSQL.

---

## 11.10. Thư viện Frontend chính

| Thư viện | Phiên bản | Mục đích |
|---|---|---|
| `react` · `react-dom` | `18.3.*` | Framework UI |
| `typescript` | `5.6.*` | Kiểu tĩnh |
| `@mui/material` · `@mui/icons-material` | `5.16.*` | Design system |
| `@emotion/react` · `@emotion/styled` | `11.*` | CSS-in-JS (phụ thuộc của MUI) |
| `@tanstack/react-query` | `5.*` | Trạng thái máy chủ, polling, cache |
| `zustand` | `5.*` | Trạng thái wizard + persist localStorage |
| `react-router-dom` | `6.*` | Định tuyến |
| `react-hook-form` | `7.*` | Form hiệu năng cao |
| `zod` · `@hookform/resolvers` | `3.*` | Validation client |
| `recharts` | `2.*` | Biểu đồ Dashboard |
| `vite` | `5.*` | Build tool |
| `vitest` · `@testing-library/react` | | Unit test |
| `@playwright/test` | | E2E test |

> ⭐ **Không dùng:** bất kỳ bộ xem tài liệu nhúng nào (D2.1 — đầu ra `.docx` mở bằng Word) · thư viện icon từ CDN · Google Fonts (font nhúng woff2).

---

[← 10 — Bảo mật & Logging](10-bao-mat-va-logging.md) · [Mục lục](README.md) · [Tiếp: 12 — Đặc tả module →](12-dac-ta-module.md)
