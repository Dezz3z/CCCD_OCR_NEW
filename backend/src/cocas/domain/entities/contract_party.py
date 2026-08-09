"""ContractParty entity (§4.4.11 `contract_party` — ⭐ the multi-party hinge, ADR-16)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cocas.domain.enums.entity_type import EntityType


@dataclass(slots=True)
class ContractParty:
    """One party's slot in a contract. v1.0 always has exactly one row
    (`party_key="holder"`) — kept as its own table/entity so a second party
    can be added later by a one-line migration instead of a rewrite (§4.4.11).
    """

    id: uuid.UUID
    contract_id: uuid.UUID
    party_key: str
    party_index: int
    party_label: str
    entity_type: EntityType
    customer_id: uuid.UUID
    sort_order: int
    created_at: datetime
    bank_account_id: uuid.UUID | None = None
    ocr_session_id: uuid.UUID | None = None
    is_primary: bool = False
    party_extra: dict[str, object] = field(default_factory=dict)
