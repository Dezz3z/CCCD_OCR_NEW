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

🔴🔴 **The consequence, found 2026-08-12 on the first `upgrade head` since P1:
this migration does not create the schema as it stood at revision 002 — it
creates the schema as the models stand TODAY.** `create_all()` reads live
`Base.metadata`, so the moment a later revision adds a column and the model
gains it too, revision 002 starts emitting that column, and the later
`op.add_column()` hits `DuplicateColumnError` on a fresh database. Measured:
`identity_markers` (010) failed exactly this way, and `page_count` (011) would
have failed as its mirror image — `op.drop_column()` for a column that today's
models no longer declare, so 002 never created it.

Every structural step after this one is therefore written **state-aware**
(`_column_exists()` before `add_column`/`drop_column`). That is not defensive
padding: on a fresh database the later revision has nothing to do, and on a
database created before it the revision does the real work. The alternative —
freezing 19 tables of hand-written DDL here — would reintroduce exactly the
model/migration drift this file exists to prevent, and would make the
`Base.metadata` introspection tests stop testing what the database actually is.

✅ Verified 2026-08-09 against real PostgreSQL 18.4 — see
`cocas/infrastructure/persistence/models/base.py`'s docstring. ⭐ Re-verified
2026-08-12 end to end (`001 → 011`, then `downgrade base`, then `upgrade head`)
after the three defects above were fixed.

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
