# 01 — Kiến trúc tổng thể

[← Mục lục](README.md)

---

## 1.1. Nguyên tắc kiến trúc nền tảng

| Mã | Nguyên tắc | Diễn giải & Hệ quả thiết kế |
|---|---|---|
| **P-01** | **Offline-First / Air-Gap by Design** | Không chỉ "không gọi Internet" mà **không có khả năng** gọi. Backend chỉ bind `127.0.0.1`. Tauri CSP chặn toàn bộ `connect-src` trừ cổng sidecar. Font/icon/CSS nhúng cục bộ. Model OCR đóng gói kèm installer. Kiểm chứng bằng test chạy trên máy đã rút dây mạng |
| **P-02** | **Dependency Rule (Clean Architecture)** | Phụ thuộc chỉ hướng vào trong: Presentation → Application → Domain. Infrastructure cắm vào Domain qua Port. Domain **không import** FastAPI, SQLAlchemy, PaddleOCR, docxtpl, `os`, `datetime.now()` |
| **P-03** | **Replaceable Engines (Ports & Adapters)** | OCR, lưu trữ, render, hàng đợi đều là Port. Đổi engine = thêm 1 adapter + đổi 1 khoá cấu hình |
| **P-04** | **Extraction ≠ OCR** | Trích xuất là pipeline đa kênh: QR → MRZ → OCR → Fusion. OCR chỉ là 1 trong 3 nguồn |
| **P-05** | **Data Minimization** | Ảnh CCCD là PII nhạy cảm nhất. Mặc định xoá ảnh gốc sau khi sinh hợp đồng thành công; chỉ giữ hash + thumbnail |
| **P-06** | **Template-Driven, Zero-Code Extension** | Thêm mẫu hợp đồng = upload `.docx` + khai báo trong UI. Không sửa code, không rebuild, không khởi động lại |
| **P-07** | **Everything is Logged** | Mọi thao tác chạm PII hoặc sinh tài liệu đều ghi `activity_log`. Mục đích: truy vết sự cố và tuân thủ NĐ 13/2023 |
| **P-08** | **Fail Loud, Degrade Gracefully** | OCR chết → chuyển sang nhập tay hoàn toàn. Không bao giờ mất dữ liệu người dùng đang nhập ⭐ *(D2.1: vế "LibreOffice chết → DOCX vẫn tải được" không còn đối tượng — chỉ có một đầu ra duy nhất)* |
| **P-09** | **Deterministic & Reproducible** | Cùng input + cùng phiên bản template → cùng output. Mỗi hợp đồng lưu snapshot dữ liệu đã render |
| **P-10** | **Radical Simplicity — Không xây cho quy mô không tồn tại** | Hệ thống phục vụ **một người, một máy**. Mọi cơ chế chỉ có ý nghĩa ở quy mô nhiều người đều bị cấm ở v1.0, kể cả khi "để sẵn cho tương lai" — vì P-02 và P-03 đã đảm bảo mở rộng được sau này mà không phải trả giá trước |
| **P-11** | **Windows là lớp xác thực. Ứng dụng không dựng lại lớp đó** | Người dùng đã đăng nhập Windows để mở được máy. Bắt đăng nhập lần hai không tăng bảo mật, chỉ tạo thêm mật khẩu để quên. Định danh người thực hiện = tên tài khoản Windows |
| **P-12** | **Template điều khiển quy trình, không chỉ nội dung** | Mẫu hợp đồng khai báo cần bao nhiêu bên, giấy tờ gì, thông tin gì. Wizard là bộ thực thi bản khai báo đó |
| **P-13** | **Bảo mật đúng một mục tiêu: dữ liệu không rời khỏi máy** | Mọi biện pháp phải trả lời được *"nó ngăn dữ liệu thoát ra bằng con đường nào?"*. Không trả lời được thì bị loại |

---

## 1.2. Ràng buộc thiết kế

| Loại | Ràng buộc | Ảnh hưởng thiết kế |
|---|---|---|
| **Phạm vi** | Đúng một máy tính. Không mạng. Không nhiều người dùng đồng thời | Loại bỏ toàn bộ hạ tầng phân tán |
| **Tổ chức** | Không có luồng phê duyệt từ cấp trên | Máy trạng thái Contract không có `PENDING_APPROVAL` |
| **Pháp lý** | Dữ liệu CCCD là dữ liệu cá nhân nhạy cảm (NĐ 13/2023/NĐ-CP) | Bắt buộc: mã hoá at-rest, nhật ký hoạt động, cơ chế xoá theo yêu cầu |
| **Mạng** | Không Internet, không LAN | Không HTTPS, không chứng chỉ. Chỉ loopback |
| **Nền tảng** | Windows 10/11 x64. Người dùng **có thể không có quyền Administrator** | Bắt buộc per-user install vào `%LOCALAPPDATA%`; PostgreSQL portable không đăng ký Service |
| **Kỹ năng người dùng** | Nhân viên nghiệp vụ, không phải kỹ thuật viên | Không terminal, không sửa file config tay, một `.exe` duy nhất |
| **Hiệu năng** | OCR CPU-only, 1 job tại một thời điểm | Queue chỉ để giữ UI không treo, không để scale |
| **Kích thước gói** | ⭐ Model OCR + PostgreSQL *(D2.1 bỏ LibreOffice ~420 MB)* | ~700 MB → installer nén LZMA |
| **Sao lưu** | Không có DBA, không có backup server | ⭐ Ứng dụng phải tự sao lưu ra file `.cocasbak` mã hoá |

