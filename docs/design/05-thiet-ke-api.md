# 05 — Thiết kế API

[← Mục lục](README.md)

**FastAPI · ⭐ 62 endpoint · OpenAPI 3.1 · Loopback only**

> ⭐ **D2.1 — 64 → 62 endpoint.** Đã gỡ `POST /contracts/{id}/retry-pdf` và `GET /contracts/{id}/documents/pdf` cùng toàn bộ khâu xuất PDF (§9.13).

---

## 5.1. Quy ước chung

### 5.1.1. Thông tin cơ bản

| Mục | Giá trị |
|---|---|
| Base URL | `http://127.0.0.1:{port}` — cổng động, **chỉ loopback** |
| Tiền tố phiên bản | `/api/v1` |
| Định dạng | JSON (UTF-8) · `multipart/form-data` cho upload · binary stream cho download |
| Đặc tả | OpenAPI 3.1 tự sinh, tại `/api/docs` — ⭐ **chỉ bật khi `app.debug = true`**, tắt trong bản phát hành |
| Múi giờ | Mọi timestamp là **ISO-8601 UTC** hậu tố `Z`. Frontend quy đổi sang giờ Việt Nam |
| Ngày (date-only) | `yyyy-MM-dd` trong JSON; hiển thị `dd/MM/yyyy` ở UI |

### 5.1.2. Header

| Header | Bắt buộc | Mô tả |
|---|---|---|
| ⭐ `X-Local-Token` | ✅ **Mọi request** | Local Handshake Token do Tauri sinh. Sai → `403 COCAS-1007` — **lớp bảo vệ duy nhất ở cổng vào** |
| `X-Correlation-ID` | ⬜ | Client sinh UUID; không có thì server tự sinh. Luôn trả lại trong response header |
| `If-Match: <version>` | ✅ **chỉ endpoint hợp đồng** | Khoá lạc quan. Lệch → `409 COCAS-7014` |
| `Accept-Language` | ⬜ | `vi` (mặc định) / `en` |

> **Đã bỏ:** `Authorization: Bearer` (D1.6 — không có xác thực) · `Idempotency-Key` (D2.0 — thay bằng vô hiệu hoá nút + ràng buộc UNIQUE).

### 5.1.3. Phản hồi thành công

Trả **thẳng đối tượng**, không bọc trong `{"data": ...}`:

```json
{
  "id": "0192f4a1-8b3c-7def-9012-3456789abcde",
  "status": "COMPLETED",
  "created_at": "2026-08-08T09:14:22.481Z"
}
```

Danh sách có phân trang:

```json
{
  "items": [ ],
  "page": 1,
  "page_size": 20,
  "total_items": 137,
  "total_pages": 7,
  "has_next": true
}
```

### 5.1.4. Phản hồi lỗi (thống nhất toàn hệ thống)

```json
{
  "error": {
    "code": "COCAS-2003",
    "type": "VALIDATION_ERROR",
    "message": "Số CCCD phải có đúng 12 chữ số.",
    "message_en": "Citizen ID must be exactly 12 digits.",
    "hint": "Kiểm tra lại trường 'Số CCCD'. Nếu ảnh mờ, hãy chụp lại mặt trước.",
    "details": [
      { "field": "id_number", "code": "INVALID_LENGTH", "message": "Độ dài hiện tại: 11 ký tự." }
    ],
    "correlation_id": "c1a4e0b2-9f33-4a11-8d77-2e5b1c9f0a44",
    "timestamp": "2026-08-08T09:14:22.481Z",
    "retryable": false
  }
}
```

**Bắt buộc:** `code`, `type`, `message` (tiếng Việt cho người dùng cuối), `correlation_id`, `timestamp`.
⭐ **`hint`** — luôn phải trả lời *"tôi nên làm gì bây giờ?"*. Đây là khác biệt giữa phần mềm doanh nghiệp và nghiệp dư.
⭐ **`retryable`** — cho phép frontend tự động thử lại với backoff mà không hỏi người dùng.

### 5.1.5. Bảng mã lỗi

