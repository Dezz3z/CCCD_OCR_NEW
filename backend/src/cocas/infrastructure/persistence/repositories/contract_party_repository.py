"""`SqlAlchemyContractPartyRepository`."""
from __future__ import annotations

from cocas.domain.entities.contract_party import ContractParty
from cocas.domain.enums.entity_type import EntityType
from cocas.infrastructure.persistence.models.contract_party import ContractPartyModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyContractPartyRepository(SqlAlchemyRepository[ContractParty, ContractPartyModel]):
    model = ContractPartyModel

    def _to_domain(self, row: ContractPartyModel) -> ContractParty:
        return ContractParty(
            id=row.id,
            contract_id=row.contract_id,
            party_key=row.party_key,
            party_index=row.party_index,
            party_label=row.party_label,
            entity_type=EntityType(row.entity_type),
            customer_id=row.customer_id,
            sort_order=row.sort_order,
            created_at=row.created_at,
            bank_account_id=row.bank_account_id,
            ocr_session_id=row.ocr_session_id,
            is_primary=row.is_primary,
            party_extra=dict(row.party_extra) if row.party_extra else {},
        )

    def _apply_to_row(self, entity: ContractParty, row: ContractPartyModel) -> None:
        row.id = entity.id
        row.contract_id = entity.contract_id
        row.party_key = entity.party_key
        row.party_index = entity.party_index
        row.party_label = entity.party_label
        row.entity_type = entity.entity_type.value
        row.customer_id = entity.customer_id
        row.bank_account_id = entity.bank_account_id
        row.ocr_session_id = entity.ocr_session_id
        row.is_primary = entity.is_primary
        row.party_extra = dict(entity.party_extra)
        row.sort_order = entity.sort_order
        row.created_at = entity.created_at
