"""Background job types (§4.3.3 `JobType`, `job.job_type`)."""
from enum import Enum


class JobType(str, Enum):
    """The kind of work a queued `job` row represents."""

    OCR = "OCR"
    PDF_CONVERT = "PDF_CONVERT"
    BACKUP = "BACKUP"
    RETENTION_PURGE = "RETENTION_PURGE"
    ORPHAN_SWEEP = "ORPHAN_SWEEP"
    TEMPLATE_VALIDATE = "TEMPLATE_VALIDATE"
