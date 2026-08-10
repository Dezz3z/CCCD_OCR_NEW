"""seed_document_type_can_cuoc_2024

Seeds the second `document_type` row: `CAN_CUOC_2024`, plus its `issue_place`
aliases.

⭐ **Vietnam issues two ID card generations and they are not interchangeable.**
The sample photos turned out to contain both; the design (and every coordinate
seeded by `20260811_003`) described only the 2021 `CĂN CƯỚC CÔNG DÂN`. The 2024
`CĂN CƯỚC` differs in the places that matter most to this pipeline:

| | CCCD 2021 (`CCCD_CHIP`) | Căn cước 2024 (`CAN_CUOC_2024`) |
|---|---|---|
| Front title | `CĂN CƯỚC CÔNG DÂN` | `CĂN CƯỚC` |
| Number label | `Số / No.` | `Số định danh cá nhân` |
| ⭐ **QR code** | **FRONT** | ⭐ **BACK** |
| ⭐ **Expiry date** | **FRONT** (`Có giá trị đến`) | ⭐ **BACK** (`…năm hết hạn`) |
| Issuing authority | `CỤC TRƯỞNG CỤC CẢNH SÁT…` | `BỘ CÔNG AN` |
| MRZ | back, same TD1 layout and position | identical |

A new row rather than an edit to `20260811_003`: that migration is a seed with
`ON CONFLICT DO NOTHING`, so editing it in place would leave every already-
migrated database without the new card generation and without its aliases.

Idempotent: `ON CONFLICT (code) DO NOTHING` for the type, an explicit existence
check for the aliases (mirroring `20260811_004`, whose rows may carry a NULL
`alias_normalized` and so fall outside the partial unique index).

Revision ID: 20260811_009_seed_doctype_2024
Revises: 20260811_008_seed_template
Create Date: 2026-08-10

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260811_009_seed_doctype_2024"
down_revision = "20260811_008_seed_template"
branch_labels = None
depends_on = None

CAN_CUOC_2024_ID = "018f1000-0000-7000-8000-000000000002"
BO_CONG_AN = "BỘ CÔNG AN"

_FIELD_SCHEMA = [
    {"key": "full_name", "type": "text", "required": True, "label": "Họ và tên"},
    {"key": "id_number", "type": "text", "required": True, "label": "Số định danh"},
    {"key": "date_of_birth", "type": "date", "required": True, "label": "Ngày sinh"},
    {"key": "issue_date", "type": "date", "required": True, "label": "Ngày cấp"},
    {"key": "expiry_date", "type": "date", "required": False, "label": "Ngày hết hạn"},
    {"key": "issue_place", "type": "text", "required": True, "label": "Nơi cấp"},
]

# ⭐ MEASURED 2026-08-10 on the 7 Căn cước 2024 photos in the sample — 5 fronts
# and 2 backs — by the same method `20260811_003` used: run the real engine,
# locate the region holding each known value, and take the observed range plus
# padding. No coordinate here was chosen by eye.
#
# | Field | Side | Observed y | n |
# |---|---|---|---|
# | `id_number` | front | 0.457–0.543 | 5 |
# | `full_name` | front | 0.610–0.675 | 5 |
# | `date_of_birth` | front | 0.766–0.829 | 5 |
# | `issue_date` | back | 0.342–0.385 | 2 |
# | `expiry_date` | back | 0.448–0.496 | 2 |
# | `issue_place` | back | 0.506–0.564 | 2 |
# | `mrz` | back | 0.661–0.914 | 2 |
#
# ⭐ Every front field sits ~0.06–0.20 LOWER than on a 2021 card: the 2024 front
# spends more lines on its header. Reusing the 2021 map would put `full_name`
# over the number and `date_of_birth` over the name.
#
# ⚠️ The back boxes rest on n=2. They are padded more generously than the fronts
# for that reason, and are the first thing to re-measure when the Golden Set
# arrives.
_ZONE_MAP = {
    "id_number": {"x": 0.26, "y": 0.42, "w": 0.41, "h": 0.16, "side": "FRONT"},
    "full_name": {"x": 0.26, "y": 0.57, "w": 0.57, "h": 0.14, "side": "FRONT"},
    "date_of_birth": {"x": 0.25, "y": 0.73, "w": 0.27, "h": 0.13, "side": "FRONT"},
    "issue_date": {"x": 0.38, "y": 0.30, "w": 0.28, "h": 0.13, "side": "BACK"},
    "expiry_date": {"x": 0.38, "y": 0.41, "w": 0.30, "h": 0.13, "side": "BACK"},
    # ⚠️ `y` starts at 0.49, not the 0.47 the padding rule would give. The
    # expiry line ends at 0.496, and `find_place` is deliberately permissive —
    # at 0.47 more than half of that line fell inside this zone and a garbled
    # `Không thời hạn` was returned as the issuing authority. Measured.
    "issue_place": {"x": 0.19, "y": 0.49, "w": 0.60, "h": 0.12, "side": "BACK"},
    "mrz": {"x": 0.02, "y": 0.62, "w": 0.96, "h": 0.36, "side": "BACK"},
}

# ⭐ `issue_date` and `expiry_date` anchors are DELIBERATELY truncated to their
# distinguishing tails, and this is the whole reason they are not the full
# printed labels. Both lines begin `Ngày, tháng, năm …`, and scored against each
# other the full phrases cross-match at **83.9** and **83.3** — over the 75
# threshold. `_beside_label` returns the first matching label in reading order,
# and the issue label is printed first, so `expiry_date` would have taken the
# ISSUE date and reported it confidently. Measured on the real backs, `năm cấp`
# and `năm hết hạn` each match exactly one line and nothing else.
#
# `issue_place` has no label here either: the card prints the authority itself,
# `BỘ CÔNG AN`, which is already one of the two canonical `IssuePlace` values.
_ANCHOR_PATTERNS = {
    "front": {
        "id_number": ["Số định danh cá nhân", "Personal identification number"],
        "full_name": ["Họ, chữ đệm và tên khai sinh", "Full name"],
        "date_of_birth": ["Ngày, tháng, năm sinh", "Date of birth"],
    },
    "back": {
        "issue_date": ["năm cấp", "Date of issue"],
        "expiry_date": ["năm hết hạn", "Date of expiry"],
        "issue_place": ["BỘ CÔNG AN", "MINISTRY OF PUBLIC SECURITY"],
    },
}

# The 2024 card only ever prints `BỘ CÔNG AN`, so it needs the exact-match tier
# and the keyword tier for that one canonical value — not the 16 rows
# `20260811_004` seeds for the 2021 authority.
#
# (alias_normalized, keywords, match_tier, assigned_confidence)
_ALIAS_ROWS: list[tuple[str | None, list[str] | None, int, float]] = [
    ("BO CONG AN", None, 1, 1.00),
    ("BO CONG AN MINISTRY OF PUBLIC SECURITY", None, 1, 1.00),
    (None, ["BO", "CONG", "AN"], 2, 0.90),
]

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

_alias = sa.table(
    "normalization_alias",
    sa.column("id", PG_UUID(as_uuid=False)),
    sa.column("document_type_id", PG_UUID(as_uuid=False)),
    sa.column("field_key", sa.String),
    sa.column("alias_normalized", sa.String),
    sa.column("canonical_value", sa.String),
    sa.column("match_tier", sa.SmallInteger),
    sa.column("keywords", JSONB),
    sa.column("assigned_confidence", sa.Float),
    sa.column("is_active", sa.Boolean),
    sa.column("created_by", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.execute(
        pg_insert(_document_type)
        .values(
            id=CAN_CUOC_2024_ID,
            code="CAN_CUOC_2024",
            name="Căn cước (mẫu 2024)",
            field_schema=_FIELD_SCHEMA,
            zone_map=_ZONE_MAP,
            anchor_patterns=_ANCHOR_PATTERNS,
            # ⭐ `has_qr` stays True — the card does carry a QR. Which SIDE it is
            # on is not expressible here, and the QR channel does not need to
            # know: it scans whatever image it is handed.
            has_qr=True,
            has_mrz=True,
            is_ocr_supported=True,
            expected_aspect_ratio=1.585,
            is_active=True,
            created_at=sa.func.now(),
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )

    connection = op.get_bind()
    for alias_normalized, keywords, match_tier, confidence in _ALIAS_ROWS:
        exists = connection.execute(
            sa.select(_alias.c.id).where(
                _alias.c.document_type_id == CAN_CUOC_2024_ID,
                _alias.c.field_key == "issue_place",
                _alias.c.canonical_value == BO_CONG_AN,
                _alias.c.match_tier == match_tier,
                _alias.c.alias_normalized.is_(None)
                if alias_normalized is None
                else _alias.c.alias_normalized == alias_normalized,
            )
        ).first()
        if exists is not None:
            continue
        connection.execute(
            _alias.insert().values(
                id=str(uuid.uuid4()),
                document_type_id=CAN_CUOC_2024_ID,
                field_key="issue_place",
                alias_normalized=alias_normalized,
                canonical_value=BO_CONG_AN,
                match_tier=match_tier,
                keywords=keywords,
                assigned_confidence=confidence,
                is_active=True,
                created_by="seed",
                created_at=sa.func.now(),
            )
        )


def downgrade() -> None:
    op.execute(
        _alias.delete().where(_alias.c.document_type_id == CAN_CUOC_2024_ID)
    )
    op.execute(
        _document_type.delete().where(_document_type.c.code == "CAN_CUOC_2024")
    )
