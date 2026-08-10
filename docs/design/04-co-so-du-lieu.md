# 04 — Thiết kế cơ sở dữ liệu

[← Mục lục](README.md)

**PostgreSQL 16 portable · 19 bảng · SQLAlchemy 2.0 async · Alembic**

> ⭐ **Sửa số liệu (2026-08-09):** con số "18 bảng" trong các tài liệu khác là đếm nhầm — §4.4 có 18 mục con được đánh số, nhưng mục **4.4.15 gộp chung hai bảng** (`province_code` **và** `bank_directory`) dưới một tiêu đề. Đếm theo sơ đồ ERD ở §4.2 và theo danh sách migration seed ở §4.9 (có migration `seed_province_code` **và** `seed_bank_directory` tách riêng) thì con số đúng là **19 bảng**. Mọi tài liệu khác đã được cập nhật theo con số này.

---

## 4.1. Nguyên tắc thiết kế

| Mã | Nguyên tắc | Diễn giải |
|---|---|---|
| **DB-01** | **UUIDv7 làm khoá chính** | Có tiền tố thời gian → sắp xếp gần đúng theo thời gian (tốt cho B-tree), không lộ số lượng bản ghi, client sinh trước được |
| **DB-02** | **Không xoá cứng dữ liệu nghiệp vụ** | `customer`, `contract`, `contract_template` chỉ soft-delete. Xoá cứng chỉ cho `card_image` (P-05) |
| **DB-03** | **Bất biến cho dữ liệu chứng từ** | `contract` sau `COMPLETED` không được UPDATE trường nghiệp vụ. Sửa = tạo bản mới có `supersedes_id` |
| **DB-04** | **Snapshot thay vì tham chiếu** | `contract.render_snapshot_enc` chứa toàn bộ dữ liệu đã bơm vào template (P-09) |
| **DB-05** | **Mã hoá một khoá (KEK), bảo vệ bằng DPAPI** | Mọi trường PII mã hoá bằng AES-256-GCM với AAD gắn bảng + cột + id |
| **DB-06** | **Blind index cho tra cứu trên trường mã hoá** | `*_bidx` = `HMAC-SHA256(pepper, normalize(value))[0:16]` |
| **DB-07** | **Dữ liệu tham chiếu nằm trong bảng, không trong code** | Alias chuẩn hoá, danh mục ngân hàng, mã tỉnh, loại giấy tờ — admin sửa qua UI (P-06) |
| **DB-08** | **Nhật ký hoạt động append-only** | Vai trò CSDL của ứng dụng chỉ có `SELECT`, `INSERT` trên `activity_log` |
| **DB-09** | **Khoá lạc quan chỉ nơi có tranh chấp thật** | ⭐ Chỉ `contract` có cột `version` (tranh chấp giữa job PDF nền và thao tác huỷ) |
| **DB-10** | **Ràng buộc ở CSDL, không chỉ ở code** | CSDL là tuyến phòng thủ cuối cùng |
| **DB-11** | **Tên bảng số ít, snake_case, tiếng Anh** | `customer` không phải `customers` |
| **DB-12** | **Mọi timestamp là `TIMESTAMPTZ`, lưu UTC** | Presentation quy đổi sang giờ Việt Nam |

---

## 4.2. Sơ đồ quan hệ thực thể

```mermaid
erDiagram
    CARD_IMAGE        }o--|| OCR_SESSION       : "front_image / back_image"
    OCR_SESSION       ||--o| OCR_RESULT        : "sinh ra (1-1)"
    OCR_RESULT        ||--|{ OCR_FIELD         : "gồm 6 trường"
    OCR_SESSION       ||--o| CONTRACT_PARTY    : "phiên quét của bên"

    CUSTOMER          ||--o{ BANK_ACCOUNT      : "có"
    CUSTOMER          ||--o{ CONTRACT_PARTY    : "đóng vai bên"
    CUSTOMER          ||--o{ CONTRACT          : "primary_customer_id"

    CONTRACT_TEMPLATE ||--|{ TEMPLATE_VERSION  : "có nhiều phiên bản"
    CONTRACT_TEMPLATE ||--o| TEMPLATE_VERSION  : "active_version_id"
    TEMPLATE_VERSION  ||--o{ CONTRACT          : "được dùng để sinh"
    CONTRACT          ||--|{ CONTRACT_PARTY    : "gồm N bên (v1.0: 1)"
    CONTRACT          ||--|{ CONTRACT_DOCUMENT : "có DOCX và PDF"
    CONTRACT          ||--o| CONTRACT          : "supersedes (tự tham chiếu)"
    BANK_ACCOUNT      ||--o{ CONTRACT_PARTY    : "TK của bên"

    DOCUMENT_TYPE     ||--o{ OCR_SESSION       : "phân loại giấy tờ"
    DOCUMENT_TYPE     ||--o{ CARD_IMAGE        : "loại ảnh"
    DOCUMENT_TYPE     ||--o{ NORMALIZATION_ALIAS : "phạm vi áp dụng"

    PROVINCE_CODE     }o..o| CUSTOMER          : "suy luận từ 3 số đầu CCCD"
    BANK_DIRECTORY    }o..o| BANK_ACCOUNT      : "gợi ý tên NH"
    JOB               }o..o| OCR_SESSION       : "đa hình target"
    JOB               }o..o| CONTRACT          : "đa hình target"

    CARD_IMAGE {
        uuid     id PK
        varchar  uploaded_by "tên tài khoản Windows"
        uuid     document_type_id FK
        varchar  side_hint
        varchar  side_resolved
        real     side_confidence
        bytea    sha256
        varchar  vault_path "TƯƠNG ĐỐI"
        varchar  mime_type
        int      width_px
        int      height_px
        bigint   size_bytes
        smallint exif_orientation
        real     quality_score
        jsonb    quality_flags
        varchar  thumbnail_path
        tstz     purged_at
        varchar  purge_reason
        tstz     created_at
    }

    OCR_SESSION {
        uuid     id PK
        varchar  created_by
        uuid     document_type_id FK
        uuid     front_image_id FK
        uuid     back_image_id FK
        varchar  status
        varchar  party_key "bản lề nhiều bên"
        smallint party_index
        boolean  auto_swapped
        real     overall_confidence
        varchar  engine_name
        varchar  engine_version
        varchar  preprocessing_profile
        int      duration_ms
        varchar  correlation_id
        jsonb    diagnostics
        varchar  error_code
        text     error_message
        tstz     created_at
        tstz     completed_at
    }

    OCR_RESULT {
        uuid     id PK
        uuid     ocr_session_id FK UK
        boolean  qr_available
        bytea    qr_raw_enc "MÃ HOÁ"
        boolean  mrz_available
        bytea    mrz_raw_enc "MÃ HOÁ"
        boolean  mrz_checksum_valid
        smallint mrz_corrections_applied
        bytea    raw_engine_output_enc "MÃ HOÁ"
        jsonb    channel_summary
        jsonb    validation_report
        jsonb    cross_check_flags
        tstz     created_at
    }

    OCR_FIELD {
        uuid     id PK
        uuid     ocr_result_id FK
        varchar  field_key
        bytea    raw_value_enc "MÃ HOÁ"
        bytea    normalized_value_enc "MÃ HOÁ"
        bytea    final_value_enc "MÃ HOÁ"
        varchar  source
        real     confidence
        boolean  needs_review
        boolean  user_corrected
        bytea    user_value_enc "MÃ HOÁ"
        jsonb    bbox
        jsonb    candidates
        smallint normalization_tier
    }

    JOB {
        uuid     id PK
        varchar  job_type
        varchar  status
        uuid     target_id
        varchar  target_type
        jsonb    payload
        smallint priority
        smallint attempt_count
        smallint max_attempts
        tstz     next_retry_at
        tstz     started_at
        tstz     finished_at
        tstz     heartbeat_at
        smallint progress_percent
        varchar  progress_message
        varchar  error_code
        text     error_detail
        boolean  is_retryable_error
        varchar  correlation_id
        varchar  worker_token
        tstz     created_at
    }

    CUSTOMER {
        uuid     id PK
        varchar  created_by
        uuid     ocr_session_id FK
        varchar  full_name
        varchar  full_name_search "không dấu"
        bytea    id_number_enc "MÃ HOÁ"
        bytea    id_number_bidx UK
        varchar  id_number_masked
        bytea    date_of_birth_enc "MÃ HOÁ"
        smallint birth_year
        varchar  gender
        varchar  issue_place "CHECK 2 giá trị"
        date     issue_date
        date     expiry_date
        boolean  no_expiry
        varchar  phone
        bytea    phone_bidx
        varchar  email
        bytea    email_bidx
        bytea    address_enc "MÃ HOÁ"
        varchar  securities_account_no
        bytea    securities_account_bidx UK
        date     securities_account_opened_at
        varchar  province_code
        varchar  data_quality
        text     note
        tstz     created_at
        tstz     updated_at
        tstz     deleted_at
    }

    BANK_ACCOUNT {
        uuid     id PK
        uuid     customer_id FK
        bytea    account_number_enc "MÃ HOÁ"
        bytea    account_number_bidx
        varchar  account_number_masked
        varchar  bank_code
        varchar  bank_name "bản sao"
        varchar  branch
        varchar  account_holder_name
        boolean  is_primary
        tstz     created_at
        tstz     updated_at
        tstz     deleted_at
    }

    CONTRACT_TEMPLATE {
        uuid     id PK
        varchar  code UK
        varchar  name
        text     description
        varchar  category
        uuid     active_version_id FK
        jsonb    party_schema "ĐIỀU KHIỂN WIZARD"
        smallint party_schema_version
        jsonb    contract_fields
        jsonb    suppressed_variables
        varchar  contract_no_pattern
        int      contract_no_seq
        varchar  export_name_pattern
        boolean  requires_images
        boolean  is_active
        smallint sort_order
        tstz     created_at
        tstz     updated_at
        tstz     deleted_at
    }

    TEMPLATE_VERSION {
        uuid     id PK
        uuid     template_id FK
        int      version_no
        varchar  file_path
        bytea    file_sha256
        bigint   file_size_bytes
        varchar  original_filename
        jsonb    declared_variables
        jsonb    required_variables
        jsonb    optional_variables
        jsonb    unknown_variables
        jsonb    richtext_variables
        boolean  has_loops
        boolean  has_conditionals
        varchar  validation_status
        jsonb    validation_report
        text     changelog
        varchar  created_by
        tstz     created_at
        tstz     archived_at
    }

    CONTRACT {
        uuid     id PK
        varchar  contract_no UK
        varchar  export_name
        uuid     primary_customer_id FK
        uuid     template_version_id FK
        varchar  created_by
        uuid     supersedes_id FK
        smallint revision_no
        smallint party_count
        varchar  status
        bytea    render_snapshot_enc "MÃ HOÁ"
        bytea    snapshot_sha256
        jsonb    extra_variables
        date     contract_date
        varchar  void_reason
        tstz     voided_at
        varchar  voided_by
        varchar  error_code
        text     error_message
        int      version "KHOÁ LẠC QUAN"
        tstz     created_at
        tstz     updated_at
    }

    CONTRACT_PARTY {
        uuid     id PK
        uuid     contract_id FK
        varchar  party_key
        smallint party_index
        varchar  party_label "bản sao"
        varchar  entity_type "v1.0 CHECK INDIVIDUAL"
        uuid     customer_id FK
        uuid     bank_account_id FK
        uuid     ocr_session_id FK
        boolean  is_primary
        jsonb    party_extra
        smallint sort_order
        tstz     created_at
    }

    CONTRACT_DOCUMENT {
        uuid     id PK
        uuid     contract_id FK
        varchar  doc_type
        varchar  file_path
        bytea    file_sha256
        bigint   file_size_bytes
        smallint page_count
        varchar  generator
        int      generation_ms
        int      download_count
        tstz     last_downloaded_at
        tstz     created_at
    }

    DOCUMENT_TYPE {
        uuid     id PK
        varchar  code UK
        varchar  name
        jsonb    field_schema
        jsonb    zone_map
        jsonb    anchor_patterns
        boolean  has_qr
        boolean  has_mrz
        boolean  is_ocr_supported
        real     expected_aspect_ratio
        boolean  is_active
        tstz     created_at
    }

    NORMALIZATION_ALIAS {
        uuid     id PK
        uuid     document_type_id FK
        varchar  field_key
        varchar  alias_normalized "NULL khi tier 4"
        varchar  canonical_value
        smallint match_tier
        jsonb    keywords
        real     assigned_confidence
        boolean  is_active
        varchar  created_by
        tstz     created_at
    }

    PROVINCE_CODE {
        varchar  code PK
        varchar  name
        varchar  region
        boolean  is_active
    }

    BANK_DIRECTORY {
        varchar  code PK
        varchar  short_name
        varchar  full_name
        varchar  bin
        int      account_min_len
        int      account_max_len
        boolean  is_active
        smallint sort_order
    }

    ACTIVITY_LOG {
        bigint   seq PK
        varchar  actor_username "tài khoản Windows"
        varchar  action
        varchar  entity_type
        uuid     entity_id
        varchar  outcome
        jsonb    detail "ĐÃ CHE PII"
        varchar  correlation_id
        tstz     created_at
    }

    SYSTEM_SETTING {
        varchar  key PK
        jsonb    value
        varchar  value_type
        jsonb    default_value
        jsonb    constraints
        varchar  label_vi
        text     description
        varchar  scope
        boolean  is_sensitive
        boolean  requires_restart
        varchar  updated_by
        tstz     updated_at
    }

    BACKUP_RECORD {
        uuid     id PK
        varchar  created_by
        varchar  trigger_type
        varchar  file_path "TUYỆT ĐỐI - ngoại lệ"
        bytea    file_sha256
        bigint   file_size_bytes
        int      customer_count
        int      contract_count
        int      image_count
        varchar  app_version
        varchar  schema_version
        boolean  is_encrypted
        varchar  status
        int      duration_ms
        text     error_detail
        tstz     created_at
        tstz     verified_at
    }
```