| Dải | Nhóm | HTTP | Mã |
|---|---|---|---|
| `COCAS-1xxx` | **Cổng vào** | 403 | `1007` Local Token không hợp lệ *(mã duy nhất còn lại trong dải này)* |
| `COCAS-2xxx` | **Validation dữ liệu** | 400/422 | `2001` thiếu trường bắt buộc · `2002` sai định dạng · `2003` CCCD không đúng 12 số · `2004` ngày không hợp lệ · `2005` ngày cấp > ngày hết hạn · `2006` SĐT Việt Nam không hợp lệ · `2007` email không hợp lệ · `2008` STK chỉ được chứa số · `2009` nơi cấp không thuộc 2 giá trị chuẩn · `2010` thẻ đã hết hạn · `2011` tuổi không hợp lệ · `2012` STK chứng khoán sai định dạng · `2013` STK chứng khoán sai mã thành viên |
| `COCAS-3xxx` | **Nạp file & Ảnh** | 400/413/415/422 | `3001` vượt dung lượng · `3002` định dạng không hỗ trợ · `3003` magic bytes không khớp · `3004` ảnh hỏng · `3005` kích thước ngoài phạm vi · `3006` nghi decompression bomb · `3007` tải cùng một ảnh hai lần |
| `COCAS-4xxx` | **OCR** | 409/422/500/503 | `4001` phiên không tồn tại · `4002` phiên chưa hoàn tất · `4003` không phân loại được mặt · `4004` tải trùng một mặt · `4005` hai ảnh không cùng một thẻ · `4006` chất lượng ảnh quá kém · `4007` engine OCR không sẵn sàng · `4008` phiên đã được sử dụng · `4009` hết số lần thử lại |
| `COCAS-5xxx` | **Khách hàng** | 404/409/422 | `5001` không tìm thấy · `5002` CCCD đã tồn tại · `5004` không thể xoá (còn hợp đồng) · `5005` STK trùng trong cùng khách hàng · `5007` STK chứng khoán đã thuộc khách hàng khác |
| `COCAS-6xxx` | **Template** | 400/404/422 | `6001` không tìm thấy · `6002` file không phải DOCX hợp lệ · `6003` cú pháp Jinja2 sai · `6004` chứa biến không xác định · `6005` không có phiên bản active · `6006` checksum file không khớp · `6007` file mẫu thiếu trên đĩa · `6008` biến cần in đậm viết dạng thường · `6009` biến không xác định · `6010` chứa placeholder ảnh · `6011` biến bắt buộc của party_schema không xuất hiện · `6012` `{% for %}` trên biến không phải mảng · `6014` **cấu trúc Jinja2 nguy hiểm** · `6015` file quá lớn · `6016` `party_schema` yêu cầu tính năng chưa hỗ trợ ở v1.0 |
| `COCAS-7xxx` | **Hợp đồng** | 404/409/422/500 | `7001` không tìm thấy · `7002` thiếu biến bắt buộc · `7003` render DOCX thất bại · ~~`7004`~~ ~~`7005`~~ *(D2.1 — đã gỡ cùng khâu PDF, **không tái sử dụng số**)* · `7006` hợp đồng đã bị huỷ · `7007` không thể sửa hợp đồng đã hoàn tất · `7008` tài liệu chưa sẵn sàng · `7009` **checksum tài liệu không khớp** · `7010` số bên không khớp `party_schema` · `7011` `entity_type` không khớp khai báo · `7012` thiếu `bank_account_id` · `7013` một chủ thể đóng 2 vai · `7014` **xung đột phiên bản** |
| `COCAS-8xxx` | **Hệ thống** | 500/503/507 | `8001` lỗi CSDL · `8002` lỗi hệ thống tệp · `8003` hết dung lượng đĩa · `8004` lỗi giải mã · `8005` dịch vụ chưa sẵn sàng · `8006` job thất bại · `8007` backup thất bại · `8008` phiên bản schema không tương thích · `8009` sai mật khẩu backup |
| `COCAS-9xxx` | **Giao thức** | 400 | `9002` JSON sai cú pháp · `9003` tham số phân trang không hợp lệ · `9004` tham số `sort` ngoài danh sách trắng |

### 5.1.6. Mã trạng thái HTTP

| Mã | Khi nào |
|---|---|
| `200` | GET, PUT, PATCH thành công |
| `201` | Tạo tài nguyên xong, có `Location` header |
| `202` | Đã nhận, xử lý bất đồng bộ, có `Location` + `poll_url` |
| `204` | Xoá thành công, không có body |
| `400` | Request sai cú pháp / tham số |
| `403` | Local Token sai |
| `404` | Tài nguyên không tồn tại hoặc đã soft-delete |
| `409` | Xung đột trạng thái / phiên bản / trùng lặp |
| `410` | Tài nguyên đã bị purge (ảnh) |
| `413` | File vượt giới hạn |
| `415` | MIME không được phép |
| `422` | Cú pháp đúng nhưng vi phạm quy tắc nghiệp vụ |
| `500` | Lỗi không lường trước — **luôn kèm `correlation_id`** |
| `503` | Engine OCR chưa sẵn sàng |
| `507` | Hết dung lượng đĩa |

### 5.1.7. Phân trang, lọc, sắp xếp

| Tham số | Mặc định | Ràng buộc |
|---|---|---|
| `page` | `1` | ≥ 1 |
| `page_size` | `20` | 1–100 |
| `sort` | tuỳ endpoint | ⭐ **Danh sách trắng** — `-created_at`, `full_name`… Ngoài danh sách → `400 COCAS-9004` |
| `q` | — | ≤ 100 ký tự — tìm toàn văn (`full_name_search` + blind index) |
| `date_from` / `date_to` | — | `yyyy-MM-dd` |
| `status` | — | Enum, cho phép nhiều giá trị |

> ⭐ **Bảo mật:** `sort` chỉ chấp nhận giá trị trong danh sách trắng cho từng endpoint — chống SQL injection qua tên cột. **Không bao giờ ghép chuỗi tên cột từ input.**

---

## 5.2. Danh mục ⭐ 62 endpoint

