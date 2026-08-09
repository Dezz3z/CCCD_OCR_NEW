"""`SqlAlchemyTemplateVersionRepository`."""
from __future__ import annotations

from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.infrastructure.persistence.models.template_version import TemplateVersionModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyTemplateVersionRepository(SqlAlchemyRepository[TemplateVersion, TemplateVersionModel]):
    model = TemplateVersionModel

    def _to_domain(self, row: TemplateVersionModel) -> TemplateVersion:
        return TemplateVersion(
            id=row.id,
            template_id=row.template_id,
            version_no=row.version_no,
            file_path=row.file_path,
            file_sha256=row.file_sha256,
            file_size_bytes=row.file_size_bytes,
            original_filename=row.original_filename,
            declared_variables=list(row.declared_variables),
            required_variables=list(row.required_variables),
            optional_variables=list(row.optional_variables),
            validation_status=TemplateValidationStatus(row.validation_status),
            created_by=row.created_by,
            created_at=row.created_at,
            unknown_variables=list(row.unknown_variables) if row.unknown_variables else [],
            richtext_variables=list(row.richtext_variables) if row.richtext_variables else [],
            has_loops=row.has_loops,
            has_conditionals=row.has_conditionals,
            validation_report=dict(row.validation_report) if row.validation_report else {},
            changelog=row.changelog,
            archived_at=row.archived_at,
        )

    def _apply_to_row(self, entity: TemplateVersion, row: TemplateVersionModel) -> None:
        row.id = entity.id
        row.template_id = entity.template_id
        row.version_no = entity.version_no
        row.file_path = entity.file_path
        row.file_sha256 = entity.file_sha256
        row.file_size_bytes = entity.file_size_bytes
        row.original_filename = entity.original_filename
        row.declared_variables = list(entity.declared_variables)
        row.required_variables = list(entity.required_variables)
        row.optional_variables = list(entity.optional_variables)
        row.unknown_variables = list(entity.unknown_variables)
        row.richtext_variables = list(entity.richtext_variables)
        row.has_loops = entity.has_loops
        row.has_conditionals = entity.has_conditionals
        row.validation_status = entity.validation_status.value
        row.validation_report = dict(entity.validation_report)
        row.changelog = entity.changelog
        row.created_by = entity.created_by
        row.created_at = entity.created_at
        row.archived_at = entity.archived_at
