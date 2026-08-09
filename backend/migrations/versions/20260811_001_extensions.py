"""extensions

⭐ Must run BEFORE `initial_schema` (§4.7, §4.9 — order fixed 2026-08-09):
`initial_schema` creates `ix_customer__name_trgm`, a GIN index using the
`gin_trgm_ops` operator class, which only exists once `pg_trgm` is enabled.
Running these in the original doc order (schema first, extensions second)
fails on a fresh database.

Revision ID: 20260811_001_extensions
Revises:
Create Date: 2026-08-11

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260811_001_extensions"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm: trigram fuzzy matching, backs ix_customer__name_trgm (§4.7).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # pgcrypto: available for auxiliary hashing needs (§4.7) — application-level
    # AES-256-GCM (ICryptoService) does not depend on this, it uses `cryptography`.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
