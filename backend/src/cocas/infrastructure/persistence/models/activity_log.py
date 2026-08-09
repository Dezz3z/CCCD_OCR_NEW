"""`activity_log` (§4.4.16) — ⭐ append-only (DB-08): the app's DB role only has SELECT/INSERT
on this table (granted in the initial-schema migration, not enforceable via the ORM alone).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base


class ActivityLogModel(Base):
    __tablename__ = "activity_log"
    __table_args__ = (
        CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="outcome_valid"),
        Index("ix_activity_log__created", "created_at"),
        Index("ix_activity_log__entity", "entity_type", "entity_id", "created_at"),
        Index("ix_activity_log__action", "action", "created_at"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_username: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    detail: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
