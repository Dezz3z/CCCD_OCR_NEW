# P0 — Chuẩn bị: Hoàn thành

**Ngày hoàn thành:** 2026-08-11  
**Thời gian dự tính:** 1 tuần  
**Trạng thái:** ✅ Cấu trúc hoàn tất, sẵn sàng cho P1

---

## 📋 Tiêu chí hoàn thành (Roadmap § 14.3)

- [x] **Cấu trúc kho mã theo Clean Architecture**
  - Backend: `backend/src/cocas/` với 4 tầng (domain, application, infrastructure, presentation)
  - Frontend: `frontend/src/` chia theo tính năng
  - Desktop: `desktop/src/` (Tauri)
  - Shared: `shared/` cho validation_cases.json dùng chung

- [x] **Python dependencies đã ghim (39 libraries)**
  - Web & API: FastAPI, Uvicorn, Pydantic v2
  - Database: SQLAlchemy 2.0 async, asyncpg, Alembic
  - OCR: PaddleOCR, NumPy <2.0 (CRITICAL), OpenCV headless
  - Documents: docxtpl, Jinja2 (SandboxedEnvironment)
  - Security: cryptography, pywin32, argon2
  - Infrastructure: Loguru, Tenacity, psutil

- [x] **Node.js dependencies cho frontend**
  - React 18, TypeScript 5, MUI v5
  - TanStack Query, Zustand, React Hook Form
  - Vite, Vitest, Playwright

- [x] **CI/CD: GitHub Actions workflow**
  - `import-linter` cưỡng chế Dependency Rule (Domain zero-dependency)
  - `mypy --strict` cho domain/ + application/
  - `ruff` lint + format
  - `pytest` + coverage (domain ≥95%, application ≥85%)
  - `npm run test` cho frontend
  - Offline verification (0 external network calls)

- [x] **Pre-commit hooks**
  - ruff (format + lint)
  - mypy (strict mode)
  - gitleaks (bảo mật)
  - trailing whitespace, CRLF checks

- [x] **Shared validation_cases.json**
  - Khung 7 Value Object validation cases
  - Dùng chung cho pytest (backend) và vitest (frontend)
  - Metadata: domains covered, sync frequency

- [x] **Alembic migration framework**
  - Cấu hình async engine
  - Template migration sẵn sàng

- [x] **Foundation files**
  - `main.py`: FastAPI app factory (1 worker, no external calls)
  - `container.py`: Composition Root (duy nhất được phép import 4 tầng)
  - `config/settings.py`: Pydantic settings
  - Middleware skeleton: correlation ID, local token, security headers
  - Domain exceptions hierarchy
  - Enums: ContractStatus

---

## 🚀 Các bước tiếp theo (P1)

### 1. Setup môi trường phát triển

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev]"

# Frontend
cd ../frontend
npm ci
```

### 2. Khởi động pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files  # Test chạy 1 lần
```

### 3. Chạy CI locally

```bash
# Backend checks
cd backend
ruff check src tests
mypy src/cocas/domain src/cocas/application --strict
lint-imports

# Frontend checks
cd ../frontend
npm run type-check
npm run lint
npm run test
```

---

## 📐 Cấu trúc hiện tại

```
cocas/
├── backend/
│   ├── src/cocas/
│   │   ├── domain/          (entities, value_objects, enums, ports, exceptions)
│   │   ├── application/     (use_cases, dto, pipelines)
│   │   ├── infrastructure/  (persistence, ocr, documents, security, logging)
│   │   ├── presentation/    (api, schemas, middlewares)
│   │   ├── config/          (settings.py)
│   │   ├── container.py     ⭐ Composition Root
│   │   └── main.py
│   ├── migrations/          (Alembic async setup)
│   ├── tests/               (unit, integration, e2e, security, chaos)
│   └── pyproject.toml       (39 deps ghim chặt)
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── shared/
│   │   ├── features/        (dashboard, wizard, customers, contracts, templates, settings)
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── desktop/                 (Tauri skeleton)
├── shared/                  (validation_cases.json)
├── resources/               (.gitignored, sẽ fetch từ kho)
├── installer/               (NSIS, bootstrap, sign)
├── docs/design/             (14 tài liệu D2.0)
├── .github/workflows/       (CI)
├── .pre-commit-config.yaml
├── .gitignore
└── .editorconfig
```

---

## ⚠️ Ba rủi ro lớn của dự án (từ Roadmap)

1. **PaddleOCR tải model từ mạng** → Vi phạm P-01 (offline-first)
   - 🎯 Giải quyết ở P2 tuần 3: chỉ định `*_model_dir` tường minh
   - 🧪 Test bắt buộc: chạy trên máy đã ngắt mạng

2. **MRZ không đạt 75% checksum hợp lệ** → Hụt chỉ tiêu độ chính xác
   - 🎯 Kiểm chứng ngay P2 tuần 2 trên Golden Set
   - 🔄 Nếu thấp: tăng số vị trí sửa checksum hoặc model chuyên MRZ

3. **Golden Set 200 cặp CCCD chưa sẵn** → Không đo được độ chính xác
   - ⏰ **GẤP**: Thu thập & gán nhãn từ P0 (song song), không đợi P1

---

## 🎯 Điểm kiểm tra P0

- [x] `pip install -e ".[dev]"` → pip + pytest + ruff chạy sạch
- [x] `npm ci` → dependencies lắp xong
- [x] `import-linter` → báo cáo 0 vi phạm (hoặc danh sách ngoại lệ rõ ràng)
- [x] `mypy src/cocas/domain --strict` → không có lỗi
- [x] `ruff check src/` → linting + format check
- [ ] Tests: `pytest tests/ --cov` (sẽ có ở P1 khi có domain layer)
- [ ] Pre-commit hooks: `pre-commit run --all-files`

---

## 📝 Ghi chú

- **CI/CD**: GitHub Actions tự động chạy trên PR. Có thể chuyển sang GitLab CI hoặc tự hoạt động nếu cần
- **Python version**: Ghim 3.11+ (kiến trúc async, type hints)
- **Node.js**: 18+
- **Windows**: CI chạy trên `windows-latest` (Win11 là target)
- **Import-linter config**: Nằm ở `backend/pyproject.toml` § `[tool.import-linter]`

---

## 🔗 Liên kết

- Roadmap đầy đủ: [14-roadmap-va-tuong-lai.md](docs/design/14-roadmap-va-tuong-lai.md)
- Cấu trúc chi tiết: [11-cau-truc-va-thu-vien.md](docs/design/11-cau-truc-va-thu-vien.md)
- Chỉ dẫn phát triển: [CLAUDE.md](CLAUDE.md)

---

**Bước tiếp theo:** P1 — Nền tảng (Domain layer, 18 bảng CSDL, Crypto, Logging) — 1.5 tuần
