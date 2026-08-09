"""Backup run status (§4.3.3 `BackupStatus`, `backup_record.status`)."""
from enum import Enum


class BackupStatus(str, Enum):
    """Lifecycle status of a `.cocasbak` backup run."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    VERIFIED = "VERIFIED"
    CORRUPTED = "CORRUPTED"
