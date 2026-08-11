# 09 — Template Engine & Sinh tài liệu

[← Mục lục](README.md)

**docxtpl (Jinja2 sandboxed) · ⭐ Đầu ra DUY NHẤT là `.docx` · Từ điển 25 biến**

> ⭐ **D2.1 — Đã gỡ bỏ hoàn toàn khâu xuất PDF và LibreOffice.** Hệ thống chỉ sinh `.docx`. Xem §9.13 để biết lý do và hệ quả.

---

# PHẦN A — TEMPLATE ENGINE

## 9.1. Vòng đời một mẫu hợp đồng

```mermaid
stateDiagram-v2
    [*] --> UPLOADED: Tải file .docx
    UPLOADED --> PARSING: Mở file, quét biến bằng AST
    PARSING --> INVALID: Cú pháp Jinja2 sai / file hỏng / SSTI
    PARSING --> ANALYZED: Quét thành công

    ANALYZED --> VALID: Mọi biến đều có trong từ điển
    ANALYZED --> WARNING: Có biến lạ / thiếu style / có placeholder ảnh

    INVALID --> [*]: Từ chối, báo lỗi kèm số dòng

    VALID --> PREVIEWED: Sinh bản xem thử với dữ liệu giả
    WARNING --> PREVIEWED

    PREVIEWED --> REGISTERED: Xác nhận đăng ký
    REGISTERED --> ACTIVE: Kích hoạt phiên bản

    ACTIVE --> SUPERSEDED: Có phiên bản mới được kích hoạt
    ACTIVE --> SUSPENDED: Tạm dừng

    SUSPENDED --> ACTIVE: Kích hoạt lại
    SUPERSEDED --> ACTIVE: Quay lại phiên bản cũ

    note right of SUPERSEDED
        KHÔNG BAO GIỜ XOÁ.
        Hợp đồng cũ trỏ tới template_version
        cụ thể và phải tái lập được.
    end note
```

---

## 9.2. Quét biến (Template Introspection)

**Cách làm:** dùng chính bộ phân tích cú pháp của Jinja2 để lấy **cây AST**, rồi thu thập các nút biến.

> ⭐ **Không dùng regex quét text.** Regex không hiểu `{% if %}`, `{% for %}`, bộ lọc `|`, và sẽ bỏ sót hoặc bắt nhầm.

| # | Bước | Chi tiết |
|---|---|---|
| 1 | Kiểm tra định dạng file | Phải là ZIP hợp lệ chứa `word/document.xml` — kiểm magic bytes `PK\x03\x04`, **không tin đuôi file** |
| 2 | Trích văn bản mẫu | docxtpl gộp các `run` bị chẻ (Word hay chẻ `{{ full_name }}` thành nhiều run khi soạn thảo) |
| 3 | Phân tích cú pháp Jinja2 | Lấy AST. Lỗi → `COCAS-6003` **kèm số dòng và mô tả** |
| 4 | Thu thập biến | Duyệt AST lấy `Name`, `Getattr`, `Getitem`. Phân biệt biến gốc (`full_name`), thuộc tính (`holder.full_name`), phần tử mảng (`co_holder[0]`) |
| 5 | Phân loại | Đối chiếu từ điển biến hệ thống → `required` / `optional` / `unknown` |
| 6 | Phát hiện cấu trúc | Có `{% for %}`? `{% if %}`? `{{r ... }}` (rich text)? `{%p ... %}` (paragraph/ảnh)? |
| 7 | ⭐ Quét bảo mật | Từ chối mẫu chứa cấu trúc nguy hiểm (§9.9) |

**Kết quả lưu vào `template_version`:** `declared_variables`, `required_variables`, `optional_variables`, `unknown_variables`, `richtext_variables`, `has_loops`, `has_conditionals`, `validation_status`, `validation_report`.

---

## 9.3. Danh mục chẩn đoán khi kiểm tra mẫu