| # | Method | Đường dẫn | Mô tả |
|---|---|---|---|
| **Hệ thống (3)** ||||
| 1 | GET | `/health` | Kiểm tra sống (dùng bởi Tauri supervisor) |
| 2 | GET | `/api/v1/system/health` | Sức khoẻ chi tiết + thông tin phiên bản |
| 3 | GET | `/api/v1/system/diagnostics` | Chẩn đoán đầy đủ (đĩa, log, tệp mồ côi, kích thước bảng) |
| **Ảnh (4)** ||||
| 4 | POST | `/api/v1/upload/front` | Tải ảnh mặt trước |
| 5 | POST | `/api/v1/upload/back` | Tải ảnh mặt sau |
| 6 | GET | `/api/v1/images/{id}?size=thumb\|full` | Xem ảnh |
| 7 | DELETE | `/api/v1/images/{id}` | Xoá ảnh chưa dùng |
| **OCR (9)** ||||
| 8 | POST | `/api/v1/ocr` | Tạo phiên + đưa vào hàng đợi |
| 9 | GET | `/api/v1/ocr` | Danh sách phiên gần đây |
| 10 | GET | `/api/v1/ocr/{id}` | ⭐ Lấy kết quả đầy đủ |
| 11 | GET | `/api/v1/ocr/{id}/progress` | Tiến độ (nhẹ, để poll) |
| 12 | PATCH | `/api/v1/ocr/{id}/fields` | Sửa trường OCR |
| 13 | POST | `/api/v1/ocr/{id}/reassign-sides` | Gán lại mặt thủ công |
| 14 | POST | `/api/v1/ocr/{id}/retry` | Chạy lại OCR |
| 15 | POST | `/api/v1/ocr/{id}/confirm` | Xác nhận kết quả |
| 16 | DELETE | `/api/v1/ocr/{id}` | Huỷ phiên |
| **Khách hàng (6)** ||||
| 17 | POST | `/api/v1/customers` | Tạo khách hàng |
| 18 | GET | `/api/v1/customers` | Danh sách + tìm kiếm + `?id_number=&exact=true` |
| 19 | GET | `/api/v1/customers/{id}` | Chi tiết |
| 20 | PUT | `/api/v1/customers/{id}` | Cập nhật |
| 21 | DELETE | `/api/v1/customers/{id}` | Soft delete |
| 22 | GET | `/api/v1/customers/{id}/contracts` | Hợp đồng của khách hàng |
| **TK ngân hàng (4)** ||||
| 23 | POST | `/api/v1/customers/{id}/bank-accounts` | Thêm |
| 24 | PUT | `/api/v1/bank-accounts/{id}` | Sửa |
| 25 | DELETE | `/api/v1/bank-accounts/{id}` | Xoá |
| 26 | POST | `/api/v1/bank-accounts/{id}/set-primary` | Đặt làm TK chính |
| **Mẫu hợp đồng (11)** ||||
| 27 | GET | `/api/v1/templates` | Danh sách mẫu |
| 28 | GET | `/api/v1/templates/{id}` | Chi tiết + biến |
| 29 | GET | `/api/v1/templates/{id}/requirements` | ⭐ `party_schema` đã resolve — **điều khiển wizard** |
| 30 | POST | `/api/v1/templates` | Đăng ký mẫu mới |
| 31 | POST | `/api/v1/templates/validate` | Kiểm tra file trước khi đăng ký |
| 32 | POST | `/api/v1/templates/{id}/versions` | Tải phiên bản mới |
| 33 | POST | `/api/v1/templates/{id}/versions/{vid}/activate` | Kích hoạt phiên bản |
| 34 | PUT | `/api/v1/templates/{id}` | Sửa metadata |
| 35 | DELETE | `/api/v1/templates/{id}` | Vô hiệu hoá |
| 36 | POST | `/api/v1/templates/{id}/preview` | Sinh bản xem thử với dữ liệu giả |
| 37 | GET | `/api/v1/templates/variables` | Từ điển biến hệ thống |
| **Hợp đồng (7)** ||||
| 38 | POST | `/api/v1/contracts/generate` | Sinh hợp đồng |
| 39 | GET | `/api/v1/contracts` | Danh sách + lọc |
| 40 | GET | `/api/v1/contracts/{id}` | Chi tiết + `parties[]` |
| 41 | POST | `/api/v1/contracts/{id}/regenerate` | Sinh lại (revision mới) |
| 42 | POST | `/api/v1/contracts/{id}/void` | Huỷ hợp đồng |
| 43 | GET | `/api/v1/contracts/{id}/documents` | Liệt kê tài liệu |
| 44 | GET | `/api/v1/contracts/{id}/documents/docx` | Tải DOCX |
| **Tham chiếu (5)** ||||
| 45 | GET | `/api/v1/reference/banks` | Danh mục ngân hàng |
| 46 | GET | `/api/v1/reference/provinces` | Danh mục tỉnh/thành |
| 47 | GET | `/api/v1/reference/aliases` | Từ điển chuẩn hoá |
| 48 | POST | `/api/v1/reference/aliases` | Thêm alias mới |
| 49 | DELETE | `/api/v1/reference/aliases/{id}` | Xoá alias |
| **Cấu hình (3)** ||||
| 50 | GET | `/api/v1/settings` | Đọc cấu hình |
| 51 | PUT | `/api/v1/settings/{key}` | Sửa một cấu hình |
| 52 | POST | `/api/v1/settings/reset` | Khôi phục mặc định |
| **Nhật ký (2)** ||||
| 53 | GET | `/api/v1/activity-logs` | Xem nhật ký hoạt động |
| 54 | GET | `/api/v1/activity-logs/export` | ⭐ Xuất CSV / JSONL — **bản lề lưu trữ lạnh** |
| **Sao lưu (3)** ||||
| 55 | POST | `/api/v1/backups` | Tạo bản sao lưu |
| 56 | GET | `/api/v1/backups` | Danh sách bản sao lưu |
| 57 | POST | `/api/v1/backups/restore` | Khôi phục (có xác minh trước) |
| **Công việc (3)** ||||
| 58 | GET | `/api/v1/jobs` | Danh sách job |
| 59 | GET | `/api/v1/jobs/{id}` | Chi tiết job |
| 60 | POST | `/api/v1/jobs/{id}/cancel` | Huỷ job |
| **Tổng quan (2)** ||||
| 61 | GET | `/api/v1/dashboard/summary` | Số liệu tổng quan |
| 62 | GET | `/api/v1/dashboard/ocr-accuracy` | ⭐ Báo cáo độ chính xác OCR thực tế |

---

## 5.3. Đặc tả chi tiết endpoint trọng yếu

### 5.3.1. `GET /templates/{id}/requirements` ⭐ Endpoint điều khiển wizard

