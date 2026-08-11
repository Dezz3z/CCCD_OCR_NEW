"""markers_tier5

Two changes, both needed before P3's `ExtractionPipeline` can write a row.

⭐ **1. `document_type.identity_markers`** — the phrases printed on exactly one
card generation. `MarkerDocumentTypeSelector` (Port 19) uses them to decide
which `zone_map` to extract through, because the user cannot be asked: both
generations are in circulation and a session that declares the wrong one
extracts every field through the wrong coordinates.

The lists below are not new guesses. They are the markers measured across the
whole 46-photo sample on 2026-08-10 (`scripts/verify_qr_mrz.py`), including the
two omissions that measurement forced: `CĂN CƯỚC` and `IDENTITY CARD` are the
2024 card's own titles and still do **not** appear, because `CĂN CƯỚC CÔNG DÂN`
scores 100 against `CĂN CƯỚC` and a marker matching both generations
distinguishes neither.

🔴 **2. `ck_ocr_field__tier_range` widened from 1..4 to 1..5.** The fifth
normalization tier shipped on 2026-08-11 (§12.5.1) and resolves 20 of 20
`issue_place` readings in the sample — every one of which the old CHECK would
have rejected at INSERT time, inside a background job, after all the OCR work
was already paid for. The constraint was written when four tiers were all
there were; nothing about it was reconsidered when the fifth arrived.

Revision ID: 20260811_010_markers_tier5
Revises: 20260811_009_seed_doctype_2024
Create Date: 2026-08-11

⚠️ The revision id is short because Alembic's `alembic_version.version_num` is
`VARCHAR(32)`; the first draft called this `20260811_010_doctype_markers_and_tier5`
(37 chars) and `tests/unit/migrations/test_revision_ids.py` caught it.

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20260811_010_markers_tier5"
down_revision = "20260811_009_seed_doctype_2024"
branch_labels = None
depends_on = None

# ⚠️ Every phrase below was scored against all 774 recognized lines of the
# sample before being listed. See the module docstring for the two that were
# measured and then deliberately left out.
_MARKERS = {
    "CCCD_CHIP": ["CĂN CƯỚC CÔNG DÂN", "Đặc điểm nhân dạng", "Quê quán", "Nơi thường trú"],
    "CAN_CUOC_2024": ["Số định danh cá nhân", "Nơi đăng ký khai sinh", "Nơi cư trú"],
}

_document_type = sa.table(
    "document_type",
    sa.column("code", sa.String),
    sa.column("identity_markers", JSONB),
)

_OLD_TIER_CHECK = "normalization_tier IS NULL OR normalization_tier BETWEEN 1 AND 4"
_NEW_TIER_CHECK = "normalization_tier IS NULL OR normalization_tier BETWEEN 1 AND 5"


def upgrade() -> None:
    op.add_column(
        "document_type",
        sa.Column(
            "identity_markers",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    for code, markers in _MARKERS.items():
        op.execute(
            _document_type.update()
            .where(_document_type.c.code == code)
            .values(identity_markers=markers)
        )

    op.drop_constraint("ck_ocr_field__tier_range", "ocr_field", type_="check")
    op.create_check_constraint("tier_range", "ocr_field", _NEW_TIER_CHECK)


def downgrade() -> None:
    # ⚠️ Going back narrows the CHECK again, so any `ocr_field` row already
    # written at tier 5 makes this fail. That is the correct behaviour: silently
    # deleting or rewriting a user's extracted values to fit an older constraint
    # would be worse than refusing to downgrade.
    op.drop_constraint("ck_ocr_field__tier_range", "ocr_field", type_="check")
    op.create_check_constraint("tier_range", "ocr_field", _OLD_TIER_CHECK)
    op.drop_column("document_type", "identity_markers")
