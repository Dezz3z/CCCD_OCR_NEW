# COCAS — CCCD OCR & Contract Automation System

Hệ thống Desktop tự động tạo hợp đồng từ ảnh CCCD (Căn cước công dân), chạy **hoàn toàn cục bộ** trên Windows — không có khả năng gọi Internet.

## Tài liệu thiết kế

Nguồn chân lý duy nhất của dự án nằm ở [`docs/design/`](docs/design/README.md) — bộ 14 tài liệu thiết kế phiên bản **D2.0**, bao gồm kiến trúc, sơ đồ hệ thống, cơ sở dữ liệu, API, giao diện, module OCR, validation, template tài liệu, bảo mật, cấu trúc thư viện, đặc tả module, kiểm thử/đóng gói và roadmap.

Xem [`CLAUDE.md`](CLAUDE.md) để biết 13 nguyên tắc bất biến, ngăn xếp công nghệ, quy ước mã nguồn và trạng thái triển khai hiện tại.

## Ngăn xếp công nghệ

| Tầng | Công nghệ |
|---|---|
| Desktop | Tauri (Rust) + WebView2 |
| Frontend | React 18 + TypeScript 5 + MUI v5 + TanStack Query + Zustand |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · Uvicorn |
| OCR | PaddleOCR PP-OCRv4 (CPU, offline) + OpenCV + zxing-cpp |
| CSDL | PostgreSQL 16 portable · SQLAlchemy 2.0 async · Alembic |
| Tài liệu | docxtpl (Jinja2 sandboxed) + LibreOffice headless CLI |

## Trạng thái hiện tại

**Giai đoạn 1 (Thiết kế): ✅ Hoàn thành** — tài liệu D2.0 đã đóng băng.
**Giai đoạn 2 (Triển khai): Chưa bắt đầu** — bước tiếp theo là khung dự án, CI, import-linter.
