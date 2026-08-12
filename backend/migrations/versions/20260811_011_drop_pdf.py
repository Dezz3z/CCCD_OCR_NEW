"""drop_pdf

⭐ **D2.1 — PDF export and LibreOffice are gone; `.docx` is the only output**
(design §9.13). This migration brings an already-migrated database in line
with the narrowed domain enums. A fresh install gets the same shape from
`002_initial_schema`, which builds every CHECK from those enums.

Four things change, and each one is a constraint that would otherwise reject
rows the new code never writes — or accept rows it can no longer read:

| # | Change | Why it cannot wait |
|---|---|---|
| 1 | `contract.status` CHECK: 9 → 6 values | A row left at `PDF_CONVERTING` cannot be loaded into the new `ContractStatus`; the enum lookup raises before any business code runs |
| 2 | `job.job_type` CHECK: 6 → 5 values | Same, for a queued `PDF_CONVERT` job — and `JobRunner` polls that table forever |
| 3 | `contract_document.doc_type` CHECK: 2 → 1 value | Same, for a PDF document row |
| 4 | `contract_document.page_count` dropped | Only ever meant "pages of the PDF"; `.docx` has no page count until a word processor lays it out |

⚠️ **Rows are migrated, not deleted.** Contracts stuck in a PDF stage move to
the state that describes what actually exists on disk: `DOCX_READY` and
`PDF_CONVERTING` and `PDF_FAILED` all mean *the `.docx` was written* — that is
`COMPLETED` under D2.1. Deleting them would destroy legal records (§4.4.10 —
`contract` rows are never hard-deleted). Queued `PDF_CONVERT` jobs are the one
exception: they describe work that no longer exists, so they are removed.

The three `document.libreoffice*` / `document.pdf_converter` settings rows go
too (28 → 25 keys, §4.4.17). Leaving them would put dead toggles on the
Settings screen — which reads that table, not a hardcoded list.

Revision ID: 20260811_011_drop_pdf
Revises: 20260811_010_markers_tier5
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op

from cocas.infrastructure.persistence.models.base import sql_in

# revision identifiers, used by Alembic.
revision = "20260811_011_drop_pdf"
down_revision = "20260811_010_markers_tier5"
branch_labels = None
depends_on = None

_OLD_CONTRACT_STATUS = (
    "DRAFT", "GENERATING", "DOCX_READY", "PDF_CONVERTING", "COMPLETED",
    "GENERATION_FAILED", "PDF_FAILED", "SUPERSEDED", "VOIDED",
)
_NEW_CONTRACT_STATUS = (
    "DRAFT", "GENERATING", "COMPLETED", "GENERATION_FAILED", "SUPERSEDED", "VOIDED",
)
_OLD_JOB_TYPE = (
    "OCR", "PDF_CONVERT", "BACKUP", "RETENTION_PURGE", "ORPHAN_SWEEP", "TEMPLATE_VALIDATE",
)
_NEW_JOB_TYPE = ("OCR", "BACKUP", "RETENTION_PURGE", "ORPHAN_SWEEP", "TEMPLATE_VALIDATE")
_OLD_DOC_TYPE = ("DOCX", "PDF")
_NEW_DOC_TYPE = ("DOCX",)

_DEAD_SETTING_KEYS = (
    "document.pdf_converter",
    "document.libreoffice_timeout_sec",
    "document.libreoffice_idle_shutdown_min",
)


def _replace_check(table: str, name: str, expression: str) -> None:
    """Drop then re-create a CHECK; `name` is the short form (no `ck_<table>__`).

    ⚠️ Both calls take the SHORT name. The docstring said so and the code then
    expanded it anyway — `env.py` supplies `target_metadata`, so `op` applies
    `NAMING_CONVENTION` itself and `f"ck_{table}__{name}"` came back out as
    `ck_contract__ck_contract__status_valid`. Measured 2026-08-12.
    """
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def _column_exists(table: str, column: str) -> bool:
    """Whether `table.column` is present in the live database right now.

    Needed because revision 002 runs `Base.metadata.create_all()` and therefore
    materialises **today's** models — see its docstring. `page_count` is gone
    from the models, so a fresh database never had it and the `drop_column`
    below has nothing to drop; a database created before D2.1 does have it.
    """
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    # 1 — data first: a narrowed CHECK is rejected while a violating row exists.
    op.execute(
        sa.text(
            "UPDATE contract SET status = 'COMPLETED' "
            "WHERE status IN ('DOCX_READY', 'PDF_CONVERTING', 'PDF_FAILED')"
        )
    )
    op.execute(sa.text("DELETE FROM job WHERE job_type = 'PDF_CONVERT'"))
    op.execute(sa.text("DELETE FROM contract_document WHERE doc_type = 'PDF'"))
    op.execute(
        sa.text("DELETE FROM system_setting WHERE key IN :keys").bindparams(
            sa.bindparam("keys", value=_DEAD_SETTING_KEYS, expanding=True)
        )
    )

    # 2 — then the constraints.
    #
    # ⭐ `sql_in`, not an f-string around the tuple: `_NEW_DOC_TYPE` has exactly
    # one member, and `repr(("DOCX",))` is `('DOCX',)` — the trailing comma is
    # Python, not SQL, and PostgreSQL answers `syntax error at or near ")"`.
    # The same defect shipped in `contract_document`'s model CHECK and broke
    # revision 002 outright; this copy sat one revision downstream, waiting.
    _replace_check("contract", "status_valid", sql_in("status", _NEW_CONTRACT_STATUS))
    _replace_check("job", "job_type_valid", sql_in("job_type", _NEW_JOB_TYPE))
    _replace_check(
        "contract_document", "doc_type_valid", sql_in("doc_type", _NEW_DOC_TYPE)
    )

    if _column_exists("contract_document", "page_count"):
        op.drop_column("contract_document", "page_count")


def downgrade() -> None:
    # ⚠️ Widening back is safe; the deleted rows are not restored. A downgrade
    # gives you a schema that *accepts* PDF again, not a database that
    # remembers the PDFs it had — that data is gone with the D2.1 decision and
    # inventing rows here would be worse than an honest gap.
    if not _column_exists("contract_document", "page_count"):
        op.add_column(
            "contract_document",
            sa.Column("page_count", sa.SmallInteger(), nullable=True),
        )
    _replace_check("contract", "status_valid", sql_in("status", _OLD_CONTRACT_STATUS))
    _replace_check("job", "job_type_valid", sql_in("job_type", _OLD_JOB_TYPE))
    _replace_check(
        "contract_document", "doc_type_valid", sql_in("doc_type", _OLD_DOC_TYPE)
    )