**Response `200`**
```json
{
  "template_id": "0192e001-1111-7000-a000-000000000001",
  "code": "01A_GDKQ",
  "name": "Mẫu 01A/GDKQ",
  "version_no": 1,
  "party_schema_version": 1,
  "parties": [
    {
      "key": "holder",
      "label": "Khách hàng",
      "entity_type": "INDIVIDUAL",
      "required": true,
      "min": 1, "max": 1,
      "is_primary": true,
      "documents": [
        {
          "doc_type_code": "CCCD_CHIP",
          "doc_type_name": "Căn cước công dân gắn chip",
          "required": true,
          "sides": ["FRONT", "BACK"],
          "ocr_supported": true
        }
      ],
      "collect": ["contact"],
      "extra_fields": [
        {
          "key": "securities_account_no",
          "label": "Số tài khoản chứng khoán",
          "type": "securities_account",
          "required": true,
          "prefill_from": "customer.securities_account_no",
          "placeholder": "008C123456"
        }
      ]
    }
  ],
  "contract_fields": [],
  "estimated_steps": 3,
  "step_labels": ["Chọn mẫu", "Khách hàng", "Hoàn tất"],
  "variables": {
    "required": ["securities_account_no","full_name","id_number","dob",
                 "issue_date","expiry_date","issue_place","phone","email","address"],
    "unknown": []
  }
}
```

**Mã trạng thái:** `200` · `404 COCAS-6001` · `422 COCAS-6005` (chưa có phiên bản active).

---

### 5.3.2. `POST /upload/front` (và `/back`)

**Request:** `multipart/form-data` với phần `file` (binary, bắt buộc).

**Response `201`** (kèm `Location: /api/v1/images/{id}`)
```json
{
  "id": "0192f4b2-1c4d-7000-a111-222233334444",
  "side_hint": "FRONT",
  "sha256": "3f7a9c1e8b2d4056...",
  "mime_type": "image/jpeg",
  "width_px": 1920,
  "height_px": 1210,
  "size_bytes": 487232,
  "quality_score": 0.87,
  "quality_flags": [],
  "thumbnail_url": "/api/v1/images/0192f4b2-1c4d-7000-a111-222233334444?size=thumb",
  "created_at": "2026-08-08T09:12:04.221Z"
}
```

**Response `201` kèm cảnh báo chất lượng:**
```json
{
  "id": "...",
  "quality_score": 0.41,
  "quality_flags": ["TOO_DARK", "BLURRY"],
  "warnings": [
    {
      "code": "IMAGE_QUALITY_LOW",
      "message": "Ảnh hơi tối và mờ. Kết quả OCR có thể kém chính xác.",
      "hint": "Nên chụp lại ở nơi đủ sáng, đặt thẻ trên nền tối, giữ máy song song với mặt thẻ."
    }
  ]
}
```

**Mã trạng thái:** `201` · `400 COCAS-2001` · `409 COCAS-3007` (kèm `existing_image_id`) · `413 COCAS-3001` · `415 COCAS-3002/3003` · `422 COCAS-3004/3005/3006` · `507 COCAS-8003`.

---

### 5.3.3. `POST /ocr`

**Request**
```json
{
  "front_image_id": "0192f4b2-1c4d-7000-a111-222233334444",
  "back_image_id":  "0192f4b3-5e6f-7000-b222-333344445555",
  "document_type_code": "CCCD_CHIP",
  "party_key": "holder",
  "party_index": 0,
  "options": { "preprocessing_profile": "default", "force_full_ocr": false }
}
```

**Response `202`** (kèm `Location`, `Retry-After: 2`)
```json
{
  "id": "0192f4c0-aaaa-7000-c333-444455556666",
  "status": "QUEUED",
  "job_id": "0192f4c0-bbbb-7000-d444-555566667777",
  "queue_position": 1,
  "estimated_seconds": 6,
  "poll_url": "/api/v1/ocr/0192f4c0-aaaa-7000-c333-444455556666/progress",
  "created_at": "2026-08-08T09:12:31.007Z"
}
```

**Mã trạng thái:** `202` · `404 COCAS-3004` · `409 COCAS-4004` (hai `image_id` giống nhau) · `410` (ảnh đã purge) · `503 COCAS-4007` (`retryable: true`).

---

### 5.3.4. `GET /ocr/{id}` ⭐ Endpoint quan trọng nhất

**Response `200`** — hoàn tất có cảnh báo:

```json
{
  "id": "0192f4c0-aaaa-7000-c333-444455556666",
  "status": "COMPLETED_WITH_WARNINGS",
  "document_type_code": "CCCD_CHIP",
  "party_key": "holder",
  "party_index": 0,
  "overall_confidence": 0.91,
  "auto_swapped": true,
  "duration_ms": 3820,
  "engine": { "name": "paddle", "version": "2.9.0" },

  "channels": {
    "qr":  { "available": true, "confidence": 1.00, "attempts": 1 },
    "mrz": { "available": true, "checksum_valid": true, "corrections_applied": 0 },
    "ocr": { "available": true, "regions_detected": 23 }
  },

  "images": {
    "front": { "id": "0192f4b2-...", "url": "/api/v1/images/0192f4b2-...", "side_confidence": 0.97 },
    "back":  { "id": "0192f4b3-...", "url": "/api/v1/images/0192f4b3-...", "side_confidence": 0.94 }
  },

  "fields": {
    "full_name": {
      "value": "NGUYỄN VĂN AN",
      "source": "QR",
      "confidence": 1.00,
      "needs_review": false,
      "user_corrected": false,
      "bbox": { "x": 0.38, "y": 0.40, "w": 0.60, "h": 0.09 },
      "candidates": [
        { "source": "QR",  "confidence": 1.00, "agrees": true },
        { "source": "OCR", "confidence": 0.93, "agrees": true }
      ]
    },
    "id_number": {
      "value": "001199012345",
      "source": "QR",
      "confidence": 1.00,
      "needs_review": false,
      "bbox": { "x": 0.38, "y": 0.28, "w": 0.57, "h": 0.10 },
      "derived": {
        "province_code": "001",
        "province_name": "Thành phố Hà Nội",
        "gender_inferred": "NAM",
        "birth_century_inferred": 1900,
        "consistent_with_dob": true
      }
    },
    "date_of_birth": {
      "value": "1990-05-14", "value_display": "14/05/1990",
      "source": "QR", "confidence": 1.00, "needs_review": false
    },
    "issue_date": {
      "value": "2021-08-20", "value_display": "20/08/2021",
      "source": "OCR", "confidence": 0.88, "needs_review": false,
      "bbox": { "x": 0.30, "y": 0.74, "w": 0.40, "h": 0.07 }
    },
    "expiry_date": {
      "value": "2030-05-14", "value_display": "14/05/2030", "no_expiry": false,
      "source": "MRZ", "confidence": 0.98, "needs_review": false
    },
    "issue_place": {
      "value": "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
      "raw_value": "CUC CS QLHC VE TTXH",
      "source": "OCR",
      "confidence": 0.72,
      "needs_review": true,
      "normalization_tier": 2,
      "allowed_values": [
        "BỘ CÔNG AN",
        "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"
      ]
    }
  },

  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [
      {
        "code": "LOW_CONFIDENCE", "field": "issue_place",
        "message": "Nơi cấp được nhận dạng với độ tin cậy 72%.",
        "hint": "Vui lòng đối chiếu với ảnh mặt sau và xác nhận."
      },
      {
        "code": "SIDES_AUTO_SWAPPED", "field": null,
        "message": "Hệ thống đã tự động hoán đổi ảnh mặt trước và mặt sau.",
        "hint": "Kiểm tra lại ảnh xem trước để đảm bảo đúng."
      }
    ],
    "infos": [
      { "code": "CARD_VALID", "message": "Thẻ còn hiệu lực đến 14/05/2030 (còn 3 năm 9 tháng)." }
    ]
  },

  "next_actions": ["EDIT_FIELDS", "CONFIRM", "RETRY_OCR"],
  "created_at": "2026-08-08T09:12:31.007Z",
  "completed_at": "2026-08-08T09:12:34.827Z"
}
```

