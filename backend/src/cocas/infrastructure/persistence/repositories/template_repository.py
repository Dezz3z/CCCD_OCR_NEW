"""`SqlAlchemyTemplateRepository`."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from cocas.domain.entities.template import Template
from cocas.infrastructure.persistence.models.contract_template import ContractTemplateModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyTemplateRepository(SqlAlchemyRepository[Template, ContractTemplateModel]):
    model = ContractTemplateModel

    async def list_active(self) -> list[Template]:
        """Templates the user may pick from, in the order the UI shows them.

        ⚠️ Filters `deleted_at IS NULL` **and** `is_active` — they are not the
        same fact. A deactivated template is hidden from new contracts but its
        old contracts must still regenerate (P-09), which is why deactivating
        is not deleting and why both columns exist.
        """
        statement = (
            select(self.model)
            .where(self.model.deleted_at.is_(None), self.model.is_active.is_(True))
            .order_by(self.model.sort_order, self.model.code)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(row) for row in rows]

    async def get_for_update(self, template_id: uuid.UUID) -> Template | None:
        """⭐ `SELECT … FOR UPDATE` — the row lock `contract_no_seq` needs (DB-09).

        `Template.next_contract_sequence()` documents this as its
        precondition, and it is not decoration: `contract_no` is UNIQUE, so
        two concurrent generations reading the same counter produce one
        contract and one `DuplicateEntityError` **after** both have paid for
        a render. One Uvicorn worker makes that unlikely, not impossible —
        the `JobRunner` polls the same database from the same process.
        """
        statement = (
            select(self.model)
            .where(self.model.id == template_id)
            .with_for_update()
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

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
