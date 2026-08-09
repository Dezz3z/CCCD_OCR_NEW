"""initial_schema

Creates all 19 tables (§4.4) with their columns, CHECK constraints, foreign
keys, and indexes.

⭐ Implementation note: this migration drives `Base.metadata.create_all()` /
`drop_all()` directly rather than hand-writing 19 sets of `op.create_table()`
calls. For a from-scratch initial schema, this guarantees the migration can
never drift from the ORM models — they are, structurally, the same object.
`create_all()` also correctly handles the deliberate `contract_template` ⟷
`template_version` reference cycle (§4.6 #8) via each column's
`use_alter=True`, emitting the second FK as a separate `ALTER TABLE` after
both tables exist.

⚠️ This pattern is appropriate ONLY for an initial schema. Every migration
after this one must describe an incremental, additive change with explicit
`op.*` calls (expand → migrate → contract, §4.9) — `create_all()` cannot
express "add one column" or "widen this CHECK" without recreating everything.

✅ Verified 2026-08-09 against real PostgreSQL 18.4 — see
`cocas/infrastructure/persistence/models/base.py`'s docstring.

Revision ID: 20260811_002_initial_schema
Revises: 20260811_001_extensions
Create Date: 2026-08-11

"""
from alembic import op

from cocas.infrastructure.persistence.models import Base

# revision identifiers, used by Alembic.
revision = "20260811_002_initial_schema"
down_revision = "20260811_001_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
