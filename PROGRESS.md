# COCAS Development Progress

**Project:** COCAS v1.0 — Desktop app tự động tạo hợp đồng từ ảnh CCCD  
**Target:** 12.5 tuần, 2 người (hoặc ~24 tuần nếu 1 người)  
**Status:** In Progress

---

## 📊 Timeline Overview

```
P0: Chuẩn bị        [====] ✅ DONE (2026-08-11)
P1: Nền tảng        [====] ✅ DONE (2026-08-09)
P2: OCR Module      [====] 🔄 MÃ NGUỒN XONG (4/4 tuần) — chờ Golden Set ⭐ Critical path
P3: Nghiệp vụ       [====] 🔄 module 6/6 xong · module 7 làm 16/62 endpoint — ⭐ MỐC M3 ĐẠT
P4: Giao diện       [    ] ⏳ TODO (3 tuần)
P5: Desktop         [    ] ⏳ TODO (2 tuần)
P6: Hoàn thiện      [    ] ⏳ TODO (2 tuần)
P7: Nghiệm thu      [    ] ⏳ TODO (1 tuần)
```

---

## 📋 Detailed Progress

### ✅ P0 — Chuẩn bị (1 tuần)
**Completed:** 2026-08-11  
**Commit:** [`c359799`](https://github.com/Dezz3z/CCCD_OCR_NEW/commit/c359799)

**Deliverables:**
- [x] Cấu trúc kho mã theo Clean Architecture
  - Backend: 4 tầng (domain, application, infrastructure, presentation)
  - Frontend: chia theo tính năng (dashboard, wizard, customers, contracts, templates, settings)
  - Desktop: Tauri skeleton
- [x] Python dependencies (39 libs) đã ghim
  - Web: FastAPI 0.115, Uvicorn 0.32, Pydantic v2 2.9
  - DB: SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.14
  - OCR: PaddleOCR 2.9, NumPy <2.0 (CRITICAL), OpenCV headless 4.10
  - Documents: docxtpl 0.18, Jinja2 3.1 (SandboxedEnvironment)
  - Security: cryptography 43, pywin32 308, argon2-cffi 23.1
  - Infrastructure: Loguru 0.7, Tenacity 9.0, psutil 6.1
- [x] Node.js dependencies
  - React 18.3, TypeScript 5.6, MUI 5.16
  - TanStack Query 5, Zustand 5, React Hook Form 7
  - Vite 5.4, Vitest 2.1
- [x] CI/CD: GitHub Actions workflow
  - import-linter: Cưỡng chế Dependency Rule
  - mypy --strict: domain + application
  - ruff: lint + format
  - pytest + vitest
- [x] Pre-commit hooks (ruff, mypy, gitleaks)
- [x] shared/validation_cases.json (7 Value Objects)
- [x] Alembic async migration framework
- [x] Foundation files (main.py, container.py, exceptions, middlewares)

**Verification:**
- ✅ Directory structure complete
- ✅ pyproject.toml & package.json configured
- ✅ CI workflow ready
- ✅ Pre-commit hooks ready

---

### ✅ P1 — Nền tảng (1.5 tuần)
**Status:** DONE
**Completed:** 2026-08-09

**Deliverables (from roadmap § 14.3):**
- [x] ⭐ **Domain layer đầy đủ (10 VO, 8 Entity, 5 Service, 18 Port) — HOÀN THÀNH**
  - [x] **Value Objects (10/10)** — CitizenId, VietnamesePhone, EmailAddress, BankAccountNumber, SecuritiesAccountNumber, IssuePlace, IdCardDates, PersonName, ConfidenceScore, StyledValue. mypy --strict sạch · ruff sạch · import-linter sạch (`backend/src/cocas/domain/value_objects/`)
  - [x] **Enums (14/14)** — CardSide, OcrSessionStatus, FieldKey, FieldSource, JobType, JobStatus, ContractStatus (đã sửa đúng 9 giá trị theo §4.3.3), EntityType, DocType, Gender, DataQuality, TemplateValidationStatus, ActivityOutcome, BackupStatus (`backend/src/cocas/domain/enums/`)
  - [x] **Exception tree mở rộng** — 23 lớp lỗi lá theo đúng bảng "Ném ra" ở từng module §12 (OcrProcessingError/DocumentGenerationError/StorageError/CryptoError/PersistenceError/BackupError làm gốc phân nhóm), `code`/`field`/`hint` override trên `DomainException` (`backend/src/cocas/domain/exceptions.py`)
  - [x] **Entities (8/8)** — Customer, Contract (state machine + DB-03/DB-09 optimistic lock), ContractParty, OcrSession, Template, TemplateVersion, BankAccount, CardImage (`backend/src/cocas/domain/entities/`)
  - [x] **Domain Services (5/5)** — IssuePlaceNormalizer (4 tầng + rapidfuzz), FieldFusionService (8 quy tắc hợp nhất), CardValidityPolicy, ContractNumberGenerator, ExportNameGenerator (`backend/src/cocas/domain/services/`)
  - [x] **18 Ports** — 7 OCR (`ocr.py`) · 5 persistence (`persistence.py`, incl. `IAliasRepository`) · storage · 2 documents · queue · crypto · 2 system. Mỗi Port có fake/null (`tests/fixtures/fake_ports.py`, tiêu chí nghiệm thu §12.19)
  - ⭐ **405 test domain xanh · `mypy --strict` sạch (55 file) · `ruff` sạch · `import-linter` 0 vi phạm (4/4 contract)**
- [x] ⭐ **19 bảng CSDL + 8 migrations — ĐÃ XÁC THỰC TRÊN POSTGRESQL 18.4 THẬT** (SQLAlchemy 2.0 ORM + Alembic, `backend/src/cocas/infrastructure/persistence/models/`, `backend/migrations/versions/`)
  - Migration 001 `extensions` → 002 `initial_schema` (đảo thứ tự so với tài liệu gốc — lý do trong docstring migration) → 003-008 `seed_*` (đổi tên rút gọn — lý do dưới)
  - **`upgrade head → downgrade base → upgrade head` chạy thành công trên PostgreSQL 18.4 thật** (2026-08-09, DB cài bởi người dùng tại `D:\Software\PostgreSQL`) — đúng tiêu chí nghiệm thu P1. Đã kiểm tra thêm: chạy lại `upgrade head` trên DB đã migrate không lỗi/không trùng dữ liệu (idempotent), toàn bộ 19 bảng + đủ số dòng seed (1/16/63/10/28/2) khớp kỳ vọng
  - 85 test cấu trúc qua `Base.metadata` + biên dịch DDL Postgres thật + kiểm tra đồ thị revision (không cần kết nối) — 0 lỗi
  - ⭐ **2 lỗi thật chỉ phát hiện được nhờ chạy trên Postgres thật** (không thể bắt bằng introspection/biên dịch DDL đơn thuần):
    1. `ocr_session` có 2 FK cùng trỏ `card_image` (front/back) → cùng bị đặt trùng tên theo `naming_convention` mặc định → Postgres từ chối tạo bảng (`DuplicateObjectError`). Đã đặt tên tường minh riêng cho từng FK
    2. 4/8 revision id dài quá 32 ký tự → vỡ `UPDATE alembic_version` giữa chừng vì cột `version_num` của chính Alembic là `VARCHAR(32)` cứng, không có tham số nới. Đã rút gọn tên + thêm test tĩnh canh giữ giới hạn này (`tests/unit/migrations/test_revision_ids.py`)
  - ⭐ Sửa số liệu tài liệu: "18 bảng" → **19 bảng** (04-co-so-du-lieu.md §4.4.15 gộp 2 bảng dưới 1 tiêu đề) — đã cập nhật CLAUDE.md, README.md, roadmap
- [x] **Dữ liệu seed (idempotent, `ON CONFLICT`/kiểm tồn tại trước khi insert)**
  - `document_type`: 1 bản ghi CCCD_CHIP (⚠️ `zone_map` là placeholder, chưa hiệu chỉnh — cần Golden Set)
  - `normalization_alias`: đủ 16 bản ghi theo đúng bảng seed §4.4.14
  - `province_code`: đủ 63 tỉnh — mã đối chiếu 3 nguồn độc lập trong phiên này
  - `bank_directory`: **10/50 ngân hàng** (chỉ những NH tài liệu nêu rõ độ dài STK). Người dùng xác nhận 2026-08-09: tên NH/số TK khách hàng sẽ tự nhập qua UI khi dùng thật — không cần mở rộng danh mục 50 NH ngay bây giờ
  - `system_setting`: đủ 28 khoá cấu hình mặc định theo §4.4.17
  - `contract_template`: 2 mẫu `01A_HD_GDN`, `01A_GDKQ` (⚠️ chưa có `active_version_id` — cần 2 file `.docx` thật). `export_name_pattern` của GDKQ **đã được người dùng xác nhận 2026-08-09**: `01A_GDKQ - {full_name}`
- [x] ⭐ **Repository + UnitOfWork — ĐÃ XÁC THỰC TRÊN POSTGRESQL THẬT** (`backend/src/cocas/infrastructure/persistence/repositories/`, `unit_of_work.py`)
  - Base chung `SqlAlchemyRepository[TEntity, TModel]`: get/list/exists/add/update qua `Specification`, dịch `IntegrityError→DuplicateEntityError`, `OperationalError→DatabaseUnavailableError`, khoá lạc quan qua `expected_version`
  - 7/8 repository đầy đủ: CardImage, OcrSession, Template, TemplateVersion, ContractParty, **Customer** (mã hoá/giải mã/blind-index/che PII đầy đủ), BankAccount
  - ⚠️ **`Contract` chưa có repository** — `render_snapshot_enc`/`snapshot_sha256` là `NOT NULL` trong schema nhưng entity `Contract` (đã chốt ở module Entities) không mang theo bytes đã mã hoá, chỉ có hash. Bên tạo ra bytes đó (`RenderContextBuilder`/`DocxRenderer`) chưa tồn tại tới P3 — cố làm repository bây giờ sẽ đoán sai hình dạng. Hoãn có chủ đích (P-10)
  - `SqlAlchemyUnitOfWork`: 1 transaction/UoW, tự rollback khi thoát khối `async with` mà chưa `commit()`
  - **16/16 test tích hợp xanh trên PostgreSQL 18.4 thật** (`tests/integration/persistence/`, gate qua biến môi trường `COCAS_TEST_DATABASE_URL` — không có mật khẩu nào lọt vào file đã commit) — bao gồm đúng ⭐ **kịch bản mốc demo M1**: tạo Customer giả, đọc lại, xác nhận `id_number_enc` là nhị phân không đọc được qua SQL thô
  - ⭐ **3 lỗi thật chỉ phát hiện được nhờ chạy thật** (không thể bắt bằng test đơn vị/introspection):
    1. Fixture test tự tạo bảng bằng `create_all()` bỏ qua migration 001 → thiếu extension `pg_trgm`/`pgcrypto`. Đã thêm vào fixture
    2. `pytest-asyncio` 0.24: fixture session-scope + test function-scope loop khác nhau → asyncpg `"Future attached to a different loop"`. Đã đồng bộ về `function` scope (cả `asyncio_default_fixture_loop_scope` trong `pyproject.toml` lẫn engine fixture)
    3. ⭐ **Nghiêm trọng nhất — vi phạm DB-12 trên toàn schema:** mọi cột `Mapped[datetime]` trong 15 bảng đều thiếu `timezone=True`, nên migration (gọi thẳng `Base.metadata.create_all()`) đã tạo ra `TIMESTAMP WITHOUT TIME ZONE` thay vì `TIMESTAMPTZ` — chỉ lộ ra khi asyncpg từ chối mã hoá datetime có tzinfo vào cột không tzinfo (`TypeError: can't subtract offset-naive and offset-aware datetimes`). Sửa một chỗ duy nhất: `type_annotation_map = {datetime: DateTime(timezone=True)}` trên `Base` — verify lại bằng `information_schema.columns`, xác nhận `timestamp with time zone`, và chạy lại **toàn bộ chu trình `upgrade head → downgrade base → upgrade head`**
- [x] ⭐ **Crypto Service (AES-256-GCM, DPAPI, blind index) — ĐÃ CHẠY THẬT VỚI DPAPI WINDOWS** (`backend/src/cocas/infrastructure/security/`)
  - `DpapiKeyManager` (`dpapi.py`): load-or-create KEK, bọc bằng DPAPI thật (`win32crypt.CryptProtectData/CryptUnprotectData` — test thật trên máy này, không mock), write-temp→verify→rename
  - `DpapiCryptoService`/`NullCryptoService` (`crypto.py`): AES-256-GCM đúng định dạng ô `version(1)‖nonce(12)‖ciphertext‖tag(16)`, HKDF tách PEPPER/VAULT_KEY từ KEK
  - `blind_index.py`: chuẩn hoá tái dùng trực tiếp từ 5 Value Object (không lặp lại regex)
  - 98 test xanh: round-trip, chống hoán vị ô qua AAD, chống giả mạo, nonce không lặp lại, DPAPI thật (tạo/đọc lại/khôi phục)
  - ⭐ **2 lỗi thật phát hiện khi chạy test** (không phải suy luận tĩnh): (1) nhầm `hashlib.sha256()` với `cryptography.hazmat.primitives.hashes.SHA256()` cho HKDF; (2) **lỗ hổng đụng độ blind-index chéo cột** — công thức gốc trong tài liệu `HMAC-SHA256(PEPPER, normalize(value))` không trộn tên trường, nên SĐT và số TK ngân hàng cùng chuỗi số sẽ ra cùng blind index. Đã sửa cả tài liệu (04, 12) và code: `HMAC-SHA256(PEPPER, field_name ‖ normalize(value))`
- [x] ⭐ **Logging (Loguru + PII filter) — HOÀN THÀNH** (`backend/src/cocas/infrastructure/logging/`)
  - `loguru_config.py`: 3 sink theo đúng §10.8.1 — console (dev), `app.log` (INFO, JSON, xoay hàng ngày, giữ 30 ngày), `error.log` (ERROR, JSON + traceback, xoay hàng tuần, giữ 90 ngày). `logger.configure(patcher=...)` gắn PII filter + `correlation_id`/`user` vào **mọi** bản ghi qua `logger` toàn cục — không cần import một instance riêng
  - `correlation_id` truyền qua `contextvars` (`bind_correlation_id`/`get_correlation_id`, §10.10) — tự động xuyên suốt `await`, không cần truyền tay
  - `pii_filter.py`: 2 lớp — `redact_text()` quét hình dạng regex (CCCD/SĐT/TK ngân hàng/TK chứng khoán/email theo đúng bảng §10.9) trên `message`; `redact_context()` quét theo **tên khoá** (đệ quy qua dict/list) cho các giá trị không có hình dạng nhận diện được (họ tên → viết tắt, địa chỉ → chỉ giữ tỉnh/thành, mật khẩu/token/QR-MRZ thô → `[REDACTED]`)
  - ⭐ **Test hồi quy bắt buộc theo CI** (`tests/security/test_pii_in_logs.py`, marker `security`): chạy luồng nghiệp vụ mẫu qua logger thật, `grep` toàn bộ nội dung `app.log`/`error.log` tìm 4 giá trị PII đúng theo bảng §10.9 (`001199012345`, `0912345678`, `nguyenvanan@example.com`, `008C123456`) — **0 kết quả**. Đây là lớp phòng thủ cuối, quét cả file thô chứ không chỉ trường `message`
  - ⭐ **2 lỗ hổng thật phát hiện khi viết test này** (không lộ ra khi chỉ đọc code):
    1. `diagnose=True` (mặc định của Loguru) in giá trị biến cục bộ vào traceback — patcher chỉ sửa `record["message"]`/`record["extra"]`, không chạm vào bộ dựng traceback, nên PII trong một biến cục bộ tại nơi crash vẫn lọt ra ngoài. Đã chốt `diagnose=False` trên cả 2 sink file
    2. `str(exception)` (dòng tóm tắt "ValueError: ...") không đi qua `record["message"]` — một exception dựng bằng f-string chứa PII runtime (`ValueError(f"... {id_number} ...")`) vẫn lọt ra dù `diagnose=False`. Đã thêm `_redact_exception_value()`: sửa `exc.args` tại chỗ (đệ quy qua `__cause__`/`__context__`) trước khi Loguru render — không dựng lại exception (giữ nguyên tương thích với constructor tuỳ biến như `TemplateSyntaxError(line, detail)`)
  - ⭐ Sửa tài liệu: `10-bao-mat-va-logging.md` §10.9 — ví dụ SĐT che sai (6 chấm thay vì 7, không khớp độ dài `0912345678` 10 ký tự − 3 số cuối)
  - 36 test đơn vị + tích hợp (`tests/unit/infrastructure/logging/`, `tests/security/`) — sink tạo đúng file, JSON hợp lệ, correlation_id gắn đúng, PII bị che trước khi ghi, traceback không rò biến cục bộ
- [x] ⭐ **Port 16/17 sản xuất (`SystemClock`, `Uuid7Generator`) — HOÀN THÀNH** (`backend/src/cocas/infrastructure/system/`) — UUIDv7 qua `uuid_utils` (đã ghim `0.10.*`), 7 test xanh (đơn điệu theo thời gian, duy nhất, đúng version)
- [x] ⭐ **Composition Root (`container.py`) — HOÀN THÀNH, nối toàn bộ đồ thị phụ thuộc thật**
  - `Container.__init__(settings)`: cấu hình logging trước tiên → `DpapiKeyManager(settings.dpapi_key_path).load_or_create_kek()` → `DpapiCryptoService(kek)` → `SystemClock`/`Uuid7Generator` → `create_async_engine(settings.database_url)` + `async_sessionmaker`
  - `Container.unit_of_work()`: factory trả về `SqlAlchemyUnitOfWork` mới mỗi lần gọi (1 transaction/lời gọi, đúng mẫu đã dùng ở test tích hợp module 9), không giữ 1 UoW dùng chung
  - `Settings` thêm `dpapi_key_path` (mặc định `%LOCALAPPDATA%\COCAS\data\keys\master.key.dpapi`, tính bằng `default_factory` chứ không phải hằng số ở thời điểm định nghĩa lớp)
  - `main.py`: `lifespan` gọi `init_container(settings)` lúc khởi động, gắn vào `app.state.container`, gọi `container.close()` (đóng connection pool) lúc tắt — đã kiểm bằng `TestClient` thật (kích hoạt đúng vòng đời FastAPI, không mock)
  - 8 test đơn vị (`tests/unit/test_container.py`, `tests/unit/test_main_app_lifecycle.py`): dựng đủ dependency, tái sử dụng KEK giữa 2 container từ cùng settings, `unit_of_work()` trả instance mới mỗi lần, vòng đời lifespan thật qua `TestClient`
  - ⚠️ **Không có "chế độ dev dùng `NullCryptoService`"** — Container luôn dùng `DpapiCryptoService` thật, nhất quán với P-11 (đúng một mục tiêu triển khai: Windows). `NullCryptoService`/`FrozenClock`/`SequentialIdGenerator` chỉ tồn tại trong `tests/fixtures/fake_ports.py`, không bao giờ được Container sản xuất tham chiếu tới
- [x] ⭐ **Build `.exe` thử lần đầu (PyInstaller) — HOÀN THÀNH** (`backend/build.spec`, `backend/scripts/demo_m1_customer.py`)
  - ⭐ **Mốc demo M1 — chạy bằng script độc lập, không chỉ test tích hợp:** `scripts/demo_m1_customer.py` dựng `Container` thật (DPAPI thật, chưa mock) trên CSDL demo `cocas_m1_demo` (migrate bằng `alembic upgrade head` thật), tạo Customer giả qua repository, đọc lại giải mã đúng, rồi đọc THÔ cột `id_number_enc` bằng SQL trực tiếp (bỏ qua repository/crypto) và xác nhận chuỗi CCCD gốc không xuất hiện trong 41 byte nhị phân — đúng tiêu chí mốc M1 (§14.3). Script tự dọn dẹp bản ghi + CSDL demo sau khi chạy; mật khẩu Postgres dùng tạm qua biến môi trường/`alembic.ini` sửa-rồi-revert, không lọt vào Git (đã `grep` xác nhận 0 kết quả)
  - `build.spec`: đóng gói `cocas.main` (FastAPI backend) kiểu `onedir` theo đúng §13.13/§11.8 — `hiddenimports` cho `uvicorn.protocols.*`/`alembic.ddl.postgresql`, `binaries` tường minh cho `libzbar-64.dll`/`libiconv.dll` (pyzbar) và `libmagic.dll` (python-magic-bin) vì nạp qua ctypes không qua `import`, `datas` gồm dữ liệu nội bộ gói `paddleocr` + thư mục `migrations/`, `excludes` bớt `tkinter`/`matplotlib`/`PyQt5`/`IPython`/`pytest`/`notebook`, `upx_exclude` cho DLL OpenCV/Paddle (nén UPX các DLL này gây crash — đã ghi rõ trong tài liệu)
  - ⭐ **1 lỗi đóng gói thật phát hiện ngay ở lần build đầu tiên** (đúng mục đích của bước này — bắt lỗi ở P1 thay vì đợi tới P6): liệt kê `"asyncpg.pgproto"` trong `hiddenimports` không đủ — asyncpg tự nạp submodule Cython biên dịch sẵn `asyncpg.pgproto.pgproto` từ bên trong một extension `.pyx`, PyInstaller's static analysis không thấy được nên `.exe` build xong nhưng crash ngay khi khởi động (`ModuleNotFoundError: No module named 'asyncpg.pgproto.pgproto'`, bắt được bằng cách **chạy thử `.exe` thật**, không phải chỉ nhìn log build). Sửa bằng `collect_submodules("asyncpg")` thay vì liệt kê tay từng tên — build lại, `.exe` khởi động thành công, `GET /openapi.json` trả `200 OK`, và xác nhận `Container` thật đã chạy (tạo file DPAPI thật ở `%LOCALAPPDATA%\COCAS\data\keys\master.key.dpapi`, ghi `logs/app.log`/`error.log` thật) — đúng nghĩa "chạy được", không chỉ "build được"
  - ⚠️ **Chưa đóng gói model PaddleOCR thật** (`resources/ocr-models/` chưa tồn tại — chưa có adapter OCR nào tới P2 cần trỏ vào đó) — phạm vi trial này là chứng minh PyInstaller **đóng gói và chạy được** với `paddlepaddle`/`paddleocr`/OpenCV làm phụ thuộc nặng, không phải kiểm chứng độ chính xác OCR khi đóng gói (việc đó thuộc P2 test 10 trong 13-kiem-thu-va-dong-goi.md)
  - ⚠️ **Kích thước gói `onedir` thực đo: ~505 MB** (tài liệu §13.12 ước tính 180 MB cho bản cuối cùng đã tối ưu) — chưa cắt bớt phụ thuộc bắc cầu của `paddleocr` (scipy, shapely, pyclipper, lmdb...) hay tinh chỉnh `excludes` sâu hơn. Rủi ro "Kích thước gói > 1.5 GB" (§14.5) cần theo dõi tiếp khi cộng thêm `resources/` (~850 MB) ở P5/P6
  - ⚠️ **Quyết định có chủ đích: `console=True` cho bản trial này**, khác với `console=False` mà tài liệu §13.13 yêu cầu cho bản production. Lý do: `loguru_config.configure_logging()`'s console sink gọi `logger.add(sys.stderr, ...)` — dưới chế độ windowed/`console=False` của PyInstaller, `sys.stderr` là `None`, sẽ crash `Container.__init__` ngay khi khởi động. Đây là một rủi ro đóng gói thật khác, **cố ý để lại cho P5/P6** (khi có Tauri Supervisor thật để đọc log qua file thay vì console) thay vì vá tạm bây giờ — ghi chú rõ trong `build.spec`

**⚠️ Lỗi môi trường phát triển phát hiện khi cài lại `pip install -e ".[dev]"` từ đầu (không liên quan trực tiếp đến module Logging, nhưng chặn mọi cài đặt dev từ P0 tới giờ):**
- `pyproject.toml` liệt kê `"gitleaks>=8.18.0,<8.19.0"` như một pip dependency — **gitleaks không tồn tại trên PyPI** (chỉ phân phối qua GitHub release/Homebrew/choco, không phải gói Python) → `pip install -e ".[dev]"` luôn thất bại ngay từ đầu. Đã xoá khỏi `[project.optional-dependencies].dev`; bước "Gitleaks — Secret scan" riêng trong `ci.yml` (vốn cũng gọi sai `pip install gitleaks`) đã sửa sang `choco install gitleaks` (runner CI là `windows-latest`, có sẵn Chocolatey)
- `"radon>=6.1.0,<6.2.0"` — phiên bản mới nhất thật trên PyPI là `6.0.1`, dải `6.1.x` chưa từng tồn tại. Sửa lại `>=6.0.0,<6.1.0`
- Do bước cài dev-dependencies (không có `continue-on-error`) chưa từng chạy xanh với 2 lỗi trên, khả năng cao **CI backend job đã fail ở đúng bước "Install dependencies" từ khi 2 dòng này được thêm vào** — cần theo dõi lần chạy CI tiếp theo để xác nhận đã xanh trở lại

**Milestones:**
- [x] ⭐ M1: Script tạo Customer giả, đọc lại, xác nhận `id_number_enc` là nhị phân không đọc được — `backend/scripts/demo_m1_customer.py`, chạy thành công trên PostgreSQL 18.4 thật 2026-08-09

**Risks:**
- 🟡 PostgreSQL portable trên Windows có thể vướng initdb
  - 🎯 Giải quyết ngay ở P1

---

### 🔄 P2 — Module OCR (4 tuần) ⭐ CRITICAL PATH
**Status:** ⭐ **4/4 tuần mã nguồn XONG 2026-08-10** — còn lại là Golden Set (dữ liệu, không phải mã)  
**Est. Completion:** 2026-09-23 (theo kế hoạch) — thực tế phần mã nguồn xong sớm

**Deliverables:**
- [x] **Tuần 1: Tiền xử lý ảnh (9 phép biến đổi, tạo lười)** — `infrastructure/ocr/preprocessing/`
  - `OpenCvPreprocessor` (Port 3 `IImagePreprocessor`) · `LazyPreprocessedImageSet` (v0–v4 lười, có cache) · `transforms.py` (9 phép) · `NumpyImageData`
  - 79 test đơn vị xanh trên ảnh tổng hợp · `scripts/preview_preprocessing.py` để soi ảnh thật
  - Đo trên 53 ảnh CCCD thật của người dùng: **46 ảnh xử lý được** (7 ảnh bị từ chối vì cạnh ngắn < 320 px — đúng thiết kế), **44/46 nắn phối cảnh thành công**, v2 dựng trong ~20 ms
- [x] **Tuần 2: Kênh QR + Kênh MRZ** — `infrastructure/ocr/channels/`
  - `ZxingQrDecoder` (Port 5 `IQrDecoder`) — chuỗi 3 lần thử, không bao giờ ném ngoại lệ
  - `Td1MrzReader` (Port 6 `IMrzReader`) + `td1.py` (logic chuỗi TD1 thuần, không ảnh/không I/O)
  - 69 test đơn vị mới (33 TD1 · 19 QR · 17 MRZ) — **733 test toàn dự án xanh**, `ruff` sạch, `import-linter` 4/4 hợp đồng
  - `scripts/verify_qr_mrz.py` — công cụ đo tỉ lệ đọc, dùng lại khi có Golden Set
  - ⚠️ **Chỉ tiêu chưa chốt được:** QR đo 18/53 ảnh (~54–81% mặt trước, dải rộng vì ảnh **chưa gán nhãn** trước/sau) — dưới mốc ≥90%. MRZ **chưa đo được**: cần `IRegionRecognizer`, tới tuần 3 mới có
- [x] **Tuần 3: PaddleOCR adapter + Side Classifier + Field Extractor + sửa xoay 180°** — hoàn tất 2026-08-10
  - `PaddleOcrAdapter` (Port 1 `IOcrEngine` + Port 2 `IRegionRecognizer`) — model_dir tường minh, ⭐ **P-01 kiểm chứng bằng cách cắt sạch socket**: 0 lần gọi mạng, không tạo cache tải về
  - `PaddleOrientationOracle` — hoàn tất tín hiệu xoay 180° cho **mặt trước** (§7.4.1 mục 4), nối vào tiền xử lý qua protocol một phương thức nên tiền xử lý **không phụ thuộc engine**
  - `HeuristicSideClassifier` (Port 4) — 4 tín hiệu, đo **36/36 đúng** trên ảnh thật
  - `ZoneAndAnchorExtractor` (Port 7) + `field_patterns` + `text_matching` — 2 chiến lược, `zone_map` **đã hiệu chỉnh bằng ảnh thật**
  - `scripts/fetch_ocr_models.py` — bước dựng tải 16 MB model về `resources/ocr-models/`
  - **885 test toàn dự án xanh** (+128), ruff sạch, `mypy --strict` domain+application 0 lỗi, import-linter 4/4
  - ⭐ **Chỉ tiêu MRZ ≥75% ĐÃ ĐẠT: 22/22 = 100%**, `repairs applied {0: 22}` — bộ sửa lỗi chưa từng phải chạy
  - ⭐ **Trích trường đo được:** `id_number` **14/14** · `date_of_birth` **12/12** · `full_name` 11/15
- [x] **Tuần 3b: Thế hệ thẻ thứ hai + chỉ tiêu QR** — hoàn tất 2026-08-10
  - ⭐ **Bộ mẫu chứa HAI thế hệ thẻ, phát hiện muộn 3 tuần.** 39 ảnh CCCD gắn chip 2021, **7 ảnh Căn cước 2024** — thế hệ mới in QR ở **mặt sau** và ngày hết hạn ở **mặt sau**. Đồng bộ vào `07 §7.4.7`, `03 §S4/S5`, `04 §4.4.13`
  - `20260811_009_seed_doctype_2024.py` — doctype thứ hai (`zone_map` đo trên 7 ảnh thật, anchor riêng, 3 alias `BỘ CÔNG AN`). **Không sửa một dòng mã trích trường nào** — `DocumentTypeSpec` vốn đã hỗ trợ nhiều loại (P-06/P-12), đây là lần đầu cơ chế đó chịu tải thật
  - ⭐ **Chỉ tiêu QR ≥90% ĐÃ ĐẠT: 20/21 = 95.2%** (từ 18/21). Thêm 2 lần thử đọc **kênh Blue** — hoa văn guilloche lam ngọc của thẻ biến mất ở kênh này. Không mất thẻ nào, +43 ms/ảnh
  - ⭐ **Con số 66.7% cũ sai vì mẫu số sai**, không phải vì kênh yếu: nó suy nhãn mặt từ "có MRZ ⇒ mặt sau", nên đếm thừa 5 mặt trước 2024 (vốn không in QR) và đếm thiếu 2 mặt sau 2024 (có in QR). `verify_qr_mrz.py` nay gán nhãn thế hệ bằng **chữ in trên thẻ**
  - **931 test xanh** (+46), ruff sạch, `mypy --strict` 0 lỗi, `mypy` gói OCR 0 lỗi, import-linter 4/4
- [x] **Tuần 4: Chuẩn hoá + Fusion + Validation** — hoàn tất 2026-08-10
  - ⭐ **`FieldNormalizer`** (Domain Service D1, S9) — dạng chuẩn duy nhất cho từng trường: ngày ra **ISO `YYYY-MM-DD`**, `KHÔNG THỜI HẠN` là **hằng số giá trị** chứ không phải `None`, tên NFC-UPPER, số CCCD 12 chữ số. Không bao giờ ném ngoại lệ; giá trị chuẩn hoá hỏng bị **loại** chứ không cho lọt thô
  - ⭐ **`FieldFusionService` đủ 8 quy tắc** (trước đó mới có 4): thêm hệ số trường cho kênh OCR (quy tắc 2), thưởng đồng thuận đúng **+0.10** kèm cờ `agreement`, xung đột chỉ tính khi **cả hai nguồn ≥ 0.90** rồi hạ về 0.50, và ⭐ **quy tắc 6 — suy luận từ mã số** (mã tỉnh · thế kỷ · 2 số cuối năm sinh) đối chiếu chéo với ngày sinh → cờ `ID_INCONSISTENT`
  - **`ConfidenceCalculator`** (D4) — điểm tổng có trọng số; trường không đọc được tính **0** chứ không loại khỏi mẫu số
  - ⭐ **`domain/validation/`** — `ValidationEngine` + registry 4 tập quy tắc + **đủ 23 quy tắc `V-OCR-*`**. Quy tắc là **đối tượng trong registry**, engine không biết quy tắc nào tồn tại (§12.7). 3 tập của P3 đăng ký **rỗng chứ không thiếu**: tập rỗng trả báo cáo hợp lệ, tập thiếu ném lỗi — hai câu trả lời khác nhau cho "hợp đồng này sinh được chưa"
  - ⭐ **Sửa phân loại mặt cho Căn cước 2024** (mục treo cuối tuần 3b): **0/10 → 10/10 cặp**, xem phát hiện #31
  - `scripts/verify_side_classification.py` + `scripts/verify_extraction.py` — hai công cụ đo mới, dùng lại nguyên vẹn khi có Golden Set
  - **1096 test toàn dự án xanh** (+165), ruff sạch, `mypy --strict` domain+application 0 lỗi, import-linter 4/4. Độ phủ mã mới: fusion 100% · calculator 100% · validation engine 100% · `ocr_rules` 99% · normalizer 98%
- [x] ⭐ **Bổ sung 2026-08-11: tầng 5 cho `issue_place`** — phân biệt 2 giá trị bằng **3 chữ đầu** thay vì so khớp toàn chuỗi (`domain/services/issue_place_shape.py`). 22/22 đúng, 0/752 phán quyết sai trên các dòng khác. **1155 test xanh** (+59), độ phủ 2 file mới 100%. Xem phát hiện #34

**⭐ Đo toàn chuỗi S3→S11 trên 46 ảnh thật (2026-08-10, `scripts/verify_extraction.py`)**

Thẻ được **ghép từ chính dữ liệu, không từ tên file**: mọi ảnh của một thẻ mang cùng số CCCD (mặt trước in trong QR, mặt sau in trong MRZ), nên khớp theo số đó ghép được **20 thẻ** (17 thẻ đủ hai mặt) từ 46 ảnh; 6 ảnh không kênh chính xác nào đọc được thì để riêng thay vì ghép mò.

| Trường | Đọc được | Độ tin cậy TB | Cần review | Nguồn thắng |
|---|---|---|---|---|
| `id_number` | **20/20** | 1.00 | 0 | QR 19 · MRZ 1 |
| `date_of_birth` | **20/20** | 1.00 | 0 | QR 19 · MRZ 1 |
| `issue_date` | **20/20** | 0.99 | 0 | QR 19 · OCR 1 |
| `expiry_date` | **20/20** | 0.98 | 0 | **MRZ 20** |
| `full_name` | 19/20 | 1.00 | 0 | QR 19 |
| ⭐ `issue_place` | **20/20** | **0.89** | **1** | OCR 20 |

> ⭐ Dòng `issue_place` đo lại **2026-08-11** sau khi thêm tầng 5 (phát hiện #34). Số cũ của lần đo 2026-08-10: **12/20 · 0.60 · 12 ô review**. Năm dòng còn lại không đổi.

- ⭐⭐ **False Confidence đo được lần đầu tiên: 0/16 = 0.0%** (chỉ tiêu ≤0.5%, **chặn phát hành**). Proxy: QR/MRZ là kênh chính xác nên chúng làm **nhãn** cho các trường mà OCR cũng đọc được; một trường OCR ≥0.95 mà lệch nhãn là một ca False Confidence. Mẫu số nhỏ (16) và chỉ phủ phần giao — **không thay thế được Golden Set**, nhưng đây là lần đầu chỉ số này không còn là ô trống.
- ⭐ **Hệ số trường của quy tắc 2 làm đúng việc của nó.** OCR khớp kênh chính xác **33/50 = 66%** — 17 ca lệch gần như toàn bộ là `full_name` mất dấu (§7.4.5). Không ca lệch nào lọt vào mức ≥0.95 **sau khi nhân hệ số 0.75**, tức là chính hệ số này giữ False Confidence ở 0.
- ⭐ **`expiry_date` 20/20 đến từ MRZ, không kênh nào khác đóng góp** — xác nhận đúng điều §7.4.4 gọi MRZ là "trường không kênh nào khác cung cấp".
- ✅ ~~**`issue_place` là điểm yếu duy nhất còn lại**~~ — **đo lại 2026-08-11 sau tầng 5: 20/20, conf 0.89, 1 ô review**, cả 22 lần đọc đều do tầng 5 giải quyết. Số cũ (12/20 ở tầng 4, conf 0.60) có **hai** nguyên nhân và cái lớn hơn nằm ở phép đo: script gieo 2 dòng alias trong khi seed thật có 19, và cả 2 đều tầng 4 — mà tầng 3 chỉ xét dòng có `alias_normalized`, nên tầng 3 **không có gì để so**. Nhưng gieo đủ 19 dòng thật cũng chỉ được 13/22 ở 0.65. Xem phát hiện #34.
- **Validation:** 10/20 thẻ bị chặn — `V-OCR-017` ×9 (thiếu `issue_place`), `V-OCR-001` ×3 (thẻ chỉ có một mặt trong bộ mẫu), `V-OCR-002` ×2 (hai ảnh cùng mặt), `V-OCR-018` ×12 cảnh báo (đúng 12 giá trị `issue_place` ở 0.60). Mọi nguyên nhân đều truy được về một trường cụ thể, không có lỗi "không rõ vì sao".
  - ⭐ **Đo lại 2026-08-11: còn 5/20 thẻ bị chặn** — `V-OCR-001` ×3, `V-OCR-002` ×2, `V-OCR-017` ×1, `V-OCR-018` ×1. Toàn bộ 5 ca còn lại là **lỗi dữ liệu mẫu** (bộ ảnh dev có thẻ chỉ một mặt và có cặp trùng mặt), không phải lỗi pipeline.
- **Điểm tổng:** trung bình 0.92 · thấp nhất 0.68 · cao nhất 0.96. ⭐ Đo lại 2026-08-11: trung bình **0.97** · thấp nhất 0.71 · cao nhất 0.99.
- 🔴 **Thời gian: trung bình 7.7 s/ảnh, p95 17.5 s/ảnh** trên máy dev **4 nhân / 4 GB RAM** — ngân sách là **9 s cho cả CẶP**. Xem rủi ro p95 bên dưới.
  - ⚠️ Đo lại 2026-08-11 trên cùng máy, cùng bộ ảnh: trung bình **5.9 s**, p95 **10.2 s**. **Không phải do thay đổi nào** — tầng 5 không đụng vào đường OCR. Đây là **dao động tải máy giữa hai lần chạy**, và bản thân nó là số đo đáng ghi: cùng một pipeline trên cùng một máy lệch nhau **1.7 lần** ở p95, nên đừng chốt hay bác bỏ chỉ tiêu latency dựa trên một lần chạy.

**Phát hiện khi chạy trên ảnh thật (đã sửa, đã đồng bộ vào `07-module-ocr.md` §7.4.1):**
1. ⭐ **Dò contour theo đặc tả gốc chỉ nắn được 4/46 ảnh.** Hai nguyên nhân, đều là trường hợp phổ biến chứ không phải ngoại lệ: (a) ảnh chụp bằng điện thoại cầm dọc → thẻ nằm ngang trong khung dọc, tỉ lệ quad ra 1/1.585 = 0.63 nên bị chốt tỉ lệ loại thẳng; (b) ảnh đã crop sát thẻ → không còn đường viền nào để dò. Sửa: đổi nhãn 4 đỉnh về khổ ngang, và lấy chính 4 góc ảnh làm quad khi tỉ lệ khung ảnh nằm trong dải cho phép. Sau khi sửa: **44/46**.
2. **Dò contour trên ảnh 1600px tốn tới 1.9 giây/ảnh.** Chuyển sang dò trên bản thu nhỏ cạnh dài 800px rồi nhân ngược toạ độ quad → còn ~20 ms, kết quả không đổi.
3. ⭐ **Phát hiện 180° bằng heuristic thuần OpenCV từng LẬT NGƯỢC một thẻ vốn đã đúng** — khối địa chỉ mặt sau cũng là 3 dòng full-width cách đều y hệt MRZ. Sửa: chỉ xoay khi có **đúng một** khối như vậy sát mép; hai khối ở hai mép → mơ hồ → không xoay. Hệ quả: 19/19 mặt sau có MRZ đều ra đúng chiều, **0 ca lật nhầm**.
4. **Mặt trước chưa tự sửa được 180°** — không có MRZ nên không có tín hiệu nào đủ tin cậy trước khi có engine OCR. Hai tín hiệu còn lại trong §7.4.1 (model `cls` của PaddleOCR, đếm vùng text ở 0° vs 180°) đều cần engine → **hoàn tất ở tuần 3**, không phải bug bỏ quên.
5. Sửa một lỗi gamma trong khâu cân bằng sáng: công thức dùng `1/gamma` làm **tối thêm** ảnh vốn đã tối. Lỗi này không lộ ra khi đọc code, chỉ lộ khi có test so sánh độ sáng trước/sau.

**Phát hiện tuần 2 (đã đồng bộ vào `07-module-ocr.md` §7.4.3, `03`, `01`, `11`, `13`):**

6. ⭐ **Cả hai bộ giải mã QR mà thiết kế D2.0 chỉ định đều KHÔNG dùng được với danh sách thư viện đã ghim.** Chỉ lộ ra khi chạy thật trên 53 ảnh, không thể suy ra từ đọc tài liệu:

   | Bộ giải mã | Đọc được | Tốc độ | Vấn đề |
   |---|---|---|---|
   | `cv2.QRCodeDetector` (có sẵn trong bản đã ghim) | 1/53 | nhanh | **Định vị được QR nhưng không giải mã nổi** ở mọi tỉ lệ (1×–8×) và mọi cách nhị phân hoá. QR CCCD ~130 px cho ~57 module ≈ 2.3 px/module — dưới ngưỡng của bộ giải mã này |
   | `pyzbar` (đã ghim trong `pyproject.toml`) | **không chạy nổi** | — | `libzbar-64.dll` cần `MSVCR120.dll` (VC++ 2013 Redistributable). ⭐ **Không phải lỗi máy dev**: máy khách chưa cài redist sẽ hỏng y hệt sau khi đóng gói NSIS |
   | `cv2.wechat_qrcode` (§7.4.3 chỉ định làm lần thử 1) | 21/53 | **4060 ms/ảnh** | Nằm trong `opencv-contrib`, không phải `opencv-python-headless` đã ghim. 2 ảnh/hồ sơ ⇒ ~8 giây chỉ riêng khâu QR |
   | ⭐ **`zxing-cpp`** (đã chọn) | **21/53** | **66 ms/ảnh** | Wheel tự chứa — không model, không DLL hệ thống ⇒ **gỡ hẳn rủi ro VC++ redist khỏi khâu đóng gói** |

   `zxing-cpp` cho **đúng độ chính xác của WeChat, nhanh gấp 61 lần** (chỉ lệch 2/53 ảnh, theo cả hai chiều). Người dùng chốt phương án 2026-08-09. Đã bỏ `pyzbar` khỏi `pyproject.toml` và gỡ khối copy `libzbar-64.dll`/`libiconv.dll` khỏi `build.spec`.

7. ⭐ **Bố cục QR và MRZ đã được xác nhận trên dữ liệu thật, không còn là giả định.** 18 payload QR cho thấy đúng 7 phần như đặc tả (`{12 số}|{CMND 9 số}|{họ tên}|{ddmmyyyy}|{giới tính}|{địa chỉ}|{ddmmyyyy}`), nhưng **5/18 mẫu có 11 phần** — 4 phần cuối rỗng. Bộ phân tích phải chấp nhận phần thừa rỗng, nếu không sẽ loại nhầm 28% payload hợp lệ thành "bố cục lạ".

8. ⭐ **MRZ của CCCD Việt Nam đặt số CCCD ở vùng dữ liệu tuỳ chọn, KHÔNG ở trường số tài liệu.** Đọc trực tiếp từ một thẻ thật: dòng 1 vị trí 5–13 chứa **CMND cũ 9 số**, còn **CCCD 12 số nằm ở vị trí 15–26**. Lấy nhầm trường sẽ ra số CMND cũ và làm quy tắc hợp nhất #5 (`CARD_MISMATCH`) báo động giả với mọi thẻ. Cả 5 check digit (kể cả check tổng 50 ký tự) đã tự tính tay và khớp.

9. ⭐ **Bảng ánh xạ cưỡng bức bộ ký tự phải áp THEO VỊ TRÍ, không áp toàn cục.** Đặc tả §7.4.4 liệt kê `O,Q,D→0 · I,l→1 · S→5 · B→8` — nhưng A–Z đều là ký tự **hợp lệ** trong TD1. Áp toàn cục sẽ biến `DO`→`00`, `HOANG`→`H0ANG`, `SON`→`50N`, phá mọi họ tên Việt có D/O/S/B. Sửa: chỉ ép chữ→số trong các dải TD1 định nghĩa là số (vị trí 5–13, 15–28 dòng 1; 0–5, 8–13 dòng 2); dòng 3 (họ tên) không bao giờ bị ép. Đây đúng là ý nghĩa thực tế của "charset_hint chỉ là bộ lọc hậu xử lý" (CLAUDE.md điều dễ sai #3).

10. **Nghi ngờ `warp_succeeded=True` trên gần như mọi ảnh — điều tra xong, KHÔNG phải lỗi.** Ảnh mẫu hầu hết đã cắt sát thẻ, tỉ lệ 1.56–1.61 nằm đúng trong dải `[1.45, 1.72]`, nên `full_frame_quad` chấp nhận là đúng thiết kế. Hai ảnh bị từ chối có tỉ lệ 1.74 và 1.80 — từ chối cũng đúng.

11. **Ngưỡng `MIN_SHORT_EDGE = 320` làm mất 3 ảnh mà `zxing-cpp` đọc được QR** (21 ảnh đọc được ở mức thô → 18 ảnh qua được pipeline). Đúng đặc tả (tiền điều kiện `IOcrEngine` là cạnh ngắn ≥ 320) nên **giữ nguyên**; ghi lại vì nó là một phần chênh lệch giữa "trần khả năng" và "tỉ lệ thực tế".

**Phát hiện tuần 3 (đã đồng bộ vào `07-module-ocr.md` §7.4.1/§7.4.2/§7.4.4/§7.4.5/§7.4.6, `03` §S6, migration seed):**

12. ⭐ **`lang='vi'` của PaddleOCR không cho model tiếng Việt, và không cho cả PP-OCRv4.** `parse_lang` gộp tiếng Việt vào nhóm `latin`; mục `latin` trong bảng **v4** trỏ tới URL **v3**. Bảng chữ thật sự dùng là `latin_dict.txt` (185 ký tự) phủ **4/42** chữ hoa có dấu tiếng Việt, trong khi `vi_dict.txt` (113 ký tự) phủ 42/42 nhưng **không bao giờ được chọn** — và không có model nào khớp nó (`vi_PP-OCRv3_rec_infer.tar` → **HTTP 404**). Hệ quả: `FULL_NAME` từ kênh OCR **mất dấu chứ không sai chữ**, kiểu hỏng mà hợp nhất xử lý được vì QR mang tên có dấu. Người dùng chốt 2026-08-10: **đo trước, chốt sau** — không đi huấn luyện model riêng khi chưa có bằng chứng nó chặn KPI.

13. ⭐ **Toạ độ `zone_map` gieo sẵn lệch ~0.2 theo trục y ở MỌI trường mặt trước** — lớn hơn chiều cao một trường. Ô `full_name` trỏ đúng vào dòng phụ đề `Citizen Identity Card` và giao nó cho hợp nhất **như tên khách hàng** (6/15 ảnh). Hai trường mặt sau bị đặt ở đáy thẻ, còn thực tế ngày cấp và cơ quan cấp in ở **phía trên**. Đã hiệu chỉnh toàn bộ bằng chân lý từ QR/MRZ, không toạ độ nào chọn bằng mắt. Sau khi sửa: `full_name` 6/15 → **11/15**.

14. ⭐ **Dải quét MRZ cũ (y 0.82–0.98) nằm DƯỚI hai dòng đầu của khối MRZ.** MRZ thật đo được ở **y 0.66–0.93** trên 20 mặt sau. Dải cũ đọc trúng khối địa chỉ và sinh ra chuỗi rác đầy tự tin (`NH<71ENPHU0C<0UANGNAM`). Cùng lúc: **`v3` đọc MRZ tốt hơn `v4`** — 20 khối so với 12 — bác bỏ giả định "nhị phân hoá tốt hơn hẳn cho MRZ" của thiết kế.

15. ⭐ **Chỉ tiêu MRZ đạt 100% (22/22) nhưng cần ĐÚNG HAI thay đổi, không cái nào một mình đủ:** bỏ số kiểm tổng khỏi cổng chặn (36%→73%) **và** nắn lại số kiểm bị chuỗi `<` nuốt mất (73%→100%). Bộ nhận dạng đếm sai chuỗi dài ký tự giống nhau, nên số kiểm cuối dòng 2 hay bị đẩy lệch vài cột hoặc mất hẳn — trong khi mọi cột dữ liệu đọc đúng.

16. ⭐ **Bỏ số kiểm tổng khỏi cổng chặn tạo ra một hồi quy mà test bắt được:** nó chính là thứ ngăn `_repair` tự chế ra kết quả "hợp lệ" từ nhiễu. Sửa bằng ràng buộc "khối **đã sửa** chỉ được tin khi số kiểm tổng cũng khớp". ⚠️ Kèm một tính chất tinh vi của ICAO 9303: **số kiểm tổng không làm chứng cho nhóm số tài liệu ở dòng 1** — cả hai tổng bắt đầu tại `line1[5]` cùng pha 7-3-1 và nhóm đó dài đúng 3 chu kỳ, nên mọi sửa lỗi thoả nhóm đó cũng tự thoả số kiểm tổng. Không đúng với 3 nhóm còn lại, và đó mới là các nhóm đưa trường vào hợp nhất.

17. ⭐ **Tín hiệu "đếm số vùng text ở 0° vs 180°" của thiết kế KHÔNG TỒN TẠI.** Đo trên 18 mặt trước: 17.7 vs 15.8 vùng, độ tin cậy 0.911 vs 0.904 — không phân biệt được. Nguyên nhân: bộ phân loại góc theo dòng của PaddleOCR tự lật **từng dòng**, nên thẻ lộn ngược vẫn cho một trang chữ đầy đủ và tự tin, 74% trong đó sai. Thay bằng **dấu vân chữ in sẵn ở dải trên**: 44/46 đúng cả hai chiều, **0 sai**.

18. ⭐ **`partial_ratio` của rapidfuzz không an toàn với chuỗi ngắn — lỗi ảnh hưởng mọi chỗ so khớp.** Mảnh 2 ký tự `ON` đạt **100 điểm** với `CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM` vì nó là chuỗi con. Đủ để gọi 6/46 thẻ lộn ngược là đúng chiều. Sửa: nhân điểm với `min(1, len(text)/len(anchor))`.

19. ⭐ **Bộ nhận dạng nuốt dấu cách một cách có hệ thống** (`CONG HOAXAHOI`, `SOCIALISTREPUBLIC`, `DANGDUY NGHIA`), làm mất ~18 điểm khi so với anchor viết đúng — đủ đẩy chính tiêu đề của thẻ xuống dưới ngưỡng. Sửa: bỏ hẳn khoảng trắng trước khi so. Kết quả: oracle từ 39/46 lên **44/46**, không thêm ca sai nào.

20. **`recognize_region()` trên một dải KHÔNG rẻ theo tỉ lệ diện tích** — dải cao 32% tốn 41% chi phí toàn thẻ, vì bộ dò của PaddleOCR chuẩn hoá theo cạnh dài mà dải full-width có cùng cạnh dài với thẻ. Hệ quả: đã cho khâu đọc dải tiêu đề của bộ phân loại mặt **chạy lười** (QR/MRZ đã chốt 36/46 ảnh, và trên 36 ảnh đó anchor chưa từng đổi kết luận). Quy trình P3 nên nhận dạng toàn thẻ **một lần** rồi dùng lại các vùng.

21. **Hai tín hiệu texture của §7.4.2 (chân dung/vân tay) không triển khai** — cần Haar cascade, thêm tệp nhị phân phải đóng gói. Bốn tín hiệu còn lại đã phân loại 36/36 đúng. Bỏ theo P-10, có số liệu chống lưng, ghi rõ để thêm lại nếu Golden Set đòi.
22. ⭐⭐ **Bộ mẫu chứa HAI thế hệ thẻ, và điều đó không lộ ra suốt 3 tuần.** 39 ảnh CCCD gắn chip 2021 + **7 ảnh Căn cước 2024**. Thế hệ 2024 in **QR ở mặt sau** (không phải mặt trước) và **ngày hết hạn ở mặt sau**, đổi tiêu đề thành `CĂN CƯỚC`, đổi nhãn số thẻ thành `Số định danh cá nhân`, đổi cơ quan cấp thành `BỘ CÔNG AN`. Lý do giấu được lâu: **mọi phép đo đều làm theo tỉ lệ tổng, không bao giờ soi từng ca lệch.** Cách phát hiện: hỏi "vì sao 8 ảnh này không đọc được QR" rồi mở từng ảnh ra xem. Sửa: thêm doctype thứ hai — **0 dòng mã trích trường phải đổi**, vì `DocumentTypeSpec` vốn đã mang `zone_map`/`anchor_patterns` riêng cho từng loại (P-06/P-12).
23. ⭐ **Hoa văn nền của thẻ là thứ chặn QR, không phải độ phân giải.** Hai ảnh 1280×812 và 1295×793 (QR nhìn rõ bằng mắt) trượt cả 3 lần thử. Nguyên nhân: guilloche lam ngọc in **xuyên qua** mã QR. Màu lam ngọc sáng ở kênh Blue và tối ở kênh Red, nên tách kênh Blue xoá được nhiễu trong khi module QR gần đen vẫn tối; ảnh xám trộn nó trở lại ở trọng số 0.114. Thêm 2 lần thử kênh Blue (một có làm nét, một dùng binarizer `GlobalHistogram`) ⇒ **18/21 → 20/21**. ⚠️ Đổi tham số lần thử 3 (`1.6→3×` thành `2.5→4×`) đọc thêm 1 thẻ nhưng **mất** 1 thẻ khác: **thêm vào thắng chỉnh sửa**.
24. ⭐ **Anchor `Ngày, tháng, năm cấp` và `Ngày, tháng, năm hết hạn` bắt nhầm dòng của nhau** — 83.9 và 83.3 điểm, đều vượt ngưỡng 75. `_beside_label` trả nhãn khớp **đầu tiên theo thứ tự đọc**, mà nhãn ngày cấp in trước ⇒ `expiry_date` sẽ nhận **ngày cấp** và báo đầy tự tin. Sửa bằng cách cắt anchor còn phần đuôi phân biệt (`năm cấp` / `năm hết hạn`). **Cùng lớp lỗi này còn sót trong seed 2021: anchor `Số:` chấm 80.0 với `SOCIALIST REPUBLIC OF VIET NAM`** — đã gỡ (đã có `_TALLEST_WINS` lo `id_number` không cần nhãn).
25. ⭐ **Ngưỡng `KHÔNG THỜI HẠN` = 85 là chốt chặn không bao giờ kích hoạt được, và giữ nguyên là đúng.** Quét 774 dòng OCR thật: giá trị **thật** `ovong thoi hg` chấm **69.8**, còn dòng cao điểm nhất toàn bộ mẫu là **một cái tên người** (`PHAM THI PHU'O'NG THOA`, **76.2**). Giá trị đúng nằm *dưới* nhiễu ⇒ không ngưỡng nào nhận nó mà không nhận cả tên người trước. Chấm theo từ cũng không cứu được (chỉ 1/3 từ sống sót qua nhận dạng). Để trống là kết cục đúng — `expiry_date` không bắt buộc. ⚠️ Chú thích cũ nói chuỗi này chấm 80 và là "nhiễu từ phần không liên quan của thẻ": **sai cả hai vế**.
26. **`find_date` phải chấp nhận ngày không có dấu phân cách.** Thẻ thật in `04/06/2025` nhưng bộ nhận dạng trả `04062025`, và trường ngày cấp mất hẳn. Thêm mẫu 8 chữ số đứng riêng + ràng buộc năm 1900–2100, chỉ thử sau khi mẫu có dấu phân cách trượt. Đo A/B trên 774 dòng: **0 mất, 1 nhận thêm** — thuần cộng thêm.
27. **`find_place` từ chối mọi chuỗi có chữ số là chặt gấp đôi.** `BỘ CÔNG AN` được đọc thành `BO C0NG AI`, và đúng một chữ số `0` vứt bỏ cả dòng. Điều quy tắc này thực sự cần làm là phân biệt trường nơi cấp với ngày/số in cạnh nó, nên đổi sang tìm **run** chữ số (`\d{2}`): số in luôn có run, chữ bị đọc nhầm thì không.

**Phát hiện tuần 4 (đã đồng bộ vào `03` §S9/§S10, `07` §7.4.2/§7.4.7/§7.5.0/§7.5.2, `08` §8.4, `12` §12.6a/§12.6b):**

28. ⭐ **Chuẩn hoá không phải bước "làm đẹp dữ liệu" — không có nó thì hợp nhất hỏng theo hai chiều cùng lúc.** Ba kênh cho ba cách viết của một ngày (`13031987` từ QR, `13031987` từ MRZ, `13/03/1987` từ bộ trích trường). Đưa nguyên vào `FieldFusionService` thì quy tắc 3 (thưởng đồng thuận) **không bao giờ** kích hoạt, còn quy tắc 4 (phát hiện xung đột) kích hoạt trên **mọi** thẻ — hai nguồn tin cậy cao "mâu thuẫn" về một giá trị mà thật ra chúng đồng ý. Đây là lý do S9 phải đứng trước S10, chứ không phải vì cột CSDL cần định dạng đẹp.
29. ⭐ **Bước sửa lỗi ngày theo đặc tả gốc BỊA RA giá trị mới — bắt được nhờ chính ca biên mà §8.11 bắt buộc phải có.** "Thử biến thể, chọn ngày hợp lệ duy nhất" quét cả 8 chữ số biến `29/02/2023` (ngày **không tồn tại**, và §8.11 liệt kê nó như ca **phải bị từ chối**) thành `2028-02-29` — cách đọc tự nhất quán duy nhất trong toàn bộ không gian 256 biến thể. Một phép sửa dời năm sinh đi 5 năm để lịch khớp thì không phải phép sửa. Siết hai ràng buộc: **không bao giờ đổi chữ số của năm** và **nhiều nhất một chữ số được đổi** (`00/00/1990` cũng "duy nhất" thành `06/06/1990` nếu cho phép hai). Không gian còn ≤ 4 ứng viên, và "duy nhất" mới có nghĩa. ⚠️ Cả hai ràng buộc **không mất phép sửa nào đã đo được** — `date_of_birth` 12/12 và `issue_date` 2/2 đọc đúng mà bước này chưa từng phải chạy.
30. ⭐ **Trong chuẩn hoá tên, THỨ TỰ là thứ mang tải: sửa chữ số trước, lọc ký tự sau.** Lọc trước thì `H0ANG` mất chữ số `0` (ngoài bộ ký tự tiếng Việt) và thành **`HANG`** — một cái tên trông hoàn toàn hợp lý nhưng không phải cái in trên thẻ. §03 S9 vốn ghi đúng thứ tự; hiện thực đầu tiên vẫn làm ngược, và điều đó **chỉ lộ ra khi viết test**, không lộ khi đọc code.
31. ⭐⭐ **QR + MRZ trên cùng một ảnh KHÔNG phải thế hoà — đó là quan sát quyết định nhất mà bộ phân loại mặt có được.** Đo đúng mục treo cuối tuần 3b: coi hai tín hiệu là hai lá phiếu độc lập thì chúng triệt tiêu đúng 0.40–0.40 và **0/10 cặp Căn cước 2024** ra `RESOLVED` (toàn bộ `AMBIGUOUS`), trong khi 12 cặp CCCD 2021 đối chứng đạt 12/12. Nhưng **không thế hệ nào in cả hai lên cùng một mặt, trừ đúng mặt sau của thẻ 2024**, nên *tổ hợp* nhận diện mặt sau mạnh hơn từng tín hiệu riêng → một tín hiệu độc lập trọng số **0.80**. Kết quả: **10/10 đúng, 0 sai**, và **rẻ hơn 26%** vì không còn phải đọc dải tiêu đề để phá thế hoà.
    - ⚠️ Cách sửa "đúng bài" hơn — đưa anchor mặt trước/sau vào `document_type.anchor_patterns` theo P-06 — **vướng con gà–quả trứng**: S4 chạy *trước* khi biết thế hệ thẻ. Tín hiệu tổ hợp gỡ được nút thắt mà không phải trả lời câu hỏi đó; câu hỏi vẫn để ngỏ cho P3.
    - ⚠️ Phép đo cố ý đưa ảnh vào **sai thứ tự** (ảnh A là mặt sau). Một bộ phân loại mặc định "A là mặt trước" sẽ đạt 100% trên đầu vào đúng thứ tự và 0% ở đây — mà sai thứ tự mới đúng là tình huống ALT-01 tồn tại để xử lý.
32. ⭐ **Nhận dạng toàn thẻ HAI lượt không đắt gấp đôi mà đắt gấp 5–7 lần, và nó gây `OcrTimeoutError` thật.** Bản đầu của `verify_extraction.py` gọi `recognize()` một lượt cho phát hiện thế hệ thẻ và một lượt cho trích trường: **12,8 → 27,9 → 44,6 s/ảnh** và bắt đầu vượt ngân sách 20 s của adapter. Gộp còn **một lượt** rồi suy thế hệ từ chính các vùng text đó: **7,7 s/ảnh trung bình, 0 timeout**. Nguyên nhân là máy dev chỉ có **4 nhân / 4 GB RAM** nên chi phí không tuyến tính theo số lượt. Đây chính là khuyến nghị §7.4.6 phát hiện #20 dành cho P3, giờ có số đo chống lưng — và nó nói rằng khuyến nghị đó **không phải tối ưu vặt mà là điều kiện để chạy được**.
33. ⭐ **Ghép hai mặt của một thẻ không cần nhãn: dùng chính số CCCD.** Mặt trước in nó trong QR, mặt sau in nó trong MRZ, nên khớp theo số đó ghép được 20 thẻ (17 đủ hai mặt) từ 46 ảnh **không có nhãn nào**. Thủ thuật này cũng là thứ làm cho phép đo False Confidence khả thi trước khi có Golden Set — và nó dùng lại được y nguyên khi có Golden Set để **kiểm tra chéo nhãn thủ công**.

**Phát hiện bổ sung 2026-08-11 (đã đồng bộ vào `03` §S9, `07` §7.5.1, `12` §12.5/§12.5.1):**

34. ⭐⭐ **`issue_place` là trường ĐÓNG 2 giá trị, nên phải PHÂN LOẠI nó chứ đừng ĐỌC nó.** Bốn tầng của `IssuePlaceNormalizer` đều so khớp **toàn bộ** chuỗi với một danh mục cách viết — đúng cho trường mở, sai cho trường đóng: nó làm câu trả lời phụ thuộc vào việc bộ nhận dạng đọc đúng bao nhiêu phần của một tên cơ quan 23 ký tự, trong khi chỉ cần **phần mở đầu**. `BỘ CÔNG AN` mở bằng `BOC`, `CỤC TRƯỞNG CỤC CẢNH SÁT…` mở bằng `CUC`. Thêm **tầng 5** lấy 3 chữ đầu: **22/22 đúng ở 0.92**, và quét **752 dòng còn lại** của cùng 46 ảnh qua đúng phép thử đó ra **0 phán quyết** — vừa nhạy vừa hẹp.
    - ⚠️ **Ba nguyên nhân chồng nhau, và cái lớn nhất nằm trong phép đo, không nằm trong trường.** (1) Đây là trường **duy nhất không kênh chính xác nào đọc được** — QR trả 4 trường, MRZ TD1 trả 3, không kênh nào mang tên cơ quan cấp, nên nó 100% phụ thuộc OCR. (2) Script đo gieo **2** dòng alias trong khi seed thật có **19**, và cả 2 đều **tầng 4** — mà tầng 3 chỉ xét dòng có `alias_normalized`, nên tầng 3 **không có gì để so** và không thể kích hoạt; mọi ca rơi thẳng xuống 0.60. "Trường yếu đều ở 0.60" là tính chất của fixture. (3) Nhưng gieo đủ 19 dòng thật **cũng không cứu được** — xem dưới.
    - ⚠️ **Tầng 3 và tầng 4 không phải hai đường dự phòng độc lập: chúng chết vì cùng một lỗi.** Bộ nhận dạng dính chữ (`CUCTRUONG CUCCANH SAT`) làm giao của `token_set_ratio` rỗng **và đồng thời** làm mất token `CUC` mà tầng 4 đòi phải có đủ. Đo với đủ 19 dòng alias thật: tầng 3 đúng 13/22 ở 0.65, tầng 4 đúng 1/22, và **8/22 không ra giá trị nào**. Bậc thang tầng gợi ý một sự dự phòng mà cấu trúc không hề có.
    - ⚠️⚠️ **Tín hiệu "phân biệt bằng độ dài" hấp dẫn trên giấy và SAI trên máy.** Hai giá trị chuẩn chênh nhau gần 5 lần (8 ký tự / 38 ký tự) — nhìn là thấy không thể trượt. Nhưng văn bản **thực sự đến được** bộ chuẩn hoá thì khoảng cách biến mất: vùng 2021 chỉ bắt được dòng đầu của tên cơ quan (19 ký tự), còn vùng 2024 nuốt luôn dòng tiếng Anh bên dưới (31 ký tự). Đo được **2021 = 19–20, 2024 = 15 và 31 — chồng lấn, và ngược chiều.** Độ dài là thuộc tính của **vùng cắt**, không phải của trường. Chỉ độ dài **từ đầu tiên** (`BỘ` 2 ký tự / `CỤC` ≥3) là dùng được, và chỉ đủ tư cách **xác nhận** chứ không quyết định (mẫu thế hệ 2024 chỉ có 2 ảnh).
    - ⭐ **Hai nhánh mã chết lộ ra nhờ ngưỡng coverage 95% của `domain/`, và cả hai đều là phát hiện thật.** (a) `fuzz.ratio` trên 3 ký tự chỉ trả được {0, 33.3, 66.7, 100} nên bậc "quyết định nhưng chưa chắc chắn" (80–95) **không thể xảy ra** — nghĩa là quy tắc thật sự là "chữ đầu khớp **chính xác**", và hai hằng số confidence trung gian là mã chết. (b) Guard `MIN_HEAD_LEN` không bao giờ chạy được vì bộ lọc token đầu đã bảo đảm điều đó rồi. Xoá cả hai; giữ lại **lý do** ở chỗ nó thực sự được thi hành.
    - **Kết quả toàn chuỗi S3→S11:** `issue_place` 12/20 → **20/20**, conf 0.60 → **0.89**, ô phải review 12 → **1**, thẻ bị chặn 10/20 → **5/20**, `V-OCR-017` 9 → **1**, độ tin cậy tổng trung bình 0.92 → **0.97**. False Confidence giữ nguyên **0/16 = 0.0%**.
    - ⚠️ Ô duy nhất còn phải review là mặt sau thẻ 2024 mà **chính bộ nhận dạng** chỉ tự tin 0.595 — `FieldNormalizer` chặn trần confidence của nơi cấp bằng `min(conf_vùng, conf_tầng)`, nên tầng 5 nói 0.92 vẫn bị hạ về 0.59. Đúng và cố ý: giữ nguyên chứ không nới, vì trường này không có kênh chính xác nào kiểm chứng.

**Milestones:**
- [x] ⭐ **M2 — ĐẠT 2026-08-10, vượt phạm vi đặt ra.** Mốc yêu cầu "2 ảnh CCCD thật → 6 trường đúng, chạy offline". Đo được: **20 thẻ thật** qua đủ chuỗi S3→S11 (tiền xử lý → QR/MRZ/OCR → trích trường → chuẩn hoá → hợp nhất → validation), hoàn toàn cục bộ (P-01 đã có test cắt socket từ tuần 3). ⭐ **Đo lại 2026-08-11 sau tầng 5: đủ 6/6 trường đọc 100%**, độ tin cậy tổng trung bình **0.97** (trước 0.92)
  - Công cụ: `python backend/scripts/verify_extraction.py "<thư mục ảnh>"`

**KPIs** (đo trên 46 ảnh dev, **không phải Golden Set** — mọi con số còn cần nhãn kiểm định để chốt chính thức):

| Chỉ số | Mục tiêu | Đo được | Ghi chú |
|---|---|---|---|
| MRZ checksum | ≥75% | **100%** (22/22) | 0 lần phải sửa lỗi |
| QR read rate | ≥90% | **95.2%** (20/21) | mẫu số = ảnh **thật sự in QR** |
| ⭐ **False Confidence** | **≤0.5%** | ⭐ **0.0%** (0/16) | lần đầu đo được; proxy QR/MRZ, mẫu số nhỏ |
| Phân loại mặt | ≥99% | **22/22** (12 cặp 2021 + 10 cặp 2024) | đưa vào **sai thứ tự** có chủ đích |
| Field Accuracy (có QR/MRZ) | ≥99% | ⭐ **6/6 trường đạt 100%** đọc được | `issue_place` 60% → **100%** sau tầng 5 (2026-08-11) |
| Field Accuracy (OCR thuần) | ≥95% | 66% khớp kênh chính xác | gần như toàn bộ ca lệch là `full_name` mất dấu |
| Full-Card Accuracy | ≥92% | **chưa đo** | cần nhãn vàng cho cả 6 trường |
| 🔴 p95 latency | ≤9s **mỗi cặp** | **17.5 / 10.2 s mỗi ẢNH** | ⚠️ hai lần chạy cùng máy cùng ảnh lệch **1.7×** — xem rủi ro |

**Risks:**
- ✅ ~~PaddleOCR tải model từ mạng (vi phạm P-01)~~ — **ĐÓNG 2026-08-10.** `model_dir` tường minh, thiếu tệp → ném lỗi chứ không tải. Kiểm chứng bằng cách **cắt sạch lời gọi socket** rồi chạy `warm_up()` + `recognize()`: cả hai thành công, 0 lần gọi mạng, không có `~/.paddleocr`. Giữ làm test hồi quy `tests/security/test_ocr_offline.py`
- ✅ ~~MRZ không đạt 75%~~ — **ĐÓNG 2026-08-10: đo 22/22 = 100%**, 0 lần phải sửa lỗi, 2/2 ảnh có cả hai kênh cho số CCCD khớp nhau. ⚠️ Mẫu chưa gán nhãn nên Golden Set vẫn cần để chốt chính thức
- 🟠 **`FULL_NAME` từ kênh OCR mất dấu tiếng Việt** (phát hiện #12) — model latin không có đầu ra cho 38/42 chữ hoa có dấu, và **không tồn tại** model rec tiếng Việt để thay
  - 🎯 Người dùng chốt 2026-08-10: **đo trước, chốt sau**. Đo được: `full_name` 11/15 khớp chính xác; 3/4 ca còn lại chỉ **thiếu dấu cách**, 1 ca sai một ký tự. QR là nguồn chính (trọng số 1.00) nên ảnh hưởng nhỏ hơn lo ngại ban đầu. Quyết định cuối khi có Golden Set
- 🔴 **Ngân sách p95 ≤ 9 s — ĐO THẬT LÀ 17.5 s/ẢNH, nâng mức rủi ro từ 🟠 lên 🔴** (đo 2026-08-10 toàn chuỗi S3→S11). Trung bình 7.7 s/ảnh; ngân sách là 9 s cho **cả cặp**, tức ~4.5 s/ảnh
  - Máy đo là máy dev của người dùng: **4 nhân / 4 GB RAM**. Chưa biết máy đích thực tế — đây là biến số lớn nhất chưa nắm được
  - ⚠️ **Đo lại 2026-08-11 trên đúng máy đó, đúng bộ ảnh đó: trung bình 5.9 s, p95 10.2 s** — lệch **1.7×** so với lần đo 2026-08-10 mà **không có thay đổi nào trên đường OCR**. Tức là phương sai giữa các lần chạy lớn ngang cỡ khoảng cách tới chỉ tiêu. **Đừng chốt hay bác bỏ chỉ tiêu này bằng một lần chạy** — khi đo thật (P3, hoặc khi có Golden Set) phải chạy nhiều lượt và báo cáo cả dải, không chỉ một con số
  - ✅ Đã áp dụng: nhận dạng toàn thẻ **một lượt duy nhất**, thế hệ thẻ suy từ chính các vùng text đó (phát hiện #32) — đã cắt từ 28–45 s xuống 7.7 s và xoá sạch `OcrTimeoutError`
  - 🎯 P3 còn 3 đòn bẩy chưa dùng: (1) **bỏ hẳn lượt OCR khi QR đã đọc được cả 5 trường** — đo cho thấy QR thắng 19/20 ở 4 trường, nên với thẻ có QR tốt thì kênh OCR chỉ còn phục vụ `issue_place`; (2) chạy hai ảnh **song song** (ngân sách là cho cặp, không phải cho ảnh); (3) hạ `target_long_edge` và đo lại độ chính xác
  - ⚠️ **Đừng chốt hạ chất lượng trước khi thử (1) và (2)** — cả hai không đụng gì tới độ chính xác
- ✅ ~~QR chưa đạt ≥90%~~ — **ĐÓNG 2026-08-10: đo 20/21 = 95.2%.** Hai nguyên nhân tách bạch, và cái thứ hai lớn hơn cái thứ nhất:
  - **Mẫu số sai** (phát hiện #22): 5 mặt trước Căn cước 2024 bị tính là "QR trượt" dù thế hệ đó **không in QR ở mặt trước**, và 2 mặt sau có QR thì bị bỏ sót. Sửa nhãn ⇒ 66.7% → 85.7% mà không đụng một dòng mã giải mã nào
  - **Kênh yếu thật** (phát hiện #23): thêm 2 lần thử đọc **kênh Blue** ⇒ 85.7% → **95.2%**, 0 thẻ bị mất, +43 ms/ảnh
  - ⚠️ Nhãn thế hệ vẫn đọc bằng mắt trên 46 ảnh, chưa phải nhãn kiểm định — Golden Set vẫn cần để chốt chính thức
- ✅ ~~Phân loại mặt trên Căn cước 2024 chưa đo~~ — **ĐÓNG 2026-08-10.** Dự đoán đúng: **0/10 cặp** ra `RESOLVED`. Sửa bằng tín hiệu tổ hợp QR+MRZ → BACK trọng số 0.80 (không phải bằng tín hiệu chân dung như dự kiến, vì tín hiệu đó cần Haar cascade): **10/10 đúng, 0 sai**, đối chứng 2021 giữ 12/12, và **nhanh hơn 26%**. Xem phát hiện #31
- ✅ ~~**`issue_place` là trường yếu duy nhất còn lại**~~ — **ĐÓNG 2026-08-11 bằng tầng 5 (phát hiện #34).** Đo lại toàn chuỗi: **20/20 thẻ** (trước 12/20), conf trung bình **0.89** (trước 0.60), **1** ô phải review (trước 12), thẻ bị chặn **5/20** (trước 10/20 — 5 ca còn lại đều là lỗi dữ liệu mẫu: thiếu ảnh mặt trước hoặc trùng mặt, không phải lỗi pipeline). `V-OCR-017` từ 9 xuống 1
  - ⚠️ **Hai nguyên nhân, và nguyên nhân lớn hơn nằm ở phép đo.** Script chỉ gieo **2** dòng alias trong khi seed thật có **19**, và cả 2 dòng đó đều **tầng 4** — mà tầng 3 chỉ xét dòng có `alias_normalized`, nên nó **không có gì để so** và không thể kích hoạt. Mọi ca rơi thẳng xuống 0.60. "Trường yếu đều ở 0.60" là tính chất của fixture, không phải của trường
  - ⚠️ Nhưng gieo đủ 19 dòng thật **cũng không cứu được**: đo lại cho thấy tầng 3 đúng 13/22 ở 0.65, tầng 4 đúng 1/22, và **8/22 không ra giá trị nào**. Xem phát hiện #34
  - 🎯 Còn lại: tầng 5 **chưa có nhãn độc lập nào kiểm chứng** — `issue_place` nằm ngoài phần giao mà proxy False Confidence phủ được. Golden Set là cách duy nhất
- 🔴 Chưa có Golden Set 200 cặp ảnh **đã gán nhãn trước/sau + thế hệ thẻ**
  - 🎯 **Vẫn chặn việc chốt chính thức mọi KPI của P2**, kể cả những chỉ tiêu đã đo đạt
  - ⭐ **Cập nhật 2026-08-10: False Confidence không còn là ô trống — đo được 0/16 = 0.0%** bằng proxy QR/MRZ-làm-nhãn (phát hiện #33). Nhưng proxy chỉ phủ **phần giao** giữa OCR và kênh chính xác, nên nó **không** nói gì về `issue_place` (không kênh chính xác nào có) hay `issue_date` trên thẻ 2021. Golden Set vẫn là thứ duy nhất đo được chỉ số đầy đủ
  - ⭐ **Nhãn phải có cả trường "thế hệ thẻ".** Bộ 53 ảnh chứa cả hai thế hệ suốt 3 tuần mà không lộ ra, vì mọi phép đo đều làm theo tỉ lệ tổng chứ không soi từng ca lệch. Golden Set thiếu nhãn này sẽ giấu đúng lỗi đó thêm một lần nữa

---

### 🔄 P3 — Nghiệp vụ & Sinh tài liệu (3 tuần)
**Status:** IN PROGRESS — bắt đầu 2026-08-11  
**Est. Completion:** 2026-10-14

**Thứ tự module đã chốt** (mỗi module: cấu trúc → mã → giải thích → chạy → test, xong mới sang cái sau):

| # | Module | Trạng thái |
|---|---|---|
| 1 | ⭐ **`ExtractionPipeline`** (Application §12.3) — biến 7 Port của P2 thành một lời gọi | ✅ **2026-08-11** |
| 2 | ⭐ **Alias repository + Use Case OCR + nối `container.py`** | ✅ **2026-08-11** |
| 3 | ⭐ **`TemplateInspector`** (Port 20, AST Jinja2, 10 mã chẩn đoán, chặn SSTI) | ✅ **2026-08-11** |
| 4 | ⭐ **`RenderContextBuilder` + `DocxContextAdapter` + `DocxRenderer` + repo `Contract`** (nợ từ P1) | ✅ **2026-08-11** |
| 5 | ~~`PdfConverter` + `LibreOfficeManager` + font tiếng Việt~~ | 🗑️ **ĐÃ GỠ (D2.1)** |
| 6 | `JobRunner` (polling bảng `job`) | ⏳ |
| 7 | ⭐ **62** endpoint + test tích hợp | ⏳ |

**Deliverables:**
- [x] ⭐ **`ExtractionPipeline`** — 9 chặng S3→S11, không bao giờ ném ngoại lệ, tiến độ mỗi chặng
- [x] ⭐ **Port 19 `IDocumentTypeSelector`** + `MarkerDocumentTypeSelector` — nhận thế hệ thẻ từ chữ đã đọc
- [x] ⭐ Migration `010` — cột `identity_markers` + 🔴 nới CHECK `tier_range` lên 1..5
- [x] ⭐ **Port 10 `IAliasRepository` có hiện thực thật** + repo `document_type` + repo `ocr_result`
- [x] ⭐ **`ProcessOcrSessionUseCase`** + `container.py` nối trọn chuỗi OCR
- [x] ⭐ **D2.1 — gỡ toàn bộ khâu xuất PDF và LibreOffice** (migration `011`)
- [x] ⭐ **Port 20 `ITemplateInspector` + `DocxTemplateInspector`** — 2 mẫu thật VALID, 12/12 payload SSTI bị chặn
- [x] ⭐ **Từ điển 28 biến hệ thống** (§9.5 — sửa từ con số 25 sai trong tài liệu)
- [x] ⭐ **`RenderContextBuilder` + `DocxContextAdapter`** — 29 biến, `StyledValue` không bao giờ chạm `docxtpl` ở tầng Application
- [x] ⭐ **DOCX Renderer (Port 12)** — 2 mẫu thật, **STK in đậm**, p95 332/618 ms, khớp `docxtpl` từng ký tự
- [x] ⭐ **Bảng định dạng §9.7 đầy đủ 11 kiểu** (`value_formatter.py`, gồm đọc số tiền thành chữ tiếng Việt)
- [x] ⭐ **Repo `Contract` + `ContractDocument`** — hết nợ P1, đủ 9/9 repository
- [x] Đặt tên file xuất *(`ExportNameGenerator` đã có từ P1; module 4 chỉ dùng, không sửa)*
- [x] ⭐ **`IFileStorage` (Port 11) — `EncryptedFileVault` + `path_guard`**, VAULT_KEY riêng, AAD = đường dẫn
- [x] ⭐ **10 quy tắc `V-CTR-*`** (§8.6) — tập `CONTRACT_GENERATION` hết rỗng
- [x] ⭐ **`GenerateContractUseCase`** — trọn §9.11, 2 transaction, p95 201–320 ms trên 2 mẫu thật
- [ ] 62 endpoint
- [ ] JobRunner (polling bảng job, không Queue)

**Milestones:**
- M3: API tuần tự → ⭐ **DOCX** mở được bằng Word, STK in đậm

#### ⭐ Module 1 — `ExtractionPipeline` (2026-08-11)

Đo thật trên **15 thẻ ghép đúng** (46 ảnh dùng được của bộ mẫu, ghép bằng số CCCD hai kênh chính xác cùng in — **không** ghép theo tên file):

| Chỉ số | Kết quả |
|---|---|
| Thẻ đọc đủ 6/6 trường | **15/15** |
| Ô phải review | **0** |
| Độ tin cậy tổng | trung bình **0.99** (min 0.98) |
| Lỗi validation | **0** |
| ⭐ Lượt quét toàn thẻ | **1.00/cặp thay vì 2 — cắt đúng 50% công nhận dạng** |
| 🔴 Thời gian mỗi **cặp** | trung bình **9.5 s**, p95 **12.4 s** — ngân sách 9 s |
| ⭐ Port 19 (quét riêng 46 ảnh) | **43/44 quyết định đúng · 0 sai · 1 từ chối trả lời** |

Test: **1228 xanh** (từ 1155) · ruff sạch · `mypy --strict` sạch · import-linter 4/4.

**Phát hiện #35 — bẫy mẫu số lại xuất hiện, lần này ở chính bộ đo.** Bản đầu của `verify_pipeline.py` ghép ảnh theo **tên file liền nhau**. Kết quả trông như lỗi pipeline: 23/26 cặp báo `SOURCE_CONFLICT`, `id_number` tin cậy trung bình 0.68, và **không nhận ra một thẻ Căn cước 2024 nào**. Thực tế là hai ảnh của hai người khác nhau bị đưa vào `execute()` như một thẻ. `verify_extraction.py` đã ghi rõ cách ghép đúng ngay trong docstring của nó — và vẫn bị lặp lại. Sau khi sửa: 15/15 thẻ, 6/6 trường, 0 xung đột.

**Phát hiện #36 — 🔴 `ck_ocr_field__tier_range` vẫn là 1..4 trong khi tầng 5 đã chạy từ hôm trước.** Tầng 5 giải **20/20** lần đọc `issue_place` trong bộ mẫu, nghĩa là ràng buộc cũ sẽ từ chối gần như **mọi** dòng `ocr_field` — lúc INSERT, trong job nền, sau khi đã trả toàn bộ chi phí OCR. Không lộ ra khi đọc mã vì hai bên nằm ở hai tầng khác nhau và không có gì nối chúng. Đã nới bằng migration `010`, thêm hằng số `IssuePlaceNormalizer.MAX_TIER`, và thêm `tests/unit/migrations/test_constraint_names.py` so hai bên **không cần CSDL** (test đó cũng kiểm mọi `op.drop_constraint` có trỏ tới ràng buộc thật hay không).

**Phát hiện #37 — không dùng `anchor_patterns` để nhận thế hệ thẻ.** Ý tưởng "chấm điểm anchor của từng thế hệ" đẹp trên giấy và sai trên dữ liệu: hai thế hệ khai chung `Full name`, `Date of birth`, `BỘ CÔNG AN`, và `Ngày, tháng, năm` (2021) là **tiền tố** của `Ngày, tháng, năm sinh` (2024). Đếm anchor khớp là đo **ảnh rõ tới đâu**. Dùng danh sách marker đã đo sẵn ở tuần 3b, đưa vào cột `document_type.identity_markers`.

**Điểm mù còn lại của module 1:**
- ⚠️ **Chưa đo được pipeline trên một thẻ Căn cước 2024 nào.** Thế hệ đó in QR **cạnh** MRZ ở mặt sau, nên mặt trước không có kênh chính xác nào ⇒ không sinh số CCCD ⇒ **không ghép cặp được bằng phương pháp hiện tại**. Đã bù bằng `--selector-sweep` đo riêng Port 19 trên từng ảnh (6/7 ảnh 2024 nhận đúng), nhưng toàn chuỗi trên thẻ 2024 vẫn là **chưa đo**.
- ⚠️ Ca Port 19 từ chối trả lời là một **mặt sau 2024** chữ nhoè. Tín hiệu **cấu trúc** (một ảnh mang cả QR lẫn MRZ ⇒ mặt sau 2024) giải được, nhưng Port 19 chỉ nhận `regions`. Vá được bằng cách thêm "thế hệ này in QR ở mặt nào" vào `document_type` — hoãn có chủ đích (P-10).
- ⚠️ **Chưa chạy migration `010` trên PostgreSQL thật** — cụm portable ở cổng 55432 không chạy trên máy này. Test tĩnh đã kiểm tên ràng buộc và dải tầng, nhưng `upgrade head` thật vẫn là việc phải làm ở module 2.

#### ⭐ D2.1 — Gỡ toàn bộ khâu xuất PDF và LibreOffice (2026-08-11)

Quyết định của người dùng: **chỉ cần `.docx`**. Tài liệu thiết kế sửa trước, mã nguồn sau (đúng quy tắc trong `CLAUDE.md`).

| Nơi | Trước | Sau |
|---|---|---|
| Port | 19 | ⭐ **18** — bỏ `IPdfConverter`, **để khuyết số 13** |
| Endpoint | 64 | **62** — bỏ `retry-pdf` và `documents/pdf` |
| `ContractStatus` | 9 giá trị | **6** — bỏ `DOCX_READY` · `PDF_CONVERTING` · `PDF_FAILED` |
| `JobType` | 6 | **5** — bỏ `PDF_CONVERT` |
| `DocType` | 2 | **1** |
| Khoá cấu hình | 28 | **25** |
| Lớp ngoại lệ | 23 | **20** |
| Gói cài đặt (ước tính) | ~1.1 GB | ~700 MB |

- **Vì sao để khuyết số Port 13 thay vì đánh lại số:** đánh lại sẽ làm sai mọi trích dẫn `§12.1x` đang nằm trong mã nguồn, tài liệu khác và lịch sử commit. Giữ khoảng trống là **rẻ hơn một lần** và **đúng mãi mãi**; đánh lại số là rẻ hôm nay và sai từ ngày mai. Cùng lý do với `COCAS-7004`/`7005`: gỡ mã lỗi nhưng **không tái sử dụng số**.
- ⭐ **Gỡ PDF làm sụp luôn hai trạng thái trung gian.** `DOCX_READY` chỉ có nghĩa "đã có DOCX, chưa có PDF" — sau D2.1 khoảng thời gian đó bằng không, nên `GENERATING` đi thẳng `COMPLETED` và `mark_docx_ready()` nhập vào `mark_completed(snapshot_sha256, now)`. Giữ lại `DOCX_READY` sẽ là một trạng thái mà **không thao tác nào có thể quan sát được**.
- ⚠️ **Migration `011` chuyển dữ liệu, không xoá.** Hợp đồng đang kẹt ở `DOCX_READY`/`PDF_CONVERTING`/`PDF_FAILED` đều có nghĩa *file `.docx` đã ghi xong* ⇒ chuyển sang `COMPLETED`. Xoá chúng là **huỷ chứng từ pháp lý** để làm vừa một ràng buộc CHECK. Chỉ job `PDF_CONVERT` đang xếp hàng bị xoá — chúng mô tả công việc không còn tồn tại.
- ⚠️ **Seed migration `007` bị sửa tại chỗ xuống 25 khoá thay vì để `011` xoá bù.** Cơ sở dữ liệu seed **sau** D2.1 không được phép sinh ra 3 dòng mà `011` tồn tại để xoá; `011` chỉ dành cho CSDL seed trước nó.
- ⭐ **Một con số dẫn xuất đã lạc hậu ngay lập tức:** "chính sách xoá ảnh giảm dung lượng **9 lần**" (§4.10) thành **~20 lần** sau khi bỏ 180 MB PDF/1000 hợp đồng. Khi phần "không phải ảnh" nhỏ đi thì tỉ lệ này **lớn lên**, không nhỏ đi — đúng chiều ngược với trực giác khi cắt phạm vi.
- ⭐ **Rủi ro 🟠 "LibreOffice thiếu font tiếng Việt" đã đóng** — nó là rủi ro đứng đầu sổ P3 và biến mất cùng thứ sinh ra nó, không phải nhờ giảm nhẹ.
- ⚠️ **Đổi lại, mất khung xem trước trong ứng dụng.** WebView2 xem được PDF nhưng không xem được `.docx`. W4/W6 nay chỉ hiện tên tài liệu + nút mở bằng Word — chấp nhận có chủ ý, vì người dùng vẫn phải mở Word để ký/sửa.

Test: **1251 xanh** (từ 1224) · ruff sạch · `mypy --strict` sạch · import-linter 4/4.

#### ⭐ Module 2 — Alias repository + Use Case OCR + nối `container.py` (2026-08-11)

Thứ bị chặn từ module 1 đã thông: `ExtractionPipeline` **chạy được từ Composition Root với dữ liệu thật**.

| Thành phần mới | Vai trò |
|---|---|
| `SqlAlchemyAliasRepository` | ⭐ Port 10 — hiện thực thật đầu tiên, có cache + `invalidate()` |
| `SqlAlchemyDocumentTypeRepository` | Nạp `DocumentTypeSpec` (nguồn hợp lệ duy nhất cho tham số `doc_types`) |
| `SqlAlchemyOcrResultRepository` | Ghi `ocr_result` + 6 `ocr_field`, mã hoá mọi giá trị |
| `OcrResultSnapshot` / `OcrFieldSnapshot` | Từ vựng Domain để Application dịch `ExtractionResult` sang |
| `ProcessOcrSessionUseCase` | Chạy chuỗi + lưu, dùng chung cho `POST /ocr` và job `OCR` |

- ⭐ **Hai repository này nhận session *factory*, không nhận session.** Chúng phục vụ `IssuePlaceNormalizer` — một Domain Service sống suốt vòng đời tiến trình bên trong pipeline, không phục vụ transaction của một Use Case. Gắn session vào sẽ hoặc (a) ghim singleton vào một session mà Use Case sẽ đóng dưới chân nó, hoặc (b) kéo một lượt đọc 19 dòng dữ liệu tham chiếu vào transaction nghiệp vụ.
- ⭐ **`find_by_alias` không phải một truy vấn riêng** mà đọc chính cache của `list_active`. Hai đường SQL khác nhau tới cùng một bảng là cách tầng 2 và tầng 3 bắt đầu bất đồng ý về việc *có những dòng nào*.
- ⚠️ **`alias_normalized` là NULL ở dòng tầng 4** (chúng mang `keywords`). Tra cứu chuỗi rỗng mà khớp NULL sẽ trả về một dòng từ khoá và gán giá trị chuẩn của nó ở **độ tin cậy đầy đủ** — sai đầy tự tin, đúng loại lỗi §7.9 chặn phát hành.
- ⭐ **Use Case dùng HAI transaction ngắn kẹp lấy lượt OCR** — ngoại lệ có chủ đích với §12.14, đã ghi vào tài liệu (§12.14.1). Một transaction bao trọn 9.5 giây sẽ giữ nguyên một kết nối pool trong 9.5 giây mà không dùng, và sự cố giữa chừng sẽ rollback cả trạng thái `PROCESSING` → phiên về `QUEUED` trong khi log nói ngược lại. Cái giá: sự cố **giữa** hai transaction để lại phiên `PROCESSING` vĩnh viễn — việc của cơ chế phục hồi job treo (§12.15).
- ⭐ **Infrastructure không được import `ExtractionResult`.** Nó là DTO tầng Application, mà `cocas.infrastructure` nằm **dưới** `cocas.application` trong hợp đồng import-linter. Bản đầu của repository làm đúng thế và bị chặn — nên `OcrResultSnapshot` ra đời làm từ vựng Domain, và Use Case là bên dịch. Không cần thêm số Port nào: nó khớp `IWriteRepository[T]` (Port 9).
- ⭐ **Phiên `FAILED` không có dòng `ocr_result` nào** (§4.4.3). Ghi một dòng toàn NULL sẽ khiến "lượt chạy không ra gì" không phân biệt được với "thẻ trắng".
- ⚠️ **`mrz_corrections_applied`: `NULL` ≠ `0`.** `NULL` = không có MRZ để đọc; `0` = đọc được và không phải sửa gì. Tỉ lệ sửa lỗi §7.5 chia cho vế thứ hai — để `0` thay `NULL` sẽ kéo tỉ lệ xuống bằng dữ liệu không tồn tại.
- ⚠️ **AAD gắn vào `ocr_field.id`, không gắn vào phiên hay tên trường.** Gắn thô hơn thì một ciphertext dời được giữa 6 dòng của cùng kết quả: `dob` dán đè `id_number` vẫn giải mã sạch và hợp đồng mang ngày sinh làm số căn cước.
- ⭐ **`PaddleOcrAdapter.warm_up()` cố ý KHÔNG gọi trong `Container.__init__`** — nạp model từ đĩa phải hỏng to vào lúc có người đang nhìn, không phải lúc màn hình chờ đang che.

⭐ **Chạy lại `verify_pipeline.py` sau toàn bộ thay đổi** (cùng 15 cặp, cùng máy): 15/15 thẻ đủ 6/6 trường, 0 ô review, conf 0.99, 1.00 lượt quét/cặp — **không hồi quy**.

| Chỉ số thời gian | Lần đo 1 (module 1) | Lần đo 2 (sau module 2) |
|---|---|---|
| Trung bình / cặp | 9.5 s | **5.3 s** |
| p95 / cặp | 12.4 s | **10.5 s** |
| Số cặp vượt ngân sách 9 s | — | **1/15** |

⚠️ **Đừng đọc đây là "đã nhanh hơn nhờ module 2".** Module 2 không đụng gì vào đường nhận dạng. Đây chính là **biến động 1.7 lần giữa hai lần chạy giống hệt nhau** đã ghi ở module 1, nay đo được lần thứ hai theo chiều ngược lại. Kết luận đúng duy nhất rút ra được: **p95 vẫn vượt 9 s, và một lần chạy vẫn không đủ để chốt hay bác bỏ chỉ tiêu này.**

**Điểm mù còn lại của module 2:**
- ⚠️ **5 test tích hợp mới chưa chạy trên PostgreSQL thật** (`tests/integration/persistence/test_ocr_persistence.py`) — cụm portable ở cổng 55432 vẫn không chạy trên máy này. Chúng là **cách duy nhất** kiểm chứng `ck_ocr_field__tier_range` đã nới đúng, và cùng lý do đó `upgrade head` với migration `010`+`011` vẫn là món nợ.
- ⚠️ **Chưa có `IFileStorage`**, nên Use Case nhận **bytes ảnh** chứ không tự nạp từ Vault. Bên gọi (endpoint/job) chịu trách nhiệm đó — module 6/7.

#### ⭐ Module 3 — `TemplateInspector` (Port 20) (2026-08-11)

Lần đầu tiên trong dự án **hai file `.docx` thật được đưa vào một phép đo** — và hoá ra chúng đã có sẵn placeholder Jinja2 đúng như §4.5 dự đoán.

| Chỉ số | Kết quả |
|---|---|
| Mẫu thật đăng ký được | **2/2** — cả hai `VALID`, **0 chẩn đoán** |
| `01A_HD_GDN.docx` | **12 biến** — đúng bằng con số §4.5 dự đoán ("12 biến") |
| `01A_HD_GDKQ.docx` | **9 biến**, `securities_account_no` nhận đúng là **required + richtext** |
| Payload SSTI bị chặn | **12/12** |
| Mẫu sạch bị chặn nhầm | **0/4** |
| Test mới | **74** (55 inspector · 12 từ điển biến · 7 kiểu trả về) |

Đo lại bất cứ lúc nào: `python backend/scripts/verify_template_inspection.py "<thư mục .docx>"`.

**Ba phát hiện, đều chỉ lộ ra khi chạy thật:**

1. 🔴🔴 **Biện pháp bảo mật §9.9 #3 bản D2.0 là một cổng chặn LUÔN ĐÓNG.** Blacklist quét XML thô khớp `open` bên trong `http://schemas.openxmlformats.org/…` — không gian tên **bắt buộc của chính định dạng**. Đo: **101** lần khớp trong `01A_HD_GDN.docx`, **15** trong `01A_HD_GDKQ.docx`. Không phải hai file này xui: **mọi `.docx` từng tồn tại** đều mang chuỗi đó ⇒ tỉ lệ từ chối 100% kể cả file sạch. Sửa thành 5 luật trên **hình dạng AST**, blacklist hạ xuống làm lưới thứ hai và **chỉ quét thân thẻ Jinja2** (đo lại: 16 thẻ → 0 khớp, 11 thẻ → 0 khớp).
2. ⭐⭐ **`{{r var }}` không phải cú pháp Jinja2.** `patch_xml()` của docxtpl đổi nó thành `{{ var }}` **trước khi** bộ phân tích chạy, nên `richtext_vars` / `COCAS-6008` / `COCAS-6010` không thể lấy từ AST. Bất biến "dùng AST, không dùng regex" của §12.8 chỉ áp cho **thu thập biến** — chỗ regex thật sự sai. Quét marker bằng cách **xoá mọi thẻ XML**: thao tác đó tự nối lại các `run` mà Word chẻ ra, nên không cần logic gộp run riêng (đã test với `{{r secur|ities_acc|ount_no }}` chẻ 3 mảnh).
3. ⭐ **`.docx` không có "dòng".** `COCAS-6003` báo **số thứ tự đoạn văn**: chèn `\n` trước mỗi `<w:p` rồi lấy `lineno - 1` (đo: lỗi ở đoạn 6 → `lineno` 7), kèm trích nguyên văn đoạn đó. ⚠️ Số này đếm cả đoạn trong bảng nên lớn hơn `len(.paragraphs)` — GDKQ có **273** đoạn so với **16** đoạn cấp cao nhất.

**Ba quyết định có chủ ý:**
- **Thêm Port 20, không tái dùng số 13 đang khuyết** (§12.19.2). Ba Use Case gọi thẳng inspector và `cocas.application` bị cấm import `docxtpl`; không có Port thì quyết định từ chối mẫu phải trèo lên tầng Presentation.
- **Chỉ 8/10 mã chẩn đoán nằm trong `diagnostics[]`** — `6002`/`6003` được **ném**, vì hai ca đó không phân tích được gì (§12.8.1).
- **Không thêm "nhiều bên" thành lý do từ chối thứ tư** của `COCAS-6016`: §4.5 liệt kê đúng ba giới hạn v1.0, và `RenderContextBuilder` §12.9 bước 2 vốn dựng được cây nhiều bên.

**Điểm mù còn lại của module 3:**
- ⚠️ **`inspect()` chưa được Use Case nào gọi** — `RegisterTemplateUseCase` / `ValidateTemplateUseCase` là việc module 7. Hiện chỉ `Container` giữ instance.
- ⚠️ **`COCAS-6015` (>10 MB) chỉ được test bằng cách hạ ngưỡng** — chưa có file thật nào chạm mốc đó (hai mẫu: 872 KB và 577 KB).
- ⚠️ **Mọi ca kiểm thử tổng hợp đều do `python-docx` sinh ra**, không phải Word. Hai mẫu thật *có* do Word lưu và marker `{{r … }}` trong đó vẫn đọc đúng, nên rủi ro này nhỏ hơn vẻ ngoài — và cách quét (xoá **mọi** thẻ XML) vốn miễn nhiễm với `w:proofErr`/`w:bookmarkStart` chèn giữa thẻ. Cái chưa có bằng chứng là một mẫu Word **có vòng lặp / có điều kiện**.

#### ⭐ Module 4 — `RenderContextBuilder` + `DocxContextAdapter` + `DocxRenderer` + repo `Contract` (2026-08-11)

**Lần đầu tiên hệ thống sinh ra một file `.docx` thật.** Hai mẫu thật vào, hai hợp đồng đã điền ra, số TK chứng khoán in đậm.

| Chỉ số | `01A_HD_GDN` | `01A_HD_GDKQ` |
|---|---|---|
| Biến trong ngữ cảnh | 29 | 29 |
| Chuẩn bị mẫu (một lần) | 4.0 s | 6.5 s |
| ⭐ **Render mỗi hợp đồng** | p50 **291** · p95 **332** ms | p50 **324** · p95 **618** ms |
| Ngân sách NFR-03 | p95 ≤ 800 ms — ✅ | ✅ |
| ⭐ So với `docxtpl.render()` | **nhanh hơn 50 lần** | **nhanh hơn 57 lần** |
| Văn bản `<w:t>` khớp `docxtpl` | ✅ 21 412 ký tự | ✅ 28 262 ký tự |
| Tập run in đậm khớp `docxtpl` | ✅ | ✅ (có `008C123456`) |
| Còn `{{` / in ra `None` / lộ `StyledValue` | không / không / không | không / không / không |

Đo lại: `python backend/scripts/verify_docx_render.py "<thư mục .docx>"` *(thêm `--skip-reference` để bỏ phần đối chứng docxtpl, vốn tốn 15–37 s/mẫu)*.

**Bốn phát hiện:**

1. 🔴🔴 **Đi đúng đường thiết kế mô tả thì mất 14.4 s và 33.6 s cho một hợp đồng** — 18–42 lần ngân sách 800 ms. Chia pha ra thì thấy chỗ không ai đoán được: **`map_tree` chiếm 63%** — ba dòng `root.replace(body, tree)` dời cây lxml 57 000 phần tử sang mô hình đối tượng `python-docx`, chỉ để `save()` tuần tự hoá lại thứ ta **đã có sẵn dưới dạng chuỗi**. Và **thực thi template chỉ tốn 2 ms**: toàn bộ phần đắt là *chuẩn bị*, không phụ thuộc dữ liệu khách hàng. Hai sự thật đó cùng chỉ về một thiết kế: **hai pha `prepare` (có đệm) / `render`** (§9.12.1).
   - ⭐ Hệ quả với tài liệu: **§9.17 tối ưu #1 không còn là "tối ưu"**. Bản D2.0 hứa "nhanh hơn ~40%"; đo thật là **40–90 lần**, và thiếu nó thì NFR-03 vỡ chứ không phải chậm hơn.
2. ⚠️ **Nguyên nhân gốc là vệ sinh file mẫu, không phải thư viện.** `word/document.xml` nặng **2.0 MB** / **2.8 MB** cho **21 449** / **28 320** ký tự văn bản — tỉ lệ đánh dấu **94–100 lần**. Word đã băm văn bản thành 7 447 / 11 564 `w:r` (**≈2.9 ký tự mỗi run**) kèm 7 392 / 11 308 `w:proofErr` và 8 088 / 13 306 thuộc tính `w:rsid`. Đã thử gỡ `proofErr`+`rsid`: văn bản đầu ra **giống hệt** nhưng chỉ nhanh hơn **1.4 lần** — phần lớn khối lượng nằm ở `rPr` lặp trên từng run, muốn gỡ phải **gộp run**, tức sửa file của người dùng. Hoãn có chủ đích; thiết kế hai pha đã đủ.
3. ⭐⭐ **Bẫy mẫu số, lần thứ tư — và lần này là bộ đo tự làm nhiễu chính nó.** Bản đầu của `verify_docx_render.py` đo timing xen kẽ với phần đối chứng `docxtpl`. Kết quả: **mẫu nào đo THỨ HAI thì trượt p95**, và giữa hai lần chạy giống hệt nhau thì mẫu trượt **đổi chỗ cho nhau** (lần 1: GDKQ p95 1462 ms trượt / GDN 585 ms đạt; lần 2: GDKQ 698 ms đạt / GDN 1813 ms trượt). Đo lại từng mẫu trong tiến trình sạch: **p95 463–634 ms, cả 4 lần đo đều đạt**. Nguyên nhân: một lượt render `docxtpl` 37 s cộng một lần chuẩn bị nguội vừa quần bộ nhớ trên máy 4 GB. Đã sửa bộ đo: **gom toàn bộ timing trước, đối chứng sau**, mỗi mẫu một `DocxRenderer` riêng.
   - ⚠️ Kiểm chứng riêng rằng **đệm 2 mẫu cùng lúc KHÔNG phải nguyên nhân**: đo 4 tổ hợp (1 mẫu / 2 mẫu × 2 mẫu) trong 4 tiến trình sạch → p95 463 / 599 / 565 / 634 ms. Giữ 2 mẫu trong đệm tốn ~50–100 ms, không phải gấp ba.
4. ⭐ **`{{r var }}` và bảng định dạng §9.7 không kiểm được bằng mắt.** `format_currency_text` (đọc số tiền thành chữ) phải tự viết vì không thư viện nào trong 38 thư viện đã ghim đọc được tiếng Việt; bốn ca bất quy tắc (`mốt`, `lăm`, `tư`, `linh`) là toàn bộ độ khó, và `1 000 005` → `một triệu không trăm linh năm đồng` chỉ đúng khi nhóm sau nhóm đầu **buộc phải đọc cả chữ số hàng trăm bằng 0**.

**Bốn quyết định có chủ ý:**
- **Vẫn giữ `fix_tables` + `fix_docpr_ids` của docxtpl** dù cả hai mẫu đều `has_loops = false` — 156 ms để một mẫu tương lai có `{% for %}` trong bảng không vỡ số cột.
- **Bỏ timeout 10 s và giới hạn 1000 vòng lặp** (§9.12.2). Vòng lặp vô hạn cần iterable không giới hạn (ngữ cảnh chỉ có kiểu nguyên thuỷ) hoặc đệ quy (Port 20 từ chối **mọi** nút `Call`, kể cả macro tự gọi). Và timeout in-process không hiện thực đúng được: `concurrent.futures` hết giờ chỉ **bỏ chờ**, luồng vẫn quay 100% CPU vĩnh viễn — trên 4 nhân, tệ hơn triệu chứng nó chữa.
- **Snapshot đi vào repo qua `stage_snapshot()`, không gắn lên entity `Contract`** — 20–40 KB chi tiết render mà mọi lời gọi `get()` phải giải mã, kể cả màn hình danh sách.
- **Repo chặn `snapshot_sha256 = None` bằng `BusinessRuleViolation`, không để asyncpg ném.** `_base.add()` dịch **mọi** `IntegrityError` thành `DuplicateEntityError` "bản ghi đã tồn tại" — sai câu cho một dòng chưa từng được ghi.

**Điểm mù còn lại của module 4** *(hai mục đầu đã đóng ở module 6)*:
- ✅ ~~Chưa có `GenerateContractUseCase`~~ — **xong ở module 6**.
- ✅ ~~Chưa có `IFileStorage`~~ — **xong ở module 6**; `.docx` đi thẳng vào Vault dưới dạng byte, không qua file rõ.
- ⚠️ **Hai repo mới chưa chạy trên PostgreSQL thật** — cùng lý do cũ (cụm 55432 không chạy). `render_snapshot_enc` NOT NULL, AAD gắn theo `contract.id`, và `uq_contract_document__type` đều là thứ chỉ CSDL thật xác nhận được.
- ⚠️ **Chưa có golden file** (§9.18). Phép đối chứng với `docxtpl` bắt được thay đổi *nội dung*, không bắt được thay đổi *bố cục* — và bố cục là thứ duy nhất người dùng nhìn thấy.

**Risks:**
- 🔴 **p95 12.4 s/cặp so với ngân sách 9 s.** Đòn bẩy 2 đã cắt từ ~15.4 s xuống 9.5 s trung bình; phần còn lại nằm trong **bản thân lượt quét**. Ba hướng chưa thử: hạ `target_long_edge`; bỏ lượt đọc dải tiêu đề của bộ phân loại mặt khi QR/MRZ đã quyết; bỏ lần giải mã QR trùng mà bộ phân loại mặt gọi thêm (~66 ms/ảnh, đã đo, **cố ý chưa làm** vì mọi cách lấy an toàn đều phức tạp hơn phần lợi).
- ⚠️ **Hợp đồng ĐẦU TIÊN dùng một mẫu tốn 4–6.5 s** (pha chuẩn bị). Chấp nhận được, nhưng đừng đo p95 bằng lần chạy đầu, và cân nhắc làm ấm lúc khởi động ở P5.
  - ⚠️ Máy đích thật vẫn **chưa biết**, và p95 từng lệch 1.7 lần giữa hai lần chạy giống hệt nhau. Đừng chốt hay bác bỏ chỉ tiêu này bằng một lần chạy.
- ✅ ~~🟠 LibreOffice thiếu font tiếng Việt~~ — **đóng 2026-08-11 (D2.1)**: gỡ hẳn khâu xuất PDF, rủi ro biến mất cùng thứ sinh ra nó

#### ⭐ Module 6 — `EncryptedFileVault` (Port 11) + `GenerateContractUseCase` (2026-08-11)

**Mảnh áp chót của P3.** Bốn mảnh của module 4 đã render được `.docx` nhưng không ai xâu chúng lại, và file vẫn nằm trần trên đĩa. Module này đóng cả hai: hợp đồng đi trọn `GENERATING → COMPLETED`, file nằm trong Vault mã hoá, 10 quy tắc `V-CTR-*` gác cửa.

| Thành phần | Vai |
|---|---|
| `infrastructure/storage/path_guard.py` | Hình dạng → `resolve()` → `is_relative_to()` (§10.4.2) |
| `infrastructure/storage/encrypted_file_vault.py` | ⭐ Port 11 — AES-256-GCM dưới **VAULT_KEY** riêng |
| `domain/validation/contract_rules.py` | ⭐ 10 quy tắc `V-CTR-*` (§8.6) — tập `CONTRACT_GENERATION` hết rỗng |
| `application/use_cases/contract/generate_contract.py` | ⭐ Trọn §9.11, 2 transaction |
| `dto/contract.py` | `GenerateContractCommand` · `PartyRequest` · `GeneratedContract` |
| `ports/documents.py` | ⭐ `render_to_bytes()` + `RenderedDocument` |
| `unit_of_work.py` · `container.py` · `settings.py` | Nối dây: `contracts`/`contract_documents`, `file_storage`, `vault_dir`/`templates_dir` |

**Đo thật** (`verify_contract_generation.py`, `EncryptedFileVault` thật trên thư mục tạm, 2 lần chạy):

| | `01A_HD_GDN` | `01A_HD_GDKQ` |
|---|---|---|
| Nguội | 3.1 s | 4.7–5.8 s |
| ⭐ Ấm p50 | **179 / 189 ms** | **221 / 239 ms** |
| ⭐ Ấm p95 | **201 / 279 ms** | **267 / 320 ms** |
| Kích thước | 893 KB | 591 KB |

Ngân sách §9.11 là "201 sau ~500 ms" ⇒ **đạt, dư gấp đôi**. Mọi phép kiểm ✅: mở được bằng `python-docx`, 12/9 biến khai báo đều có giá trị, STK in đậm, `file_sha256` khớp bản rõ và **không** khớp ciphertext, **0 file `.docx` rõ trên đĩa**, 0 file `.tmp`, đường thất bại §9.16 để lại `GENERATION_FAILED` với 0 file mồ côi.

⭐ **Ghi Vault mã hoá gần như miễn phí.** Đo lại riêng bộ render **trong cùng phiên máy**: p50 256/172 ms, p95 371/217 ms — trùng dải với toàn chuỗi. ⚠️ Và đừng so với 291/324 ms của module 4 rồi kết luận "đã nhanh hơn": cùng một đoạn mã, không sửa dòng nào, chênh lệch là **phương sai của máy 4 nhân/4 GB**.

**Năm phát hiện:**

1. 🔴🔴 **Port 11 và Port 12 đúng riêng lẻ nhưng không ghép được.** `render()` ghi ra **đường dẫn**, `save()` nhận **byte**; bắc cầu theo đúng đặc tả chỉ có một cách — render ra file tạm rồi đọc lại — tức là đặt **một hợp đồng không mã hoá lên NTFS**, nơi file đã xoá vẫn khôi phục được. Mâu thuẫn §4.8.3 ("toàn bộ file trong Vault" thuộc cột 🔒) và mối đe doạ T9. Thêm `render_to_bytes()`; `render()` giữ nguyên chữ ký, trở thành `render_to_bytes()` + write-verify-rename, dành cho bản xem thử §9.10 vốn **cố ý** là file rõ.
   - ⭐ Chỗ để phát hiện loại lỗi này là **kiểu dữ liệu ở đường nối giữa hai Port**. `str` gặp `bytes`, và thứ duy nhất bắc được cầu là một file mà không ai muốn có.
2. ⭐⭐ **Vault phải dùng VAULT_KEY, không dùng `ICryptoService`.** Phản xạ là truyền service vào — nó đã có `encrypt`/`decrypt` với AAD, đã kiểm thử, đã nằm trong Container. Nhưng §4.8.1 dựng cây khoá 3 nhánh và `encrypt()` là nhánh **dùng thẳng KEK** (mã hoá ô PII). Gọi nó từ Vault sẽ mã hoá mọi ảnh CCCD và mọi hợp đồng dưới cùng khoá với các cột PII — **xoá bỏ đúng sự tách biệt cây khoá tồn tại để tạo ra**, mà không một dòng code nào trông sai. `DpapiCryptoService.vault_key` đã có sẵn từ P1; Container truyền **giá trị**, không truyền service. Có test riêng (`test_vault_key_is_not_the_kek`) chặn đường "đơn giản hoá" này.
   - ⭐ **AAD là `relative_path`, không phải UUID** — gồm cả category lẫn ngày, nên một `.enc` chép từ `card_image/…` sang `contract_document/…` **thất bại xác thực** thay vì giải mã vào nhầm chỗ. Cùng lớp phòng thủ như AAD của `ocr_field`, áp cho hệ thống file.
   - ⭐ `save()` **giải mã thử một lần** sau khi ghi. Đó là thứ duy nhất chứng minh AAD lúc ghi khớp AAD lúc đọc; sai thì file ghi sạch, hash sạch, và hỏng **im lặng** cho tới khi ai đó xin lại hợp đồng vài năm sau (P-09). Chi phí dưới 1 ms cho 900 KB.
3. ⚠️ **Trên Windows, `gốc / tương_đối` không bảo vệ gì.** `PureWindowsPath("C:/vault") / "C:/Windows/x"` ra `C:/Windows/x`; `… / "/Windows/x"` cũng vậy — vế phải tuyệt đối **thay thế** vế trái. `resolve()` + `is_relative_to()` vẫn bắt được cả ba dạng, nhưng **chỉ nhờ phép kiểm thứ hai**; đọc bước ghép rồi kết luận "đã ghép vào gốc nên nằm trong gốc" là suy luận sai và dễ lan sang chỗ khác. Nên `path_guard` kiểm **hình dạng trước** bằng regex chốt `{category}/{yyyy}/{mm}/{dd}/{uuid}.enc`: chuỗi không do hệ thống sinh ra **không bao giờ trở thành một `Path`**. Có test khẳng định chính hành vi pathlib đó, để ngày nó đổi thì test lên tiếng chứ không phải chốt chặn âm thầm mất một lớp.
4. ⭐⭐ **Hai transaction, và lý do khác hẳn `ProcessOcrSessionUseCase`.** §12.14.1 tách vì thời lượng (9.5 s giữ một kết nối pool). Ở đây tách vì §9.16 đòi render hỏng để lại hợp đồng ở `GENERATION_FAILED` — mà trong một transaction, ngoại lệ rollback **xoá luôn dòng vừa INSERT** và không còn gì mang trạng thái đó. Nghĩa là trạng thái `GENERATING` của §9.11 **không phải trang trí**: nó tồn tại chính xác vì dòng phải được commit **trước** việc có thể hỏng. Ghi thành ngoại lệ §12.14.2 trong tài liệu.
   - ⚠️ Cái giá: ghi Vault xong mà transaction 2 hỏng để lại một `.enc` mồ côi ⇒ **xoá file khi transaction ghi sổ hỏng** (nỗ lực tốt nhất). Không có dòng `contract_document` thì nó là rác đã mã hoá, và để lại sẽ thành một sai lệch **giả** trong job đối chiếu §9.15.
   - ⭐ Quy tắc chặn ném **trước khi ghi dòng nào**, nên rollback huỷ luôn lần tăng `contract_no_seq` — đúng ý: một yêu cầu bị từ chối **không được đốt một số hợp đồng** (cột UNIQUE; khoảng trống không giải thích được khi kiểm toán).
5. ⚠️⚠️ **Bẫy mẫu số lần thứ 5 — và lại nằm trong bộ đo.** `verify_contract_generation.py` kiểm "số hợp đồng có xuất hiện trong văn bản" và báo đỏ trên **cả hai tài liệu hoàn toàn đúng**. Quét lại bằng Port 20: `01A_HD_GDN` khai 12 biến, `01A_HD_GDKQ` khai 9 — **không mẫu nào dùng `{{contract_no}}`**. Khớp §9.14.1: số hợp đồng là định danh **nội bộ** (nhật ký, tra cứu, mã truy vết), không phải thứ in ra trang. Bộ đo khẳng định một điều mà mẫu chưa bao giờ hứa. Đổi phép kiểm thành: **mọi biến chính mẫu khai báo** đều có giá trị trong văn bản.
   - ⚠️ Lỗi thứ hai cùng lần: phép quét "có `.docx` rõ nào trên đĩa không" duyệt cả workspace nên bắt phải **Template Store của mẫu kia** — mà template thì **đúng là** file rõ theo thiết kế (§11). Cả hai đều là bộ đo sai, không phải code sai.

**Ba quyết định có chủ ý:**
- **Không xây `PlainFileVault`** dù §12.19 từng liệt kê — Container không có chế độ dev (P-11), y như quyết định đã chốt ở P1 cho `NullCryptoService`. Hiện thực fake bắt buộc là `InMemoryFileStorage` trong fixtures.
- **`V-CTR-002` chỉ kiểm "file tồn tại" ở tầng quy tắc, phần checksum để `DocxRenderer` lo.** Đọc file để băm ở tầng quy tắc là nhân đôi I/O của mọi lần sinh hợp đồng — mà renderer vốn đã băm (khoá đệm là `(đường dẫn, sha256)`) và ném `TemplateChecksumMismatchError`.
- **`contract.contract_date` NOT NULL vẫn được ghi, dù `{{contract_date}}` bị `suppressed`.** Cột ghi **khi nào hợp đồng được lập**; tài liệu để trống dòng ngày cho người dùng ký tay. Hai câu hỏi khác nhau, không phải mâu thuẫn.

**Bốn cổng kiểm tra:** 1499 test xanh (+71) · ruff sạch · `mypy --strict` 85 file 0 lỗi · import-linter 4/4 hợp đồng giữ nguyên. Coverage: `contract_rules.py` **100%**, `generate_contract.py` 96%, `encrypted_file_vault.py` 92%, `path_guard.py` 93%.

**Điểm mù còn lại:**
- ⚠️ **Chưa chạy trên PostgreSQL thật** — cụm 55432 vẫn không chạy. `get_for_update()` (`SELECT … FOR UPDATE`) là thứ **chỉ** CSDL thật kiểm được: fake UoW không có khoá dòng, nên đường đua hai hợp đồng cùng lúc chưa từng được thử.
- ⚠️ **`GeneratedContract` chưa ai tiêu thụ** — nó là hình dạng của body `201` ở §5.3.8, và endpoint là module 7.
- ⚠️ **Ảnh CCCD vẫn chưa đi vào Vault.** Port 11 đã có và `VaultCategory.CARD_IMAGE` đã khai, nhưng luồng upload (module 7) mới là nơi gọi nó. P-05 (xoá ảnh gốc sau khi sinh hợp đồng) vì thế cũng chưa nối được.

---

### ⭐⭐ P3 module 7 (lát cắt demo) — 16/62 endpoint · MỐC M3 ĐẠT
**Completed:** 2026-08-12

**Mục tiêu có chủ ý hẹp:** đúng tập endpoint mà [§5.4](docs/design/05-thiet-ke-api.md) gọi để đưa hai tấm ảnh CCCD thành một file `.docx`. 46 endpoint còn lại là quản trị, tra cứu và chẩn đoán — việc thật, nhưng không nằm trên con đường đó.

**Kết quả đo (`backend/scripts/demo_m3_contract.py`, server thật + PostgreSQL thật):**

```
15 lượt gọi HTTP + 1 vòng poll  →  ✅ 16/16
OCR      COMPLETED · 6.6–7.9 s · 6/6 trường · conf 1.00 (QR) / 0.90 (issue_place)
Hợp đồng 01A-GDN-202608-00001 → 00002 (số tăng đúng qua 2 lần chạy)
Sinh     4.3–4.6 s (gồm cả lần chuẩn bị mẫu nguội)
File     872 KB · zip hợp lệ · 21 502 ký tự · 0 placeholder sót
         chứa tên khách, số CCCD, ngày sinh 27/02/1979, tên ngân hàng
```

**Đã dựng hạ tầng chạy được:**
- ⭐ `backend/scripts/pgctl.ps1` — `initdb`/`start`/`stop`/`reset` cụm riêng ở 55432, không cần quyền admin, mượn nhị phân của bản PostgreSQL cài sẵn. Đây là bản dựng tay của phần "PostgreSQL portable" mà Supervisor sẽ làm ở P5.
- ⭐ `backend/scripts/bootstrap_templates.py` — nạp 2 mẫu `.docx` thật vào Template Store **qua Use Case thật**, nên `declared_variables` trong CSDL (12 và 9) là thứ Port 20 đọc được, không phải danh sách chép tay.

#### 🔴🔴 Sáu lỗi mà 1532 test xanh không thấy

Cụm CSDL không chạy kể từ P1. Lần `alembic upgrade head` đầu tiên sau đó tìm ra sáu khiếm khuyết — chi tiết đầy đủ ở [`§12.20`](docs/design/12-dac-ta-module.md).

1. **`CHECK (doc_type IN ('DOCX',))`.** `repr` của tuple một phần tử mang dấu phẩy đuôi — cú pháp Python, không phải SQL. Di chứng D2.1 khi `DocType` co còn một thành viên; migration `002` chết ngay bảng `contract_document`. Khuôn `f"… IN {tuple}"` có ở **11 chỗ**; thay bằng `sql_in(column, values)` — bỏ f-string khỏi chỗ gọi thì bẫy không mọc lại được.
2. **Migration `009` gieo dòng từ khoá ở `match_tier=2`** trong khi `ck_normalization_alias__tier4` đòi tầng 4. Dòng đó **chưa từng vào được database nào**. `assigned_confidence=0.90` cũng là số không đạt được: chỉ tầng 2 đọc cột đó, tầng 4 trả hằng `_KEYWORD_CONFIDENCE = 0.60`. Một dòng seed nói dối về hành vi nó cấu hình.
3. **`002` dùng `Base.metadata.create_all()`** ⇒ nó tạo schema **hôm nay**, không phải schema tại revision 002. `010` `add_column(identity_markers)` gặp `DuplicateColumnError`; `011` `drop_column(page_count)` sẽ gặp ảnh gương của nó. Sửa: các bước cấu trúc sau `002` **nhận biết trạng thái** (`_column_exists()`). Viết tay DDL 19 bảng sẽ tái tạo đúng drift mà `create_all` tồn tại để ngăn.
4. **Alembic tự áp `NAMING_CONVENTION`** lên tên truyền vào `drop_constraint` ⇒ `ck_ocr_field__ck_ocr_field__tier_range`. ⚠️ Và **test cũ *yêu cầu* tên đầy đủ** — nó khẳng định đúng cái sai, xanh suốt. Test giờ đảo chiều, cộng một phép kiểm cấm truyền tên đã có tiền tố.
5. **`ocr_field` INSERT trước `ocr_result`** ⇒ vỡ `fk_ocr_field__ocr_result`, và flush chết ở câu đầu nên INSERT cha **không bao giờ chạy**. Hai mapper không có `relationship()` nên đơn vị công việc của SQLAlchemy không có gì để sắp thứ tự. Sửa: flush cha xong mới thêm con.
   - ⚠️ Nấp ngay sau nó: `ocr_result.created_at` NOT NULL mà `OcrResultSnapshot` **không có trường đó**. Chỉ lộ ra sau khi sửa lỗi thứ nhất.
   - ⚠️ Và repository gán **mọi** `IntegrityError` thành `DUPLICATE_OCR_RESULT`, khiến cuộc điều tra đi tìm một dòng không tồn tại. Giờ nó mang theo tên ràng buộc.
6. **`contract.snapshot_sha256` nhận hash `.docx`** trong khi §4.4.10 định nghĩa nó là "chứng minh **snapshot** không bị sửa" — trùng lặp với `contract_document.file_sha256` và bỏ trống đúng việc nó sinh ra để làm. Nó còn đến **muộn một transaction**: cột NOT NULL, dòng INSERT ở `GENERATING` trước khi render. Sửa: `mark_completed(now)` bỏ tham số, giá trị đặt lúc dựng từ `render_snapshot.digest()`.

⚠️ **Bài học chung:** test đọc `Base.metadata` kiểm *hình dạng khai báo*, không kiểm *thứ database chấp nhận*. Bốn trong sáu lỗi nằm đúng khoảng cách đó.

#### 🔴 Hàng đợi biết mình hỏng ≠ người dùng biết

Job OCR hết 3 lượt thử, ghi `FAILED` đúng chuẩn — mà `ocr_session.status` **vẫn `PROCESSING`**, nên `GET /ocr/{id}/progress` trả "đang xử lý" mãi mãi. Wizard không đi tiếp được và không có gì báo lỗi. `JobRunner` nhận thêm `on_terminal_failure`, Container nối vào `FailOcrSessionUseCase`. Bất biến mới: **một job thất bại lần cuối phải giải phóng đối tượng của nó**, và việc đó phải ở runner — handler đã ném ngoại lệ thì không chạy được nữa.

#### ⚠️ Bẫy mẫu số lần thứ 6 — vẫn trong bộ đo, lần này ở khâu chuẩn bị

`demo_m3_contract.py` ghép cặp ảnh bằng **QR đơn kênh**, và server trả `DUPLICATE_SIDE`. Lý do: trên thẻ 2021 QR nằm ở **mặt trước**, nên "hai ảnh cùng cho ra số CCCD này qua QR" nghĩa là **hai tấm ảnh của cùng một mặt**. Một kênh không ghép được thẻ — nó chỉ gom được ảnh của một mặt. Sửa: QR → mặt trước, MRZ → mặt sau, và **ghi lại kênh nào đọc được**.

Lần thứ 7 ngay sau đó: khi dùng lại khách hàng cũ, script để `bank_account_id = None` và `V-CTR-007` chặn đúng. Chỗ sửa không phải script mà là **phản hồi tra trùng** — nó phải đủ để *đi tiếp*, nên `GET /customers?id_number=…&exact=true` nay trả kèm `bank_accounts[]`.

#### ⭐ Ba quyết định cấu trúc

- **`TemplateStore` là nửa để RÕ của kho lưu trữ, không phải một `VaultCategory`** ([§12.21](docs/design/12-dac-ta-module.md)). `DocxRenderer` mở mẫu **theo đường dẫn** và đệm theo `(path, sha256)`; đi qua `IFileStorage` nghĩa là giải mã 2–3 MB mỗi hợp đồng để trả byte lại cho thứ vốn muốn một file. Và mẫu không chứa dữ liệu khách hàng. Cho hai kho chung interface là cách một hợp đồng bị ghi nhầm sang nửa để rõ.
- **`warm_up()` gọi trong handler job đầu tiên, qua `asyncio.to_thread`.** `__init__` cố ý không gọi (đúng), nhưng khoảng trống đó khiến job OCR đầu tiên ném `OcrEngineUnavailableError` ba lần. Hàng đợi là chỗ đúng: nó là bên duy nhất cần engine, trả giá một lần, và một model thiếu làm hỏng một job người dùng **nhìn thấy** thay vì một lần khởi động không ai xem (P-08).
- **`COCAS-3007` kiểm trước khi ghi Vault**, và mang theo `image_id` của ảnh đã có. Trước đó ảnh bị mã hoá, ghi, xác minh rồi mới bị UNIQUE từ chối và xoá đi. Kèm theo: phản hồi giờ đủ để client mời "dùng lại ảnh đã tải".

#### Bốn cổng kiểm tra
**1634 test xanh (+102)** · ruff sạch (`src tests scripts`) · `mypy --strict` 93 file 0 lỗi · import-linter 4/4. Coverage tầng Application của các Use Case mới: `download_contract_document` **100%**, `manage_customer` **100%**, `read_templates` 98%, `register_template_version` 99%, `upload_card_image` 97%, `manage_ocr_session` 96%, `run_ocr_job` 94%.

#### 🔴 Máy 3.9 GB đã giết tiến trình uvicorn hai lần
PaddleOCR nạp cùng lúc với một cụm Postgres cấu hình mặc định làm hết RAM; tiến trình bị hệ điều hành kết liễu **không để lại traceback**, chỉ dừng log giữa chừng. Hạ `shared_buffers` xuống 32MB (và `max_connections` xuống 20) là thứ làm nó chạy được. Ghi vào `pgctl.ps1`.

#### Điểm mù còn lại
- ⚠️ **46/62 endpoint chưa làm** — trong đó có cả `POST /templates` (đăng ký mẫu mới, hiện thực P-06) và toàn bộ nhóm sao lưu/chẩn đoán.
- ⚠️ **`RETENTION_PURGE` chưa có handler.** Ảnh CCCD **đã** vào Vault (nợ cũ đóng), nhưng chưa gì xoá chúng ⇒ **P-05 vẫn chưa nối xong**, chỉ khác là giờ đã có dữ liệu để xoá.
- ⚠️ **`SELECT … FOR UPDATE` chạy được nhưng chưa bị đua.** Migration và luồng chính đã trên PostgreSQL thật, nhưng hai hợp đồng đồng thời trên cùng một mẫu thì chưa thử.
- ⚠️ **Chỉ đo trên thẻ CCCD_CHIP 2021.** Toàn chuỗi trên Căn cước 2024 vẫn chưa chạy lần nào — điểm mù cũ từ P2, chưa đóng.
- ⚠️ **Tự động hoá `alembic upgrade head` lúc khởi động chưa có** (bootstrap lần đầu của P5). Hiện phải chạy tay.

---

### ⏳ P4 — Giao diện (3 tuần, song song P3)
**Status:** TODO  
**Est. Start:** 2026-09-23  
**Est. Completion:** 2026-10-14

**Deliverables:**
- [ ] App Shell + Design System (MUI, fonts)
- [ ] Wizard 3 bước (sinh động từ party_schema)
- [ ] ImageInspector + ConfidenceField (highlight ảnh)
- [ ] DynamicFieldSet (5 kiểu ô, 2 mẫu 2 form)
- [ ] Tự lưu nháp (localStorage)
- [ ] Các màn hình còn lại (dashboard, list, detail, settings)
- [ ] 14 phím tắt

**Milestones:**
- M4: Người thật tạo xong 1 HĐ không cần hướng dẫn

**Risks:**
- 🟡 Đồng bộ highlight ảnh phức tạp
  - 🎯 Tuần 2 P4: làm sớm, giản lược nếu quá khó

---

### ⏳ P5 — Tích hợp Desktop (2 tuần)
**Status:** TODO  
**Est. Start:** 2026-10-14  
**Est. Completion:** 2026-10-28

**Deliverables:**
- [ ] Tauri Shell (CSP strict, single-instance)
- [ ] Supervisor (spawn backend, health check, restart ×3)
- [ ] Local Handshake Token
- [ ] PostgreSQL portable (initdb, pg_ctl)
- [ ] LibreOffice portable (listener lười, font)
- [ ] Bootstrap lần đầu (migration + seed)
- [ ] Nạp model OCR ở luồng nền

**Milestones:**
- M5: Double-click exe → ~35 giây → Dashboard

**Risks:**
- 🔴 Đây là giai đoạn nhiều bất ngờ nhất
  - 🎯 Dành sẵn 3 ngày đệm

---

### ⏳ P6 — Hoàn thiện & Đóng gói (2 tuần)
**Status:** TODO  
**Est. Start:** 2026-10-28  
**Est. Completion:** 2026-11-11

**Deliverables:**
- [ ] Sao lưu & Khôi phục (.cocasbak)
- [ ] Màn hình Chẩn đoán (health, dung lượng, check file)
- [ ] Installer NSIS (per-user, no admin)
- [ ] Ký số (installer + exe)
- [ ] Kiểm thử toàn diện (coverage, security)

**Milestones:**
- M6: Cài trên 3 máy khác nhau (Win10, Win11, standard user) → tất cả chạy

---

### ⏳ P7 — Nghiệm thu (1 tuần)
**Status:** TODO  
**Est. Start:** 2026-11-11  
**Est. Completion:** 2026-11-18

**Deliverables:**
- [ ] UAT (2–3 người ≥3 ngày, ≥50 HĐ)
- [ ] Đo chỉ số thật (Correction Rate, thời gian/HĐ)
- [ ] Sửa lỗi ưu tiên
- [ ] Bàn giao (mã, tài liệu, installer, đào tạo 2h)

---

## 🚨 Critical Checkpoints

| # | Checkpoint | Phase | Khi quá hạn | Xử lý |
|---|---|---|---|---|
| 1 | Golden Set 200 cặp CCCD | P0 | Không kiểm chứng được MRZ, False Confidence | ⚠️ **VẪN THIẾU** — giờ là thứ duy nhất chặn việc chốt KPI |
| 2 | ~~PaddleOCR tải model offline~~ | P2w3 | ~~Vi phạm P-01~~ | ✅ **ĐÓNG 2026-08-10** — `model_dir` tường minh + test cắt socket thật |
| 3 | ~~MRZ ≥75% checksum~~ | P2w2 | ~~Hụt chỉ tiêu độ chính xác~~ | ✅ **ĐÓNG 2026-08-10** — đo 22/22 = 100%, 0 lần sửa lỗi |
| 4 | Build .exe thử | P1 | PyInstaller không đóng gói được | Test ngay P1 |
| 5 | PostgreSQL portable Windows | P1 | Chặn P5 | Spike ở P1, không đợi P5 |
| 6 | ~~Font LibreOffice~~ | P3 | ~~PDF sai layout~~ | ✅ **ĐÓNG 2026-08-11 (D2.1)** — gỡ hẳn khâu xuất PDF, rủi ro biến mất cùng thứ sinh ra nó |

---

## 📈 Metrics Tracked

- **Code Quality**
  - import-linter: 0 vi phạm Dependency Rule
  - mypy: 0 lỗi (domain + application strict)
  - Coverage: domain ≥95%, application ≥85%
  - Ruff: 0 linting warnings

- **OCR Performance** (P2 onwards)
  - Field Accuracy: ≥95% (OCR), ≥99% (QR/MRZ)
  - False Confidence: ≤0.5%
  - MRZ Checksum: ≥75%
  - QR Read Rate: ≥90%
  - Latency p95: ≤9s

- **Release Quality** (P6-P7)
  - Test coverage: domain ≥95%, app ≥85%
  - Installation: 3 machines ✅
  - UAT: ≥50 contracts, correction rate tracked

---

## 📝 Notes

- **Model:** Haiku 4.5 cho P0, P1 phần cơ bản; Sonnet 5 cho module lớn; Opus 5 cho P2 OCR (critical)
- **CI:** Chạy tự động trên PR, commit analysis
- **Pre-commit:** Bắt buộc ruff + mypy trước push
- **Database:** PostgreSQL 16 portable, cổng 55432, async everywhere
- **Windows:** Target Win11 Home, test trên Win10 + Win11

---

**Last Updated:** 2026-08-12 (P3 module 7 — lát cắt demo, mốc M3 đạt)  
**Next Review:** Sau khi chốt phạm vi P4