### Giả định kỹ thuật đã chốt

| # | Giả định |
|---|---|
| G-01 | Chỉ xử lý **CCCD gắn chip 12 số** (mẫu 2021+ và Căn cước 2024+). Không hỗ trợ CMND 9 số ở v1.0 |
| G-02 | Mặt trước có **QR code**, mặt sau có **vùng MRZ (TD1, 3 dòng × 30 ký tự)** |
| G-03 | Trường "Có giá trị đến" có thể mang giá trị **"KHÔNG THỜI HẠN"** |
| G-04 | Máy đích: Windows 10/11 x64, ≥ 8 GB RAM, ≥ 4 nhân CPU, không bắt buộc GPU |
| G-05 | Ngôn ngữ nghiệp vụ: tiếng Việt; ngôn ngữ mã nguồn/định danh: tiếng Anh |
| G-06 | Ngày trên CCCD định dạng `dd/mm/yyyy` |

---

## 1.3. Yêu cầu phi chức năng (NFR)

| Mã | Thuộc tính | Chỉ tiêu | Cách xác minh |
|---|---|---|---|
| NFR-01 | Độ chính xác trích xuất | ≥ 99% khi QR/MRZ đọc được; ≥ 95% field-level với OCR thuần | Golden Set 200 cặp ảnh gán nhãn |
| NFR-02 | Thời gian OCR 1 mặt | p50 ≤ 2.0s · p95 ≤ 4.5s (CPU 4 nhân, ảnh 1600px) | Benchmark tự động |
| NFR-03 | Thời gian sinh DOCX | p95 ≤ 800 ms | Benchmark |
| **NFR-05** | **Khởi động ứng dụng** | **p50 ≤ 10s · p95 ≤ 15s** | Stopwatch tự động |
| NFR-06 | Đáp ứng UI | Không thao tác nào khoá > 200 ms. Việc > 500 ms phải chạy nền có thanh tiến độ | React Profiler |
| NFR-07 | Khả năng tự phục hồi | Tắt máy đột ngột → mở lại vẫn chạy, DB không hỏng, job dở dang đánh `FAILED`, form đang nhập được khôi phục | Chaos test `taskkill /F` |
| NFR-08 | Bảo mật | Không secret hardcode; PII mã hoá AES-256-GCM; khoá bảo vệ bằng Windows DPAPI | SAST + review |
| NFR-09 | Khả năng bảo trì | Coverage ≥ 95% Domain, ≥ 85% Application; độ phức tạp vòng ≤ 10 | pytest-cov, radon |
| NFR-10 | Mở rộng loại giấy tờ | Thêm loại mới không sửa module OCR core | Spike GPLX giai đoạn sau |
| NFR-11 | Kích thước & thời gian cài | Gói ≤ 1.2 GB; cài ≤ 5 phút; **không cần quyền Administrator** | Kiểm thử trên máy sạch, tài khoản standard |
| NFR-12 | Truy vết | Mọi thao tác có `correlation_id` xuyên suốt log; log tự che PII | Kiểm tra + test regex |
| NFR-13 | Sao lưu & khôi phục | Sao lưu ≤ 2 phút; khôi phục ≤ 5 phút; có kiểm tra toàn vẹn | Kiểm thử khôi phục trên máy khác |
| NFR-14 | Gỡ cài sạch | Để lại dữ liệu (mặc định) hoặc xoá hoàn toàn (xác nhận 2 bước) | Kiểm thử |

---

## 1.4. Mô hình triển khai — Single Workstation

### 1.4.1. Sơ đồ tổng thể