| Mã | Mức | Điều kiện | Thông điệp cho người dùng |
|---|---|---|---|
| `COCAS-6002` | 🔴 | File không phải DOCX hợp lệ | "File không đúng định dạng Word (.docx)." |
| `COCAS-6003` | 🔴 | Lỗi cú pháp Jinja2 | "Lỗi cú pháp tại dòng {n}: {chi tiết}. Kiểm tra dấu ngoặc `{{ }}` và `{% %}`." |
| `COCAS-6008` | 🟡 | Biến khai báo `render_style` nhưng viết dạng thường | ⭐ "Biến '{v}' cần in đậm. Sửa `{{ v }}` thành `{{r v }}`." |
| `COCAS-6009` | 🟡 | Biến không có trong từ điển | "Biến '{v}' không xác định — sẽ được thay bằng chuỗi rỗng. Nếu cần, khai báo ở 'Trường bổ sung'." |
| `COCAS-6010` | 🟡 | Chứa placeholder ảnh (`{%p ... %}`) | "Hệ thống không nhúng ảnh vào hợp đồng. Placeholder này sẽ bị bỏ trống." |
| `COCAS-6011` | 🟡 | Biến bắt buộc của `party_schema` không xuất hiện | "Mẫu khai báo cần '{v}' nhưng file không dùng biến này." |
| `COCAS-6012` | 🟡 | `{% for %}` trên biến không phải mảng | "Biến '{v}' không lặp được." |
| `COCAS-6014` | 🔴 | ⭐ Cấu trúc Jinja2 nguy hiểm | "Mẫu chứa cấu trúc không được phép vì lý do an toàn." |
| `COCAS-6015` | 🟡 | File > 10 MB | "File khá lớn — có thể chứa ảnh nền không cần thiết." |
| `COCAS-6016` | 🔴 | ⭐ `party_schema` dùng tính năng chưa hỗ trợ ở v1.0 | "Mẫu hợp đồng dành cho tổ chức / nhiều bên chưa được hỗ trợ ở phiên bản này." |

---

## 9.4. Phiên bản hoá

| Nguyên tắc | Chi tiết |
|---|---|
| **Không ghi đè** | Tải file mới = tạo `template_version` mới với `version_no + 1`. File cũ giữ nguyên trên đĩa |
| **Kích hoạt tường minh** | Phiên bản mới **không** tự động thành `active`. Phải xem thử rồi bấm "Kích hoạt" |
| **Quay lui được** | Bấm "Kích hoạt" trên phiên bản cũ bất kỳ → nó thành `active` ngay |
| ⭐ **Hợp đồng khoá phiên bản** | `contract.template_version_id` trỏ **phiên bản cụ thể** — cập nhật mẫu không đụng hợp đồng cũ |
| ⭐ **Toàn vẹn file** | Mỗi lần dùng, so `SHA-256` file trên đĩa với CSDL. Lệch → `COCAS-6006`, **chặn sinh hợp đồng** |
| **Nhật ký thay đổi** | `changelog` bắt buộc ≥ 10 ký tự khi tải phiên bản mới |
| **Không xoá** | Phiên bản chỉ được `archived_at`, không bao giờ DELETE |

**Bố cục lưu trữ:**
```
data/templates/
└── {template_id}/
    ├── v1/  template.docx  +  manifest.json
    ├── v2/  template.docx  +  manifest.json
    └── v3/  template.docx  +  manifest.json   ← active
```

`manifest.json` chứa bản sao metadata (sha256, biến, ngày tạo) — để phục hồi CSDL từ thư mục nếu cần.

---

## 9.5. ⭐ Từ điển biến hệ thống v1.0 (25 biến)

Đây là danh sách biến người soạn template được dùng trong `.docx`. Endpoint `GET /templates/variables` trả về bảng này.

### Biến từ CCCD (11)

| Biến | Nhãn tiếng Việt | Kiểu | Render | Ví dụ | GĐN | GDKQ |
|---|---|---|---|---|:---:|:---:|
| `{{full_name}}` | Họ và tên | text | UPPERCASE có dấu | NGUYỄN VĂN AN | ✅ | ✅ |
| `{{id_number}}` | Số CCCD | text | 12 chữ số liền | 001199012345 | ✅ | ✅ |
| `{{id_number_spaced}}` | Số CCCD (nhóm 4) | text | `0011 9901 2345` | | ⬜ | ⬜ |
| `{{dob}}` | Ngày sinh | date | `dd/MM/yyyy` | 14/05/1990 | ✅ | ✅ |
| `{{dob_text}}` | Ngày sinh (chữ) | text | `ngày 14 tháng 05 năm 1990` | | ⬜ | ⬜ |
| `{{issue_date}}` | Ngày cấp | date | `dd/MM/yyyy` | 20/08/2021 | ✅ | ✅ |
| `{{issue_date_text}}` | Ngày cấp (chữ) | text | `ngày 20 tháng 08 năm 2021` | | ⬜ | ⬜ |
| `{{expiry_date}}` | Ngày hết hạn | date | `dd/MM/yyyy` **hoặc** `KHÔNG THỜI HẠN` | 14/05/2030 | ✅ | ✅ |
| `{{issue_place}}` | Nơi cấp | enum | 1 trong 2 giá trị chuẩn | CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI | ✅ | ✅ |
| `{{issue_place_short}}` | Nơi cấp (viết tắt) | enum | `BCA` / `CỤC CS QLHC VỀ TTXH` | | ⬜ | ⬜ |
| `{{gender}}` | Giới tính | enum | Nam / Nữ | Nam | ⬜ | ⬜ |

### Biến liên hệ (3)

