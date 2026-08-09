"""SQLAlchemy declarative base and shared column mixins (§4.3 quy ước chung).

✅ Verified 2026-08-09: `upgrade head → downgrade base → upgrade head` runs
clean against real PostgreSQL 18.4 (§4.9). Structural correctness (table/
column/constraint/FK shape) is additionally covered by
`tests/unit/infrastructure/persistence/` via `Base.metadata` introspection,
which needs no live database and catches regressions fast.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ⭐ §4.3.1 naming convention — kept close enough to the doc's rule that
# Alembic autogenerate and the design doc agree on names; tables needing an
# exact multi-word name (e.g. `ck_customer__issue_place_valid`) pass an
# explicit `name=` on the constraint instead of relying on this default.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s__%(column_0_name)s",
    "uq": "uq_%(table_name)s__%(column_0_name)s",
    "ck": "ck_%(table_name)s__%(constraint_name)s",
    "fk": "fk_%(table_name)s__%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model.

    ⭐ Bug fixed 2026-08-09 (found by actually inserting a tz-aware datetime
    against real PostgreSQL — asyncpg raised `TypeError: can't subtract
    offset-naive and offset-aware datetimes`): every bare `Mapped[datetime]`
    column across all 15 tables with timestamps was mapping to a plain
    `TIMESTAMP WITHOUT TIME ZONE`, since SQLAlchemy's built-in type map for
    `datetime` defaults to `timezone=False`. That silently violated DB-12
    ("Mọi timestamp là TIMESTAMPTZ, lưu UTC") across the entire schema.
    `type_annotation_map` fixes it in exactly one place instead of 20 — every
    model just declares `Mapped[datetime]` and gets `TIMESTAMPTZ` for free.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[type, Any]] = {datetime: DateTime(timezone=True)}


class UuidPkMixin:
    """`id UUID PK` (DB-01) — the application supplies a UUIDv7 via `IIdGenerator`;
    there is deliberately no server-side default (client-generated ids, per DB-01's
    own rationale: "client sinh trước được").
    """

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)


class CreatedAtMixin:
    """`created_at TIMESTAMPTZ NOT NULL` (§4.3.2) — every table has this."""

    created_at: Mapped[datetime] = mapped_column(nullable=False)


class CreatedByMixin:
    """`created_by VARCHAR(64) NOT NULL` — a Windows account name, not a FK (§4.3.2)."""

    created_by: Mapped[str] = mapped_column(nullable=False)
