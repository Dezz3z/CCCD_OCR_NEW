"""`job` (§4.4.5) — ⭐ THE queue. `JobRunner` polls this table; there is no `asyncio.Queue`."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin, sql_in

_JOB_TYPE_VALUES = tuple(t.value for t in JobType)
_JOB_STATUS_VALUES = tuple(s.value for s in JobStatus)


class JobModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(sql_in("job_type", _JOB_TYPE_VALUES), name="job_type_valid"),
        CheckConstraint(sql_in("status", _JOB_STATUS_VALUES), name="status_valid"),
        CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100", name="progress_range"
        ),
        Index("ix_job__dispatch", "priority", "created_at", postgresql_where="status = 'QUEUED'"),
        Index("ix_job__stale", "heartbeat_at", postgresql_where="status = 'RUNNING'"),
        Index("ix_job__target", "target_type", "target_id"),
    )

    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    # ⭐ Deliberately NOT a ForeignKey — polymorphic target (§4.6 #17). Referential
    # integrity for this is enforced at the Application layer + the ORPHAN_SWEEP job.
    target_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    progress_message: Mapped[str | None] = mapped_column(String(150), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_retryable_error: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    worker_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