---

## 4.3. Quy ước chung

### 4.3.1. Đặt tên

| Đối tượng | Quy ước | Ví dụ |
|---|---|---|
| Bảng | `snake_case`, **số ít** | `contract_document` |
| Cột | `snake_case` | `expiry_date` |
| Khoá chính | luôn `id` (trừ `activity_log` dùng `seq`, bảng tham chiếu dùng `code`) | `id` |
| Khoá ngoại | `<bảng_đích>_id` | `customer_id` |
| Chỉ mục | `ix_<bảng>__<cột>` | `ix_contract__customer_id` |
| Chỉ mục duy nhất | `uq_<bảng>__<cột>` | `uq_customer__id_number_bidx` |
| CHECK | `ck_<bảng>__<mô_tả>` | `ck_customer__issue_place_valid` |
| FK constraint | `fk_<bảng>__<bảng_đích>` | `fk_contract__template_version` |
| Cột mã hoá | hậu tố `_enc`, kiểu `BYTEA` | `id_number_enc` |
| Blind index | hậu tố `_bidx`, kiểu `BYTEA(16)` | `phone_bidx` |
| Cột hiển thị đã che | hậu tố `_masked` | `id_number_masked` |
| Enum | `VARCHAR` + `CHECK`, **không dùng native ENUM** | vì `ALTER TYPE` khó rollback trong migration |

### 4.3.2. Cột chung

| Cột | Kiểu | Áp dụng cho | Ý nghĩa |
|---|---|---|---|
| `id` | `UUID` (v7) | Mọi bảng nghiệp vụ | Khoá chính |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Mọi bảng | UTC |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | Bảng có thể sửa | Cập nhật bởi tầng ứng dụng, **không dùng trigger** |
| `created_by` | ⭐ `VARCHAR(64)` | Bảng nghiệp vụ | **Tên tài khoản Windows**, không phải FK |
| `version` | `INTEGER NOT NULL DEFAULT 1` | ⭐ **Chỉ `contract`** | Khoá lạc quan |
| `deleted_at` | `TIMESTAMPTZ NULL` | `customer`, `bank_account`, `contract_template` | Soft delete |

### 4.3.3. Danh mục Enum

| Enum | Bảng.cột | Giá trị hợp lệ |
|---|---|---|
| `CardSide` | `card_image.side_hint/side_resolved` | `FRONT`, `BACK`, `UNKNOWN` |
| `OcrSessionStatus` | `ocr_session.status` | `CREATED`, `QUEUED`, `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `NEEDS_REUPLOAD`, `NEEDS_MANUAL_ASSIGN`, `FAILED`, `CONFIRMED`, `CONSUMED`, `CANCELLED` |
| `FieldKey` | `ocr_field.field_key` | `full_name`, `id_number`, `date_of_birth`, `issue_date`, `expiry_date`, `issue_place` |
| `FieldSource` | `ocr_field.source` | `QR`, `MRZ`, `OCR`, `MANUAL`, `NONE` |
| `JobType` | `job.job_type` | `OCR`, `PDF_CONVERT`, `BACKUP`, `RETENTION_PURGE`, `ORPHAN_SWEEP`, `TEMPLATE_VALIDATE` |
| `JobStatus` | `job.status` | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED` |
| `ContractStatus` | `contract.status` | `DRAFT`, `GENERATING`, `DOCX_READY`, `PDF_CONVERTING`, `COMPLETED`, `GENERATION_FAILED`, `PDF_FAILED`, `SUPERSEDED`, `VOIDED` |
| `EntityType` | `contract_party.entity_type` | ⭐ v1.0: `INDIVIDUAL` · sau: + `ORGANIZATION` |
| `DocType` | `contract_document.doc_type` | `DOCX`, `PDF` |
| `IssuePlace` | `customer.issue_place` | `BỘ CÔNG AN`, `CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI` |
| `Gender` | `customer.gender` | `NAM`, `NỮ`, `KHÁC`, `UNKNOWN` |
| `DataQuality` | `customer.data_quality` | `OCR_VERIFIED`, `MANUAL`, `MIXED` |
| `TemplateValidationStatus` | `template_version.validation_status` | `VALID`, `WARNING`, `INVALID` |
| `Outcome` | `activity_log.outcome` | `SUCCESS`, `FAILURE` |
| `BackupStatus` | `backup_record.status` | `RUNNING`, `SUCCEEDED`, `FAILED`, `VERIFIED`, `CORRUPTED` |

---

## 4.4. Đặc tả chi tiết từng bảng

### 4.4.1. `card_image`

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | Đồng thời là tên file trong Vault |
| `uploaded_by` | VARCHAR(64) | NOT NULL | Tên tài khoản Windows |
| `document_type_id` | UUID | NOT NULL, FK `document_type` | v1.0 luôn là `CCCD_CHIP` |
| `side_hint` | VARCHAR(10) | NOT NULL | Gợi ý từ endpoint |
| `side_resolved` | VARCHAR(10) | NULL | Kết quả thật từ Classifier (S4) |
| `side_confidence` | REAL | NULL, CHECK 0..1 | |
| `sha256` | BYTEA(32) | NOT NULL | Hash ảnh **sau khi re-encode** |
| `vault_path` | VARCHAR(300) | NOT NULL | ⭐ **Đường dẫn TƯƠNG ĐỐI** so với gốc Vault |
| `mime_type` | VARCHAR(50) | NOT NULL | Từ magic bytes, không từ client |
| `width_px` / `height_px` | INTEGER | NOT NULL, CHECK 320..12000 | |
| `size_bytes` | BIGINT | NOT NULL, CHECK ≤ 10485760 | |
| `exif_orientation` | SMALLINT | NULL | Lưu trước khi xoá EXIF (cần cho S3.1) |
| `quality_score` | REAL | NULL, CHECK 0..1 | |
| `quality_flags` | JSONB | NULL | `["TOO_DARK","BLURRY","GLARE_DETECTED"]` |
| `thumbnail_path` | VARCHAR(300) | NULL | Thumbnail 240px |
| `purged_at` | TIMESTAMPTZ | NULL | NULL = ảnh gốc còn trên đĩa |
| `purge_reason` | VARCHAR(50) | NULL | `RETENTION_POLICY`, `USER_REQUEST`, `CONTRACT_COMPLETED` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

