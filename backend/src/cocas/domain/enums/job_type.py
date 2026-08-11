"""Background job types (§4.3.3 `JobType`, `job.job_type`).

⭐ D2.1 — 6 → 5 giá trị: `PDF_CONVERT` đã bị gỡ cùng khâu xuất PDF (§9.13).
"""
from enum import Enum


class JobType(str, Enum):
    """The kind of work a queued `job` row represents."""

    OCR = "OCR"
    BACKUP = "BACKUP"
    RETENTION_PURGE = "RETENTION_PURGE"
    ORPHAN_SWEEP = "ORPHAN_SWEEP"
    TEMPLATE_VALIDATE = "TEMPLATE_VALIDATE"
