"""seed_bank_directory

Seeds `bank_directory` (§4.4.15) — used by V-FRM-007 to check a bank
account number's length against the selected bank.

⚠️ PARTIAL SEED: the design doc names "~50 ngân hàng" but only spells out
account-number length ranges for these 10 in its own text (§4.4.15's
comparison table). Rather than inventing plausible-but-unverified lengths
for the other ~40 banks, only these 10 (fully sourced from the design doc
itself) are seeded. The `bin` (NAPAS 6-digit) values are commonly-published
figures from general knowledge, NOT verified via lookup this session —
cross-check before relying on them (they aren't used by any validation
rule; only `account_min_len`/`account_max_len` are). Completing the full
directory is real business data the user/admin should supply — new rows
can be added anytime via the Settings UI (DB-07), no migration required.

Idempotent: `ON CONFLICT (code) DO NOTHING`.

Revision ID: 20260811_006_seed_bank
Revises: 20260811_005_seed_province
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260811_006_seed_bank"
down_revision = "20260811_005_seed_province"
branch_labels = None
depends_on = None

_bank_directory = sa.table(
    "bank_directory",
    sa.column("code", sa.String),
    sa.column("short_name", sa.String),
    sa.column("full_name", sa.String),
    sa.column("bin", sa.String),
    sa.column("account_min_len", sa.Integer),
    sa.column("account_max_len", sa.Integer),
    sa.column("is_active", sa.Boolean),
    sa.column("sort_order", sa.SmallInteger),
)

# (code, short_name, full_name, bin, min_len, max_len, sort_order)
_SEED_ROWS: list[tuple[str, str, str, str, int, int, int]] = [
    ("VCB", "Vietcombank", "Ngân hàng TMCP Ngoại thương Việt Nam", "970436", 13, 13, 10),
    ("TCB", "Techcombank", "Ngân hàng TMCP Kỹ thương Việt Nam", "970407", 14, 14, 20),
    ("BIDV", "BIDV", "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam", "970418", 14, 14, 30),
    ("CTG", "VietinBank", "Ngân hàng TMCP Công thương Việt Nam", "970415", 12, 12, 40),
    ("MB", "MB Bank", "Ngân hàng TMCP Quân đội", "970422", 10, 13, 50),
    ("ACB", "ACB", "Ngân hàng TMCP Á Châu", "970416", 6, 16, 60),
    ("STB", "Sacombank", "Ngân hàng TMCP Sài Gòn Thương Tín", "970403", 12, 16, 70),
    ("VPB", "VPBank", "Ngân hàng TMCP Việt Nam Thịnh Vượng", "970432", 9, 15, 80),
    ("AGB", "Agribank", "Ngân hàng Nông nghiệp và Phát triển Nông thôn Việt Nam", "970405", 13, 13, 90),
    ("TPB", "TPBank", "Ngân hàng TMCP Tiên Phong", "970423", 8, 15, 100),
]


def upgrade() -> None:
    assert len(_SEED_ROWS) == 10
    for code, short_name, full_name, bin_code, min_len, max_len, sort_order in _SEED_ROWS:
        op.execute(
            pg_insert(_bank_directory)
            .values(
                code=code,
                short_name=short_name,
                full_name=full_name,
                bin=bin_code,
                account_min_len=min_len,
                account_max_len=max_len,
                is_active=True,
                sort_order=sort_order,
            )
            .on_conflict_do_nothing(index_elements=["code"])
        )


def downgrade() -> None:
    codes = [row[0] for row in _SEED_ROWS]
    op.execute(_bank_directory.delete().where(_bank_directory.c.code.in_(codes)))
