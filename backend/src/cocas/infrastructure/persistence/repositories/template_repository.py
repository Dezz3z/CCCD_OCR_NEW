"""`SqlAlchemyTemplateRepository`."""
from __future__ import annotations

from cocas.domain.entities.template import Template
from cocas.infrastructure.persistence.models.contract_template import ContractTemplateModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyTemplateRepository(SqlAlchemyRepository[Template, ContractTemplateModel]):
    model = ContractTemplateModel

    def _to_domain(self, row: ContractTemplateModel) -> Template:
        return Template(
            id=row.id,
            code=row.code,
            name=row.name,
            party_schema=list(row.party_schema),
            contract_no_pattern=row.contract_no_pattern,
            export_name_pattern=row.export_name_pattern,
            created_at=row.created_at,
            description=row.description,
            category=row.category,
            active_version_id=row.active_version_id,
            party_schema_version=row.party_schema_version,
            contract_fields=list(row.contract_fields),
            suppressed_variables=list(row.suppressed_variables),
            contract_no_seq=row.contract_no_seq,
            requires_images=row.requires_images,
            is_active=row.is_active,
            sort_order=row.sort_order,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )

    def _apply_to_row(self, entity: Template, row: ContractTemplateModel) -> None:
        row.id = entity.id
        row.code = entity.code
        row.name = entity.name
        row.description = entity.description
        row.category = entity.category
        row.active_version_id = entity.active_version_id
        row.party_schema = list(entity.party_schema)
        row.party_schema_version = entity.party_schema_version
        row.contract_fields = list(entity.contract_fields)
        row.suppressed_variables = list(entity.suppressed_variables)
        row.contract_no_pattern = entity.contract_no_pattern
        row.contract_no_seq = entity.contract_no_seq
        row.export_name_pattern = entity.export_name_pattern
        row.requires_images = entity.requires_images
        row.is_active = entity.is_active
        row.sort_order = entity.sort_order
        row.created_at = entity.created_at
        row.updated_at = entity.updated_at
        row.deleted_at = entity.deleted_at
