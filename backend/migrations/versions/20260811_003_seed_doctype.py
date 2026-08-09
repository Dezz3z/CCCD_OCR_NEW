"""seed_document_type

Seeds the single v1.0 `document_type` row: `CCCD_CHIP`.

⚠️ `zone_map` coordinates are PROVISIONAL placeholders, not measured from
real card images — the Golden Set (200 labeled CCCD image pairs) has not
been collected yet (progress.md checkpoint #1, roadmap §14.5 risk
"`zone_map` khởi tạo sai lệch nhiều"). They exist so the column is non-null
and the `ZONE` extraction strategy has *something* to try; P2 week 3-4 must
recalibrate them against real photos before they're trustworthy.
`anchor_patterns` label text IS reliable — these are the literal Vietnamese
field labels printed on every CCCD chip card, not measured data.

Idempotent: `ON CONFLICT (code) DO NOTHING`.

Revision ID: 20260811_003_seed_doctype
Revises: 20260811_002_initial_schema
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260811_003_seed_doctype"
down_revision = "20260811_002_initial_schema"
branch_labels = None
depends_on = None

# ⭐ Fixed UUID so later seed migrations (normalization_alias) can reference
# this row deterministically without a lookup query.
CCCD_CHIP_ID = "018f1000-0000-7000-8000-000000000001"

_FIELD_SCHEMA = [
    {"key": "full_name", "type": "text", "required": True, "label": "Họ và tên"},
    {"key": "id_number", "type": "text", "required": True, "label": "Số CCCD"},
    {"key": "date_of_birth", "type": "date", "required": True, "label": "Ngày sinh"},
    {"key": "issue_date", "type": "date", "required": True, "label": "Ngày cấp"},
    {"key": "expiry_date", "type": "date", "required": False, "label": "Ngày hết hạn"},
    {"key": "issue_place", "type": "text", "required": True, "label": "Nơi cấp"},
]

# PROVISIONAL — relative (0..1) boxes on the warped 1012x638 standardized
# frame (§7.4.1). Rough approximations of typical CCCD-chip layout, NOT
# calibrated against real cards. Corrected via the Settings UI once real
# images are available (document_type.zone_map is designed to be editable).
_ZONE_MAP = {
    "full_name": {"x": 0.38, "y": 0.28, "w": 0.57, "h": 0.10, "side": "FRONT"},
    "id_number": {"x": 0.38, "y": 0.14, "w": 0.45, "h": 0.09, "side": "FRONT"},
    "date_of_birth": {"x": 0.38, "y": 0.40, "w": 0.30, "h": 0.08, "side": "FRONT"},
    "issue_date": {"x": 0.10, "y": 0.78, "w": 0.35, "h": 0.09, "side": "BACK"},
    "expiry_date": {"x": 0.10, "y": 0.78, "w": 0.35, "h": 0.09, "side": "FRONT"},
    "issue_place": {"x": 0.10, "y": 0.62, "w": 0.80, "h": 0.14, "side": "BACK"},
}

# Literal Vietnamese labels printed on the card — reliable, not calibrated data.
_ANCHOR_PATTERNS = {
    "front": {
        "full_name": ["Họ và tên", "Full name"],
        "id_number": ["Số", "No."],
        "date_of_birth": ["Ngày sinh", "Date of birth"],
    },
    "back": {
        "issue_date": ["Ngày, tháng, năm", "Date, month, year"],
        "issue_place": ["Nơi cấp", "Place of issue"],
        "expiry_date": ["Có giá trị đến", "Date of expiry"],
    },
}

_document_type = sa.table(
    "document_type",
    sa.column("id", PG_UUID(as_uuid=False)),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("field_schema", JSONB),
    sa.column("zone_map", JSONB),
    sa.column("anchor_patterns", JSONB),
    sa.column("has_qr", sa.Boolean),
    sa.column("has_mrz", sa.Boolean),
    sa.column("is_ocr_supported", sa.Boolean),
    sa.column("expected_aspect_ratio", sa.Float),
    sa.column("is_active", sa.Boolean),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.execute(
        pg_insert(_document_type)
        .values(
            id=CCCD_CHIP_ID,
            code="CCCD_CHIP",
            name="Căn cước công dân gắn chip",
            field_schema=_FIELD_SCHEMA,
            zone_map=_ZONE_MAP,
            anchor_patterns=_ANCHOR_PATTERNS,
            has_qr=True,
            has_mrz=True,
            is_ocr_supported=True,
            expected_aspect_ratio=1.585,
            is_active=True,
            created_at=sa.func.now(),
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )


def downgrade() -> None:
    op.execute(_document_type.delete().where(_document_type.c.code == "CCCD_CHIP"))