| Biến | Nhãn | Ví dụ | GĐN | GDKQ |
|---|---|---|:---:|:---:|
| `{{phone}}` | Số điện thoại | 0912345678 | ✅ | ✅ |
| `{{email}}` | Email | an@example.com | ✅ | ✅ |
| `{{address}}` | Địa chỉ | Số 12, ngõ 34, phố Kim Mã, phường Kim Mã, quận Ba Đình, Hà Nội | ✅ | ✅ |

### Biến ngân hàng (5)

| Biến | Nhãn | Ví dụ | GĐN | GDKQ |
|---|---|---|:---:|:---:|
| `{{bank_account}}` | Số tài khoản ngân hàng | 1234567890123 | ✅ | ❌ |
| `{{bank_name}}` | Tên ngân hàng | Ngân hàng TMCP Ngoại thương Việt Nam | ✅ | ❌ |
| `{{bank_short_name}}` | Tên NH viết tắt | Vietcombank | ⬜ | ❌ |
| `{{branch}}` | Chi nhánh | Chi nhánh Ba Đình | ✅ | ❌ |
| `{{account_holder_name}}` | Chủ tài khoản | NGUYEN VAN AN | ⬜ | ❌ |

### Biến chứng khoán (1) ⭐

| Biến | Nhãn | Kiểu | `render_style` | Cú pháp trong DOCX | GĐN | GDKQ |
|---|---|---|---|---|:---:|:---:|
| `{{securities_account_no}}` | Số tài khoản chứng khoán | securities_account | ⭐ `{bold: true}` | ⭐ **`{{r securities_account_no }}`** | ⬜ | ✅ |

### Biến hệ thống (6)

| Biến | Nhãn | Ví dụ | Ghi chú |
|---|---|---|---|
| `{{contract_no}}` | Số hợp đồng | 01A-GDN-202608-00042 | Tự sinh |
| `{{contract_date}}` | Ngày hợp đồng | *(rỗng)* | ⭐ Nằm trong `suppressed_variables` của cả 2 mẫu |
| `{{contract_date_text}}` | Ngày HĐ (chữ) | *(rỗng)* | ⭐ Bị tắt |
| `{{today}}` | Ngày hiện tại | 08/08/2026 | |
| `{{day}}` / `{{month}}` / `{{year}}` | Ngày / Tháng / Năm | *(rỗng)* | ⭐ Bị tắt |
| `{{created_by_name}}` | Người lập | nvnghiep | Tài khoản Windows |

**Chú giải:** ✅ mẫu dùng · ⬜ có sẵn nhưng mẫu chưa dùng · ❌ không áp dụng.

> ⭐ Các biến `_text` (ngày dạng chữ) rất hay dùng trong hợp đồng Việt Nam — dòng *"Hôm nay, ngày 08 tháng 08 năm 2026, tại…"*. Chúng được cung cấp sẵn để người soạn template không phải ghép thủ công.

---

## 9.6. Bộ dựng ngữ cảnh render

⭐ **Tách làm hai thành phần để không vi phạm Clean Architecture:**

| Thành phần | Tầng | Trách nhiệm |
|---|---|---|
| **`RenderContextBuilder`** | **Application** | Dựng từ điển **chỉ chứa kiểu nguyên thuỷ**. Biến cần định dạng bọc trong `StyledValue{text, style}` — Value Object thuần của Domain |
| **`DocxContextAdapter`** | **Infrastructure** | Duyệt ngữ cảnh, chuyển `StyledValue` → `docxtpl.RichText` ngay trước khi render |

> **Vì sao tách:** `RichText` là lớp của thư viện `docxtpl` (Infrastructure). Nếu tầng Application tạo nó, đó là rò rỉ kiến trúc vi phạm P-02. Lợi ích phụ: đổi sang thư viện render khác (hoặc render HTML) chỉ cần đổi adapter.

### Bảy bước dựng ngữ cảnh

| # | Bước | Chi tiết |
|---|---|---|
| 1 | Nạp các bên | Đọc `contract_party`, giải mã PII |
| 2 | Dựng cây nhiều bên | `{"holder": {...}}` |
| 3 | ⭐ **Làm phẳng cho mẫu một bên** | `party_schema` chỉ có 1 bên → **sao chép** mọi khoá của bên đó lên cấp gốc. Kết quả: cả `{{full_name}}` và `{{holder.full_name}}` đều chạy |
| 4 | Thêm biến hệ thống | `contract_no`, `today`, `day/month/year`, `created_by_name` |
| 5 | Thêm biến bổ sung | Từ `contract.extra_variables` và `contract_party.party_extra` |
| 6 | ⭐ **Định dạng theo kiểu** | Ngày → `dd/MM/yyyy`; tiền tệ → phân cách hàng nghìn; `None` → chuỗi rỗng |
| 7 | ⭐ **Bọc `StyledValue`** | Biến có `render_style` → bọc thành `StyledValue(text, style)` |
| 8 | ⭐ **Áp `suppressed_variables`** | Biến trong danh sách → ghi đè thành chuỗi rỗng |

