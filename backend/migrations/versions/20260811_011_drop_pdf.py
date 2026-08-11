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
    """Drop then re-create a CHECK; `name` is the short form (no `ck_<table>__`)."""
    op.drop_constraint(f"ck_{table}__{name}", table, type_="check")
    op.create_check_constraint(name, table, expression)


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
    _replace_check("contract", "status_valid", f"status IN {_NEW_CONTRACT_STATUS}")
    _replace_check("job", "job_type_valid", f"job_type IN {_NEW_JOB_TYPE}")
    _replace_check(
        "contract_document", "doc_type_valid", f"doc_type IN {_NEW_DOC_TYPE}"
    )

    op.drop_column("contract_document", "page_count")


def downgrade() -> None:
    # ⚠️ Widening back is safe; the deleted rows are not restored. A downgrade
    # gives you a schema that *accepts* PDF again, not a database that
    # remembers the PDFs it had — that data is gone with the D2.1 decision and
    # inventing rows here would be worse than an honest gap.
    op.add_column(
        "contract_document", sa.Column("page_count", sa.SmallInteger(), nullable=True)
    )
    _replace_check("contract", "status_valid", f"status IN {_OLD_CONTRACT_STATUS}")
    _replace_check("job", "job_type_valid", f"job_type IN {_OLD_JOB_TYPE}")
    _replace_check(
        "contract_document", "doc_type_valid", f"doc_type IN {_OLD_DOC_TYPE}"
    )