---

### 4.4.2. `ocr_session`

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `created_by` | VARCHAR(64) | NOT NULL | |
| `document_type_id` | UUID | NOT NULL, FK | ⭐ Chìa khoá mở rộng sang GPLX/Hộ chiếu |
| `front_image_id` / `back_image_id` | UUID | NOT NULL, FK `card_image` | Sau S4 là ảnh **thực sự** đúng mặt |
| `status` | VARCHAR(30) | NOT NULL, CHECK ∈ `OcrSessionStatus` | |
| `party_key` | VARCHAR(40) | NULL | ⭐ Bản lề nhiều bên. v1.0 luôn `"holder"` |
| `party_index` | SMALLINT | NULL DEFAULT 0 | ⭐ Bản lề nhiều bên |
| `auto_swapped` | BOOLEAN | NOT NULL DEFAULT FALSE | ALT-01 |
| `overall_confidence` | REAL | NULL, CHECK 0..1 | Trung bình có trọng số (S10.7) |
| `engine_name` / `engine_version` | VARCHAR(50) | NULL | Đối chiếu khi nâng cấp engine |
| `preprocessing_profile` | VARCHAR(50) | NULL | `default`, `low_light`, `high_glare` |
| `duration_ms` | INTEGER | NULL | |
| `correlation_id` | VARCHAR(40) | NOT NULL | |
| `diagnostics` | JSONB | NULL | Thời gian từng chặng, cờ kỹ thuật. **Không chứa PII** |
| `error_code` / `error_message` | VARCHAR(50) / TEXT | NULL | |
| `created_at` / `completed_at` | TIMESTAMPTZ | | |

**Ràng buộc:**
- `ck_ocr_session__different_images`: `front_image_id <> back_image_id`
- `ck_ocr_session__completed_has_time`: `status ∈ {COMPLETED, COMPLETED_WITH_WARNINGS, FAILED} → completed_at IS NOT NULL`

---

### 4.4.3. `ocr_result` (1-1 với session)

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `ocr_session_id` | UUID | NOT NULL, **UNIQUE**, FK ON DELETE CASCADE | Đảm bảo 1-1 |
| `qr_available` | BOOLEAN | NOT NULL | |
| `qr_raw_enc` | BYTEA | NULL | 🔒 Chuỗi QR gốc |
| `mrz_available` | BOOLEAN | NOT NULL | |
| `mrz_raw_enc` | BYTEA | NULL | 🔒 3 dòng MRZ gốc |
| `mrz_checksum_valid` | BOOLEAN | NULL | |
| `mrz_corrections_applied` | SMALLINT | NULL, CHECK 0..3 | Số ký tự đã sửa để checksum đúng |
| `raw_engine_output_enc` | BYTEA | NULL | 🔒 JSON nén `[(bbox,text,conf)]`. Xoá sau 180 ngày |
| `channel_summary` | JSONB | NOT NULL | `{"full_name":"QR","expiry_date":"MRZ",...}` — **chỉ nguồn, không giá trị** |
| `validation_report` | JSONB | NOT NULL | `{errors[], warnings[], infos[]}` — mã lỗi, không giá trị PII |
| `cross_check_flags` | JSONB | NULL | `["SOURCE_CONFLICT:id_number","CARD_MISMATCH"]` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

---

### 4.4.4. `ocr_field` ⭐ Bảng quan trọng nhất cho cải tiến

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `ocr_result_id` | UUID | NOT NULL, FK ON DELETE CASCADE | |
| `field_key` | VARCHAR(30) | NOT NULL, CHECK ∈ `FieldKey` | |
| `raw_value_enc` | BYTEA | NULL | 🔒 Giá trị thô trước chuẩn hoá |
| `normalized_value_enc` | BYTEA | NULL | 🔒 Sau S9 |
| `final_value_enc` | BYTEA | NULL | 🔒 Sau S10 (fusion) |
| `source` | VARCHAR(10) | NOT NULL, CHECK ∈ `FieldSource` | Nguồn thắng cuộc |
| `confidence` | REAL | NOT NULL, CHECK 0..1 | |
| `needs_review` | BOOLEAN | NOT NULL | |
| `user_corrected` | BOOLEAN | NOT NULL DEFAULT FALSE | ⭐ Người dùng có sửa không |
| `user_value_enc` | BYTEA | NULL | 🔒 Giá trị người dùng chấp nhận |
| `bbox` | JSONB | NULL | `{"x":0.38,"y":0.28,"w":0.57,"h":0.10}` → UI vẽ khung highlight |
| `candidates` | JSONB | NULL | `[{"source":"QR","confidence":1.0,"agrees":true}]` — **chỉ nguồn và điểm** |
| `normalization_tier` | SMALLINT | NULL, CHECK 1..4 | Tầng nào của bộ chuẩn hoá khớp (cho `issue_place`) |

**Ràng buộc:** `uq_ocr_field__result_key` UNIQUE `(ocr_result_id, field_key)`.

> ⭐ Truy vấn `WHERE user_corrected = TRUE GROUP BY field_key, source` cho ra **báo cáo độ chính xác thực tế** trên chính dữ liệu khách hàng — nền tảng cải tiến ở Chương 19, không cần gửi dữ liệu đi đâu.

---

### 4.4.5. `job` ⭐ Là hàng đợi duy nhất

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `job_type` | VARCHAR(30) | NOT NULL, CHECK ∈ `JobType` | |
| `status` | VARCHAR(15) | NOT NULL, CHECK ∈ `JobStatus` | |
| `target_id` | UUID | NULL | ID thực thể liên quan (đa hình — **không FK cứng**) |
| `target_type` | VARCHAR(30) | NULL | `ocr_session`, `contract` |
| `payload` | JSONB | NULL | Tham số job. **Không chứa PII**, chỉ ID |
| `priority` | SMALLINT | NOT NULL DEFAULT 100 | Số nhỏ = ưu tiên cao |
| `attempt_count` / `max_attempts` | SMALLINT | NOT NULL / DEFAULT 3 | |
| `next_retry_at` | TIMESTAMPTZ | NULL | Backoff 5s → 25s → 125s |
| `started_at` / `finished_at` | TIMESTAMPTZ | NULL | |
| `heartbeat_at` | TIMESTAMPTZ | NULL | ⭐ Worker cập nhật mỗi 10s → phát hiện job chết |
| `progress_percent` | SMALLINT | NULL, CHECK 0..100 | |
| `progress_message` | VARCHAR(150) | NULL | "Đang đọc vùng MRZ mặt sau…" |
| `error_code` / `error_detail` | VARCHAR(50) / TEXT | NULL | |
| `is_retryable_error` | BOOLEAN | NULL | Phân biệt lỗi tạm thời vs vĩnh viễn |
| `correlation_id` | VARCHAR(40) | NOT NULL | |
| `worker_token` | VARCHAR(40) | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Chỉ mục quan trọng:** `ix_job__dispatch` trên `(priority, created_at)` WHERE `status = 'QUEUED'`.

**Phục hồi sau crash:** lúc khởi động, tìm `status='RUNNING' AND heartbeat_at < now() - interval '5 minutes'` → `FAILED` với `STALE_JOB_RECOVERED`.

> ⭐ **`JobRunner` polling bảng này mỗi 500 ms bằng `SELECT … FOR UPDATE SKIP LOCKED LIMIT 1`. Không có `asyncio.Queue`. Một nguồn chân lý duy nhất.**

---

### 4.4.6. `customer`

| Cột | Kiểu | Ràng buộc | 🔒 | Mô tả |
|---|---|---|:---:|---|
| `id` | UUID | PK | | |
| `created_by` | VARCHAR(64) | NOT NULL | | Tài khoản Windows |
| `ocr_session_id` | UUID | NULL, FK | | NULL nếu nhập tay hoàn toàn |
| `full_name` | VARCHAR(150) | NOT NULL | | UPPERCASE, Unicode NFC |
| `full_name_search` | VARCHAR(150) | NOT NULL | | Bản không dấu, UPPERCASE — cho `pg_trgm` |
| `id_number_enc` | BYTEA | NOT NULL | 🔒 | Số CCCD 12 số |
| `id_number_bidx` | BYTEA(16) | NOT NULL, **UNIQUE** WHERE `deleted_at IS NULL` | | Chống trùng + tra cứu |
| `id_number_masked` | VARCHAR(20) | NOT NULL | | `••••••••2345` — cho log và bảng danh sách |
| `date_of_birth_enc` | BYTEA | NOT NULL | 🔒 | |
| `birth_year` | SMALLINT | NULL, CHECK 1900..now | | ⭐ Chỉ **năm** — lọc/thống kê không cần giải mã |
| `gender` | VARCHAR(10) | NULL, CHECK ∈ `Gender` | | |
| `issue_place` | VARCHAR(80) | NOT NULL, ⭐ **CHECK ∈ 2 giá trị chuẩn** | | Tầng phòng thủ thứ 3 |
| `issue_date` | DATE | NOT NULL | | |
| `expiry_date` | DATE | NULL | | NULL khi `no_expiry = TRUE` |
| `no_expiry` | BOOLEAN | NOT NULL DEFAULT FALSE | | "KHÔNG THỜI HẠN" (G-03) |
| `phone` | VARCHAR(15) | NOT NULL | | Chuẩn `0xxxxxxxxx` |
| `phone_bidx` | BYTEA(16) | NOT NULL | | |
| `email` | VARCHAR(254) | NOT NULL | | LOWERCASE |
| `email_bidx` | BYTEA(16) | NOT NULL | | |
| `address_enc` | BYTEA | NOT NULL | 🔒 | |
| `securities_account_no` | VARCHAR(20) | NULL | | ⭐ `008C123456` |
| `securities_account_bidx` | BYTEA(16) | NULL, **UNIQUE** WHERE `deleted_at IS NULL` | | Chống trùng STK CK |
| `securities_account_opened_at` | DATE | NULL | | |
| `province_code` | VARCHAR(3) | NULL, FK **mềm** | | Suy luận từ 3 số đầu CCCD |
| `data_quality` | VARCHAR(20) | NOT NULL, CHECK ∈ `DataQuality` | | |
| `note` | TEXT | NULL | | |
| `created_at` / `updated_at` / `deleted_at` | TIMESTAMPTZ | | | |

