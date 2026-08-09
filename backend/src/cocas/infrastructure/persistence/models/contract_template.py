"""`contract_template` (§4.4.8).

⭐ `active_version_id` → `template_version.id` is a deliberate reference
cycle with `template_version.template_id` → `contract_template.id`
(§4.6 #8: "created with insert order — create version first, then update
active_version_id"). `use_alter=True` lets Alembic emit this FK as a
separate `ALTER TABLE` after both tables exist, which is required to break
the cycle during `create_all`/migration.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class ContractTemplateModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "contract_template"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "template_version.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_contract_template__template_version",
        ),
        nullable=True,
    )
    party_schema: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    party_schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    contract_fields: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    suppressed_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    contract_no_pattern: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_no_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    export_name_pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    requires_images: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
