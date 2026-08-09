"""Background job status (§4.3.3 `JobStatus`, `job.status`)."""
from enum import Enum


class JobStatus(str, Enum):
    """Lifecycle status of a `job` row — the queue's only source of truth."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