**Response `200`** — cần tải lại ảnh:
```json
{
  "id": "...",
  "status": "NEEDS_REUPLOAD",
  "error": {
    "code": "COCAS-4004",
    "message": "Bạn đã tải hai ảnh của cùng một mặt.",
    "hint": "Ảnh thứ nhất và ảnh thứ hai đều được nhận diện là MẶT TRƯỚC. Vui lòng tải ảnh mặt sau (mặt có vân tay và ngày cấp)."
  },
  "detected_sides": { "image_1": "FRONT", "image_2": "FRONT" },
  "next_actions": ["REUPLOAD", "REASSIGN_SIDES"]
}
```

> ⭐ **`next_actions` là quyết định thiết kế quan trọng:** backend nói cho frontend biết hành động nào hợp lệ ở trạng thái này. Frontend **không phải sao chép logic máy trạng thái** → xoá cả một lớp bug đồng bộ.

**Mã trạng thái:** `200` (mọi trạng thái phiên, kể cả lỗi nghiệp vụ) · `404 COCAS-4001`.

---

### 5.3.5. `GET /ocr/{id}/progress` — Endpoint nhẹ để poll

Payload ~200 byte, gọi mỗi 800 ms:

```json
{
  "id": "0192f4c0-aaaa-7000-c333-444455556666",
  "status": "PROCESSING",
  "progress_percent": 65,
  "progress_message": "Đang đọc vùng MRZ mặt sau…",
  "elapsed_ms": 2410,
  "estimated_remaining_ms": 1300
}
```

---

### 5.3.6. `PATCH /ocr/{id}/fields`

**Request** (chỉ gửi trường thay đổi)
```json
{ "fields": { "issue_place": "BỘ CÔNG AN", "issue_date": "2021-08-25" } }
```

**Response `200`** — trả về **toàn bộ** phiên đã cập nhật (giống §5.3.4), trường đã sửa có `source: "MANUAL"`, `confidence: 1.00`, `user_corrected: true`, `validation` chạy lại.

**Mã trạng thái:** `200` · `409 COCAS-4008` (phiên đã `CONSUMED`) · `422 COCAS-2009` (giá trị vi phạm).

---

### 5.3.7. `POST /customers`

**Request**
```json
{
  "ocr_session_id": "0192f4c0-aaaa-7000-c333-444455556666",
  "full_name": "NGUYỄN VĂN AN",
  "id_number": "001199012345",
  "date_of_birth": "1990-05-14",
  "gender": "NAM",
  "issue_date": "2021-08-20",
  "expiry_date": "2030-05-14",
  "no_expiry": false,
  "issue_place": "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
  "phone": "0912345678",
  "email": "nguyenvanan@example.com",
  "address": "Số 12, ngõ 34, phố Kim Mã, phường Kim Mã, quận Ba Đình, Hà Nội",
  "securities_account_no": "008C123456",
  "bank_account": {
    "account_number": "1234567890123",
    "bank_code": "VCB",
    "bank_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
    "branch": "Chi nhánh Ba Đình",
    "account_holder_name": "NGUYEN VAN AN"
  },
  "note": null
}
```

**Response `201`**
```json
{
  "id": "0192f4d1-1111-7000-e555-666677778888",
  "full_name": "NGUYỄN VĂN AN",
  "id_number": "001199012345",
  "date_of_birth": "1990-05-14",
  "date_of_birth_display": "14/05/1990",
  "gender": "NAM",
  "issue_place": "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
  "issue_date": "2021-08-20",
  "expiry_date": "2030-05-14",
  "no_expiry": false,
  "phone": "0912345678",
  "email": "nguyenvanan@example.com",
  "address": "Số 12, ngõ 34, phố Kim Mã, phường Kim Mã, quận Ba Đình, Hà Nội",
  "securities_account_no": "008C123456",
  "province": { "code": "001", "name": "Thành phố Hà Nội" },
  "data_quality": "MIXED",
  "bank_accounts": [
    {
      "id": "0192f4d1-2222-7000-f666-777788889999",
      "account_number": "1234567890123",
      "bank_code": "VCB",
      "bank_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
      "branch": "Chi nhánh Ba Đình",
      "is_primary": true
    }
  ],
  "created_at": "2026-08-08T09:15:02.334Z"
}
```