### Ngữ cảnh cho mẫu `01A_GDKQ`

| Khoá | Giá trị | Ghi chú |
|---|---|---|
| `securities_account_no` | `StyledValue("008C123456", {bold: true})` | ⭐ → `RichText` ở adapter |
| `full_name` | `"NGUYỄN VĂN AN"` | |
| `id_number` | `"001199012345"` | |
| `dob` | `"14/05/1990"` | Đã định dạng |
| `issue_date` | `"20/08/2021"` | |
| `expiry_date` | `"14/05/2030"` | Hoặc `"KHÔNG THỜI HẠN"` |
| `issue_place` | `"CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"` | |
| `phone` · `email` · `address` | … | |
| `contract_no` | `"01A-KQ-202608-00042"` | Hệ thống sinh |
| `contract_date` · `contract_date_text` · `day` · `month` · `year` | `""` | ⭐ **Suppressed** |
| `holder.*` | *(bản sao mọi khoá trên)* | Tương thích cả 2 cách viết |

⭐ Sau khi dựng xong, toàn bộ ngữ cảnh được lưu vào `contract.render_snapshot_enc` — hiện thực của P-09.

---

## 9.7. Bảng định dạng theo kiểu dữ liệu

| Kiểu khai báo | Đầu vào | Đầu ra render | Khi rỗng |
|---|---|---|---|
| `text` | chuỗi | nguyên văn, đã `trim()` | `""` |
| `date` | `date` | `08/08/2026` | `""` |
| `date_text` | `date` | `ngày 08 tháng 08 năm 2026` | `""` |
| `number` | int | `1234` | `""` |
| `decimal` | float | `12,50` *(dấu phẩy thập phân kiểu Việt Nam)* | `""` |
| `currency` | int | `1.500.000` | `""` |
| `currency_text` | int | `Một triệu năm trăm nghìn đồng` | `""` |
| `percent` | float | `50%` | `""` |
| `boolean` | bool | `Có` / `Không` | `Không` |
| `enum` | chuỗi | nhãn tiếng Việt của giá trị | `""` |
| `securities_account` | chuỗi | `008C123456` **in đậm** | `""` |

> ⭐ **Quy tắc vàng:** giá trị `None`/`null` **luôn** render thành chuỗi rỗng, **không bao giờ** thành `"None"`, `"null"`, hay `"{{ variable }}"`. Đây là lỗi kinh điển của mọi hệ thống template — chặn nó bằng lớp `Undefined` tuỳ chỉnh áp cho toàn ngữ cảnh.

---

## 9.8. Xử lý biến thiếu và biến thừa

| Tình huống | Xử lý | Lý do |
|---|---|---|
| Biến **bắt buộc** thiếu giá trị | 🔴 Chặn sinh hợp đồng, `COCAS-7002` kèm danh sách biến thiếu **và nhãn tiếng Việt** | Hợp đồng thiếu thông tin bắt buộc là tài liệu hỏng |
| Biến **tuỳ chọn** thiếu giá trị | Render chuỗi rỗng, ghi log mức DEBUG | Bình thường |
| Biến **không xác định** trong file | Render chuỗi rỗng + cảnh báo lúc đăng ký mẫu | Không nên làm hỏng cả hợp đồng vì một biến gõ nhầm |
| Biến trong `suppressed_variables` | Ghi đè thành chuỗi rỗng | ⭐ Ngày HĐ và chữ ký để trống cho người dùng viết tay |
| Biến có trong từ điển nhưng file không dùng | Không sao, ghi INFO | Mẫu không bắt buộc dùng hết biến |
| ⭐ Cấu hình Jinja2 | Dùng `Undefined` tuỳ chỉnh trả chuỗi rỗng — **không dùng `StrictUndefined`** | `StrictUndefined` ném lỗi **giữa chừng render** → hợp đồng hỏng một nửa. Ta muốn kiểm tra **trước** khi render |

---

## 9.9. ⭐ Bảo mật Template Engine — Chống SSTI

> **Đây là lỗ hổng nguy hiểm nhất của toàn hệ thống.** Jinja2 là ngôn ngữ Turing-complete. Một file `.docx` độc hại (đến từ email hoặc USB) có thể chứa biểu thức truy cập được vào đối tượng Python nội bộ và **thực thi mã tuỳ ý** trên máy người dùng.

