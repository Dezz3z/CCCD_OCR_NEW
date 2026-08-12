"""`RegisterTemplateVersionUseCase` — upload + activate (§5.2 #32, #33)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from cocas.application.use_cases.template.register_template_version import (
    RegisterTemplateVersionCommand,
    RegisterTemplateVersionUseCase,
)
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import EntityNotFound, ValidationError
from cocas.domain.ports.templates import (
    DiagnosticSeverity,
    TemplateDiagnostic,
    TemplateInspection,
)

from .conftest import NOW, FakeClock, FakeUnitOfWork, SequentialIds

_DOCX = b"PK\x03\x04 template bytes"
_TEMPLATE_ID = uuid.UUID(int=0x7E)


@dataclass
class _Stored:
    relative_path: str
    sha256: bytes
    size_bytes: int


class _Store:
    def __init__(self, *, fail: bool = False) -> None:
        self.saved: list[tuple[str, int]] = []
        self.removed: list[str] = []
        self._fail = fail

    def save(self, data: bytes, template_code: str, version_no: int) -> _Stored:
        if self._fail:
            raise OSError("disk full")
        self.saved.append((template_code, version_no))
        return _Stored(
            relative_path=f"{template_code}/v{version_no}/template.docx",
            sha256=b"\x02" * 32,
            size_bytes=len(data),
        )

    def resolve(self, relative_path: str) -> Path:
        self.removed.append(relative_path)
        return Path("nonexistent") / relative_path


class _Inspector:
    def __init__(self, inspection: TemplateInspection | None = None) -> None:
        self.inspection = inspection or TemplateInspection(
            status=TemplateValidationStatus.VALID,
            declared=("full_name", "id_number"),
            required=("full_name",),
            optional=("id_number",),
        )
        self.calls: list[tuple[int, int]] = []

    def inspect(
        self,
        file_bytes: bytes,
        party_schema: object,
        contract_fields: object = (),
    ) -> TemplateInspection:
        self.calls.append((len(file_bytes), len(list(party_schema))))  # type: ignore[arg-type]
        return self.inspection


def _template(**overrides: object) -> Template:
    defaults: dict[str, object] = {
        "id": _TEMPLATE_ID,
        "code": "01A_HD_GDN",
        "name": "Mẫu số 01A/HĐ-GĐN",
        "party_schema": [{"key": "holder", "label": "Khách hàng"}],
        "contract_no_pattern": "01A-GDN-{yyyyMM}-{seq:05d}",
        "export_name_pattern": "Mẫu 01A - {full_name}",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Template(**defaults)  # type: ignore[arg-type]


def _use_case(
    uow: FakeUnitOfWork,
    clock: FakeClock,
    ids: SequentialIds,
    store: _Store | None = None,
    inspector: _Inspector | None = None,
) -> tuple[RegisterTemplateVersionUseCase, _Store, _Inspector]:
    template_store = store or _Store()
    template_inspector = inspector or _Inspector()
    return (
        RegisterTemplateVersionUseCase(
            uow_factory=uow,
            inspector=template_inspector,  # type: ignore[arg-type]
            template_store=template_store,  # type: ignore[arg-type]
            clock=clock,
            id_generator=ids,
        ),
        template_store,
        template_inspector,
    )


def _command(**overrides: object) -> RegisterTemplateVersionCommand:
    defaults: dict[str, object] = {
        "template_id": _TEMPLATE_ID,
        "file_bytes": _DOCX,
        "original_filename": "01A_HD_GDN.docx",
        "created_by": "bootstrap",
    }
    defaults.update(overrides)
    return RegisterTemplateVersionCommand(**defaults)  # type: ignore[arg-type]


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_registers_and_activates_version_one(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        template = _template()
        uow.templates.rows = {template.id: template}
        use_case, store, _ = _use_case(uow, clock, ids)

        result = await use_case.execute(_command())

        assert result.version_no == 1
        assert result.is_active is True
        assert store.saved == [("01A_HD_GDN", 1)]
        assert uow.templates.rows[template.id].active_version_id == result.version_id

    @pytest.mark.asyncio
    async def test_records_what_the_inspector_actually_found(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """⭐ Not a hand-copied list that goes stale on the first template edit."""
        template = _template()
        uow.templates.rows = {template.id: template}
        use_case, _, _ = _use_case(uow, clock, ids)

        await use_case.execute(_command())

        stored: TemplateVersion = uow.template_versions.added[0]
        assert stored.declared_variables == ["full_name", "id_number"]
        assert stored.required_variables == ["full_name"]

    @pytest.mark.asyncio
    async def test_the_next_upload_becomes_version_two(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        template = _template()
        uow.templates.rows = {template.id: template}
        use_case, store, _ = _use_case(uow, clock, ids)

        await use_case.execute(_command())
        second = await use_case.execute(_command())

        assert second.version_no == 2
        assert store.saved == [("01A_HD_GDN", 1), ("01A_HD_GDN", 2)]

    @pytest.mark.asyncio
    async def test_the_replaced_version_is_archived_not_deleted(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """P-09: an old contract must still regenerate from the file it used."""
        template = _template()
        uow.templates.rows = {template.id: template}
        use_case, _, _ = _use_case(uow, clock, ids)

        first = await use_case.execute(_command())
        await use_case.execute(_command())

        previous = uow.template_versions.rows[first.version_id]
        assert previous.is_archived is True
        assert first.version_id in uow.template_versions.rows

    @pytest.mark.asyncio
    async def test_activation_can_be_declined(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        template = _template()
        uow.templates.rows = {template.id: template}
        use_case, _, _ = _use_case(uow, clock, ids)

        result = await use_case.execute(_command(activate=False))

        assert result.is_active is False
        assert uow.templates.rows[template.id].active_version_id is None


class TestRejection:
    @pytest.mark.asyncio
    async def test_an_invalid_template_never_reaches_the_store(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """⭐ §9.9: a template is untrusted input, so it is judged before it lands."""
        template = _template()
        uow.templates.rows = {template.id: template}
        rejected = TemplateInspection(
            status=TemplateValidationStatus.INVALID,
            diagnostics=(
                TemplateDiagnostic(
                    code="COCAS-6014",
                    severity=DiagnosticSeverity.ERROR,
                    message="Cấu trúc Jinja2 nguy hiểm.",
                ),
            ),
        )
        use_case, store, _ = _use_case(uow, clock, ids, inspector=_Inspector(rejected))

        with pytest.raises(ValidationError) as exc_info:
            await use_case.execute(_command())

        assert store.saved == []
        assert "COCAS-6014" in str(exc_info.value.context)

    @pytest.mark.asyncio
    async def test_a_warning_still_registers(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """A template may be registered while WARNING, never while INVALID."""
        template = _template()
        uow.templates.rows = {template.id: template}
        warned = TemplateInspection(
            status=TemplateValidationStatus.WARNING,
            declared=("full_name",),
            diagnostics=(
                TemplateDiagnostic(
                    code="COCAS-6009",
                    severity=DiagnosticSeverity.WARNING,
                    message="Biến không xác định.",
                ),
            ),
        )
        use_case, _, _ = _use_case(uow, clock, ids, inspector=_Inspector(warned))

        result = await use_case.execute(_command())
        assert result.validation_status is TemplateValidationStatus.WARNING
        assert result.diagnostics[0]["code"] == "COCAS-6009"

    @pytest.mark.asyncio
    async def test_unknown_template(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        use_case, _, _ = _use_case(uow, clock, ids)
        with pytest.raises(EntityNotFound):
            await use_case.execute(_command())

    @pytest.mark.asyncio
    async def test_a_deleted_template_cannot_gain_a_version(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        template = _template()
        template.soft_delete(NOW)
        uow.templates.rows = {template.id: template}
        use_case, _, _ = _use_case(uow, clock, ids)
        with pytest.raises(EntityNotFound):
            await use_case.execute(_command())


class TestCompensation:
    @pytest.mark.asyncio
    async def test_a_failed_transaction_removes_the_orphan_file(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        template = _template()
        uow.templates.rows = {template.id: template}
        use_case, store, _ = _use_case(uow, clock, ids)

        async def explode(entity: object) -> None:
            raise RuntimeError("database went away")

        uow.template_versions.add = explode  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            await use_case.execute(_command())

        assert store.removed == ["01A_HD_GDN/v1/template.docx"]
