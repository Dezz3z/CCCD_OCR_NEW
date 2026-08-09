"""Tests for ContractParty entity (§4.4.11)."""
import uuid
from datetime import UTC, datetime

from cocas.domain.entities.contract_party import ContractParty
from cocas.domain.enums.entity_type import EntityType

NOW = datetime(2026, 8, 9, tzinfo=UTC)


class TestConstruction:
    def test_v1_holder_party(self) -> None:
        party = ContractParty(
            id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            party_key="holder",
            party_index=0,
            party_label="Khách hàng",
            entity_type=EntityType.INDIVIDUAL,
            customer_id=uuid.uuid4(),
            sort_order=0,
            created_at=NOW,
            is_primary=True,
        )
        assert party.entity_type == EntityType.INDIVIDUAL
        assert party.bank_account_id is None
        assert party.party_extra == {}

    def test_party_extra_holds_securities_account(self) -> None:
        party = ContractParty(
            id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            party_key="holder",
            party_index=0,
            party_label="Khách hàng",
            entity_type=EntityType.INDIVIDUAL,
            customer_id=uuid.uuid4(),
            sort_order=0,
            created_at=NOW,
            party_extra={"securities_account_no": "008C123456"},
        )
        assert party.party_extra["securities_account_no"] == "008C123456"