| # | Biện pháp | Chi tiết |
|---|---|---|
| 1 | ⭐ **`SandboxedEnvironment`** | Jinja2 cung cấp sẵn môi trường sandbox chặn truy cập thuộc tính bắt đầu bằng `_`, chặn `__class__`, `__globals__`, `__subclasses__`, `__builtins__`. **Bắt buộc, không tuỳ chọn** |
| 2 | **Danh sách trắng bộ lọc** | Chỉ cho phép: `upper`, `lower`, `title`, `trim`, `default`, `length`, `join`, `replace`, `first`, `last`. Chặn tất cả bộ lọc khác |
| 3 | **Quét mẫu nguy hiểm khi đăng ký** | Từ chối file chứa `__`, `class`, `mro`, `subclasses`, `globals`, `builtins`, `import`, `eval`, `exec`, `open`, `os.`, `sys.`, `config`, `self`, `request`, `lipsum`, `cycler`, `namespace` → `COCAS-6014` |
| 4 | **Giới hạn tài nguyên khi render** | Timeout 10 giây · giới hạn số vòng lặp 1000 · giới hạn kích thước output 50 MB |
| 5 | **Ghi nhật ký mọi thao tác template** | `TEMPLATE_REGISTERED`, `TEMPLATE_VERSION_ACTIVATED` kèm SHA-256 của file |
| 6 | **Cấm `{% include %}` / `{% extends %}` / `{% import %}`** | Chống đọc file tuỳ ý qua template |
| 7 | ⭐ **Ngữ cảnh chỉ chứa kiểu nguyên thuỷ** | **Không bao giờ** đưa đối tượng ORM, `Settings`, hay bất kỳ đối tượng có thuộc tính riêng nào vào ngữ cảnh. Chỉ `str`, `int`, `float`, `bool`, `date`, `list`, `dict`, `RichText` |

> ⭐ **Biện pháp #7 là quan trọng nhất.** Ngay cả khi sandbox bị vượt qua, nếu ngữ cảnh chỉ chứa chuỗi và số thì kẻ tấn công không có "bàn đạp" nào để leo lên đối tượng hệ thống. Đây là phòng thủ theo chiều sâu đúng nghĩa.

---

## 9.10. Xem thử mẫu với dữ liệu giả

`POST /templates/{id}/preview` sinh **`.docx`** từ **dữ liệu giả cố định**, không đụng dữ liệu thật:

| Biến | Giá trị giả |
|---|---|
| `full_name` | `NGUYỄN VĂN MẪU` |
| `id_number` | `000000000000` |
| `dob` | `01/01/1990` |
| `issue_date` | `01/01/2021` |
| `expiry_date` | `01/01/2030` |
| `issue_place` | `BỘ CÔNG AN` |
| `phone` | `0900000000` |
| `email` | `mau@example.com` |
| `address` | `Số 1, đường Mẫu, phường Mẫu, quận Mẫu, thành phố Mẫu` |
| `bank_account` | `0000000000000` |
| `bank_name` | `Ngân hàng Mẫu` |
| `branch` | `Chi nhánh Mẫu` |
| ⭐ `securities_account_no` | **`008C000000`** *(in đậm — để kiểm tra định dạng đúng chưa)* |
| `contract_no` | `MẪU-XEM-THỬ` |

Bản xem thử **không tạo bản ghi `contract`**, không ghi vào Vault, file tạm bị xoá sau 5 phút. Có **watermark chéo "BẢN XEM THỬ"** trên mọi trang.

---

# PHẦN B — SINH DOCX

## 9.11. Kiến trúc pipeline sinh tài liệu

```mermaid
graph TB
    A["GenerateContractUseCase"] --> B{{"V-CTR-001..010<br/>Kiểm tra tiền điều kiện"}}
    B -->|Lỗi| E1["❌ 422 kèm danh sách biến thiếu"]
    B -->|OK| C["Sinh contract_no + export_name"]
    C --> D["RenderContextBuilder<br/>→ dict + StyledValue"]
    D --> F["INSERT contract (GENERATING)<br/>+ contract_party<br/>+ render_snapshot_enc"]

    F --> G1["DocxContextAdapter<br/>StyledValue → RichText"]
    G1 --> G["DocxRenderer · docxtpl<br/>SandboxedEnvironment"]
    G -->|Lỗi| E2["❌ GENERATION_FAILED · COCAS-7003"]
    G --> H["Ghi file .tmp vào Vault (mã hoá)"]
    H --> I["Đọc lại · tính SHA-256 · so khớp"]
    I -->|Lệch| E3["❌ COCAS-7009"]
    I --> J["os.replace .tmp → .docx<br/>INSERT contract_document"]
    J --> P["status=COMPLETED<br/>✅ TRẢ VỀ 201 NGAY (~500ms)"]
    P --> Q["Job RETENTION_PURGE<br/>xoá ảnh CCCD gốc"]

    style P fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
```

> ⭐ **Quyết định then chốt (D2.1):** toàn bộ việc sinh tài liệu là **một giao dịch đồng bộ** kết thúc bằng `201` sau ~500 ms. Không còn khâu bất đồng bộ nào sau khi ghi `.docx`, nên `contract` đi thẳng `GENERATING → COMPLETED`; không còn trạng thái trung gian `DOCX_READY`, không còn `PDF_CONVERTING`/`PDF_FAILED`.

