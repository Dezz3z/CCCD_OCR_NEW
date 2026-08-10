"""seed_document_type

Seeds the single v1.0 `document_type` row: `CCCD_CHIP`.

⭐ `zone_map` was recalibrated against real cards on 2026-08-10 (P2 week 3) —
see the comment on `_ZONE_MAP` for the method and for how far off the original
placeholders were. `anchor_patterns` label text was always reliable: these are
the literal Vietnamese labels printed on every CCCD chip card.

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

# ⭐ CALIBRATED 2026-08-10 against real cards, replacing the provisional guesses
# this migration originally shipped. Relative (0..1) boxes on the warped
# 1012x638 frame (§7.4.1).
#
# Method: run the pipeline over the sample photos, take the QR payload (fronts)
# and the checksum-valid MRZ block (backs) as ground truth, and record the
# bounding box of the region holding each known value. The boxes below are the
# observed range plus 0.03 padding — no coordinate here was chosen by eye.
#
# ⚠️ The originals were wrong by roughly 0.2 in y on every front field, which
# is more than a field height: `full_name` pointed at the `Citizen Identity
# Card` subtitle and handed it to fusion as a customer's name. The two back
# fields were placed near the bottom of the card; on a real chip CCCD the issue
# date and issuing authority are printed near the TOP, above the fingerprints.
#
# | Field | Was | Measured y | n |
# |---|---|---|---|
# | `id_number` | y 0.14 | 0.40–0.43 | 15 fronts |
# | `full_name` | y 0.28 | 0.54–0.57 | 15 fronts |
# | `date_of_birth` | y 0.40 | 0.61–0.63 | 12 fronts |
# | `expiry_date` | y 0.78 | 0.88–0.93 | 9 fronts |
# | `issue_date` | y 0.78 (BACK) | 0.11–0.15 | 14 backs |
# | `issue_place` | y 0.62 | 0.16–0.20 | 20 backs |
# | `mrz` | y 0.82 | 0.66–0.93 | 20 backs |
#
# Still editable at runtime (that was always the point of storing it here), but
# it is now a measurement rather than a placeholder.
_ZONE_MAP = {
    "id_number": {"x": 0.26, "y": 0.37, "w": 0.54, "h": 0.15, "side": "FRONT"},
    "full_name": {"x": 0.26, "y": 0.51, "w": 0.55, "h": 0.14, "side": "FRONT"},
    "date_of_birth": {"x": 0.28, "y": 0.58, "w": 0.53, "h": 0.13, "side": "FRONT"},
    "expiry_date": {"x": 0.00, "y": 0.85, "w": 0.40, "h": 0.14, "side": "FRONT"},
    "issue_date": {"x": 0.00, "y": 0.08, "w": 0.57, "h": 0.17, "side": "BACK"},
    "issue_place": {"x": 0.13, "y": 0.13, "w": 0.44, "h": 0.16, "side": "BACK"},
    "mrz": {"x": 0.02, "y": 0.62, "w": 0.96, "h": 0.36, "side": "BACK"},
}

# Literal Vietnamese labels printed on the card — reliable, not calibrated data.
#
# ⭐ Two corrections on 2026-08-10, both from reading real cards:
#
# 1. `expiry_date` moved FRONT→ ... it was listed under `back`, but `Có giá trị
#    đến / Date of expiry` is printed on the front, as the last line (y≈0.89).
# 2. `issue_place` has **no label on a CCCD**. The card prints the authority
#    itself — `CỤC TRƯỞNG CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI` —
#    so the anchors here are the authority's own words, matched fuzzily. They
#    fold to the same string `IssuePlaceNormalizer` canonicalizes against.
#
# `id_number` keeps `Số / No.` as one phrase: `Số` alone is two characters and
# fuzzy-matches `SOCIALIST REPUBLIC` at 100.
#
# ⭐ **`Số:` was dropped 2026-08-10 for the same reason, one round later.** The
# shortened form survived the first cleanup because it looked long enough with
# its colon; scored against the real header it reaches **80.0**, over the 75
# anchor threshold. Nothing is lost by removing it — `id_number` is also found
# by region height (`_TALLEST_WINS`), which needs no label at all.
_ANCHOR_PATTERNS = {
    "front": {
        "full_name": ["Họ và tên", "Full name"],
        "id_number": ["Số / No.", "No.:"],
        "date_of_birth": ["Ngày sinh", "Date of birth"],
        "expiry_date": ["Có giá trị đến", "Date of expiry"],
    },
    "back": {
        "issue_date": ["Ngày, tháng, năm", "Date, month, year"],
        "issue_place": [
            "CỤC TRƯỞNG CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
            "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
            "BỘ CÔNG AN",
        ],
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
