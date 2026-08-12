"""`RegisterTemplateVersionUseCase` — upload one `.docx` and make it active.

Backs two endpoints of §5.2 (#32 `POST /templates/{id}/versions` and #33
`.../activate`) and the first-run bootstrap. They are one Use Case rather than
two because uploading a version nobody activates leaves the template exactly
as unusable as before, and every caller so far wants both halves.

## Ordering, and why the file is written before the transaction

Same rule as §12.14: file operations stay outside the transaction. So:

    inspect (no I/O, no render)         -> reject INVALID here, before any write
    TemplateStore.save()                -> plaintext, write-temp/verify/rename
    T1  INSERT template_version
        + archive the version it replaces
        + contract_template.active_version_id -> commit

⚠️ A transaction failure after the file lands leaves an orphan `.docx` in the
store, so it is deleted on that path — the mirror of what
`GenerateContractUseCase` does for the Vault. The asymmetry with a Vault
orphan is worth naming: an orphan template is *inert* (no row points at it, so
no contract can select it), whereas an orphan `.enc` is customer data.

⭐ Inspection happens before anything is written, not after. §9.9's whole
argument is that a template is untrusted input; writing it to disk first and
validating second would mean a rejected template still landed in the store.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Protocol

from loguru import logger

from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import EntityNotFound, ValidationError
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.domain.ports.templates import ITemplateInspector, TemplateInspection


class ITemplateStore(Protocol):
    async def get(self, entity_id: object) -> Template | None: ...

    async def update(self, entity: Template, expected_version: int | None = None) -> None: ...


class ITemplateVersionStore(Protocol):
    async def list_for_template(self, template_id: uuid.UUID) -> list[TemplateVersion]: ...

    async def add(self, entity: TemplateVersion) -> None: ...

    async def update(
        self, entity: TemplateVersion, expected_version: int | None = None
    ) -> None: ...


class ITemplateUnitOfWork(Protocol):
    templates: ITemplateStore
    template_versions: ITemplateVersionStore

    async def __aenter__(self) -> ITemplateUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class IStoredTemplateFile(Protocol):
    """What `TemplateStore.save()` reports back.

    Structural, not imported: `StoredTemplate` is a dataclass in
    `infrastructure.storage`, and Application sits **above** Infrastructure in
    the import-linter contract. Naming the three attributes here keeps the
    call site honestly typed without reaching down a layer.
    """

    @property
    def relative_path(self) -> str: ...

    @property
    def sha256(self) -> bytes: ...

    @property
    def size_bytes(self) -> int: ...


class IPlaintextTemplateStore(Protocol):
    """`TemplateStore` (Infrastructure), seen from Application."""

    def save(
        self, data: bytes, template_code: str, version_no: int
    ) -> IStoredTemplateFile: ...

    def resolve(self, relative_path: str) -> Path: ...


@dataclass(frozen=True, slots=True)
class RegisterTemplateVersionCommand:
    template_id: uuid.UUID
    file_bytes: bytes
    original_filename: str
    created_by: str
    changelog: str | None = None
    activate: bool = True


@dataclass(frozen=True, slots=True)
class RegisteredTemplateVersion:
    version_id: uuid.UUID
    template_id: uuid.UUID
    template_code: str
    version_no: int
    file_path: str
    file_sha256: bytes
    file_size_bytes: int
    validation_status: TemplateValidationStatus
    is_active: bool
    declared_variables: tuple[str, ...] = ()
    diagnostics: tuple[dict[str, object], ...] = field(default_factory=tuple)


class RegisterTemplateVersionUseCase:
    """Register (and by default activate) one version of a template."""

    def __init__(
        self,
        uow_factory: Callable[[], ITemplateUnitOfWork],
        inspector: ITemplateInspector,
        template_store: IPlaintextTemplateStore,
        clock: IClock,
        id_generator: IIdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._inspector = inspector
        self._template_store = template_store
        self._clock = clock
        self._id_generator = id_generator

    async def execute(
        self, command: RegisterTemplateVersionCommand
    ) -> RegisteredTemplateVersion:
        async with self._uow_factory() as uow:
            template = await uow.templates.get(command.template_id)
            if template is None or template.is_deleted:
                raise EntityNotFound(
                    "Không tìm thấy mẫu hợp đồng.",
                    details={"template_id": str(command.template_id)},
                )
            existing = await uow.template_versions.list_for_template(command.template_id)

        inspection = self._inspect(template, command.file_bytes)
        version_no = max((v.version_no for v in existing), default=0) + 1
        stored = self._template_store.save(
            command.file_bytes, template.code, version_no
        )

        try:
            return await self._persist(
                command, template, inspection, existing, version_no, stored
            )
        except Exception:
            self._discard(stored.relative_path)
            raise

    def _inspect(self, template: Template, file_bytes: bytes) -> TemplateInspection:
        inspection = self._inspector.inspect(
            file_bytes, template.party_schema, template.contract_fields
        )
        if not inspection.is_registrable:
            raise ValidationError(
                "File mẫu không hợp lệ — xem chi tiết chẩn đoán.",
                details={
                    "template_code": template.code,
                    "diagnostics": [
                        {"code": d.code, "message": d.message} for d in inspection.errors
                    ],
                },
            )
        return inspection

    async def _persist(
        self,
        command: RegisterTemplateVersionCommand,
        template: Template,
        inspection: TemplateInspection,
        existing: Sequence[TemplateVersion],
        version_no: int,
        stored: IStoredTemplateFile,
    ) -> RegisteredTemplateVersion:
        now: datetime = self._clock.now()
        version = TemplateVersion(
            id=self._id_generator.new_id(),
            template_id=template.id,
            version_no=version_no,
            file_path=stored.relative_path,
            file_sha256=stored.sha256,
            file_size_bytes=stored.size_bytes,
            original_filename=command.original_filename,
            declared_variables=list(inspection.declared),
            required_variables=list(inspection.required),
            optional_variables=list(inspection.optional),
            unknown_variables=list(inspection.unknown),
            richtext_variables=list(inspection.richtext_vars),
            has_loops=inspection.has_loops,
            has_conditionals=inspection.has_conditionals,
            validation_status=inspection.status,
            validation_report={
                "diagnostics": [
                    {
                        "code": d.code,
                        "severity": d.severity.value,
                        "message": d.message,
                        "variable": d.variable,
                        "paragraph": d.paragraph,
                        "part": d.part,
                    }
                    for d in inspection.diagnostics
                ]
            },
            changelog=command.changelog,
            created_by=command.created_by,
            created_at=now,
        )

        async with self._uow_factory() as uow:
            await uow.template_versions.add(version)

            if command.activate:
                # ⭐ Archive the version being replaced, never delete it: an old
                # contract must still regenerate byte-identically years later
                # (P-09), and the row is what proves which file it used.
                for previous in existing:
                    if previous.id == template.active_version_id and not previous.is_archived:
                        previous.archive(now)
                        await uow.template_versions.update(previous)
                template.activate_version(version.id, now)
                await uow.templates.update(template)

            await uow.commit()

        logger.info(
            "template version registered",
            template_code=template.code,
            version_no=version_no,
            validation_status=inspection.status.value,
            declared=len(inspection.declared),
            activated=command.activate,
        )
        return RegisteredTemplateVersion(
            version_id=version.id,
            template_id=template.id,
            template_code=template.code,
            version_no=version_no,
            file_path=version.file_path,
            file_sha256=version.file_sha256,
            file_size_bytes=version.file_size_bytes,
            validation_status=inspection.status,
            is_active=command.activate,
            declared_variables=tuple(inspection.declared),
            diagnostics=tuple(
                {"code": d.code, "severity": d.severity.value, "message": d.message}
                for d in inspection.diagnostics
            ),
        )

    def _discard(self, relative_path: str) -> None:
        """Best-effort removal of a file no row points at."""
        try:
            self._template_store.resolve(relative_path).unlink(missing_ok=True)
        except Exception as exc:  # pragma: no cover - compensation must not mask
            logger.warning(
                "orphan template file left behind",
                relative_path=relative_path,
                error=type(exc).__name__,
            )
