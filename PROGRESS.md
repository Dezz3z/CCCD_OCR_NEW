# COCAS Development Progress

**Project:** COCAS v1.0 — Desktop app tự động tạo hợp đồng từ ảnh CCCD  
**Target:** 12.5 tuần, 2 người (hoặc ~24 tuần nếu 1 người)  
**Status:** In Progress

---

## 📊 Timeline Overview

```
P0: Chuẩn bị        [====] ✅ DONE (2026-08-11)
P1: Nền tảng        [====] ✅ DONE (2026-08-09)
P2: OCR Module      [    ] ⏳ TODO (4 tuần) ⭐ Critical path
P3: Nghiệp vụ       [    ] ⏳ TODO (3 tuần)
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

### ⏳ P2 — Module OCR (4 tuần) ⭐ CRITICAL PATH
**Status:** TODO  
**Est. Start:** 2026-08-26  
**Est. Completion:** 2026-09-23

**Deliverables:**
- [ ] Tuần 1: Tiền xử lý ảnh (9 phép biến đổi, lazy)
- [ ] Tuần 2: Kênh QR (≥90%) + Kênh MRZ (≥75% checksum)
- [ ] Tuần 3: PaddleOCR adapter + Field Extractor
- [ ] Tuần 4: Chuẩn hoá + Fusion + Validation

**Milestones:**
- M2: 2 ảnh CCCD thật → 6 trường đúng (chạy offline)

**KPIs:**
- Field Accuracy (có QR/MRZ): ≥99%
- Field Accuracy (OCR): ≥95%
- Full-Card Accuracy: ≥92%
- **False Confidence: ≤0.5%** ⭐
- MRZ checksum: ≥75%
- QR read rate: ≥90%
- p95 latency: ≤9s

**Risks:**
- 🔴 PaddleOCR tải model từ mạng (vi phạm P-01)
  - 🎯 Tuần 3: chỉ định model_dir tường minh, test offline
- 🔴 MRZ không đạt 75% (không có charset whitelist)
  - 🎯 Tuần 2: kiểm chứng sớm, phương án B nếu cần
- 🔴 Chưa có Golden Set 200 cặp ảnh
  - 🎯 **Chuẩn bị NGAY từ P0** (song song, không đợi)

---

### ⏳ P3 — Nghiệp vụ & Sinh tài liệu (3 tuần)
**Status:** TODO  
**Est. Start:** 2026-09-23  
**Est. Completion:** 2026-10-14

**Deliverables:**
- [ ] Template Engine + RenderContextBuilder
- [ ] DOCX Renderer (2 mẫu thật, STK in đậm)
- [ ] PDF Converter (LibreOffice listener lười)
- [ ] Đặt tên file xuất
- [ ] 64 endpoint
- [ ] JobRunner (polling bảng job, không Queue)

**Milestones:**
- M3: API tuần tự → PDF mở được, STK in đậm

**Risks:**
- 🟠 LibreOffice thiếu font tiếng Việt
  - 🎯 Đầu P3: đóng gói font, test đầy đủ

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
| 1 | Golden Set 200 cặp CCCD | P0 | Không kiểm chứng được MRZ, False Confidence | Chuẩn bị ngay từ P0 |
| 2 | PaddleOCR tải model offline | P2w3 | Vi phạm P-01 | `model_dir` tường minh + test ngắt mạng |
| 3 | MRZ ≥75% checksum | P2w2 | Hụt chỉ tiêu độ chính xác | Kiểm chứng sớm, phương án B |
| 4 | Build .exe thử | P1 | PyInstaller không đóng gói được | Test ngay P1 |
| 5 | PostgreSQL portable Windows | P1 | Chặn P5 | Spike ở P1, không đợi P5 |
| 6 | Font LibreOffice | P3 | PDF sai layout | Đóng gói font đầu P3 |

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

**Last Updated:** 2026-08-11  
**Next Review:** Sau P1 completion
