"""Background job queue port (§12.15 `JobRunner`) — port 15 of 18.

⭐ CLAUDE.md pitfall #1: the `job` TABLE is the queue. There is no
`asyncio.Queue` anywhere. `enqueue()` is an `INSERT`; the runner polls
`SELECT … FOR UPDATE SKIP LOCKED` every 500 ms. One source of truth, and
the queue survives a crash for free.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType

DEFAULT_PRIORITY = 100


@dataclass(frozen=True, slots=True)
class JobTarget:
    """The polymorphic subject of a job — intentionally NOT a hard FK (§4.4.5)."""

    target_id: uuid.UUID
    target_type: str


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """A job's observable state, as reported by `get_status()`."""

    id: uuid.UUID
    job_type: JobType
    status: JobStatus
    attempt_count: int
    max_attempts: int
    progress_percent: int | None = None
    progress_message: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    is_retryable_error: bool | None = None
    target: JobTarget | None = None
    payload: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class IJobQueue(Protocol):
    """⭐ Port 15 — enqueue and observe background work.

    Invariants of any implementation:
      - concurrency is 1 (single machine, single user);
      - `heartbeat_at` is refreshed every 10s while a job runs, so a dead
        worker is detectable;
      - ⭐ an exception inside a handler NEVER kills the worker — it is
        caught, written to `job.error_detail`, and the job becomes FAILED;
      - retries only happen for errors flagged `is_retryable_error`.
    """

    async def enqueue(
        self,
        job_type: JobType,
        target: JobTarget | None = None,
        payload: dict[str, object] | None = None,
        priority: int = DEFAULT_PRIORITY,
    ) -> uuid.UUID:
        """Insert a QUEUED job row and return its id. Lower `priority` runs first."""
        ...

    async def cancel(self, job_id: uuid.UUID) -> bool:
        """Request cancellation. Returns False if the job already finished."""
        ...

    async def get_status(self, job_id: uuid.UUID) -> JobSnapshot | None: ...

    async def start(self) -> None:
        """Begin polling. Also recovers stale RUNNING jobs (heartbeat > 5 min old)."""
        ...

    async def stop(self, graceful_timeout: float) -> None:
        """Stop polling, waiting up to `graceful_timeout` for the current job."""
        ...
