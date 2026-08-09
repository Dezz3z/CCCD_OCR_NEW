"""`contract_party` (§4.4.11) — ⭐ the multi-party hinge kept at v1.0 on purpose (ADR-16)."""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class ContractPartyModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "contract_party"
    __table_args__ = (
        UniqueConstraint("contract_id", "party_key", "party_index", name="uq_contract_party__slot"),
        Index(
            "uq_contract_party__one_primary",
            "contract_id",
            unique=True,
            postgresql_where="is_primary",
        ),
        Index("ix_contract_party__customer", "customer_id"),
        # ⭐ v1.0 restricts entity_type to INDIVIDUAL — see EntityType enum's docstring
        # (docs/design/CLAUDE.md pitfall / ADR-16 B1): nest ORGANIZATION in later by
        # widening this CHECK, not by redesigning the table.
        CheckConstraint("entity_type IN ('INDIVIDUAL')", name="entity_type_v1_individual_only"),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), nullable=False
    )
    party_key: Mapped[str] = mapped_column(String(40), nullable=False)
    party_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    party_label: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(15), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bank_account.id", ondelete="SET NULL"), nullable=True
    )
    ocr_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ocr_session.id", ondelete="SET NULL"), nullable=True
    )
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False)
    party_extra: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