> ⭐ **Trả PII đầy đủ** (D1.6 — máy nội bộ, không có phân quyền, không cần che).

**Response `409`** — CCCD đã tồn tại:
```json
{
  "error": {
    "code": "COCAS-5002",
    "type": "DUPLICATE_CUSTOMER",
    "message": "Số CCCD này đã tồn tại trong hệ thống.",
    "hint": "Bạn có thể cập nhật thông tin khách hàng hiện có, hoặc kiểm tra lại số CCCD.",
    "details": [
      {
        "field": "id_number", "code": "DUPLICATE",
        "existing_customer": {
          "id": "0192f0aa-9999-7000-1234-abcdefabcdef",
          "full_name": "NGUYỄN VĂN AN",
          "id_number": "001199012345",
          "created_at": "2026-03-14T02:11:09Z",
          "contract_count": 2
        }
      }
    ],
    "retryable": false
  }
}
```

**Mã trạng thái:** `201` · `409 COCAS-5002` · `409 COCAS-5007` (STK CK trùng) · `422 COCAS-2xxx` (kèm `details` liệt kê từng trường) · `422 COCAS-4008` · `507 COCAS-8003`.

---

### 5.3.8. `POST /contracts/generate`

**Request**
```json
{
  "template_code": "01A_GDKQ",
  "parties": [
    {
      "party_key": "holder",
      "party_index": 0,
      "entity_type": "INDIVIDUAL",
      "customer_id": "0192f4d1-1111-7000-e555-666677778888",
      "bank_account_id": null,
      "ocr_session_id": "0192f4c0-aaaa-7000-c333-444455556666",
      "is_primary": true,
      "party_extra": { "securities_account_no": "008C123456" }
    }
  ],
  "extra_variables": {}
}
```

**Response `201`**
```json
{
  "id": "0192f4e2-3333-7000-a777-888899990000",
  "contract_no": "01A-KQ-202608-00042",
  "export_name": "Mẫu 01A-GDKQ - NGUYỄN VĂN AN",
  "revision_no": 1,
  "party_count": 1,
  "status": "COMPLETED",
  "parties": [
    {
      "party_key": "holder", "party_index": 0,
      "party_label": "Khách hàng",
      "entity_type": "INDIVIDUAL",
      "is_primary": true,
      "display_name": "NGUYỄN VĂN AN",
      "identifier": "001199012345",
      "party_extra": { "securities_account_no": "008C123456" }
    }
  ],
  "template": {
    "id": "0192e001-...", "code": "01A_GDKQ",
    "name": "Mẫu 01A/GDKQ", "version_no": 1
  },
  "contract_date": "2026-08-08",
  "documents": {
    "docx": {
      "ready": true, "size_bytes": 46521, "sha256": "a1b2c3...",
      "download_url": "/api/v1/contracts/0192f4e2-.../documents/docx",
      "generated_at": "2026-08-08T09:16:11.902Z"
    }
  },
  "version": 1,
  "created_at": "2026-08-08T09:16:11.512Z"
}
```

**Response `422`** — thiếu biến bắt buộc:
```json
{
  "error": {
    "code": "COCAS-7002",
    "type": "TEMPLATE_VARIABLE_MISSING",
    "message": "Mẫu hợp đồng yêu cầu 1 thông tin chưa có giá trị.",
    "hint": "Vui lòng bổ sung các trường được liệt kê rồi tạo lại hợp đồng.",
    "details": [
      { "field": "securities_account_no", "label": "Số tài khoản chứng khoán", "code": "REQUIRED" }
    ],
    "retryable": false
  }
}
```

**Mã trạng thái:** `201` · `404 COCAS-5001/6001` · `422 COCAS-7002/7010/7011/7012/7013` · `422 COCAS-6005` · `409 COCAS-6006/6007` · `500 COCAS-7003` · `507 COCAS-8003`.

---

### 5.3.9. `GET /contracts/{id}/documents/docx`

**Query:** `?disposition=attachment` (mặc định) hoặc `?disposition=inline`.

> ⭐ **D2.1 — đây là endpoint tải tài liệu DUY NHẤT.** `GET .../documents/pdf` đã bị gỡ cùng khâu chuyển PDF.

**Response `200`**
```
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename*=UTF-8''M%E1%BA%ABu%2001A%20-%20NGUY%E1%BB%84N%20V%C4%82N%20A.docx
Content-Length: 46521
X-Document-SHA256: 9f8e7d6c5b4a...
Cache-Control: no-store, private
X-Content-Type-Options: nosniff

<binary stream>
```

> ⭐ **Bắt buộc dùng `filename*` theo RFC 5987** — `filename=` thường không hỗ trợ tiếng Việt có dấu.

**Quy trình bắt buộc trước khi trả file:**

| # | Bước |
|---|---|
| 1 | Nạp `contract_document`, lấy `file_path` **tương đối** |
| 2 | Ghép với gốc Vault, **chuẩn hoá đường dẫn** (`Path.resolve()`) |
| 3 | ⭐ Kiểm tra kết quả **vẫn nằm trong** thư mục Vault (`is_relative_to`) → chống Path Traversal |
| 4 | Đọc file, tính SHA-256, so với `file_sha256`. Lệch → `500 COCAS-7009` + ghi nhật ký `DOCUMENT_INTEGRITY_FAILED` |
| 5 | Giải mã, stream về client |
| 6 | Tăng `download_count`, ghi nhật ký `DOCUMENT_DOWNLOADED` |

