"""`system_setting` (§4.4.17) — admin-editable config, ~30-row seed."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base


class SystemSettingModel(Base):
    __tablename__ = "system_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    # ⭐ Wraps a single JSON-typed value (bool/int/float/string/list/dict per
    # `value_type`) — e.g. `ocr.review_threshold` stores the bare number
    # `0.85`, not an object — so this is `object`, not `dict[str, object]`.
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    default_value: Mapped[object] = mapped_column(JSONB, nullable=False)
    constraints: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    label_vi: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_restart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
