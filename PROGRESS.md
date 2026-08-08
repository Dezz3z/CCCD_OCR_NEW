# COCAS Development Progress

**Project:** COCAS v1.0 — Desktop app tự động tạo hợp đồng từ ảnh CCCD  
**Target:** 12.5 tuần, 2 người (hoặc ~24 tuần nếu 1 người)  
**Status:** In Progress

---

## 📊 Timeline Overview

```
P0: Chuẩn bị        [====] ✅ DONE (2026-08-11)
P1: Nền tảng        [    ] ⏳ TODO (2 tuần)
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

### ⏳ P1 — Nền tảng (1.5 tuần)
**Status:** TODO  
**Est. Start:** 2026-08-12  
**Est. Completion:** 2026-08-26

**Deliverables (from roadmap § 14.3):**
- [ ] Domain layer đầy đủ (10 VO, 8 Entity, 5 Service, 18 Port)
  - Value Objects: CitizenId, VietnamesePhone, EmailAddress, BankAccountNumber, SecuritiesAccountNumber, IssuePlace, IdCardDates, PersonName, ConfidenceScore, StyledValue
  - Entities: Customer, Contract, ContractParty, OcrSession, Template, TemplateVersion, BankAccount, CardImage
  - Domain Services: IssuePlaceNormalizer, FieldFusionService, CardValidityPolicy, ContractNumberGenerator, ExportNameGenerator
  - 18 Ports (OCR, Storage, PDF Render, Queue, Template, etc.)
  - Exception tree
- [ ] 18 bảng CSDL + 8 migrations
- [ ] Dữ liệu seed (document_type, alias, province, bank, config, 2 templates)
- [ ] Repository + UnitOfWork pattern
- [ ] Crypto Service (AES-256-GCM, DPAPI, blind index)
- [ ] Logging (Loguru, PII filter)
- [ ] Composition Root (container.py)
- [ ] Build .exe thử lần đầu (PyInstaller)

**Milestones:**
- M1: Script tạo Customer giả, xác nhận mã hoá thành công

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
