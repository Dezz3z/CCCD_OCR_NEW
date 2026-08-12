"""`GET /templates` (§5.2 #27) and `GET /templates/{id}/requirements` (§5.3.1).

⭐ `requirements` is the endpoint that drives the wizard (P-12: "Template điều
khiển quy trình, không chỉ nội dung"). The SPA does not know that a GDN
contract needs a bank account and a GDKQ one does not — it reads `party_schema`
and builds the steps. Which is why this returns the schema **resolved**
(defaults filled in, `collect` normalised) rather than the raw JSONB: every
consumer would otherwise re-implement the same defaulting, and they would
diverge.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.exceptions import BusinessRuleViolation, EntityNotFound

#: §4.5's v1.0 limits, applied when a `party_schema` entry omits them.
_DEFAULT_ENTITY_TYPE = "INDIVIDUAL"
_DEFAULT_MIN = 1
_DEFAULT_MAX = 1


class ITemplateReader(Protocol):
    async def get(self, entity_id: object) -> Template | None: ...

    async def list_active(self) -> list[Template]: ...


class ITemplateVersionReader(Protocol):
    async def get(self, entity_id: object) -> TemplateVersion | None: ...


class ITemplateReadUnitOfWork(Protocol):
    templates: ITemplateReader
    template_versions: ITemplateVersionReader

    async def __aenter__(self) -> ITemplateReadUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    id: uuid.UUID
    code: str
    name: str
    category: str | None
    has_active_version: bool
    requires_images: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class TemplateRequirements:
    """Everything the wizard needs to render itself for one template."""

    template_id: uuid.UUID
    code: str
    name: str
    party_schema: tuple[dict[str, Any], ...]
    contract_fields: tuple[dict[str, Any], ...]
    suppressed_variables: tuple[str, ...]
    requires_images: bool
    active_version_no: int
    declared_variables: tuple[str, ...]
    required_variables: tuple[str, ...]
    #: ⭐ Derived, not stored: the number of wizard steps is
    #: `1 (choose template) + len(party_schema) + 1 (finish)`. Returning it
    #: stops the SPA from re-deriving the same arithmetic slightly differently.
    wizard_steps: int


class ListTemplatesUseCase:
    def __init__(self, uow_factory: Callable[[], ITemplateReadUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> list[TemplateSummary]:
        async with self._uow_factory() as uow:
            templates = await uow.templates.list_active()
        return [
            TemplateSummary(
                id=template.id,
                code=template.code,
                name=template.name,
                category=template.category,
                has_active_version=template.active_version_id is not None,
                requires_images=template.requires_images,
                sort_order=template.sort_order,
            )
            for template in templates
        ]


class GetTemplateRequirementsUseCase:
    def __init__(self, uow_factory: Callable[[], ITemplateReadUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, template_id: uuid.UUID) -> TemplateRequirements:
        async with self._uow_factory() as uow:
            template = await uow.templates.get(template_id)
            if template is None or template.is_deleted:
                raise EntityNotFound(
                    "Không tìm thấy mẫu hợp đồng.",
                    details={"template_id": str(template_id)},
                )
            if template.active_version_id is None:
                raise BusinessRuleViolation(
                    "Mẫu hợp đồng chưa có phiên bản được kích hoạt.",
                    code="TEMPLATE_NO_ACTIVE_VERSION",
                    hint="Vào Cài đặt → Mẫu hợp đồng và tải lên file .docx cho mẫu này.",
                )
            version = await uow.template_versions.get(template.active_version_id)
            if version is None:
                raise BusinessRuleViolation(
                    "Phiên bản đang kích hoạt của mẫu không còn tồn tại.",
                    code="TEMPLATE_ACTIVE_VERSION_MISSING",
                )

        parties = tuple(_resolve_party(entry) for entry in template.party_schema)
        return TemplateRequirements(
            template_id=template.id,
            code=template.code,
            name=template.name,
            party_schema=parties,
            contract_fields=tuple(dict(f) for f in template.contract_fields),
            suppressed_variables=tuple(template.suppressed_variables),
            requires_images=template.requires_images,
            active_version_no=version.version_no,
            declared_variables=tuple(version.declared_variables),
            required_variables=tuple(version.required_variables),
            wizard_steps=len(parties) + 2,
        )


def _resolve_party(entry: dict[str, object] | Sequence[object]) -> dict[str, Any]:
    """Fill in §4.5's v1.0 defaults for one `party_schema` entry."""
    source: dict[str, Any] = dict(entry) if isinstance(entry, dict) else {}
    collect = source.get("collect")
    return {
        "key": source.get("key", "holder"),
        "label": source.get("label", "Bên tham gia"),
        "entity_type": source.get("entity_type", _DEFAULT_ENTITY_TYPE),
        "min": int(source.get("min", _DEFAULT_MIN)),
        "max": int(source.get("max", _DEFAULT_MAX)),
        # ⚠️ An absent `collect` means "collect nothing extra", not "collect
        # everything". Defaulting the other way would make the wizard ask for a
        # bank account on a template that never mentions one.
        "collect": list(collect) if isinstance(collect, list | tuple) else [],
    }