---

## 9.12. Bộ render DOCX

| Mục | Thiết kế |
|---|---|
| Thư viện | `docxtpl` (bọc `python-docx` + Jinja2) |
| Môi trường Jinja2 | ⭐ `SandboxedEnvironment` + danh sách trắng 10 bộ lọc (§9.9) |
| `undefined` | Lớp tuỳ chỉnh trả chuỗi rỗng, ghi log DEBUG tên biến thiếu |
| Rich text | `DocxContextAdapter` chuyển `StyledValue` → `RichText`; template dùng cú pháp `{{r var }}` |
| Toàn vẹn nguồn | Kiểm SHA-256 file mẫu **trước** khi mở |
| Ghi file | ⭐ Mẫu *write-temp → verify → rename*: ghi `.tmp` → đọc lại → so hash → `os.replace()` (nguyên tử trên NTFS) |
| Mã hoá | File trong Vault mã hoá AES-256-GCM; giải mã khi tải xuống |
| Timeout | 10 giây (render thực tế < 1 giây; timeout chỉ để bắt vòng lặp vô hạn) |
| Hiệu năng mục tiêu | p95 ≤ 800 ms (NFR-03) |
| Luồng | ⭐ Chạy trong `run_in_executor` — CPU-bound, không chặn event loop |

---

## 9.13. ⭐ Đầu ra chỉ có `.docx` — đã gỡ PDF (D2.1)

**Quyết định:** hệ thống **không xuất PDF**. `.docx` là định dạng giao hàng duy nhất. LibreOffice bị gỡ khỏi ngăn xếp, khỏi gói cài đặt và khỏi mọi cấu hình.

### 9.13.1. Lý do

| # | Lý do |
|---|---|
| 1 | **Người dùng phải sửa được hợp đồng trước khi in.** Đó là cách dùng thật; PDF là bước thừa ngay sau khi tạo. |
| 2 | ⭐ **Rủi ro font tiếng Việt biến mất cùng LibreOffice.** Đây là rủi ro 🟠 đứng đầu sổ rủi ro P3 (§14.5): thiếu font metric-compatible ⇒ PDF sai layout hoàn toàn. Không chuyển đổi thì không có lớp nào để hỏng. |
| 3 | **Cắt ~350 MB khỏi gói cài đặt** và ~180 MB RAM thường trú của listener — ngân sách gói 1.5 GB (§14.5) bớt căng. |
| 4 | ⭐ **Sinh tài liệu trở thành một giao dịch đồng bộ duy nhất** (P-10). Không còn job nền, không còn trạng thái trung gian, không còn cây tiến trình con phải giám sát/kill/khởi động lại. |

### 9.13.2. Hệ quả đã áp vào thiết kế

| Nơi | Thay đổi |
|---|---|
| Port | ⭐ **Bỏ Port 13 `IPdfConverter`** (§12.12). Còn **18 Port**, đánh số 1–19 **khuyết số 13** — giữ số cũ để mọi trích dẫn hiện có không lệch |
| `ContractStatus` | 9 → **6 giá trị**: bỏ `DOCX_READY`, `PDF_CONVERTING`, `PDF_FAILED` (§4.3.3) |
| `JobType` | Bỏ `PDF_CONVERT` — còn 5 |
| `DocType` | Chỉ còn `DOCX` |
| Endpoint | Bỏ `POST /contracts/{id}/retry-pdf` và `GET /contracts/{id}/documents/pdf`. **64 → 62 endpoint** |
| Mã lỗi | Bỏ `COCAS-7004` (chuyển PDF thất bại) và `COCAS-7005` (LibreOffice timeout) |
| Ngoại lệ | Bỏ `LibreOfficeUnavailableError`, `PdfConversionTimeoutError`, `InvalidPdfOutputError` |
| Cấu hình | Bỏ 3 khoá `document.pdf_converter`, `document.libreoffice_timeout_sec`, `document.libreoffice_idle_shutdown_min`. **28 → 25 khoá** |
| Thư viện | Bỏ `pypdf`. Không đóng gói LibreOffice portable, không đóng gói font metric-compatible |
| Giao diện | Bỏ nút "Tải PDF"/"Thử lại tạo PDF"; nút tải xuống chỉ còn một |

> ⚠️ **Cột `contract_document.page_count` cũng bị bỏ.** Nó chỉ tồn tại vì `pypdf` đếm được số trang PDF; `.docx` không có khái niệm số trang cho tới khi một bộ xử lý văn bản dàn trang nó. Giữ lại cột này sẽ là một cột `NULL` vĩnh viễn, và sớm muộn ai đó sẽ hiển thị nó lên giao diện dưới dạng `0 trang`.