**Ràng buộc:**

| Tên | Nội dung |
|---|---|
| `ck_customer__issue_place_valid` | `issue_place IN ('BỘ CÔNG AN', 'CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI')` |
| `ck_customer__expiry_logic` | `(no_expiry AND expiry_date IS NULL) OR (NOT no_expiry AND expiry_date IS NOT NULL)` |
| `ck_customer__date_order` | `expiry_date IS NULL OR issue_date <= expiry_date` |
| `uq_customer__id_number` | UNIQUE `(id_number_bidx)` WHERE `deleted_at IS NULL` |
| `uq_customer__securities_account` | UNIQUE `(securities_account_bidx)` WHERE `deleted_at IS NULL AND securities_account_bidx IS NOT NULL` |

> **Không có cột `version`** — không có tranh chấp (single-instance mutex, không có job nền sửa customer).

---

### 4.4.7. `bank_account`

| Cột | Kiểu | Ràng buộc | 🔒 |
|---|---|---|:---:|
| `id` | UUID | PK | |
| `customer_id` | UUID | NOT NULL, FK ON DELETE CASCADE | |
| `account_number_enc` | BYTEA | NOT NULL | 🔒 |
| `account_number_bidx` | BYTEA(16) | NOT NULL | |
| `account_number_masked` | VARCHAR(25) | NOT NULL | |
| `bank_code` | VARCHAR(10) | NULL, FK **mềm** → `bank_directory` | |
| `bank_name` | VARCHAR(150) | NOT NULL | ⭐ **Bản sao** tên NH tại thời điểm nhập |
| `branch` | VARCHAR(150) | NOT NULL | |
| `account_holder_name` | VARCHAR(150) | NULL | Mặc định = `customer.full_name` |
| `is_primary` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` / `updated_at` / `deleted_at` | TIMESTAMPTZ | | |

**Ràng buộc:**
- `uq_bank_account__one_primary`: UNIQUE `(customer_id)` WHERE `is_primary AND deleted_at IS NULL`
- `uq_bank_account__no_dup`: UNIQUE `(customer_id, account_number_bidx)` WHERE `deleted_at IS NULL`

> **Vì sao lưu `bank_name` dạng bản sao:** ngân hàng đổi tên, nhưng hợp đồng đã in phải giữ tên tại thời điểm ký.

---

### 4.4.8. `contract_template`

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `code` | VARCHAR(50) | NOT NULL, UNIQUE | `01A_HD_GDN`, `01A_GDKQ` |
| `name` | VARCHAR(200) | NOT NULL | "Mẫu số 01A/HĐ-GĐN" |
| `description` | TEXT | NULL | |
| `category` | VARCHAR(50) | NULL | Nhóm hiển thị trên UI |
| `active_version_id` | UUID | NULL, FK `template_version` | ⭐ Phiên bản đang dùng |
| ⭐ `party_schema` | JSONB | NOT NULL | **Điều khiển wizard** — xem §4.5 |
| `party_schema_version` | SMALLINT | NOT NULL DEFAULT 1 | Phiên bản cấu trúc khai báo |
| `contract_fields` | JSONB | NOT NULL DEFAULT `[]` | Trường cấp hợp đồng. ⭐ Rỗng → wizard **bỏ qua** bước này |
| ⭐ `suppressed_variables` | JSONB | NOT NULL DEFAULT `[]` | Biến render thành chuỗi rỗng (L-05) |
| `contract_no_pattern` | VARCHAR(100) | NOT NULL | `01A-GDN-{yyyy}{MM}-{seq:05d}` |
| `contract_no_seq` | INTEGER | NOT NULL DEFAULT 0 | Bộ đếm riêng mỗi template. Tăng bằng `SELECT … FOR UPDATE` |
| ⭐ `export_name_pattern` | VARCHAR(200) | NOT NULL | `Mẫu 01A - {full_name}` |
| `requires_images` | BOOLEAN | NOT NULL DEFAULT FALSE | v1.0 luôn `FALSE` |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `sort_order` | SMALLINT | NOT NULL DEFAULT 100 | |
| `created_at` / `updated_at` / `deleted_at` | TIMESTAMPTZ | | |

---

### 4.4.9. `template_version`

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `template_id` | UUID | NOT NULL, FK | |
| `version_no` | INTEGER | NOT NULL | Tăng dần từ 1 |
| `file_path` | VARCHAR(300) | NOT NULL | **Tương đối** trong Template Store |
| `file_sha256` | BYTEA(32) | NOT NULL | ⭐ Kiểm mỗi lần dùng (ADR-10) |
| `file_size_bytes` | BIGINT | NOT NULL, CHECK ≤ 20971520 | |
| `original_filename` | VARCHAR(255) | NOT NULL | Chỉ hiển thị, **không dùng làm đường dẫn** |
| `declared_variables` | JSONB | NOT NULL | Toàn bộ biến quét được từ AST |
| `required_variables` | JSONB | NOT NULL | |
| `optional_variables` | JSONB | NOT NULL | |
| `unknown_variables` | JSONB | NOT NULL | Không có trong từ điển → cảnh báo |
| ⭐ `richtext_variables` | JSONB | NOT NULL | Biến viết dạng `{{r var }}` |
| `has_loops` / `has_conditionals` | BOOLEAN | NOT NULL | |
| `validation_status` | VARCHAR(15) | NOT NULL, CHECK ∈ `TemplateValidationStatus` | |
| `validation_report` | JSONB | NOT NULL | |
| `changelog` | TEXT | NULL | Bắt buộc ≥ 10 ký tự khi tải bản mới |
| `created_by` | VARCHAR(64) | NOT NULL | |
| `created_at` / `archived_at` | TIMESTAMPTZ | | ⭐ Không bao giờ DELETE |

**Ràng buộc:** `uq_template_version__no` UNIQUE `(template_id, version_no)`.

---

### 4.4.10. `contract`

| Cột | Kiểu | Ràng buộc | 🔒 | Mô tả |
|---|---|---|:---:|---|
| `id` | UUID | PK | | |
| `contract_no` | VARCHAR(60) | NOT NULL, **UNIQUE** | | ⭐ Số nội bộ: `01A-GDN-202608-00042` |
| ⭐ `export_name` | VARCHAR(220) | NOT NULL | | Tên file xuất: `Mẫu 01A - NGUYỄN VĂN A` — **có thể trùng** |
| `primary_customer_id` | UUID | NOT NULL, FK, ON DELETE **RESTRICT** | | Bản sao bên chính cho truy vấn danh sách |
| `template_version_id` | UUID | NOT NULL, FK, ON DELETE **RESTRICT** | | ⭐ Trỏ **phiên bản**, không phải template |
| `created_by` | VARCHAR(64) | NOT NULL | | |
| `supersedes_id` | UUID | NULL, FK `contract` | | Bản bị thay thế |
| `revision_no` | SMALLINT | NOT NULL DEFAULT 1 | | |
| `party_count` | SMALLINT | NOT NULL DEFAULT 1 | | v1.0 luôn 1 |
| `status` | VARCHAR(25) | NOT NULL, CHECK ∈ `ContractStatus` | | |
| `render_snapshot_enc` | BYTEA | NOT NULL | 🔒 | ⭐ Toàn bộ context đã bơm vào template |
| `snapshot_sha256` | BYTEA(32) | NOT NULL | | Chứng minh snapshot không bị sửa |
| `extra_variables` | JSONB | NULL | | Giá trị `contract_fields` (cũng có trong snapshot) |
| `contract_date` | DATE | ⭐ NOT NULL DEFAULT (ngày tạo) | | Lọc/thống kê nội bộ. **Không render** (nằm trong `suppressed_variables`) |
| `void_reason` | VARCHAR(300) | NULL | | ≥ 10 ký tự khi huỷ |
| `voided_at` / `voided_by` | TIMESTAMPTZ / VARCHAR(64) | NULL | | |
| `error_code` / `error_message` | VARCHAR(50) / TEXT | NULL | | |
| ⭐ `version` | INTEGER | NOT NULL DEFAULT 1 | | **Bảng DUY NHẤT có khoá lạc quan** |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | | |

**Ràng buộc:**
- `ck_contract__void_has_reason`: `status <> 'VOIDED' OR (void_reason IS NOT NULL AND voided_at IS NOT NULL)`
- `ck_contract__no_self_supersede`: `supersedes_id IS NULL OR supersedes_id <> id`
- **Bất biến cưỡng chế ở Application (DB-03):** khi `status = 'COMPLETED'`, chỉ được UPDATE `status`, `void_reason`, `voided_at`, `voided_by`, `updated_at`, `version`.

---

### 4.4.11. `contract_party` ⭐ Bảng bản lề

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `contract_id` | UUID | NOT NULL, FK ON DELETE CASCADE | |
| `party_key` | VARCHAR(40) | NOT NULL | v1.0: `"holder"` |
| `party_index` | SMALLINT | NOT NULL DEFAULT 0 | |
| `party_label` | VARCHAR(100) | NOT NULL | **Bản sao** nhãn tại thời điểm tạo |
| `entity_type` | VARCHAR(15) | NOT NULL, ⭐ **v1.0: CHECK IN ('INDIVIDUAL')** | Nới ra sau bằng migration một dòng |
| `customer_id` | UUID | NOT NULL, FK `customer` | v1.0 luôn NOT NULL |
| `bank_account_id` | UUID | NULL, FK | TK NH của bên này (nếu mẫu yêu cầu) |
| `ocr_session_id` | UUID | NULL, FK | Phiên OCR đã dùng cho bên này |
| `is_primary` | BOOLEAN | NOT NULL DEFAULT FALSE | |
| `party_extra` | JSONB | NULL | Trường riêng: `{"securities_account_no":"008C123456"}` |
| `sort_order` | SMALLINT | NOT NULL | Thứ tự hiển thị/render |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Ràng buộc:**
- `uq_contract_party__slot`: UNIQUE `(contract_id, party_key, party_index)`
- `uq_contract_party__one_primary`: UNIQUE `(contract_id)` WHERE `is_primary`

> ⭐ **Vì sao giữ bảng này ở v1.0 dù chỉ có 1 dòng mỗi hợp đồng (ADR-16):** rẻ bây giờ (1 bảng, ~10 dòng repository), đắt về sau (nếu không có, thêm bên thứ hai phải di trú toàn bộ hợp đồng cũ **và** sửa mọi truy vấn).
>
> **Mở rộng sau này:** `ALTER TABLE ADD COLUMN organization_id UUID NULL` + nới `CHECK` thêm `'ORGANIZATION'` + thêm ràng buộc XOR giữa `customer_id`/`organization_id`.

---

### 4.4.12. `contract_document`

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | UUID | PK | |
| `contract_id` | UUID | NOT NULL, FK ON DELETE CASCADE | |
| `doc_type` | VARCHAR(10) | NOT NULL, CHECK ∈ {DOCX, PDF} | |
| `file_path` | VARCHAR(300) | NOT NULL | Tương đối trong Vault |
| `file_sha256` | BYTEA(32) | NOT NULL | ⭐ Kiểm **mỗi lần tải xuống** |
| `file_size_bytes` | BIGINT | NOT NULL | |
| `page_count` | SMALLINT | NULL | Chỉ PDF |
| `generator` | VARCHAR(60) | NOT NULL | `docxtpl 0.18.0` / `LibreOffice 7.6.4` |
| `generation_ms` | INTEGER | NOT NULL | |
| `download_count` | INTEGER | NOT NULL DEFAULT 0 | |
| `last_downloaded_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Ràng buộc:** `uq_contract_document__type` UNIQUE `(contract_id, doc_type)`.

