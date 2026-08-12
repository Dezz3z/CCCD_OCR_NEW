"""`SqlAlchemyJobRepository` — ⭐ the queue itself (§4.4.5, pitfall #1).

There is no `asyncio.Queue` anywhere in this system and there must never be
one. The `job` table **is** the queue, and that is a durability decision, not a
stylistic one: an in-process queue loses every pending job when the backend
restarts, and the backend is a child process the Tauri supervisor restarts on
its own initiative (P5). A user whose OCR silently vanished because the
supervisor bounced would have no way to tell that from OCR that simply failed.

⭐ `claim_next()` is `SELECT … FOR UPDATE SKIP LOCKED`. `SKIP LOCKED` is what
makes it a queue rather than a lock convoy: a second worker steps over the row
being claimed instead of blocking behind it. v1.0 runs a single worker
(`api_workers = 1`), so today it never skips anything — it is written this way
because the day a second worker appears is not the day to discover the query
serialises.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.infrastructure.persistence.models.job import JobModel


class SqlAlchemyJobRepository:
    """Enqueue, claim and finish rows of `job`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        job_id: uuid.UUID,
        job_type: JobType,
        correlation_id: str,
        now: datetime,
        target_id: uuid.UUID | None = None,
        target_type: str | None = None,
        payload: dict[str, object] | None = None,
        priority: int = 100,
    ) -> uuid.UUID:
        self._session.add(
            JobModel(
                id=job_id,
                job_type=job_type.value,
                status=JobStatus.QUEUED.value,
                target_id=target_id,
                target_type=target_type,
                payload=payload,
                priority=priority,
                attempt_count=0,
                max_attempts=3,
                correlation_id=correlation_id,
                created_at=now,
            )
        )
        await self._session.flush()
        return job_id

    async def claim_next(self, now: datetime) -> JobModel | None:
        """Take the highest-priority queued job, or `None`.

        ⚠️ `with_for_update(skip_locked=True)` must be on the SELECT, not a
        separate lock afterwards: between an unlocked SELECT and a later
        UPDATE, another worker can claim the same row, and both would run the
        same OCR against the same session.
        """
        statement = (
            select(JobModel)
            .where(
                JobModel.status == JobStatus.QUEUED.value,
                (JobModel.next_retry_at.is_(None)) | (JobModel.next_retry_at <= now),
            )
            .order_by(JobModel.priority, JobModel.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None

        row.status = JobStatus.RUNNING.value
        row.started_at = now
        row.heartbeat_at = now
        row.attempt_count += 1
        row.progress_percent = 0
        await self._session.flush()
        return row

    async def get(self, job_id: uuid.UUID) -> JobModel | None:
        return await self._session.get(JobModel, job_id)

    async def report_progress(
        self, job_id: uuid.UUID, percent: int, message: str, now: datetime
    ) -> None:
        row = await self._session.get(JobModel, job_id)
        if row is None:
            return
        row.progress_percent = max(0, min(100, percent))
        row.progress_message = message[:150]
        row.heartbeat_at = now

    async def finish(
        self,
        job_id: uuid.UUID,
        *,
        status: JobStatus,
        now: datetime,
        error_code: str | None = None,
        error_detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        row = await self._session.get(JobModel, job_id)
        if row is None:
            return
        row.status = status.value
        row.finished_at = now
        row.error_code = error_code
        row.error_detail = error_detail
        row.is_retryable_error = retryable
        if status is JobStatus.SUCCEEDED:
            row.progress_percent = 100

    async def requeue_stale(self, older_than: datetime, now: datetime) -> int:
        """Return jobs whose worker died back to `QUEUED` (§12.15).

        ⭐ Identified by a stale `heartbeat_at`, not by elapsed time since
        `started_at`: a long OCR run is not a dead one, and the difference
        between "slow" and "gone" is whether anything is still reporting.
        """
        statement = select(JobModel).where(
            JobModel.status == JobStatus.RUNNING.value,
            JobModel.heartbeat_at < older_than,
        )
        rows = (await self._session.execute(statement)).scalars().all()
        for row in rows:
            if row.attempt_count >= row.max_attempts:
                row.status = JobStatus.FAILED.value
                row.finished_at = now
                row.error_code = "WORKER_LOST"
                row.error_detail = "Tiến trình xử lý dừng đột ngột quá số lần cho phép."
                row.is_retryable_error = False
            else:
                row.status = JobStatus.QUEUED.value
                row.started_at = None
                row.heartbeat_at = None
        await self._session.flush()
        return len(rows)