---

## 9.14. ⭐ Đặt tên file xuất

### 9.14.1. Tách bạch hai khái niệm

| | **Số hợp đồng nội bộ** | **Tên file xuất** |
|---|---|---|
| Cột | `contract.contract_no` | `contract.export_name` |
| Ví dụ | `01A-GDN-202608-00042` | `Mẫu 01A - NGUYỄN VĂN A` |
| Duy nhất? | ✅ **Bắt buộc UNIQUE** | ❌ Có thể trùng |
| Ai nhìn thấy? | Nhật ký, tra cứu nội bộ, mã truy vết | Người dùng — tên file khi tải/in |
| Vì sao cần cả hai | Không có định danh duy nhất thì không thể kiểm toán, tra cứu chính xác, phát hiện trùng | Người dùng cần tên file dễ nhận biết, không cần mã máy |

### 9.14.2. Thuật toán sinh tên file

| # | Bước | Ví dụ |
|---|---|---|
| 1 | Lấy `export_name_pattern` của mẫu | `Mẫu 01A - {full_name}` |
| 2 | Thay biến | `Mẫu 01A - NGUYỄN VĂN A` |
| 3 | Thay ký tự Windows cấm `\ / : * ? " < > \|` bằng khoảng trắng | — |
| 4 | Thu gọn khoảng trắng liên tiếp, `trim()` | — |
| 5 | Kiểm tên dành riêng (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) → thêm `_` | — |
| 6 | Cắt nếu > 180 ký tự (cắt phần tên khách hàng, giữ tiền tố mẫu) | — |
| 7 | Bỏ dấu nếu `export.strip_diacritics = true` (mặc định **không**) | — |
| 8 | Thêm phần mở rộng | `Mẫu 01A - NGUYỄN VĂN A.docx` |
| 9 | Nếu file đã tồn tại → thêm ` (2)`, ` (3)`… | `Mẫu 01A - NGUYỄN VĂN A (2).docx` |

### 9.14.3. Ba nơi tên file xuất hiện

| Nơi | Cách dùng |
|---|---|
| Header HTTP khi tải | ⭐ `Content-Disposition: attachment; filename*=UTF-8''M%E1%BA%ABu...` — **bắt buộc `filename*` theo RFC 5987**; `filename=` thường không hỗ trợ tiếng Việt có dấu |
| Hộp thoại "Lưu tệp" của Tauri | Tên gợi ý mặc định |
| Trong Vault (nội bộ) | ⭐ **KHÔNG dùng** — file trong Vault luôn tên `{uuid}.enc` |

> ⭐ **Tách bạch này quan trọng về bảo mật:** tên file trong Vault không bao giờ chứa dữ liệu người dùng → loại bỏ hoàn toàn Path Traversal, và người xem thư mục Vault không đọc được tên khách hàng.

### 9.14.4. Mẫu tên file cho 2 template

| Mẫu | `export_name_pattern` | Ví dụ |
|---|---|---|
| `01A_HD_GDN` | `Mẫu 01A - {full_name}` | `Mẫu 01A - NGUYỄN VĂN AN.docx` |
| `01A_GDKQ` | `Mẫu 01A-GDKQ - {full_name}` ⚠️ | `Mẫu 01A-GDKQ - NGUYỄN VĂN AN.docx` |

> ⚠️ **Cần xác nhận:** cả hai mẫu đều mang số hiệu **01A**. Nếu cùng dùng `Mẫu 01A - {full_name}` thì khi một khách hàng ký cả hai hợp đồng, hai file sẽ **trùng tên**.

---

## 9.15. Bảo đảm toàn vẹn tài liệu

| Thời điểm | Kiểm tra |
|---|---|
| Sau khi render DOCX | Đọc lại file, tính SHA-256, so với giá trị lúc ghi |
| Trước khi ghi bản ghi | Tính SHA-256 của `.docx` cuối cùng, lưu vào `contract_document.file_sha256` |
| ⭐ **Mỗi lần tải xuống** | Đọc file, tính lại SHA-256, so với CSDL. Lệch → `COCAS-7009`, **từ chối trả file**, ghi nhật ký `DOCUMENT_INTEGRITY_FAILED` |
| Job kiểm tra định kỳ | Hàng tuần đối chiếu toàn bộ `contract_document` với file thật; báo cáo ở màn hình Chẩn đoán |

> **Vì sao kiểm tra mỗi lần tải:** file trên đĩa có thể bị hỏng (lỗi ổ cứng), bị sửa (phần mềm khác), hoặc bị thay thế. Hợp đồng là chứng từ pháp lý — trả về file đã thay đổi mà không biết là rủi ro không chấp nhận được. Chi phí tính hash một file 200 KB là ~1 ms.

---

## 9.16. Xử lý lỗi

