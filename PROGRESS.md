# COCAS Development Progress

**Project:** COCAS v1.0 — Desktop app tự động tạo hợp đồng từ ảnh CCCD  
**Target:** 12.5 tuần, 2 người (hoặc ~24 tuần nếu 1 người)  
**Status:** In Progress

---

## 📊 Timeline Overview

```
P0: Chuẩn bị        [====] ✅ DONE (2026-08-11)
P1: Nền tảng        [====] ✅ DONE (2026-08-09)
P2: OCR Module      [=   ] 🔄 IN PROGRESS (tuần 1/4 xong) ⭐ Critical path
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

### 🔄 P2 — Module OCR (4 tuần) ⭐ CRITICAL PATH
**Status:** IN PROGRESS — tuần 1 + tuần 2 xong 2026-08-09  
**Est. Completion:** 2026-09-23

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
- [ ] Tuần 4: Chuẩn hoá + Fusion + Validation

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
- ✅ ~~PaddleOCR tải model từ mạng (vi phạm P-01)~~ — **ĐÓNG 2026-08-10.** `model_dir` tường minh, thiếu tệp → ném lỗi chứ không tải. Kiểm chứng bằng cách **cắt sạch lời gọi socket** rồi chạy `warm_up()` + `recognize()`: cả hai thành công, 0 lần gọi mạng, không có `~/.paddleocr`. Giữ làm test hồi quy `tests/security/test_ocr_offline.py`
- ✅ ~~MRZ không đạt 75%~~ — **ĐÓNG 2026-08-10: đo 22/22 = 100%**, 0 lần phải sửa lỗi, 2/2 ảnh có cả hai kênh cho số CCCD khớp nhau. ⚠️ Mẫu chưa gán nhãn nên Golden Set vẫn cần để chốt chính thức
- 🟠 **`FULL_NAME` từ kênh OCR mất dấu tiếng Việt** (phát hiện #12) — model latin không có đầu ra cho 38/42 chữ hoa có dấu, và **không tồn tại** model rec tiếng Việt để thay
  - 🎯 Người dùng chốt 2026-08-10: **đo trước, chốt sau**. Đo được: `full_name` 11/15 khớp chính xác; 3/4 ca còn lại chỉ **thiếu dấu cách**, 1 ca sai một ký tự. QR là nguồn chính (trọng số 1.00) nên ảnh hưởng nhỏ hơn lo ngại ban đầu. Quyết định cuối khi có Golden Set
- 🟠 **Ngân sách p95 ≤ 9 s cần theo dõi** (phát hiện #20) — nhận dạng toàn thẻ 2.7 s, dải 1.1–1.2 s. Ước tính hiện tại ~3.9 s/ảnh sau khi cho anchor chạy lười
  - 🎯 P3: quy trình nhận dạng toàn thẻ **một lần** rồi dùng lại các vùng, thay vì nhiều lượt đọc dải
- ✅ ~~QR chưa đạt ≥90%~~ — **ĐÓNG 2026-08-10: đo 20/21 = 95.2%.** Hai nguyên nhân tách bạch, và cái thứ hai lớn hơn cái thứ nhất:
  - **Mẫu số sai** (phát hiện #22): 5 mặt trước Căn cước 2024 bị tính là "QR trượt" dù thế hệ đó **không in QR ở mặt trước**, và 2 mặt sau có QR thì bị bỏ sót. Sửa nhãn ⇒ 66.7% → 85.7% mà không đụng một dòng mã giải mã nào
  - **Kênh yếu thật** (phát hiện #23): thêm 2 lần thử đọc **kênh Blue** ⇒ 85.7% → **95.2%**, 0 thẻ bị mất, +43 ms/ảnh
  - ⚠️ Nhãn thế hệ vẫn đọc bằng mắt trên 46 ảnh, chưa phải nhãn kiểm định — Golden Set vẫn cần để chốt chính thức
- 🟠 **Phân loại mặt trên Căn cước 2024 chưa đo** (phát hiện #24) — mặt sau có **cả** QR (bỏ phiếu FRONT 0.40) lẫn MRZ (BACK 0.40) → nhiều khả năng hoà → `AMBIGUOUS`. An toàn (không đoán bừa) nhưng có thể bắt người dùng chọn mặt thủ công cho mọi thẻ 2024
  - 🎯 Đo trước khi làm tuần 4; nếu đúng, thêm một tín hiệu phân biệt (thẻ 2024 chỉ có ảnh chân dung ở mặt trước)
- 🔴 Chưa có Golden Set 200 cặp ảnh **đã gán nhãn trước/sau + thế hệ thẻ**
  - 🎯 **Vẫn chặn việc chốt chính thức mọi KPI của P2**, kể cả những chỉ tiêu đã đo đạt. Cũng là thứ duy nhất đo được **False Confidence ≤ 0.5%** — chỉ tiêu chặn phát hành mà tới giờ **chưa đo được lần nào**
  - ⭐ **Nhãn phải có cả trường "thế hệ thẻ".** Bộ 53 ảnh chứa cả hai thế hệ suốt 3 tuần mà không lộ ra, vì mọi phép đo đều làm theo tỉ lệ tổng chứ không soi từng ca lệch. Golden Set thiếu nhãn này sẽ giấu đúng lỗi đó thêm một lần nữa

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
| 1 | Golden Set 200 cặp CCCD | P0 | Không kiểm chứng được MRZ, False Confidence | ⚠️ **VẪN THIẾU** — giờ là thứ duy nhất chặn việc chốt KPI |
| 2 | ~~PaddleOCR tải model offline~~ | P2w3 | ~~Vi phạm P-01~~ | ✅ **ĐÓNG 2026-08-10** — `model_dir` tường minh + test cắt socket thật |
| 3 | ~~MRZ ≥75% checksum~~ | P2w2 | ~~Hụt chỉ tiêu độ chính xác~~ | ✅ **ĐÓNG 2026-08-10** — đo 22/22 = 100%, 0 lần sửa lỗi |
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