**Mã trạng thái:** `200` · `404` · `409 COCAS-7008` (tài liệu chưa sẵn sàng — hợp đồng còn ở `GENERATING`) · `500 COCAS-7009` · `500 COCAS-8002`.

---

### 5.3.10. `POST /templates` — Đăng ký mẫu mới (hiện thực P-06)

**Request:** `multipart/form-data` với `file` (.docx) và `metadata` (JSON).

`metadata`:
```json
{
  "code": "01A_GDKQ",
  "name": "Mẫu 01A/GDKQ",
  "description": "Hợp đồng giao dịch ký quỹ",
  "category": "Chứng khoán",
  "contract_no_pattern": "01A-KQ-{yyyy}{MM}-{seq:05d}",
  "export_name_pattern": "Mẫu 01A-GDKQ - {full_name}",
  "suppressed_variables": ["contract_date","contract_date_text","day","month","year"],
  "party_schema": [
    {
      "key": "holder", "label": "Khách hàng",
      "entity_type": "INDIVIDUAL", "required": true,
      "min": 1, "max": 1, "is_primary": true,
      "documents": [{ "doc_type_code": "CCCD_CHIP", "required": true,
                      "sides": ["FRONT","BACK"] }],
      "collect": ["contact"],
      "extra_fields": [
        {
          "key": "securities_account_no",
          "label": "Số tài khoản chứng khoán",
          "type": "securities_account",
          "required": true,
          "prefill_from": "customer.securities_account_no",
          "persist_to": "customer.securities_account_no",
          "render_style": { "bold": true }
        }
      ]
    }
  ],
  "contract_fields": [],
  "activate_immediately": true
}
```

**Response `201`**
```json
{
  "id": "0192f500-aaaa-7000-c111-d222e333f444",
  "code": "01A_GDKQ",
  "name": "Mẫu 01A/GDKQ",
  "is_active": true,
  "active_version": {
    "id": "0192f500-bbbb-7000-e555-f666a777b888",
    "version_no": 1,
    "file_size_bytes": 68420,
    "sha256": "c4d5e6f7...",
    "validation_status": "VALID",
    "variables": {
      "required": ["securities_account_no","full_name","id_number","dob",
                   "issue_date","expiry_date","issue_place","phone","email","address"],
      "optional": [],
      "unknown": [],
      "richtext": ["securities_account_no"]
    },
    "has_loops": false,
    "has_conditionals": false,
    "validation_report": { "errors": [], "warnings": [], "infos": [] },
    "created_at": "2026-08-08T10:02:44.118Z"
  },
  "created_at": "2026-08-08T10:02:44.118Z"
}
```

**Mã trạng thái:** `201` · `400 COCAS-6002` · `409` (`code` đã tồn tại) · `413` · `422 COCAS-6003` (kèm số dòng) · `422 COCAS-6014` (SSTI) · `422 COCAS-6016` (`party_schema` yêu cầu tính năng chưa hỗ trợ).

---

### 5.3.11. `GET /system/health`

**Response `200`**
```json
{
  "status": "HEALTHY",
  "app_version": "1.0.0",
  "schema_version": "20260811_008_seed_contract_template",
  "uptime_seconds": 4821,
  "windows_user": "nvnghiep",
  "checks": {
    "database":      { "status": "UP", "latency_ms": 3,  "detail": "PostgreSQL 16.2" },
    "ocr_engine":    { "status": "UP", "latency_ms": 0,  "detail": "PaddleOCR 2.9.0, models loaded" },
    "file_vault":    { "status": "UP", "detail": "Writable, 47.2 GB free" },
    "job_runner":    { "status": "UP", "detail": "0 queued, 0 running" },
    "encryption":    { "status": "UP", "detail": "KEK loaded from DPAPI" }
  },
  "warnings": [
    {
      "code": "BACKUP_OVERDUE",
      "message": "Đã 9 ngày chưa sao lưu dữ liệu.",
      "hint": "Vào Cài đặt → Dữ liệu & Sao lưu để tạo bản sao lưu ngay."
    }
  ]
}
```

**Trạng thái tổng:** `HEALTHY` (mọi check `UP`/`IDLE`) · `DEGRADED` (một số `DOWN` nhưng vẫn dùng được — ví dụ OCR chết thì vẫn nhập tay được) · `UNHEALTHY` (database `DOWN`).
**Mã HTTP:** `200` cho `HEALTHY`/`DEGRADED`, `503` cho `UNHEALTHY`.

---

### 5.3.12. Các endpoint còn lại — tóm tắt