| Lỗi | Trạng thái hợp đồng | Người dùng thấy | Retry |
|---|---|---|---|
| Thiếu biến bắt buộc | *(chưa tạo bản ghi)* | `422` + danh sách biến thiếu, nhãn tiếng Việt | Không — phải bổ sung dữ liệu |
| File mẫu mất trên đĩa | `GENERATION_FAILED` | "Không tìm thấy file mẫu. Liên hệ quản trị viên." | Không |
| Checksum mẫu lệch | `GENERATION_FAILED` | "File mẫu đã bị thay đổi. Cần đăng ký lại." | Không |
| Lỗi render Jinja2 | `GENERATION_FAILED` | "Lỗi trong mẫu hợp đồng tại '{v}'." | Không |
| Hết đĩa | `GENERATION_FAILED` | "Không đủ dung lượng. Còn {x} MB." | Sau khi dọn đĩa |
| ⭐ Hash đọc lại lệch với hash lúc ghi | `GENERATION_FAILED` · `COCAS-7009` | "Tài liệu ghi ra không toàn vẹn. Vui lòng thử lại." | Có — sinh lại |
| Mất điện giữa chừng | `GENERATING` → job phục hồi đánh `FAILED` | "Công việc bị gián đoạn" trên Dashboard | Thủ công |

> ⭐ **Sau D2.1 không còn lỗi nào chỉ làm hỏng "một nửa" đầu ra.** Trước đây `PDF_FAILED` là trạng thái *suy giảm* theo P-08 — hợp đồng vẫn dùng được ở dạng DOCX. Nay chỉ có một đầu ra: hoặc `.docx` ra đời trọn vẹn, hoặc `GENERATION_FAILED` và người dùng bấm sinh lại.

---

## 9.17. Hiệu năng

| Giai đoạn | p50 | p95 | Ghi chú |
|---|---|---|---|
| Dựng ngữ cảnh (gồm giải mã PII) | 40 ms | 90 ms | |
| Render DOCX | 280 ms | 700 ms | Tài liệu 3–6 trang |
| Ghi + mã hoá + kiểm hash | 30 ms | 80 ms | |
| **Tổng đến khi trả `201`** | **~350 ms** | **~870 ms** | Đạt NFR-03 |

> ⭐ **D2.1: đây giờ cũng là tổng thời gian đến khi hợp đồng `COMPLETED`.** Trước khi gỡ PDF, người dùng nhận `201` sau ~870 ms nhưng phải chờ thêm 2.1–4.5 s (listener ấm) hoặc 11–15 s (cold start) mới có bản in. NFR-04 vì thế không còn đối tượng để áp.

**Tối ưu còn lại trong thiết kế:**
1. **Cache đối tượng template đã phân tích** trong bộ nhớ theo `(template_version_id, sha256)` — lần render thứ hai của cùng mẫu nhanh hơn ~40%.
2. ⭐ **Render chạy trong `run_in_executor`** — CPU-bound, không chặn event loop của Uvicorn 1 worker.

---

## 9.18. Kiểm thử module sinh tài liệu

| Loại | Nội dung |
|---|---|
| **Unit** | Bộ dựng ngữ cảnh: mỗi kiểu dữ liệu · giá trị `None` · `suppressed_variables` · `StyledValue` |
| **Unit** | Đặt tên file: ký tự cấm · tên dành riêng · quá dài · trùng tên · dấu tiếng Việt |
| **Integration** | Render 2 mẫu thật → mở lại bằng `python-docx`, kiểm tra: đủ 12/10 biến đã thay · ⭐ **run chứa STK chứng khoán có thuộc tính `bold = True`** · các biến suppressed là chuỗi rỗng |
| **Integration** | ⭐ Mở lại `.docx` đã sinh bằng `python-docx`, ghép toàn bộ text → kiểm chứa họ tên, số CCCD, STK CK *(thay cho phép trích văn bản từ PDF trước D2.1)* |
| ⭐ **Golden file** | So sánh output với file kỳ vọng đã duyệt bằng mắt. Bất kỳ thay đổi layout nào cũng làm test đỏ → buộc xem xét có chủ ý |
| **Chaos** | ⭐ Kill tiến trình backend giữa lúc render → không được để lại `.tmp` nào ở vị trí `.docx` cuối cùng, hợp đồng ở `GENERATING` phải được job phục hồi đánh `GENERATION_FAILED` và sinh lại được |
| ⭐ **Bảo mật** | Template chứa `{{ ''.__class__.__mro__ }}` phải bị **từ chối lúc đăng ký** với `COCAS-6014`; nếu lọt qua thì sandbox phải chặn lúc render |

---

[← 08 — Validation](08-validation.md) · [Mục lục](README.md) · [Tiếp: 10 — Bảo mật & Logging →](10-bao-mat-va-logging.md)
