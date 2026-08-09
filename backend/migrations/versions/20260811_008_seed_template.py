"""seed_contract_template

Seeds the 2 v1.0 contract templates from §4.5: `01A_HD_GDN`, `01A_GDKQ`.

⚠️ `active_version_id` stays NULL — no real `.docx` file has been supplied
yet (outstanding item #2 in CLAUDE.md's "Ba việc cần người dùng cung cấp").
A template with no active version simply can't generate a contract yet;
uploading + activating a `TemplateVersion` is a normal Application-layer
operation, not part of this migration.

✅ `01A_GDKQ.export_name_pattern` — CONFIRMED by user 2026-08-09 (outstanding
item #3 in CLAUDE.md, was flagged "⚠️ CẦN XÁC NHẬN" in §4.5): `01A_GDKQ -
{full_name}`. This differs from `01A_HD_GDN`'s `Mẫu 01A - {full_name}` on
purpose — both templates share the "01A" numbering, so they needed visibly
different export names to avoid collision for a customer signing both.

Idempotent: `ON CONFLICT (code) DO NOTHING`.

Revision ID: 20260811_008_seed_template
Revises: 20260811_007_seed_setting
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260811_008_seed_template"
down_revision = "20260811_007_seed_setting"
branch_labels = None
depends_on = None

_contract_template = sa.table(
    "contract_template",
    sa.column("id", PG_UUID(as_uuid=False)),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("category", sa.String),
    sa.column("party_schema", JSONB),
    sa.column("party_schema_version", sa.SmallInteger),
    sa.column("contract_fields", JSONB),
    sa.column("suppressed_variables", JSONB),
    sa.column("contract_no_pattern", sa.String),
    sa.column("contract_no_seq", sa.Integer),
    sa.column("export_name_pattern", sa.String),
    sa.column("requires_images", sa.Boolean),
    sa.column("is_active", sa.Boolean),
    sa.column("sort_order", sa.SmallInteger),
    sa.column("created_at", sa.DateTime(timezone=True)),
)

_SUPPRESSED_VARIABLES = ["contract_date", "contract_date_text", "day", "month", "year"]

_HD_GDN_PARTY_SCHEMA = [
    {
        "key": "holder",
        "label": "Khách hàng",
        "entity_type": "INDIVIDUAL",
        "required": True,
        "min": 1,
        "max": 1,
        "is_primary": True,
        "documents": [{"doc_type_code": "CCCD_CHIP", "required": True, "sides": ["FRONT", "BACK"]}],
        "collect": ["contact", "bank_account"],
        "extra_fields": [],
    }
]

_GDKQ_PARTY_SCHEMA = [
    {
        "key": "holder",
        "label": "Khách hàng",
        "entity_type": "INDIVIDUAL",
        "required": True,
        "min": 1,
        "max": 1,
        "is_primary": True,
        "documents": [{"doc_type_code": "CCCD_CHIP", "required": True, "sides": ["FRONT", "BACK"]}],
        "collect": ["contact"],
        "extra_fields": [
            {
                "key": "securities_account_no",
                "label": "Số tài khoản chứng khoán",
                "type": "securities_account",
                "required": True,
                "prefill_from": "customer.securities_account_no",
                "persist_to": "customer.securities_account_no",
                "render_style": {"bold": True},
            }
        ],
    }
]

# (id, code, name, category, party_schema, contract_no_pattern, export_name_pattern, sort_order)
_SEED_ROWS: list[tuple[str, str, str, str, list[dict], str, str, int]] = [
    (
        "018f1000-0000-7000-8000-000000000101",
        "01A_HD_GDN",
        "Mẫu số 01A/HĐ-GĐN",
        "Giao dịch ngân hàng",
        _HD_GDN_PARTY_SCHEMA,
        "01A-GDN-{yyyy}{MM}-{seq:05d}",
        "Mẫu 01A - {full_name}",
        10,
    ),
    (
        "018f1000-0000-7000-8000-000000000102",
        "01A_GDKQ",
        "Mẫu 01A/GDKQ",
        "Giao dịch chứng khoán",
        _GDKQ_PARTY_SCHEMA,
        "01A-KQ-{yyyy}{MM}-{seq:05d}",
        "01A_GDKQ - {full_name}",  # ✅ confirmed by user 2026-08-09
        20,
    ),
]


def upgrade() -> None:
    for template_id, code, name, category, party_schema, contract_no_pattern, export_name_pattern, sort_order in _SEED_ROWS:
        op.execute(
            pg_insert(_contract_template)
            .values(
                id=template_id,
                code=code,
                name=name,
                category=category,
                party_schema=party_schema,
                party_schema_version=1,
                contract_fields=[],
                suppressed_variables=_SUPPRESSED_VARIABLES,
                contract_no_pattern=contract_no_pattern,
                contract_no_seq=0,
                export_name_pattern=export_name_pattern,
                requires_images=False,
                is_active=True,
                sort_order=sort_order,
                created_at=sa.func.now(),
            )
            .on_conflict_do_nothing(index_elements=["code"])
        )


def downgrade() -> None:
    codes = [row[1] for row in _SEED_ROWS]
    op.execute(_contract_template.delete().where(_contract_template.c.code.in_(codes)))