| Endpoint | Request | Response | Mã đặc thù |
|---|---|---|---|
| `GET /images/{id}?size=` | — | `image/jpeg` (`thumb`=240px hoặc `full`) | `404` · `410` đã purge |
| `POST /ocr/{id}/reassign-sides` | `{front_image_id, back_image_id}` | Phiên cập nhật, `status=QUEUED` | `409 COCAS-4008` |
| `POST /ocr/{id}/retry` | `{preprocessing_profile?}` | `202` + job mới | `409 COCAS-4009` |
| `POST /ocr/{id}/confirm` | — | `status=CONFIRMED` | `422` còn lỗi validation |
| `GET /customers` | `q, page, page_size, sort, date_from, date_to, id_number, exact` | Danh sách phân trang | `400 COCAS-9004` |
| `PUT /customers/{id}` | Toàn bộ đối tượng | Đối tượng đã cập nhật | `404` · `422` |
| `DELETE /customers/{id}` | — | `204` | `409 COCAS-5004` còn hợp đồng |
| `POST /contracts/{id}/regenerate` | `{reason, extra_variables?}` + `If-Match` | Hợp đồng mới `revision_no+1`, bản cũ → `SUPERSEDED` | `409 COCAS-7006/7014` |
| `POST /contracts/{id}/void` | `{reason}` (≥10 ký tự) + `If-Match` | `status=VOIDED` | `409 COCAS-7006/7014` |
| `POST /templates/validate` | multipart `file` | Báo cáo biến + lỗi, **không lưu gì** | `422 COCAS-6003/6014` |
| `POST /templates/{id}/preview` | — | ⭐ `.docx` từ **dữ liệu giả** + watermark "BẢN XEM THỬ" | `422` |
| `GET /templates/variables` | — | Từ điển biến: `key`, `label_vi`, `type`, `example`, `source`, `render_style` | — |
| `GET /reference/banks` | `?q=` | NH + `account_min_len`/`max_len` | — |
| `POST /reference/aliases` | `{field_key, alias, canonical_value, tier, keywords?}` | `201` | `409` alias đã tồn tại |
| `PUT /settings/{key}` | `{value}` | Cấu hình cập nhật + `requires_restart` | `422` vi phạm `constraints` |
| `GET /activity-logs` | `action, entity_type, entity_id, actor, date_from, date_to, page` | Danh sách phân trang | — |
| `GET /activity-logs/export` | `?format=csv\|jsonl&date_from=&date_to=` | ⭐ File CSV (UTF-8 **có BOM**) hoặc JSONL | — |
| `POST /backups` | `{target_directory?, note?}` | `202` + `job_id` | `507` |
| `POST /backups/restore` | `{backup_file_path, passphrase, confirm_token}` | `202` — ⭐ tự sao lưu hiện trạng trước | `422 COCAS-8008` schema không tương thích · `403 COCAS-8009` sai mật khẩu |
| `GET /jobs/{id}` | — | Trạng thái, tiến độ, lỗi | `404` |
| `GET /dashboard/summary` | `?period=today\|week\|month` | HĐ đã tạo, KH mới, tỉ lệ OCR thành công, job lỗi, cảnh báo backup | — |
| `GET /dashboard/ocr-accuracy` | `?days=30` | ⭐ Tỉ lệ `user_corrected` theo `field_key` × `source` | — |

---

## 5.4. Luồng gọi API hoàn chỉnh (một hợp đồng)

| # | Gọi | Kết quả |
|---|---|---|
| 1 | `GET /system/health` | App khởi động, kiểm tra sẵn sàng |
| 2 | `GET /templates` | 2 mẫu đang hoạt động |
| 3 | `GET /templates/{id}/requirements` | ⭐ `party_schema` → wizard dựng 3 bước |
| 4 | `POST /upload/front` | `201` — `front_image_id` |
| 5 | `POST /upload/back` | `201` — `back_image_id` |
| 6 | `POST /ocr` | `202` — `session_id`, `job_id` |
| 7 | `GET /ocr/{id}/progress` × ~5 lần, mỗi 800 ms | `PROCESSING` 20% → 65% → 90% |
| 8 | `GET /ocr/{id}` | `COMPLETED_WITH_WARNINGS`, 6 trường + bbox |
| 9 | `PATCH /ocr/{id}/fields` | Sửa `issue_place` |
| 10 | `POST /ocr/{id}/confirm` | `CONFIRMED` |
| 11 | `GET /customers?id_number=…&exact=true` | `{items: []}` — không trùng |
| 12 | `GET /reference/banks?q=ngoai thuong` | Gợi ý VCB *(chỉ với mẫu HĐ-GĐN)* |
| 13 | `POST /customers` | `201` — `customer_id` + `bank_account_id` |
| 14 | `POST /contracts/generate` | ⭐ `201` — `COMPLETED` ngay, `.docx` sẵn sàng |
| 15 | `GET /contracts/{id}/documents/docx` | Stream `.docx` |
| 16 | *(nền)* job `RETENTION_PURGE` | Xoá 2 ảnh gốc, ghi nhật ký `IMAGE_PURGED` |

**Tổng:** ⭐ ~25 lượt gọi (gồm polling; D2.1 bỏ ~5 lượt polling job PDF) · ~40 giây, trong đó **~35 giây là thời gian nhập liệu của con người**.

---

## 5.5. Nguyên tắc bảo mật cho mọi endpoint

| # | Nguyên tắc | Thực thi |
|---|---|---|
| 1 | ⭐ **Kiểm tra Local Token trước tiên** | Middleware đầu chuỗi; sai → `403` ngay |
| 2 | **Không tin bất kỳ đầu vào nào** | Pydantic validate mọi request; `sort`/`filter` theo **danh sách trắng**; không ghép chuỗi SQL |
| 3 | ⭐ **Đường dẫn file không bao giờ đến từ client** | Client chỉ gửi UUID; server tra `file_path` từ CSDL rồi `resolve()` + kiểm tra nằm trong Vault |
| 4 | **Header bảo mật trên mọi response** | `X-Content-Type-Options: nosniff` · `X-Frame-Options: DENY` · `Cache-Control: no-store` cho response chứa PII |
| 5 | **Không rò rỉ thông tin qua lỗi** | Thông điệp không chứa đường dẫn tuyệt đối, tên bảng, stack trace. Chi tiết kỹ thuật chỉ vào log, tra bằng `correlation_id` |
| 6 | **Giới hạn kích thước ở mọi tầng** | Body JSON ≤ 1 MB · ảnh ≤ 10 MB · template ≤ 20 MB · `page_size` ≤ 100 · chuỗi tìm kiếm ≤ 100 ký tự |
| 7 | **So sánh hằng thời gian** | Local Token, checksum — dùng `hmac.compare_digest` |
| 8 | **Kiểm tra dung lượng đĩa** trước mọi thao tác ghi lớn | Cảnh báo < 500 MB, chặn < 100 MB → `507` |

---

[← 04 — Cơ sở dữ liệu](04-co-so-du-lieu.md) · [Mục lục](README.md) · [Tiếp: 06 — Giao diện →](06-giao-dien.md)