```
╔═══════════════════════════════════════════════════════════════════════════╗
║  MỘT MÁY TÍNH WINDOWS 10/11 x64 · 8 GB RAM · 4 nhân · 3 GB đĩa trống      ║
║                                                                           ║
║  ┌─────────────────────────────────────────────────────────────────────┐  ║
║  │  ContractSystem.exe   ◄── Người dùng bấm vào đây, chỉ vậy thôi       │  ║
║  │  ┌───────────────────────────────────────────────────────────────┐  │  ║
║  │  │  Tauri Shell (Rust)                                           │  │  ║
║  │  │  • Cửa sổ ứng dụng · Menu · Khay hệ thống                     │  │  ║
║  │  │  • Supervisor tiến trình con                                  │  │  ║
║  │  │  • Hộp thoại chọn file / thư mục (native)                     │  │  ║
║  │  │  • In ấn · Mở thư mục chứa file                               │  │  ║
║  │  │  • Sinh & giữ Local Handshake Token                           │  │  ║
║  │  │  • Single-instance mutex                                      │  │  ║
║  │  ├───────────────────────────────────────────────────────────────┤  │  ║
║  │  │  WebView2  ←  React 18 + TypeScript + MUI v5 (asset nhúng)    │  │  ║
║  │  │  CSP: connect-src 'self' http://127.0.0.1:<port>              │  │  ║
║  │  └───────────────────────────────────────────────────────────────┘  │  ║
║  └────────────────────────────┬────────────────────────────────────────┘  ║
║                               │  HTTP/JSON · 127.0.0.1:<cổng động>        ║
║                               │  Header: X-Local-Token                    ║
║  ┌────────────────────────────▼────────────────────────────────────────┐  ║
║  │  cocas-backend.exe   (tiến trình con — sidecar, PyInstaller onedir) │  ║
║  │  ┌───────────────────────────────────────────────────────────────┐  │  ║
║  │  │  FastAPI + Uvicorn  ·  MỘT worker, MỘT event loop             │  │  ║
║  │  │  ├─ Presentation : Routers · Middlewares · Schemas            │  │  ║
║  │  │  ├─ Application  : Use Cases · UnitOfWork · EventBus          │  │  ║
║  │  │  ├─ Domain ★     : Entities · VOs · Services · Ports          │  │  ║
║  │  │  └─ Infrastructure: Repos · Adapters                          │  │  ║
║  │  ├───────────────────────────────────────────────────────────────┤  │  ║
║  │  │  JobRunner — polling bảng `job` mỗi 500ms, đồng thời = 1      │  │  ║
║  │  ├───────────────────────────────────────────────────────────────┤  │  ║
║  │  │  PaddleOCR models (~150 MB RAM, nạp nền sau khi UI hiện)      │  │  ║
║  │  └───────────────────────────────────────────────────────────────┘  │  ║
║  └───┬──────────────┬───────────────┬──────────────────┬───────────────┘  ║
║      │              │               │                  │                  ║
║  ┌───▼────────┐ ┌───▼──────────┐ ┌──▼─────────────┐ ┌──▼───────────────┐ ║
║  │ postgres.  │ │              │ │ PaddleOCR      │ │ File Vault       │ ║
║  │ exe        │ │ --headless   │ │ models (đĩa)   │ │ AES-256-GCM      │ ║
║  │ portable   │ │ listener     │ │ det/rec/cls    │ │ tên file = UUID  │ ║
║  │ 127.0.0.1  │ │ KHỞI ĐỘNG    │ │ đóng gói kèm   │ │                  │ ║
║  │ :55432     │ │ LƯỜI, tắt    │ │                │ │                  │ ║
║  │            │ │ sau 20 phút  │ │                │ │                  │ ║
║  └────────────┘ └──────────────┘ └────────────────┘ └──────────────────┘ ║
║                                                                           ║
║  ✗ KHÔNG có cổng nào lắng nghe trên card mạng thật                        ║
║  ✗ KHÔNG có HTTP client nào trỏ ra ngoài                                  ║
║  ✗ KHÔNG telemetry, KHÔNG auto-update online                              ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### 1.4.2. Bố cục thư mục dữ liệu

```
%LOCALAPPDATA%\COCAS\                    ← Không cần quyền admin
├── app\                                 ← CHỈ ĐỌC · installer ghi · xoá khi gỡ cài
│   ├── ContractSystem.exe
│   ├── cocas-backend\                   (PyInstaller onedir)
│   ├── ocr-models\                      (det, rec, cls — chỉ đọc)
│   └── postgres\                        (nhị phân — chỉ đọc)
├── data\                                ← ĐỌC-GHI · ⭐ ĐÂY LÀ THỨ CẦN SAO LƯU
│   ├── pgdata\                          (cluster PostgreSQL)
│   ├── vault\
│   │   ├── images\{yyyy}\{mm}\{dd}\{uuid}.enc
│   │   ├── contracts\{yyyy}\{mm}\{contract_id}\{...}.docx
│   │   └── thumbnails\{uuid}.enc
│   ├── templates\{template_id}\v{n}\template.docx + manifest.json
│   ├── keys\master.key.dpapi            (KEK bọc bằng Windows DPAPI)
│   ├── config\settings.toml             (người dùng sửa qua UI)
│   ├── logs\app-{yyyy-MM-dd}.log        (xoay vòng, giữ 30 ngày)
│   └── backups\COCAS-{yyyyMMdd-HHmmss}.cocasbak
└── runtime.json                         (cổng động, PID — sinh lúc chạy, tự xoá)
```

> **Tách bạch `app/` chỉ-đọc và `data/` đọc-ghi** cho phép nâng cấp phiên bản mà không đụng dữ liệu người dùng, và gỡ cài mặc định giữ lại dữ liệu.

### 1.4.3. Trình tự khởi động

```
1. Double-click ContractSystem.exe
2. Splash Screen hiện ngay (< 300 ms)
3. Đọc %LOCALAPPDATA%\COCAS\config
4. [Lần đầu] initdb (~20s) → migration → seed → màn hình Thiết lập lần đầu
   [Lần thường] pg_ctl start (~2s)
