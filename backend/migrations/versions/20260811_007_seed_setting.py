"""seed_system_setting

Seeds the default `system_setting` rows from §4.4.17's config table (28 keys
— the doc's own count, "~30 khoá cấu hình mặc định", is an approximation).

Idempotent: `ON CONFLICT (key) DO NOTHING` — an admin who already changed a
setting must never have their value silently reset by a re-run.

Revision ID: 20260811_007_seed_setting
Revises: 20260811_006_seed_bank
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260811_007_seed_setting"
down_revision = "20260811_006_seed_bank"
branch_labels = None
depends_on = None

_system_setting = sa.table(
    "system_setting",
    sa.column("key", sa.String),
    sa.column("value", JSONB),
    sa.column("value_type", sa.String),
    sa.column("default_value", JSONB),
    sa.column("constraints", JSONB),
    sa.column("label_vi", sa.String),
    sa.column("description", sa.Text),
    sa.column("scope", sa.String),
    sa.column("is_sensitive", sa.Boolean),
    sa.column("requires_restart", sa.Boolean),
    sa.column("updated_by", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

# (key, value, value_type, constraints, label_vi, description, scope, requires_restart)
_SEED_ROWS: list[tuple[str, object, str, dict | None, str, str, str, bool]] = [
    ("ocr.review_threshold", 0.85, "float", {"min": 0.0, "max": 1.0},
     "Ngưỡng cần xem lại", "Trường có độ tin cậy dưới ngưỡng này sẽ được đánh dấu cần người dùng kiểm tra lại.", "OCR", False),
    ("ocr.engine", "paddle", "enum", {"options": ["paddle", "tesseract", "null"]},
     "Bộ máy OCR", "Bộ máy nhận dạng văn bản đang sử dụng.", "OCR", True),
    ("ocr.enable_qr_channel", True, "bool", None,
     "Bật kênh QR", "Cho phép trích xuất dữ liệu từ mã QR trên CCCD.", "OCR", False),
    ("ocr.enable_mrz_channel", True, "bool", None,
     "Bật kênh MRZ", "Cho phép trích xuất dữ liệu từ dải MRZ ở mặt sau CCCD.", "OCR", False),
    ("ocr.cpu_threads", 2, "int", {"min": 1, "max": 16},
     "Số luồng CPU cho OCR", "Số luồng CPU dành cho bộ máy nhận dạng.", "OCR", True),
    ("preproc.target_long_edge", 1600, "int", {"min": 800, "max": 3200},
     "Kích thước cạnh dài mục tiêu", "Ảnh được resize để cạnh dài bằng giá trị này trước khi xử lý.", "OCR", False),
    ("preproc.perspective_enabled", True, "bool", None,
     "Bật nắn phối cảnh", "Tự động nắn thẳng ảnh thẻ bị chụp nghiêng.", "OCR", False),
    ("preproc.denoise_method", "bilateral", "enum", {"options": ["bilateral", "nlmeans"]},
     "Phương pháp khử nhiễu", "Thuật toán khử nhiễu ảnh trước khi nhận dạng.", "OCR", False),
    ("preproc.deglare_enabled", False, "bool", None,
     "Bật khử loá", "Xử lý vùng phản quang trên ảnh — chỉ bật khi biết ảnh có loá.", "OCR", False),
    ("retention.image_policy", "DELETE_AFTER_CONTRACT", "enum",
     {"options": ["DELETE_AFTER_CONTRACT", "KEEP_N_DAYS", "KEEP_FOREVER"]},
     "Chính sách lưu ảnh gốc", "Quy định khi nào xoá ảnh CCCD gốc sau khi tạo hợp đồng (P-05).", "RETENTION", False),
    ("retention.image_keep_days", 30, "int", {"min": 0, "max": 3650},
     "Số ngày giữ ảnh", "Áp dụng khi chính sách lưu ảnh là KEEP_N_DAYS.", "RETENTION", False),
    ("retention.ocr_raw_keep_days", 180, "int", {"min": 0, "max": 3650},
     "Số ngày giữ dữ liệu OCR thô", "Thời gian giữ kết quả thô từ bộ máy OCR trước khi xoá.", "RETENTION", False),
    ("retention.log_keep_days", 30, "int", {"min": 1, "max": 3650},
     "Số ngày giữ nhật ký hệ thống", "Thời gian giữ file log trước khi xoay vòng/xoá.", "RETENTION", False),
    ("retention.activity_log_years", 5, "int", {"min": 1, "max": 20},
     "Số năm giữ nhật ký hoạt động", "Thời gian tối thiểu giữ bảng activity_log trước khi được phép xuất và xoá.", "RETENTION", False),
    ("upload.max_size_mb", 10, "int", {"min": 1, "max": 50},
     "Dung lượng tải lên tối đa (MB)", "Giới hạn kích thước file ảnh CCCD được phép tải lên.", "SYSTEM", False),
    ("validation.securities_account.member_code", "008", "string", None,
     "Mã thành viên STK chứng khoán", "Ba chữ số đầu bắt buộc của số tài khoản chứng khoán.", "SYSTEM", False),
    ("validation.securities_account.strict", True, "bool", None,
     "Kiểm tra nghiêm ngặt mã thành viên", "Nếu bật, từ chối STK chứng khoán không đúng mã thành viên cấu hình.", "SYSTEM", False),
    ("backup.auto_enabled", True, "bool", None,
     "Tự động sao lưu", "Bật lịch sao lưu tự động hàng ngày.", "BACKUP", False),
    ("backup.auto_time", "18:00", "string", None,
     "Giờ sao lưu tự động", "Thời điểm trong ngày chạy sao lưu tự động (giờ Việt Nam).", "BACKUP", False),
    ("backup.keep_count", 14, "int", {"min": 1, "max": 365},
     "Số bản sao lưu giữ lại", "Số bản .cocasbak gần nhất được giữ lại trước khi xoá bản cũ.", "BACKUP", False),
    ("backup.warn_after_days", 7, "int", {"min": 1, "max": 90},
     "Cảnh báo nếu không sao lưu quá X ngày", "Hiện cảnh báo trên Dashboard nếu chưa sao lưu trong khoảng thời gian này.", "BACKUP", False),
    ("backup.encrypt", True, "bool", None,
     "Mã hoá bản sao lưu", "Bắt buộc mã hoá file .cocasbak bằng mật khẩu backup.", "BACKUP", False),
    ("document.pdf_converter", "libreoffice", "enum", {"options": ["libreoffice", "null"]},
     "Bộ chuyển đổi PDF", "Công cụ dùng để chuyển DOCX sang PDF.", "DOCUMENT", True),
    ("document.libreoffice_timeout_sec", 60, "int", {"min": 10, "max": 300},
     "Thời gian chờ chuyển đổi PDF (giây)", "Quá thời gian này, tiến trình chuyển đổi bị huỷ.", "DOCUMENT", False),
    ("document.libreoffice_idle_shutdown_min", 20, "int", {"min": 1, "max": 120},
     "Tự tắt LibreOffice sau (phút)", "Số phút không hoạt động trước khi tắt listener LibreOffice để tiết kiệm RAM.", "DOCUMENT", False),
    ("export.strip_diacritics", False, "bool", None,
     "Bỏ dấu tên file xuất", "Nếu bật, tên file DOCX/PDF xuất ra sẽ bỏ dấu tiếng Việt.", "DOCUMENT", False),
    ("ui.date_format", "dd/MM/yyyy", "string", None,
     "Định dạng ngày hiển thị", "Định dạng ngày tháng hiển thị trên toàn bộ giao diện.", "UI", False),
    ("ui.theme", "system", "enum", {"options": ["light", "dark", "system"]},
     "Giao diện sáng/tối", "Chủ đề màu hiển thị của ứng dụng.", "UI", False),
]


def upgrade() -> None:
    assert len(_SEED_ROWS) == 28
    for key, value, value_type, constraints, label_vi, description, scope, requires_restart in _SEED_ROWS:
        op.execute(
            pg_insert(_system_setting)
            .values(
                key=key,
                value=value,
                value_type=value_type,
                default_value=value,
                constraints=constraints,
                label_vi=label_vi,
                description=description,
                scope=scope,
                is_sensitive=False,
                requires_restart=requires_restart,
                updated_by=None,
                updated_at=sa.func.now(),
            )
            .on_conflict_do_nothing(index_elements=["key"])
        )


def downgrade() -> None:
    keys = [row[0] for row in _SEED_ROWS]
    op.execute(_system_setting.delete().where(_system_setting.c.key.in_(keys)))