---

### 4.4.13. `document_type`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | UUID PK | |
| `code` | VARCHAR(30) UNIQUE | ⭐ v1.0: **`CCCD_CHIP` và `CAN_CUOC_2024`** — hai thế hệ thẻ đang lưu hành, khác nhau ở vị trí QR và ngày hết hạn ([`07 §7.4.7`](07-module-ocr.md#747-hai-thế-hệ-thẻ)). Sau: `GPLX`, `PASSPORT`, `GCN_DKDN` |
| `name` | VARCHAR(100) | "Căn cước công dân gắn chip" |
| `field_schema` | JSONB | `[{"key":"full_name","type":"text","required":true,"label":"Họ và tên"}]` |
| ⭐ `zone_map` | JSONB | Toạ độ tương đối từng trường trên khung chuẩn (S8) — **hiệu chỉnh được qua UI** |
| `anchor_patterns` | JSONB | Mẫu anchor text cho từng mặt |
| `has_qr` / `has_mrz` | BOOLEAN | Bật/tắt kênh trích xuất |
| `is_ocr_supported` | BOOLEAN | `GCN_DKDN` sẽ có `FALSE` (chỉ đính kèm) |
| `expected_aspect_ratio` | REAL | 85.6/54 ≈ 1.585 cho thẻ ID-1 |
| `is_active` | BOOLEAN | |
| `created_at` | TIMESTAMPTZ | |

> ⭐ **Bảng làm cho NFR-10 khả thi.** Thêm hỗ trợ GPLX = thêm một bản ghi (khai báo trường, vùng, anchor). Module OCR core **không đổi**.

---

### 4.4.14. `normalization_alias`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | UUID PK | |
| `document_type_id` | UUID FK | |
| `field_key` | VARCHAR(30) | Chủ yếu `issue_place`, dùng được cho mọi trường |
| `alias_normalized` | VARCHAR(200) ⭐ **NULL khi `match_tier = 4`** | Chuỗi bỏ dấu + UPPERCASE + thu gọn khoảng trắng |
| `canonical_value` | VARCHAR(200) NOT NULL | Giá trị chuẩn đầu ra |
| `match_tier` | SMALLINT NOT NULL, CHECK 1..4 | 1=exact, 2=alias, 3=fuzzy, 4=keyword |
| `keywords` | JSONB NULL | Dùng cho tier 4: `["CUC","CANH","SAT"]` |
| `assigned_confidence` | REAL NOT NULL | |
| `is_active` | BOOLEAN | |
| `created_by` | VARCHAR(64) NULL | NULL nếu là dữ liệu seed |
| `created_at` | TIMESTAMPTZ | |

**Ràng buộc:**
- `uq_normalization_alias`: UNIQUE `(document_type_id, field_key, alias_normalized)` WHERE `alias_normalized IS NOT NULL`
- `ck_normalization_alias__tier4`: `(match_tier = 4 AND keywords IS NOT NULL) OR (match_tier < 4 AND alias_normalized IS NOT NULL)`

**Dữ liệu seed (16 bản ghi cho `issue_place`):**

| alias_normalized / keywords | canonical_value | tier | conf |
|---|---|:---:|---|
| `BO CONG AN` | BỘ CÔNG AN | 1 | 1.00 |
| `BCA` | BỘ CÔNG AN | 2 | 0.95 |
| `B CONG AN` | BỘ CÔNG AN | 2 | 0.90 |
| `BO CONGAN` | BỘ CÔNG AN | 2 | 0.90 |
| `MINISTRY OF PUBLIC SECURITY` | BỘ CÔNG AN | 2 | 0.95 |
| `CUC CANH SAT QUAN LY HANH CHINH VE TRAT TU XA HOI` | CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI | 1 | 1.00 |
| `CUC CS QLHC VE TTXH` | CỤC CẢNH SÁT QLHC VỀ TTXH | 2 | 0.95 |
| `CUC CSQLHC VE TTXH` | ↑ | 2 | 0.95 |
| `CUC CANH SAT QLHC VE TTXH` | ↑ | 2 | 0.95 |
| `CUC CANH SAT QL HANH CHINH VE TRAT TU XA HOI` | ↑ | 2 | 0.95 |
| `C06` / `CUC C06` | ↑ | 2 | 0.90 |
| *(keywords)* `["CUC","CANH","SAT"]` | ↑ | 4 | 0.60 |
| *(keywords)* `["QLHC"]` / `["TTXH"]` | ↑ | 4 | 0.60 |
| *(keywords)* `["BO","CONG","AN"]` | BỘ CÔNG AN | 4 | 0.60 |

> ⭐ **Admin thêm alias mới qua UI khi gặp cách viết lạ — không cần cập nhật phần mềm.** Đây là cơ chế "tự học" đơn giản nhưng cực kỳ hiệu quả trong thực tế.

---

### 4.4.15. `province_code` & `bank_directory`

**`province_code`** (63 bản ghi seed): `code` (PK, 3 chữ số: `001`=Hà Nội, `079`=TP.HCM), `name`, `region`, `is_active`.
→ Dùng ở S10.6 đối chiếu 3 số đầu CCCD.

**`bank_directory`** (~50 bản ghi seed): `code` (PK: `VCB`, `TCB`, `MB`…), `short_name`, `full_name`, `bin` (6 số NAPAS), `account_min_len`, `account_max_len`, `is_active`, `sort_order`.

| Ngân hàng | Độ dài STK |
|---|---|
| Vietcombank (VCB) | 13 |
| Techcombank (TCB) | 14 |
| BIDV | 14 |
| VietinBank (CTG) | 12 |
| MB Bank (MB) | 10–13 |
| ACB | 6–9 hoặc 16 |
| Sacombank (STB) | 12–16 |
| VPBank | 9–15 |
| Agribank | 13 |
| TPBank | 8–15 |

---

### 4.4.16. `activity_log`

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `seq` | BIGSERIAL | **PK** | ⭐ Thứ tự tuyệt đối, đồng thời là định danh công khai |
| `actor_username` | VARCHAR(64) | NOT NULL | Tên tài khoản Windows. `"(system)"` cho job tự động |
| `action` | VARCHAR(60) | NOT NULL | 20 hành động — xem dưới |
| `entity_type` | VARCHAR(40) | NULL | `customer`, `contract`, `template`… |
| `entity_id` | UUID | NULL | |
| `outcome` | VARCHAR(10) | NOT NULL, CHECK ∈ {SUCCESS, FAILURE} | |
| `detail` | JSONB | NULL | ⭐ **Đã che PII** — chỉ mã, ID, tên trường thay đổi |
| `correlation_id` | VARCHAR(40) | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Cưỡng chế bất biến (DB-08):** vai trò CSDL của ứng dụng chỉ có `SELECT, INSERT` trên bảng này. Không `UPDATE`, không `DELETE`.

**Danh mục 20 hành động:**

| Nhóm | Hành động |
|---|---|
| Ingestion | `IMAGE_UPLOADED` · `IMAGE_REJECTED` · `IMAGE_PURGED` |
| OCR | `OCR_SESSION_CREATED` · `OCR_COMPLETED` · `OCR_FAILED` · `OCR_FIELD_CORRECTED` · `OCR_SIDES_REASSIGNED` |
| Customer | `CUSTOMER_CREATED` · `CUSTOMER_UPDATED` · `CUSTOMER_DELETED` · `CUSTOMER_DUPLICATE_DETECTED` |
| Contract | `CONTRACT_GENERATED` · `CONTRACT_REGENERATED` · `CONTRACT_VOIDED` · `DOCUMENT_DOWNLOADED` |
| Template | `TEMPLATE_REGISTERED` · `TEMPLATE_VERSION_ACTIVATED` · `TEMPLATE_DEACTIVATED` |
| System | `SETTING_CHANGED` · `BACKUP_CREATED` · `BACKUP_RESTORED` · `RETENTION_PURGE_RUN` · `DATA_EXPORTED` |

**Chính sách lưu trữ:** giữ tối thiểu **5 năm** (`retention.activity_log_years`). Sau đó xuất bằng `GET /activity-logs/export` rồi xoá thủ công. Màn hình Chẩn đoán cảnh báo khi bảng > 2 GB.

---

### 4.4.17. `system_setting`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `key` | VARCHAR(100) PK | `ocr.review_threshold` |
| `value` | JSONB | Giá trị (bọc JSON để giữ kiểu) |
| `value_type` | VARCHAR(20) | `int`, `float`, `bool`, `string`, `enum`, `json` |
| `default_value` | JSONB | Cho nút "Khôi phục mặc định" |
| `constraints` | JSONB | `{"min":0.0,"max":1.0}` — UI tự sinh ô nhập phù hợp |
| `label_vi` | VARCHAR(150) | Nhãn tiếng Việt trên UI |
| `description` | TEXT | Giải thích cho người dùng cuối |
| `scope` | VARCHAR(20) | `SYSTEM`, `OCR`, `RETENTION`, `UI`, `DOCUMENT`, `BACKUP` |
| `is_sensitive` | BOOLEAN | Che giá trị trên UI và trong gói chẩn đoán |
| `requires_restart` | BOOLEAN | UI nhắc "Cần khởi động lại" |
| `updated_by` | VARCHAR(64) | |
| `updated_at` | TIMESTAMPTZ | |

**Cấu hình seed quan trọng:**

| key | default | scope |
|---|---|---|
| `ocr.review_threshold` | `0.85` | OCR |
| `ocr.engine` | `"paddle"` | OCR |
| `ocr.enable_qr_channel` / `enable_mrz_channel` | `true` | OCR |
| `ocr.cpu_threads` | `2` | OCR |
| `preproc.target_long_edge` | `1600` | OCR |
| `preproc.perspective_enabled` | `true` | OCR |
| `preproc.denoise_method` | `"bilateral"` | OCR |
| `preproc.deglare_enabled` | `false` | OCR |
| `retention.image_policy` | `"DELETE_AFTER_CONTRACT"` | RETENTION |
| `retention.image_keep_days` | `30` | RETENTION |
| `retention.ocr_raw_keep_days` | `180` | RETENTION |
| `retention.log_keep_days` | `30` | RETENTION |
| `retention.activity_log_years` | `5` | RETENTION |
| `upload.max_size_mb` | `10` | SYSTEM |
| `validation.securities_account.member_code` | `"008"` | SYSTEM |
| `validation.securities_account.strict` | `true` | SYSTEM |
| `backup.auto_enabled` | `true` | BACKUP |
| `backup.auto_time` | `"18:00"` | BACKUP |
| `backup.keep_count` | `14` | BACKUP |
| `backup.warn_after_days` | `7` | BACKUP |
| `backup.encrypt` | `true` | BACKUP |
| `document.pdf_converter` | `"libreoffice"` | DOCUMENT |
| `document.libreoffice_timeout_sec` | `60` | DOCUMENT |
| `document.libreoffice_idle_shutdown_min` | `20` | DOCUMENT |
| `export.strip_diacritics` | `false` | DOCUMENT |
| `ui.date_format` | `"dd/MM/yyyy"` | UI |
| `ui.theme` | `"system"` | UI |

---

### 4.4.18. `backup_record`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | UUID PK | |
| `created_by` | VARCHAR(64) NULL | NULL khi tự động theo lịch |
| `trigger_type` | VARCHAR(15) | `MANUAL`, `SCHEDULED`, `PRE_RESTORE`, `PRE_UPGRADE` |
| `file_path` | VARCHAR(400) | ⭐ **Đường dẫn tuyệt đối** — ngoại lệ có kiểm soát (người dùng chọn qua hộp thoại native) |
| `file_sha256` | BYTEA(32) | |
| `file_size_bytes` | BIGINT | |
| `customer_count` / `contract_count` / `image_count` | INTEGER | Hiển thị để chọn đúng bản khôi phục |
| `app_version` / `schema_version` | VARCHAR(30) | ⭐ Chặn khôi phục backup có schema mới hơn app |
| `is_encrypted` | BOOLEAN | |
| `status` | VARCHAR(15) | CHECK ∈ `BackupStatus` |
| `duration_ms` | INTEGER | |
| `error_detail` | TEXT | |
| `created_at` / `verified_at` | TIMESTAMPTZ | |

---

## 4.5. Cấu trúc `party_schema` (JSONB)

### Ngữ pháp đầy đủ

```
party_schema: [
  {
    "key":          string          # holder | co_holder | company | representative
    "label":        string          # "Khách hàng"
    "entity_type":  INDIVIDUAL | ORGANIZATION | ANY    # v1.0 chỉ chấp nhận INDIVIDUAL
    "required":     boolean
    "min":          int (mặc định 1)                    # v1.0 phải = 1
    "max":          int (mặc định 1)                    # v1.0 phải = 1
    "is_primary":   boolean
    "documents": [
      { "doc_type_code": string, "required": boolean, "sides": ["FRONT","BACK"] }
    ]
    "collect":      [ "contact" | "bank_account" | "org_profile" ]
    "extra_fields": [
      {
        "key": string, "label": string,
        "type": "text"|"number"|"date"|"select"|"securities_account",
        "required": boolean,
        "options": [...],                # cho type=select
        "prefill_from": "customer.<field>",   # tự điền từ hồ sơ khách hàng
        "persist_to":   "customer.<field>",   # ghi ngược về hồ sơ sau khi tạo HĐ
        "render_style": { "bold": bool, "italic": bool, ... }
      }
    ]
  }
]
```

### Giới hạn v1.0 (nới ra sau bằng migration một dòng)

| Chỗ | Ràng buộc v1.0 | Nới ra sau |
|---|---|---|
| `entity_type` | Chỉ `INDIVIDUAL` — trình kiểm tra template từ chối giá trị khác với thông báo *"Mẫu hợp đồng dành cho tổ chức chưa được hỗ trợ ở phiên bản này"* | Bỏ điều kiện từ chối |
| `min`/`max` | Phải `= 1` | Bỏ giới hạn |
| `collect` | Chỉ `contact`, `bank_account` | Thêm `org_profile` |

### Khai báo 2 mẫu thật

**`01A_HD_GDN`** — Mẫu số 01A/HĐ-GĐN
```
party_schema:
  [0] key: "holder" · label: "Khách hàng" · INDIVIDUAL · required · min=max=1 · is_primary
      documents: [ { CCCD_CHIP, required, sides: [FRONT, BACK] } ]
      collect:   [ "contact", "bank_account" ]        ⭐ CÓ ngân hàng
      extra_fields: []
contract_fields:        []                            ⭐ RỖNG → bỏ qua bước 3
suppressed_variables:   ["contract_date","contract_date_text","day","month","year"]
contract_no_pattern:    "01A-GDN-{yyyy}{MM}-{seq:05d}"
export_name_pattern:    "Mẫu 01A - {full_name}"
requires_images:        false
→ 3 bước wizard · 12 biến
```

**`01A_GDKQ`** — Mẫu 01A/GDKQ
```
party_schema:
  [0] key: "holder" · label: "Khách hàng" · INDIVIDUAL · required · min=max=1 · is_primary
      documents: [ { CCCD_CHIP, required, sides: [FRONT, BACK] } ]
      collect:   [ "contact" ]                        ⭐ KHÔNG có ngân hàng
      extra_fields:
        - key:  "securities_account_no"
          label: "Số tài khoản chứng khoán"
          type: "securities_account"
          required: true
          prefill_from: "customer.securities_account_no"
          persist_to:   "customer.securities_account_no"
          render_style: { "bold": true }               ⭐ IN ĐẬM
contract_fields:        []                            ⭐ RỖNG → bỏ qua bước 3
suppressed_variables:   ["contract_date","contract_date_text","day","month","year"]
contract_no_pattern:    "01A-KQ-{yyyy}{MM}-{seq:05d}"
export_name_pattern:    "01A_GDKQ - {full_name}"   ✅ Xác nhận bởi người dùng 2026-08-09
requires_images:        false
→ 3 bước wizard · 10 biến
```

---

## 4.6. Giải thích quan hệ giữa các bảng

| # | Quan hệ | Loại | Hành vi xoá | Giải thích nghiệp vụ |
|---|---|---|---|---|
| 1 | `card_image` → `ocr_session` | N : 1 (×2 FK) | RESTRICT | Một phiên trỏ tới **hai** ảnh qua hai FK riêng. Ảnh có thể dùng lại ở phiên khác (chạy lại OCR) |
| 2 | `ocr_session` → `ocr_result` | **1 : 0..1** | CASCADE | UNIQUE trên `ocr_result.ocr_session_id`. Là `0..1` vì phiên `FAILED` không có kết quả |
| 3 | `ocr_result` → `ocr_field` | **1 : 6** | CASCADE | Đúng 6 bản ghi, cưỡng chế bằng UNIQUE `(ocr_result_id, field_key)` |
| 4 | `customer` → `bank_account` | 1 : N | CASCADE | Nhiều tài khoản, đúng một `is_primary` |
| 5 | `customer` → `contract` | 1 : N | **RESTRICT** | ⭐ Không cho xoá cứng khách hàng còn hợp đồng |
| 6 | `customer` → `contract_party` | 1 : N | RESTRICT | Khách hàng đóng vai bên trong nhiều hợp đồng |
| 7 | `contract_template` → `template_version` | 1 : N | RESTRICT | Nhiều phiên bản, không xoá bản cũ |
| 8 | `contract_template` → `template_version` (qua `active_version_id`) | 1 : 0..1 | SET NULL | ⭐ **Quan hệ vòng có chủ ý** — xử lý bằng thứ tự insert (tạo version trước, update `active_version_id` sau) |
| 9 | `template_version` → `contract` | 1 : N | **RESTRICT** | ⭐ Hợp đồng trỏ **phiên bản cụ thể** — mấu chốt để tái lập hợp đồng cũ |
| 10 | `contract` → `contract_party` | **1 : N** (v1.0 luôn = 1) | CASCADE | ⭐ Bảng bản lề |
| 11 | `contract` → `contract_document` | **1 : 0..2** | CASCADE | Tối đa 1 DOCX + 1 PDF |
| 12 | `contract` → `contract` (`supersedes_id`) | tự tham chiếu 1 : 0..1 | SET NULL | ⭐ Chuỗi phiên bản. Bản cũ chuyển `SUPERSEDED` nhưng **vẫn giữ file** |
| 13 | `document_type` → `ocr_session` / `card_image` | 1 : N | RESTRICT | Điểm mở rộng loại giấy tờ |
| 14 | `document_type` → `normalization_alias` | 1 : N | CASCADE | Mỗi loại giấy tờ có từ điển riêng |
| 15 | `province_code` ⇢ `customer` | tham chiếu **mềm** | — | Không FK cứng — mã tỉnh có thể đổi theo sáp nhập hành chính; giữ giá trị lịch sử |
| 16 | `bank_directory` ⇢ `bank_account` | tham chiếu **mềm** | — | `bank_name` đã lưu bản sao |
| 17 | `job` ⇢ `ocr_session` / `contract` | đa hình (`target_type` + `target_id`) | — | ⭐ **Không FK** vì đa hình. Đổi lại tính linh hoạt; toàn vẹn kiểm ở Application + job `ORPHAN_SWEEP` |

### Ba quyết định quan hệ đáng lưu ý

**(a) Vì sao `contract` trỏ tới `template_version` chứ không phải `contract_template`?**
Nếu trỏ tới template, khi admin cập nhật mẫu (v1 → v2), mọi hợp đồng cũ sẽ "thuộc về" mẫu mới — sai về kiểm toán. Trỏ tới phiên bản cụ thể cho phép trả lời chính xác: *"Hợp đồng 01A-GDN-202608-00042 sinh từ file mẫu SHA-256 = abc…, phiên bản 3, tải lên 12/03/2026"*.

**(b) Vì sao `contract.render_snapshot_enc` trùng lặp dữ liệu với `customer`?**
Trùng lặp có chủ ý theo thời gian. Khách đổi số điện thoại tháng sau → nếu chỉ trỏ FK, in lại sẽ ra số mới, khác bản đã ký. Snapshot đảm bảo *in lại hôm nay = in lại 5 năm sau = bản gốc*. Chi phí ~3 KB/hợp đồng.

**(c) Vì sao `job` không có khoá ngoại?**
Bảng hạ tầng đa hình phục vụ nhiều loại tác vụ; một số job (backup, purge) không có thực thể đích. Đặt FK cứng sẽ buộc thêm cột riêng cho từng loại job. Đánh đổi: mất toàn vẹn tham chiếu ở tầng DB, bù bằng kiểm tra ở Application + `ORPHAN_SWEEP`.

---

## 4.7. Chiến lược chỉ mục

| Bảng | Chỉ mục | Loại | Truy vấn phục vụ |
|---|---|---|---|
| `card_image` | `uq_card_image__uploader_sha` `(uploaded_by, sha256)` WHERE `purged_at IS NULL AND created_at > now()-24h` | UNIQUE partial | Chống tải trùng |
| `card_image` | `ix_card_image__purge_scan` `(created_at)` WHERE `purged_at IS NULL` | Partial | Job dọn ảnh |
| `ocr_session` | `ix_ocr_session__user_created` `(created_by, created_at DESC)` | B-tree | Danh sách phiên gần đây |
| `ocr_session` | `ix_ocr_session__active` `(status)` WHERE `status IN ('QUEUED','PROCESSING')` | Partial | Phục hồi sau crash |
| `ocr_field` | `uq_ocr_field__result_key` `(ocr_result_id, field_key)` | UNIQUE | Tra cứu trường |
| `ocr_field` | `ix_ocr_field__corrected` `(field_key, source)` WHERE `user_corrected` | Partial | ⭐ Báo cáo độ chính xác |
| `job` | `ix_job__dispatch` `(priority, created_at)` WHERE `status='QUEUED'` | Partial | ⭐ Lấy job kế tiếp |
| `job` | `ix_job__stale` `(heartbeat_at)` WHERE `status='RUNNING'` | Partial | Phát hiện job chết |
| `job` | `ix_job__target` `(target_type, target_id)` | B-tree | Tra job của một thực thể |
| `customer` | `uq_customer__id_number` `(id_number_bidx)` WHERE `deleted_at IS NULL` | UNIQUE partial | ⭐ Chống trùng CCCD |
| `customer` | `uq_customer__securities_account` | UNIQUE partial | Chống trùng STK CK |
| `customer` | `ix_customer__phone_bidx` / `ix_customer__email_bidx` | B-tree | Tra cứu chính xác |
| `customer` | `ix_customer__name_trgm` `(full_name_search)` **GIN pg_trgm** | GIN | ⭐ Tìm gần đúng theo tên |
| `customer` | `ix_customer__created` `(created_at DESC)` WHERE `deleted_at IS NULL` | Partial | Danh sách khách hàng |
| `bank_account` | `uq_bank_account__one_primary` | UNIQUE partial | Đúng 1 TK chính |
| `contract` | `uq_contract__no` `(contract_no)` | UNIQUE | Tra theo số HĐ |
| `contract` | `ix_contract__customer` `(primary_customer_id, created_at DESC)` | B-tree | Hợp đồng của một KH |
| `contract` | `ix_contract__status_created` `(status, created_at DESC)` | B-tree | Dashboard, lọc trạng thái |
| `contract` | `ix_contract__export_name` `(export_name)` | B-tree | Phát hiện trùng tên file |
| `contract_party` | `uq_contract_party__slot` `(contract_id, party_key, party_index)` | UNIQUE | |
| `contract_party` | `ix_contract_party__customer` `(customer_id)` | B-tree | Hợp đồng mà KH tham gia |
| `contract_document` | `uq_contract_document__type` `(contract_id, doc_type)` | UNIQUE | |
| `activity_log` | `ix_activity_log__created` `(created_at DESC)` | B-tree | Xem nhật ký theo thời gian |
| `activity_log` | `ix_activity_log__entity` `(entity_type, entity_id, created_at DESC)` | B-tree | Lịch sử một thực thể |
| `activity_log` | `ix_activity_log__action` `(action, created_at DESC)` | B-tree | Lọc theo hành động |

**Extension PostgreSQL cần bật:** `pg_trgm` (tìm gần đúng tên), `pgcrypto` (hash phụ trợ).

> **Nguyên tắc:** ở quy mô một máy (< 50.000 khách hàng, < 100.000 hợp đồng sau 5 năm), **không tạo chỉ mục thừa**. Danh sách trên khớp đúng các truy vấn thật sự tồn tại trong [05-thiet-ke-api.md](05-thiet-ke-api.md).

---

## 4.8. Chiến lược mã hoá

### 4.8.1. Cây khoá

```
Windows DPAPI (phạm vi TÀI KHOẢN người dùng + optional_entropy riêng của app)
       │  bảo vệ file data/keys/master.key.dpapi
       ▼
     KEK (32 byte, chỉ tồn tại trong RAM)
       │
       ├─ HKDF(info="cocas-bidx-v1")   → PEPPER (blind index)
       ├─ HKDF(info="cocas-vault-v1")  → VAULT_KEY (file trong Vault)
       └─ dùng trực tiếp                → mã hoá ô dữ liệu PII
```

> ⭐ **Dẫn xuất bằng HKDF thay vì sinh nhiều khoá độc lập** — chỉ phải bảo vệ **một** bí mật gốc. Xoay KEK là xoay tất cả.

### 4.8.2. Định dạng ô mã hoá (`BYTEA`)

```
version(1) ‖ nonce(12) ‖ ciphertext(n) ‖ tag(16)
```

- **Thuật toán:** AES-256-GCM (có xác thực, phát hiện được sửa đổi)
- **Nonce:** 12 byte ngẫu nhiên **mỗi lần mã hoá**, không bao giờ tái sử dụng
- ⭐ **AAD:** `entity_id ‖ table_name ‖ column_name` → chống **tấn công hoán vị ô** (sao `id_number_enc` của người A dán sang người B sẽ khiến giải mã thất bại)
- **Giải mã thất bại** → `DecryptionError` → `COCAS-8004` + ghi nhật ký `DECRYPTION_FAILED`, **không trả dữ liệu rác**

### 4.8.3. Trường mã hoá vs để rõ

| 🔒 Mã hoá | 📖 Để rõ (cần cho tìm kiếm/sắp xếp) |
|---|---|
| `customer.id_number_enc` | `customer.full_name` · `full_name_search` |
| `customer.date_of_birth_enc` | `customer.phone` · `email` |
| `customer.address_enc` | `customer.securities_account_no` |
| `bank_account.account_number_enc` | `bank_account.bank_name` · `branch` |
| `contract.render_snapshot_enc` | `customer.birth_year` · `gender` · `issue_place` · `issue_date` · `expiry_date` |
| `ocr_result.qr_raw_enc` · `mrz_raw_enc` · `raw_engine_output_enc` | Mọi trường ID, trạng thái, timestamp |
| `ocr_field.*_enc` (4 cột) | |
| Toàn bộ file trong Vault | |

> **Mức bảo vệ đạt được:** kẻ tấn công có file CSDL chỉ thấy tên + SĐT + email — **không có** số CCCD, không địa chỉ, không STK, không ảnh, không hợp đồng. Thiệt hại giảm từ *"rò rỉ danh tính hoàn chỉnh"* xuống *"rò rỉ danh bạ"*.

### 4.8.4. Blind index

`bidx = HMAC-SHA256(PEPPER, field_name ‖ normalize(value))[0:16]`

> ⭐ **Sửa công thức (2026-08-09):** bản gốc không trộn `field_name` vào thông điệp HMAC. Viết test cho thấy ngay lỗ hổng: một số điện thoại `"0912345678"` và một số tài khoản ngân hàng cùng chuỗi số `"0912345678"` sẽ cho **cùng một blind index** — kẻ tấn công có quyền đọc CSDL (nhưng không có PEPPER) có thể suy ra "SĐT của người này trùng số TK của người kia" mà không cần giải mã. Trộn `field_name` vào thông điệp loại bỏ hoàn toàn khả năng đụng độ chéo cột/chéo bảng, không đổi bất biến nào khác (vẫn tất định theo từng cặp `(field, value)`, vẫn không thể đảo ngược nếu thiếu PEPPER).

| Trường | Chuẩn hoá trước khi hash |
|---|---|
| `id_number` | Chỉ giữ chữ số |
| `phone` | Chuẩn `0xxxxxxxxx` (bỏ `+84`, khoảng trắng, dấu chấm) |
| `email` | `LOWER(trim(value))` |
| `account_number` | Chỉ giữ chữ số |
| `securities_account_no` | UPPERCASE, bỏ khoảng trắng |

**Rủi ro đã cân nhắc:** blind index tất định cho phép suy ra "hai bản ghi cùng giá trị" — đúng mục đích (chống trùng). Không suy ra được giá trị gốc nếu không có PEPPER. Cắt 16 byte → xác suất đụng độ ~2⁻⁶⁴; mọi kết quả vẫn được **xác minh lại bằng giải mã** trước khi trả về.

### 4.8.5. Ba kịch bản mất khoá

| Kịch bản | Hậu quả | Khắc phục |
|---|---|---|
| File `master.key.dpapi` bị xoá | Không giải mã được gì | Khôi phục từ bản sao lưu |
| **Admin reset mật khẩu Windows** của người dùng | DPAPI mất khả năng giải bọc | Như trên. ⭐ **Đây là lý do bắt buộc phải sao lưu định kỳ** |
| Cài lại Windows / đổi máy | Như trên | Như trên |
| Quên mật khẩu backup | ❌ **Không khôi phục được** | Không có cửa hậu — thiết kế có chủ ý |

⭐ Màn hình "Thiết lập lần đầu" **bắt buộc** hiển thị cảnh báo này và yêu cầu tick xác nhận.

### 4.8.6. Mã hoá bản sao lưu

**Vấn đề:** KEK bảo vệ bằng DPAPI gắn với tài khoản Windows cụ thể → backup chỉ chứa `master.key.dpapi` sẽ **không khôi phục được trên máy khác**.

**Giải pháp:**

| Bước | Nội dung |
|---|---|
| 1 | Yêu cầu người dùng đặt **mật khẩu bảo vệ backup** (≥ 12 ký tự) — đặt **một lần**, lưu trong Windows Credential Manager cho job tự động |
| 2 | Dẫn xuất khoá backup: `Argon2id(passphrase, salt)` với `time_cost=4, memory_cost=131072` |
| 3 | KEK gốc được **bọc lại bằng khoá backup** (không dùng DPAPI) và đưa vào file |
| 4 | Toàn bộ file `.cocasbak` mã hoá AES-256-GCM bằng khoá backup |
| 5 | Khi khôi phục: nhập mật khẩu → dẫn xuất khoá → giải mã → lấy KEK → **bọc lại bằng DPAPI của máy mới** |

**Cấu trúc `.cocasbak`:**
```
COCASBAK\x01                       ← magic bytes + version
salt(16) ‖ argon2_params(12)       ← rõ, cần để dẫn xuất khoá
nonce(12)
ciphertext:
   ├── manifest.json               (app_version, schema_version, số bản ghi, thời điểm)
   ├── kek.wrapped                 ⭐ KEK bọc bằng khoá backup
   ├── database.dump               (pg_dump định dạng custom)
   ├── vault/                      (toàn bộ file đã mã hoá, giữ nguyên)
   └── templates/                  (file .docx + manifest)
tag(16)
```

---

## 4.9. Chiến lược migration (Alembic)

| Chủ đề | Quy ước |
|---|---|
| Đặt tên revision | `{yyyyMMdd}_{seq}_{mô_tả_ngắn}` — `20260811_001_initial_schema`. ⭐ **Giới hạn cứng: toàn bộ chuỗi ≤ 32 ký tự** — cột `alembic_version.version_num` do chính Alembic tạo là `VARCHAR(32)` và không có tham số công khai nào để nới (`version_table_impl()` hard-code `String(32)`; xác nhận bằng cách chạy thật trên PostgreSQL — 4/8 migration ban đầu vượt quá 32 ký tự và làm hỏng `upgrade head` giữa chừng). Giữ `mô_tả_ngắn` ≤ 18 ký tự |
| Nguyên tắc | ⭐ **Mọi migration phải có `downgrade()` chạy được.** Không chấp nhận `pass` |
| Chia nhỏ | Một migration = một thay đổi logic |
| Dữ liệu seed | Migration **riêng biệt**, tiền tố `seed_`, phải **idempotent** |
| Thay đổi phá vỡ | Mẫu **expand → migrate → contract** qua 3 phiên bản ứng dụng |
| Kiểm tra tự động | CI chạy `upgrade head` → `downgrade base` → `upgrade head`. Cả 3 phải thành công |
| Chạy lúc nào | ⭐ **Tự động lúc khởi động ứng dụng**, trước khi backend nhận request |
| An toàn | Trước migration thay đổi cấu trúc → **tự tạo backup** (`PRE_UPGRADE`). Thất bại → tự khôi phục + màn hình chẩn đoán |
| Kiểm tra tương thích | Nếu DB **mới hơn** ứng dụng → **từ chối khởi động**, hướng dẫn cài lại bản mới |

### Danh sách migration ban đầu

> ⭐ **Sửa thứ tự (2026-08-09):** bản gốc đặt `initial_schema` trước `extensions`. Nhưng `initial_schema` tạo chỉ mục GIN `ix_customer__name_trgm` dùng toán tử lớp `gin_trgm_ops` — toán tử này chỉ tồn tại **sau khi** bật extension `pg_trgm`. Chạy đúng thứ tự cũ sẽ vỡ ngay ở migration đầu tiên trên DB rỗng. Đã đảo `extensions` lên trước `initial_schema`.
>
> ⭐ **Sửa tên revision (2026-08-09):** chạy thật trên PostgreSQL phát hiện 4/8 tên revision gốc vượt quá 32 ký tự, làm `UPDATE alembic_version` lỗi `StringDataRightTruncationError` giữa `upgrade head`. Đã rút gọn phần mô tả xuống ≤ 18 ký tự cho toàn bộ 8 revision.

| # | Revision | Nội dung |
|---|---|---|
| 1 | `20260811_001_extensions` | `pg_trgm`, `pgcrypto` — phải chạy **trước** vì `initial_schema` cần `gin_trgm_ops` |
| 2 | `20260811_002_initial_schema` | 19 bảng + chỉ mục + CHECK |
| 3 | `20260811_003_seed_doctype` | 1 bản ghi `CCCD_CHIP` + zone_map + anchor_patterns |
| 4 | `20260811_004_seed_alias` | 16 alias cho `issue_place` |
| 5 | `20260811_005_seed_province` | 63 tỉnh/thành |
| 6 | `20260811_006_seed_bank` | ~50 ngân hàng + độ dài STK |
| 7 | `20260811_007_seed_setting` | ~30 khoá cấu hình mặc định |
| 8 | `20260811_008_seed_template` | 2 mẫu: `01A_HD_GDN`, `01A_GDKQ` |
| ⭐ 9 | `20260811_009_seed_doctype_2024` | 1 bản ghi `CAN_CUOC_2024` + zone_map/anchor riêng + 3 alias `BỘ CÔNG AN` |

> ⭐ **Vì sao là migration mới chứ không sửa `003`:** `003` là seed dùng `ON CONFLICT DO NOTHING`, nên sửa tại chỗ sẽ khiến mọi CSDL **đã migrate** không bao giờ nhận được thế hệ thẻ mới lẫn alias của nó. Đây là ranh giới giữa "hiệu chỉnh số liệu của một bản ghi đã có" (sửa `003` được, như tuần 3 đã làm với `zone_map`) và "thêm một bản ghi mới" (bắt buộc migration mới).

---

## 4.10. Ước tính dung lượng

| Đối tượng | Đơn vị | 1.000 HĐ | 10.000 HĐ |
|---|---|---|---|
| `customer` (+ index) | ~1.2 KB | 1.2 MB | 12 MB |
| `ocr_session` + `ocr_result` + 6 × `ocr_field` | ~12 KB | 12 MB | 120 MB |
| `contract` + `contract_party` (snapshot ~3 KB) | ~4.5 KB | 4.5 MB | 45 MB |
| `activity_log` (~25 bản ghi/HĐ × 1.5 KB) | ~38 KB | 38 MB | 380 MB |
| File DOCX | ~45 KB | 45 MB | 450 MB |
| File PDF | ~180 KB | 180 MB | 1.8 GB |
| Thumbnail (2 ảnh) | ~30 KB | 30 MB | 300 MB |
| Ảnh gốc *(nếu KHÔNG xoá)* | ~2.5 MB | 2.5 GB | 25 GB |
| **Tổng — mặc định (xoá ảnh)** | | **≈ 310 MB** | **≈ 3.1 GB** |
| **Tổng — giữ ảnh vĩnh viễn** | | **≈ 2.8 GB** | **≈ 28 GB** |

> ⭐ **Chính sách xoá ảnh (ADR-12/P-05) không chỉ là bảo mật — nó giảm dung lượng 9 lần.** Đây là lý do nó phải là mặc định, và tại sao Cài đặt phải cảnh báo rõ khi admin chọn `KEEP_FOREVER`.

---

[← 03 — Luồng dữ liệu](03-luong-du-lieu.md) · [Mục lục](README.md) · [Tiếp: 05 — API →](05-thiet-ke-api.md)