5. Chọn cổng TCP trống ngẫu nhiên trong [49152, 65535]
6. Sinh Local Handshake Token (32 byte ngẫu nhiên)
7. Spawn cocas-backend.exe — token truyền qua BIẾN MÔI TRƯỜNG (không qua tham số
   dòng lệnh, tránh lộ trong Task Manager)
8. Backend bind 127.0.0.1:<p>, kiểm tra DB, trả /health → 200
9. ⭐ Nạp PaddleOCR ở LUỒNG NỀN (không chặn) — UI hiện trước
10. Ghi runtime.json {port, backend_pid}
11. Nạp SPA, tiêm cổng + token qua Tauri IPC
12. Đóng Splash, hiện Dashboard (~7 giây)
13. Nút "Tạo hợp đồng" hiện "Đang chuẩn bị nhận dạng…" cho tới khi model nạp xong

Từ đây Tauri giám sát backend mỗi 5 giây. Backend chết → tự khởi động lại tối đa
3 lần, sau đó hiện hộp thoại lỗi + nút "Xuất gói chẩn đoán".
```

### 1.4.4. Tắt & phục hồi sau sự cố

| Kịch bản | Hành vi thiết kế |
|---|---|
| **Tắt bình thường** | Tauri gửi `POST /admin/shutdown` → backend từ chối request mới, chờ job đang chạy tối đa 30s, đóng pool DB, thoát mã 0 → `pg_ctl stop -m fast` → xoá `runtime.json` |
| **Còn job đang chạy** | Hộp thoại: "Đang xử lý OCR, đóng ngay sẽ huỷ. Đóng / Chờ hoàn tất?" |
| **Backend crash** | Health probe phát hiện → khởi động lại → job `RUNNING` quá 5 phút bị đánh `FAILED` với `STALE_JOB_RECOVERED`, hiện ở "Công việc bị gián đoạn" trên Dashboard |
| **Mất điện đột ngột** | PostgreSQL tự phục hồi bằng WAL. Backend chạy `RecoverStaleJobsUseCase`. File `.tmp` trong Vault bị dọn. Form đang nhập khôi phục từ `localStorage` |
| **PostgreSQL không khởi động** | Màn hình chẩn đoán: log lỗi + nút "Sửa chữa cơ sở dữ liệu" + nút "Khôi phục từ bản sao lưu" |
| **Cổng bị chiếm** | Thử ngẫu nhiên tối đa 10 cổng khác |
| **Chạy 2 instance** | Named mutex Windows — instance thứ 2 đưa cửa sổ instance 1 lên trước rồi thoát |

### 1.4.5. Bảo mật kênh loopback

| # | Biện pháp | Chống lại |
|---|---|---|
| 1 | Bind cứng `127.0.0.1` (không `0.0.0.0`) | Máy khác dò cổng |
| 2 | Cổng ngẫu nhiên mỗi lần chạy trong dải ephemeral | Phần mềm khác đoán cổng cố định |
| 3 | ⭐ **Local Handshake Token** — 32 byte ngẫu nhiên, truyền qua biến môi trường tiến trình con, tiêm vào SPA qua IPC. Mọi request phải có header `X-Local-Token` | Ứng dụng/script khác trên cùng máy |
| 4 | Kiểm `Origin` / `Sec-Fetch-Site` / `Host` | Trang web độc hại, DNS rebinding |
| 5 | Không endpoint nào trả JSONP hay chấp nhận `callback` | Trang web độc hại |

> **Nói đúng mức:** Local Token **chặn hoàn toàn** trang web độc hại và tiện ích trình duyệt. Nó **làm khó nhưng không chặn tuyệt đối** phần mềm chạy cùng tài khoản Windows và cố tình dò tìm — trên Windows, biến môi trường của tiến trình con đọc được bởi tiến trình khác cùng quyền. Chống malware cùng quyền là trách nhiệm của giải pháp endpoint, không phải của ứng dụng nghiệp vụ.

### 1.4.6. Ngân sách tài nguyên

| Tài nguyên | Nghỉ | Khi OCR | Đỉnh |
|---|---|---|---|
| Tauri + WebView2 | ~120 MB | ~150 MB | 200 MB |
| Backend Python | ~280 MB | ~550 MB | 850 MB |
| PostgreSQL | ~60 MB | ~90 MB | 150 MB |
| **Tổng RAM** | **~460 MB** | **~790 MB** | **~1.55 GB** |
| CPU | ~0% | 60–90% (2–3 nhân) | 100% ngắn hạn |
| Đĩa — cài đặt | 1.1 GB | | |
| Đĩa — dữ liệu | ~350 MB / 1.000 hợp đồng (đã xoá ảnh) | | |

---

## 1.5. Danh mục thành phần

| # | Thành phần | Tầng | Trách nhiệm | Công nghệ |
|---|---|---|---|---|
| C-01 | Desktop Shell | Presentation | Cửa sổ, supervisor sidecar, hộp thoại file, in, Local Token | Tauri (Rust) |
| C-02 | Web UI | Presentation | Toàn bộ giao diện | React 18 + TS 5 + MUI v5 + TanStack Query + Zustand |
| C-03 | API Layer | Presentation | Router, validate I/O | FastAPI + Pydantic v2 |
| C-04 | Use Case Layer | Application | Điều phối, giao dịch, sự kiện | Python |
| C-05 | Domain Core | Domain | Entity, VO, rule, Port | Python thuần |
| C-06 | Ingestion Module | Infrastructure | Kiểm định file, magic bytes, re-encode, lưu Vault | python-magic, Pillow |
| C-07 | Image Preprocessor | Infrastructure | 9 phép biến đổi, 5 biến thể **tạo lười** | OpenCV |
| C-08 | Card Classifier | Infrastructure | Nhận diện mặt trước/sau | Heuristic đa tín hiệu |
| C-09 | QR Decoder | Infrastructure | Giải mã QR (3 lần thử) | zxing-cpp |
| C-10 | MRZ Reader | Infrastructure | Đọc + checksum MRZ TD1 | Region OCR + parser |
| C-11 | OCR Engine Adapter | Infrastructure | Bọc PaddleOCR sau `IOcrEngine` | PaddleOCR PP-OCRv4 |
| C-12 | Field Extractor | Infrastructure | Text → trường nghiệp vụ | rapidfuzz + zone map |
| C-13 | Normalizer | Domain Service | Chuẩn hoá, đặc biệt Nơi cấp (4 tầng) | unicodedata + alias table |
| C-14 | Fusion Engine | Domain Service | Hợp nhất 3 nguồn + confidence | Python |
| C-15 | Validation Engine | Domain | Rule nghiệp vụ + cú pháp | Pydantic v2 + rule objects |
| C-16 | Template Registry | Application/Infra | Đăng ký, phiên bản, kiểm tra template | Jinja2 AST introspection |
| C-17 | Document Renderer | Infrastructure | Bơm dữ liệu vào DOCX | docxtpl |
| C-19 | Repository Layer | Infrastructure | Truy cập CSDL | SQLAlchemy 2.0 async + Alembic |
| C-20 | File Vault | Infrastructure | Lưu nhị phân, chống traversal, mã hoá | cryptography |
| C-21 | **JobRunner** | Infrastructure | ⭐ Polling bảng `job` — **bảng `job` là hàng đợi duy nhất** | asyncio |
| C-22 | Local Token Guard | Infrastructure | Kiểm tra `X-Local-Token` hằng thời gian | — |
| C-23 | Activity Log Service | Application | Nhật ký hoạt động | SQLAlchemy |
| C-24 | Crypto Service | Infrastructure | AES-256-GCM, KEK qua DPAPI, HKDF | cryptography + pywin32 |
| C-25 | Config Service | Infrastructure | default → TOML → env → DB | pydantic-settings + tomlkit |
| C-26 | Logging | Cross-cutting | JSON có cấu trúc, che PII, xoay vòng | Loguru |
| C-27 | Health & Diagnostics | Presentation | Kiểm tra DB / OCR / đĩa | FastAPI |
| C-28 | Installer & Bootstrap | Ops | Cài, initdb, migrate, seed, shortcut | NSIS |
| C-29 | **Backup & Restore** | Application/Infra | Sao lưu DB + Vault ra 1 file mã hoá | `pg_dump` + zipfile + cryptography |

---

## 1.6. Ánh xạ Clean Architecture

```
                    ┌───────────────────────────────────────┐
                    │      PRESENTATION LAYER               │
                    │  React UI · Tauri Shell · FastAPI     │
                    │  Routers · Middlewares · Schemas(I/O) │
                    └──────────────────┬────────────────────┘
                                       │ gọi (DTO vào, DTO ra)
                    ┌──────────────────▼────────────────────┐
                    │      APPLICATION LAYER                │
                    │  Use Cases · Orchestration · UoW      │
                    │  Application Services · Event Bus     │
                    └──────────────────┬────────────────────┘
                                       │ gọi qua PORT (interface)
                    ┌──────────────────▼────────────────────┐
                    │         DOMAIN LAYER  (lõi)           │
                    │  Entities · Value Objects · Enums     │
                    │  Domain Services · Domain Events      │
                    │  Ports (ABC) · Business Rules         │
                    │  ★ KHÔNG phụ thuộc bất cứ thứ gì ★    │
                    └──────────────────▲────────────────────┘
                                       │ triển khai PORT
                    ┌──────────────────┴────────────────────┐
                    │      INFRASTRUCTURE LAYER             │
                    │  SQLAlchemy Repos · PaddleOCR Adapter │
                    │  docxtpl · FileVault                  │
                    │  Crypto · Loguru sink · JobRunner     │
                    └───────────────────────────────────────┘
