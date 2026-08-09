"""seed_normalization_alias

Seeds the 16 `issue_place` aliases from §4.4.14's seed data table.

⚠️ Doc transcription note: the source table displays canonical_value as
"↑" (repeat-above) for several rows, and the one row that spells it out a
second time ("CUC CS QLHC VE TTXH") uses the doc's own column-width
abbreviation "CỤC CẢNH SÁT QLHC VỀ TTXH" rather than the actual canonical
string. Every row here uses the one full, correct canonical value —
`CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI` — matching the
`IssuePlace` VO whitelist (only 2 values may ever appear as
`canonical_value` for `field_key="issue_place"`).

Idempotent: each row is inserted only if an identical
(document_type_id, field_key, canonical_value, match_tier, alias_normalized)
combination doesn't already exist — done with an explicit existence check
rather than `ON CONFLICT`, because 3 of the 16 rows have `alias_normalized
IS NULL` and fall outside the partial unique index (`uq_normalization_alias`
only covers `alias_normalized IS NOT NULL`).

Revision ID: 20260811_004_seed_alias
Revises: 20260811_003_seed_doctype
Create Date: 2026-08-11

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision = "20260811_004_seed_alias"
down_revision = "20260811_003_seed_doctype"
branch_labels = None
depends_on = None

CCCD_CHIP_ID = "018f1000-0000-7000-8000-000000000001"
BO_CONG_AN = "BỘ CÔNG AN"
CUC_CANH_SAT = "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"

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

# (alias_normalized, keywords, canonical_value, match_tier, assigned_confidence)
_SEED_ROWS: list[tuple[str | None, list[str] | None, str, int, float]] = [
    ("BO CONG AN", None, BO_CONG_AN, 1, 1.00),
    ("BCA", None, BO_CONG_AN, 2, 0.95),
    ("B CONG AN", None, BO_CONG_AN, 2, 0.90),
    ("BO CONGAN", None, BO_CONG_AN, 2, 0.90),
    ("MINISTRY OF PUBLIC SECURITY", None, BO_CONG_AN, 2, 0.95),
    ("CUC CANH SAT QUAN LY HANH CHINH VE TRAT TU XA HOI", None, CUC_CANH_SAT, 1, 1.00),
    ("CUC CS QLHC VE TTXH", None, CUC_CANH_SAT, 2, 0.95),
    ("CUC CSQLHC VE TTXH", None, CUC_CANH_SAT, 2, 0.95),
    ("CUC CANH SAT QLHC VE TTXH", None, CUC_CANH_SAT, 2, 0.95),
    ("CUC CANH SAT QL HANH CHINH VE TRAT TU XA HOI", None, CUC_CANH_SAT, 2, 0.95),
    ("C06", None, CUC_CANH_SAT, 2, 0.90),
    ("CUC C06", None, CUC_CANH_SAT, 2, 0.90),
    (None, ["CUC", "CANH", "SAT"], CUC_CANH_SAT, 4, 0.60),
    (None, ["QLHC"], CUC_CANH_SAT, 4, 0.60),
    (None, ["TTXH"], CUC_CANH_SAT, 4, 0.60),
    (None, ["BO", "CONG", "AN"], BO_CONG_AN, 4, 0.60),
]


def _row_exists(
    bind: sa.Connection,
    alias_normalized: str | None,
    keywords: list[str] | None,
    canonical_value: str,
    match_tier: int,
) -> bool:
    # ⭐ Bug fixed 2026-08-09 (found running the real upgrade): tier-4 rows all
    # share alias_normalized=NULL, so 3 keyword-only rows for the same
    # canonical_value/match_tier looked identical to this check unless
    # `keywords` itself is also compared — without it, 2 of 16 rows were
    # silently skipped as "already exists" (16 -> 14 actual rows inserted).
    stmt = sa.select(sa.literal(1)).where(
        _alias.c.document_type_id == CCCD_CHIP_ID,
        _alias.c.field_key == "issue_place",
        _alias.c.canonical_value == canonical_value,
        _alias.c.match_tier == match_tier,
        _alias.c.alias_normalized.is_(None) if alias_normalized is None else _alias.c.alias_normalized == alias_normalized,
        _alias.c.keywords.is_(None) if keywords is None else _alias.c.keywords == sa.literal(keywords, type_=JSONB),
    )
    return bind.execute(stmt).first() is not None


def upgrade() -> None:
    bind = op.get_bind()
    for alias_normalized, keywords, canonical_value, match_tier, confidence in _SEED_ROWS:
        if _row_exists(bind, alias_normalized, keywords, canonical_value, match_tier):
            continue
        bind.execute(
            _alias.insert().values(
                id=str(uuid.uuid4()),
                document_type_id=CCCD_CHIP_ID,
                field_key="issue_place",
                alias_normalized=alias_normalized,
                canonical_value=canonical_value,
                match_tier=match_tier,
                keywords=keywords,
                assigned_confidence=confidence,
                is_active=True,
                created_by=None,
                created_at=sa.func.now(),
            )
        )


def downgrade() -> None:
    op.execute(
        _alias.delete().where(
            _alias.c.document_type_id == CCCD_CHIP_ID, _alias.c.field_key == "issue_place"
        )
    )