```

### 1.6.1. Domain Layer — "Sự thật nghiệp vụ"

Chứa toàn bộ tri thức nghiệp vụ độc lập công nghệ. Bỏ FastAPI, bỏ PostgreSQL, bỏ PaddleOCR — tầng này **không đổi một dòng nào**.

- **Entities:** `Customer`, `Contract`, `ContractParty`, `ContractTemplate`, `TemplateVersion`, `OcrSession`, `BankAccount`
- **Value Objects:** `CitizenId`, `VietnamesePhone`, `EmailAddress`, `BankAccountNumber`, `SecuritiesAccountNumber`, `IssuePlace`, `IdCardDates`, `PersonName`, `ConfidenceScore`, `StyledValue`
- **Domain Services:** `IssuePlaceNormalizer`, `FieldFusionService`, `CardValidityPolicy`, `ContractNumberGenerator`, `ExportNameGenerator`
- **Domain Events:** `OcrCompleted`, `CustomerCreated`, `ContractGenerated`, `ValidationFailed`
- ⭐ **Ports (18):** `IOcrEngine`, `IRegionRecognizer`, `IImagePreprocessor`, `ICardSideClassifier`, `IQrDecoder`, `IMrzReader`, `IFieldExtractor`, `IReadRepository<T>`, `IWriteRepository<T>`, `IFileStorage`, `IDocumentRenderer`, `IUnitOfWork`, `IJobQueue`, `IClock`, `IIdGenerator`, `ICryptoService`, `IAliasRepository`, `IDocumentTypeSelector` — *(D2.1 gỡ `IPdfConverter`; P3 thêm `IDocumentTypeSelector`. Số Port giữ 18, đánh số 1–19 khuyết 13 — §12.19)*
- **Exceptions:** `InvalidCitizenIdError`, `CardExpiredError`, `TemplateVariableMismatchError`, `DuplicateCustomerError`, `PathTraversalError`, …

**Không được chứa:** import framework, truy cập I/O, `datetime.now()` trực tiếp (dùng `IClock`), `uuid4()` trực tiếp (dùng `IIdGenerator`).

### 1.6.2. Application Layer — "Kịch bản nghiệp vụ"

Mỗi Use Case là một kịch bản người dùng: một lớp, một phương thức `execute()`. Điều phối Domain + Port, quản lý ranh giới giao dịch, phát sự kiện, ghi nhật ký.

| Nhóm | Use Case |
|---|---|
| Ingestion | `UploadCardImageUseCase` |
| OCR | `CreateOcrSessionUseCase` · `RunOcrUseCase` · `GetOcrResultUseCase` · `ReassignCardSidesUseCase` · `RetryOcrUseCase` · `UpdateOcrFieldsUseCase` · `ConfirmOcrResultUseCase` · `CancelOcrSessionUseCase` · `ListOcrSessionsUseCase` |
| Customer | `CreateCustomerUseCase` · `UpdateCustomerUseCase` · `SearchCustomerUseCase` · `GetCustomerUseCase` · `SoftDeleteCustomerUseCase` · `ListCustomerContractsUseCase` |
| BankAccount | `AddBankAccountUseCase` · `UpdateBankAccountUseCase` · `DeleteBankAccountUseCase` · `SetPrimaryBankAccountUseCase` |
| Template | `RegisterTemplateUseCase` · `ValidateTemplateUseCase` · `ListTemplatesUseCase` · `GetTemplateRequirementsUseCase` · `AddTemplateVersionUseCase` · `ActivateTemplateVersionUseCase` · `UpdateTemplateUseCase` · `DeactivateTemplateUseCase` · `PreviewTemplateUseCase` · `GetVariableDictionaryUseCase` |
| Contract | `GenerateContractUseCase` · `RegenerateContractUseCase` · `GetContractUseCase` · `ListContractsUseCase` · `DownloadDocumentUseCase` · `VoidContractUseCase` |
| System | `GetHealthUseCase` · `GetDiagnosticsUseCase` · `GetSettingsUseCase` · `UpdateSettingUseCase` · `ResetSettingsUseCase` · `RecoverStaleJobsUseCase` · `RunRetentionPurgeUseCase` · `ListActivityLogUseCase` · `ExportActivityLogUseCase` |
| Backup | `CreateBackupUseCase` · `ListBackupsUseCase` · `RestoreBackupUseCase` |
| Reference | `ListBanksUseCase` · `ListProvincesUseCase` · `ListAliasesUseCase` · `AddAliasUseCase` · `DeleteAliasUseCase` |

**Ranh giới giao dịch:** 1 Use Case = 1 UnitOfWork = 1 transaction. Thao tác file nằm **ngoài** transaction: *ghi file tạm → commit DB → rename*.

### 1.6.3. Infrastructure Layer

Nơi duy nhất được biết PostgreSQL và PaddleOCR tồn tại. Mỗi adapter phải: dịch ngoại lệ hạ tầng → ngoại lệ Domain; không chứa quy tắc nghiệp vụ; thay được bằng fake trong test.

### 1.6.4. Presentation Layer

Chuyển đổi giao thức ↔ DTO. FastAPI router chỉ làm 4 việc: parse & validate request · resolve dependency · gọi use case · map kết quả/ngoại lệ → HTTP response. **Không có `if` nghiệp vụ nào trong router.**

---

## 1.7. Dependency Injection

Một **Composition Root** duy nhất (`container.py`) — file **duy nhất** import từ cả 4 tầng.

| Scope | Đối tượng | Lý do |
|---|---|---|
| **Singleton** | `IOcrEngine` (~150 MB) · `Settings` · `ICryptoService` · SQLAlchemy `Engine` · `IJobQueue` · `IQrDecoder` · `IMrzReader` · `IImagePreprocessor` | Khởi tạo tốn kém, không có trạng thái theo người dùng. ⭐ Ở kiến trúc một tiến trình, singleton thực sự là singleton |
| **Scoped** | `IUnitOfWork` · mọi Repository · mọi Use Case · `ActivityLogService` | Gắn với một DB session và một `correlation_id` |
| **Transient** | Value Object · DTO · Domain Service không trạng thái | Rẻ, bất biến |

### Cấu hình thay engine (hiện thực P-03)

| Khoá cấu hình | Giá trị | Adapter |
|---|---|---|
| `ocr.engine` | `paddle` (mặc định) / `tesseract` / `none` | `PaddleOcrAdapter` / `TesseractAdapter` / `NullOcrAdapter` |
| `storage.encryption` | `aes_gcm` (mặc định) / `none` | `EncryptedFileVault` / `PlainFileVault` (chỉ dev) |

---

## 1.8. Cross-cutting Concerns

| Mối quan tâm | Cơ chế |
|---|---|
| Correlation ID | Middleware sinh/nhận `X-Correlation-ID` → `contextvars` → Loguru bind tự động. ⭐ Job nền kế thừa ID từ request tạo ra nó |
| Xử lý ngoại lệ | Handler tập trung: `DomainError` → 4xx, `InfrastructureError` → 5xx, mã lỗi `COCAS-XXXX` có bảng tra cứu tiếng Việt |
| Che PII trong log | Loguru filter tự động — xem [10-bao-mat-va-logging.md](10-bao-mat-va-logging.md) |
| Nhật ký hoạt động | Decorator `@logged(action=...)` bọc Use Case, ghi trong **cùng transaction** |
| Guard tài nguyên | Kiểm dung lượng đĩa trước mỗi thao tác ghi lớn: cảnh báo < 500 MB, chặn < 100 MB |
| Khoá lạc quan | ⭐ Cơ chế chung (`IVersionedEntity` + hỗ trợ ở `IWriteRepository` + dependency đọc `If-Match`), nhưng **chỉ áp cho `contract`** |

---

## 1.9. Architecture Decision Records

| ADR | Quyết định | Lý do | Đánh đổi |
|---|---|---|---|
| **ADR-01** | **Tauri** làm vỏ desktop | Gói ~15 MB thay vì ~150 MB (Electron); WebView2 có sẵn Win10/11; bề mặt tấn công nhỏ; quản lý sidecar tốt — quan trọng vì Tauri là supervisor duy nhất của cả PostgreSQL lẫn backend | Cần toolchain Rust; phải bundle WebView2 offline installer |
| **ADR-02** | **PostgreSQL portable** trên chính máy | (a) yêu cầu công nghệ; (b) JSONB cho `render_snapshot`; (c) full-text search tiếng Việt; (d) WAL recovery mạnh khi mất điện; (e) đường nâng cấp lên server sau này | +250 MB gói cài; `initdb` ~20s lần đầu; cần supervisor tiến trình |
| **ADR-03** | **PaddleOCR** engine mặc định | Tiếng Việt có dấu tốt; có sẵn det + rec + cls; chạy CPU ổn; model mobile ~10 MB | Cài `paddlepaddle` nặng; phải ghim phiên bản chặt |
| **ADR-04** | **QR + MRZ là nguồn chính, OCR là phụ** | QR chứa dữ liệu số hoá 100% chính xác; MRZ có checksum tự kiểm | Phải xử lý QR mờ/che; pipeline phức tạp hơn |
| **ADR-05** | 🗑️ ~~**LibreOffice headless** cho PDF~~ → ⭐ **ĐẢO NGƯỢC Ở D2.1: không xuất PDF, `.docx` là đầu ra duy nhất** | Người dùng cần sửa được hợp đồng trước khi in; bỏ luôn rủi ro font tiếng Việt; cắt ~420 MB gói cài + 1 tiến trình con | Muốn có PDF thì người dùng tự "Lưu thành PDF" trong Word — chấp nhận có chủ ý (§9.13) |
| **ADR-06** | **Monolith một tiến trình, một event loop** | Không IPC, không serialize job, không tranh chấp model OCR, debug bằng một breakpoint | Job OCR nặng có thể làm chậm request khác → khắc phục bằng `run_in_executor` cho phần CPU-bound |
| **ADR-07** | ⭐ **Bảng `job` LÀ hàng đợi duy nhất** | Không có `asyncio.Queue`. `JobRunner` polling `SELECT … FOR UPDATE SKIP LOCKED` mỗi 500 ms. Một nguồn chân lý, bền qua crash, hiển thị tiến độ, retry, ghi nhật ký | Độ trễ nhận job ≤ 500 ms — không đáng kể so với OCR 4s |
| **ADR-08** | ~~JWT~~ → **Không có tầng xác thực ứng dụng** | Windows đã xác thực (P-11). Định danh = tên tài khoản Windows | Nếu cả phòng dùng chung một tài khoản Windows thì nhật ký không phân biệt được ai — mỗi người dùng tài khoản Windows riêng là thực hành chuẩn |
| **ADR-09** | **Mã hoá field-level, một KEK, bảo vệ bằng Windows DPAPI** | Biện pháp chính khi máy bị mất hoặc ổ cứng bị copy. DPAPI phạm vi user → tài khoản khác không giải mã được | Không tìm kiếm trực tiếp trên trường mã hoá → dùng blind index HMAC |
| **ADR-10** | **Template lưu ngoài CSDL + metadata trong CSDL, có phiên bản** | File `.docx` dễ backup, dễ soạn bằng Word; version cho phép tái lập hợp đồng cũ | Cần đảm bảo đồng bộ bằng checksum SHA-256 |
| **ADR-11** | **Snapshot dữ liệu render vào hợp đồng (JSONB mã hoá)** | Khách đổi địa chỉ không làm sai lệch hợp đồng đã in (P-09) | Trùng lặp ~3 KB/hợp đồng — đúng chuẩn kiểm toán |
| **ADR-12** | **Xoá ảnh gốc mặc định sau khi hoàn tất** | Giảm rủi ro rò rỉ PII (P-05); tuân thủ NĐ13; giảm dung lượng 8× | Không tra cứu lại ảnh gốc → giữ thumbnail + SHA-256 |
| **ADR-13** | **Không phân quyền, không vai trò** | Máy nội bộ, tin tưởng người dùng. Thao tác nguy hiểm dùng hộp thoại xác nhận gõ chữ thay vì phân quyền | Không có cơ chế "bốn mắt" |
| **ADR-14** | **Sao lưu là chức năng nghiệp vụ, không phải việc của IT** | Không có DBA, không có backup server. Nếu ứng dụng không tự sao lưu, dữ liệu **sẽ mất** | +3 ngày công — chi phí bắt buộc |
| **ADR-15** | **Bỏ HTTPS, thay bằng phòng thủ nhiều lớp trên loopback** | Không có LAN → HTTPS chỉ là nghi thức vô nghĩa với chứng chỉ tự ký | Nếu sau này cần LAN, phải bổ sung lại lớp TLS + tầng xác thực |
| **ADR-16** | ⭐ **Giữ `contract_party` làm bản lề, cắt `organization`** | `contract_party` rẻ bây giờ (1 bảng, 1 dòng/hợp đồng), đắt về sau (phải di trú toàn bộ + sửa mọi truy vấn). `organization` đắt bây giờ, rẻ về sau (thêm bảng mới + 1 cột nullable) | v1.0 có 1 bảng chỉ chứa 1 dòng mỗi hợp đồng |

---

## 1.10. Bounded Contexts

| Context | Sở hữu dữ liệu | Giao tiếp |
|---|---|---|
| **Document Ingestion** | `card_image` | Phát `ImageIngested` |
| **Extraction (OCR)** | `ocr_session`, `ocr_result`, `ocr_field`, `job` | Phát `OcrCompleted`; tiêu thụ `ImageIngested` |
| **Customer Master** | `customer`, `bank_account` | Phát `CustomerUpserted` |
| **Contract Authoring** | `contract_template`, `template_version`, `contract`, `contract_party`, `contract_document` | Tiêu thụ `CustomerUpserted` |
| **Compliance & Ops** | `activity_log`, `system_setting`, `normalization_alias`, `document_type`, `province_code`, `bank_directory`, `backup_record` | Tiêu thụ mọi Domain Event |

---

[← Mục lục](README.md) · [Tiếp: 02 — Sơ đồ hệ thống →](02-so-do-he-thong.md)
