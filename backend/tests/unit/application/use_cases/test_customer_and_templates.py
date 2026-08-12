"""`manage_customer`, `read_templates`, `download_contract_document`.

The three read/write Use Cases behind §5.4's steps 2, 3, 11, 13 and 15.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime

import pytest

from cocas.application.use_cases.contract.download_contract_document import (
    DownloadContractDocumentUseCase,
)
from cocas.application.use_cases.customer.manage_customer import (
    BankAccountRequest,
    CreateCustomerCommand,
    CreateCustomerUseCase,
    FindCustomerByIdNumberUseCase,
)
from cocas.application.use_cases.template.read_templates import (
    GetTemplateRequirementsUseCase,
    ListTemplatesUseCase,
)
from cocas.domain.entities.contract import Contract
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import (
    BusinessRuleViolation,
    DocumentIntegrityError,
    DuplicateEntityError,
    EntityNotFound,
)
from cocas.domain.ports.storage import VaultCategory, VaultRef

from .conftest import (
    NOW,
    FakeClock,
    FakeUnitOfWork,
    SequentialIds,
    make_contract_document,
)

_CONTENT = b"PK\x03\x04 contract bytes"


def _template(**overrides: object) -> Template:
    defaults: dict[str, object] = {
        "id": uuid.UUID(int=0x7E),
        "code": "01A_HD_GDN",
        "name": "Mẫu số 01A/HĐ-GĐN",
        "party_schema": [
            {"key": "holder", "label": "Khách hàng", "collect": ["bank_account"]}
        ],
        "contract_no_pattern": "01A-GDN-{yyyyMM}-{seq:05d}",
        "export_name_pattern": "Mẫu 01A - {full_name}",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Template(**defaults)  # type: ignore[arg-type]


def _version(template_id: uuid.UUID, **overrides: object) -> TemplateVersion:
    defaults: dict[str, object] = {
        "id": uuid.UUID(int=0x7F),
        "template_id": template_id,
        "version_no": 1,
        "file_path": "01A_HD_GDN/v1/template.docx",
        "file_sha256": bytes(32),
        "file_size_bytes": 900_000,
        "original_filename": "01A_HD_GDN.docx",
        "declared_variables": ["full_name", "id_number"],
        "required_variables": ["full_name"],
        "optional_variables": ["id_number"],
        "validation_status": TemplateValidationStatus.VALID,
        "created_by": "bootstrap",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return TemplateVersion(**defaults)  # type: ignore[arg-type]


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_reports_whether_a_template_can_be_used_yet(
        self, uow: FakeUnitOfWork
    ) -> None:
        ready = _template(id=uuid.UUID(int=1), active_version_id=uuid.UUID(int=0x7F))
        blank = _template(id=uuid.UUID(int=2), code="01A_GDKQ")
        uow.templates.rows = {ready.id: ready, blank.id: blank}

        items = await ListTemplatesUseCase(uow).execute()
        by_code = {item.code: item for item in items}
        assert by_code["01A_HD_GDN"].has_active_version is True
        assert by_code["01A_GDKQ"].has_active_version is False

    @pytest.mark.asyncio
    async def test_a_deactivated_template_is_hidden(self, uow: FakeUnitOfWork) -> None:
        hidden = _template(id=uuid.UUID(int=3), is_active=False)
        uow.templates.rows = {hidden.id: hidden}
        assert await ListTemplatesUseCase(uow).execute() == []


class TestRequirements:
    @pytest.mark.asyncio
    async def test_resolves_v1_defaults(self, uow: FakeUnitOfWork) -> None:
        template = _template(active_version_id=uuid.UUID(int=0x7F))
        uow.templates.rows = {template.id: template}
        uow.template_versions.rows = {uuid.UUID(int=0x7F): _version(template.id)}

        requirements = await GetTemplateRequirementsUseCase(uow).execute(template.id)
        party = requirements.party_schema[0]
        assert party["entity_type"] == "INDIVIDUAL"
        assert (party["min"], party["max"]) == (1, 1)
        assert party["collect"] == ["bank_account"]

    @pytest.mark.asyncio
    async def test_absent_collect_means_collect_nothing(
        self, uow: FakeUnitOfWork
    ) -> None:
        """⚠️ The other default would make the wizard ask for a bank account."""
        template = _template(
            active_version_id=uuid.UUID(int=0x7F),
            party_schema=[{"key": "holder", "label": "Khách hàng"}],
        )
        uow.templates.rows = {template.id: template}
        uow.template_versions.rows = {uuid.UUID(int=0x7F): _version(template.id)}

        requirements = await GetTemplateRequirementsUseCase(uow).execute(template.id)
        assert requirements.party_schema[0]["collect"] == []

    @pytest.mark.asyncio
    async def test_wizard_steps_is_derived_not_guessed(
        self, uow: FakeUnitOfWork
    ) -> None:
        template = _template(active_version_id=uuid.UUID(int=0x7F))
        uow.templates.rows = {template.id: template}
        uow.template_versions.rows = {uuid.UUID(int=0x7F): _version(template.id)}
        requirements = await GetTemplateRequirementsUseCase(uow).execute(template.id)
        assert requirements.wizard_steps == 3

    @pytest.mark.asyncio
    async def test_a_template_without_an_active_version_says_so(
        self, uow: FakeUnitOfWork
    ) -> None:
        template = _template()
        uow.templates.rows = {template.id: template}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await GetTemplateRequirementsUseCase(uow).execute(template.id)
        assert exc_info.value.code == "TEMPLATE_NO_ACTIVE_VERSION"

    @pytest.mark.asyncio
    async def test_unknown_template(self, uow: FakeUnitOfWork) -> None:
        with pytest.raises(EntityNotFound):
            await GetTemplateRequirementsUseCase(uow).execute(uuid.UUID(int=404))


def _create_command(**overrides: object) -> CreateCustomerCommand:
    defaults: dict[str, object] = {
        "full_name": "VÕ HUỲNH NGÂN GIAO",
        "id_number": "048179002546",
        "date_of_birth": date(1979, 2, 27),
        "issue_date": date(2022, 11, 8),
        "expiry_date": date(2039, 2, 27),
        "issue_place": "BỘ CÔNG AN",
        "phone": "0912345678",
        "email": "demo@example.com",
        "address": "Số 1 Đường Demo, Phường Demo, Quận Demo, Hà Nội",
        "created_by": "tester",
    }
    defaults.update(overrides)
    return CreateCustomerCommand(**defaults)  # type: ignore[arg-type]


class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_creates_the_customer(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        result = await CreateCustomerUseCase(uow, clock, ids).execute(_create_command())
        assert result.id_number == "048179002546"
        assert uow.commits == 1
        assert uow.customers.added[0].id == result.customer_id

    @pytest.mark.asyncio
    async def test_creates_the_bank_account_in_the_same_transaction(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        result = await CreateCustomerUseCase(uow, clock, ids).execute(
            _create_command(
                bank_account=BankAccountRequest(
                    account_number="0011001234567",
                    bank_name="Vietcombank",
                    branch="Sở giao dịch",
                )
            )
        )
        assert result.bank_account_id is not None
        assert uow.commits == 1
        assert uow.bank_accounts.added[0].customer_id == result.customer_id

    @pytest.mark.asyncio
    async def test_data_quality_records_where_the_values_came_from(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        await CreateCustomerUseCase(uow, clock, ids).execute(
            _create_command(ocr_session_id=uuid.UUID(int=5))
        )
        assert uow.customers.added[0].data_quality.value == "OCR_VERIFIED"

    @pytest.mark.asyncio
    async def test_manual_entry_is_labelled_manual(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        await CreateCustomerUseCase(uow, clock, ids).execute(_create_command())
        assert uow.customers.added[0].data_quality.value == "MANUAL"

    @pytest.mark.asyncio
    async def test_a_duplicate_cccd_is_refused_with_the_existing_id(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        use_case = CreateCustomerUseCase(uow, clock, ids)
        first = await use_case.execute(_create_command())
        with pytest.raises(DuplicateEntityError) as exc_info:
            await use_case.execute(_create_command())
        assert exc_info.value.context["details"] == {"customer_id": str(first.customer_id)}

    @pytest.mark.asyncio
    async def test_an_invalid_value_never_opens_a_transaction(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """Value objects validate before the UoW is entered."""
        from cocas.domain.exceptions import DomainException

        with pytest.raises(DomainException):
            await CreateCustomerUseCase(uow, clock, ids).execute(
                _create_command(id_number="123")
            )
        assert uow.entered == 0


class TestFindCustomer:
    @pytest.mark.asyncio
    async def test_returns_the_bank_accounts_alongside_the_customer(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """⭐ The lookup exists so the caller can continue (`COCAS-7012`)."""
        created = await CreateCustomerUseCase(uow, clock, ids).execute(
            _create_command(
                bank_account=BankAccountRequest(
                    account_number="0011001234567",
                    bank_name="Vietcombank",
                    branch="Sở giao dịch",
                )
            )
        )
        found = await FindCustomerByIdNumberUseCase(uow).execute("048179002546")
        assert found is not None
        assert found.customer.id == created.customer_id
        assert [a.id for a in found.bank_accounts] == [created.bank_account_id]

    @pytest.mark.asyncio
    async def test_absent_customer(self, uow: FakeUnitOfWork) -> None:
        assert await FindCustomerByIdNumberUseCase(uow).execute("048179002546") is None


class _Vault:
    def __init__(self, content: bytes = _CONTENT) -> None:
        self.content = content

    def load(self, ref: VaultRef) -> bytes:
        return self.content

    def save(self, data: bytes, category: VaultCategory) -> VaultRef:  # pragma: no cover
        raise NotImplementedError

    def delete(self, ref: VaultRef) -> None:  # pragma: no cover
        raise NotImplementedError

    def exists(self, ref: VaultRef) -> bool:  # pragma: no cover
        return True


def _contract(status: ContractStatus = ContractStatus.COMPLETED) -> Contract:
    return Contract(
        id=uuid.UUID(int=0xC1),
        contract_no="01A-GDN-202608-00001",
        export_name="Mẫu 01A - VÕ HUỲNH NGÂN GIAO",
        primary_customer_id=uuid.UUID(int=0xC2),
        template_version_id=uuid.UUID(int=0x7F),
        created_by="tester",
        contract_date=date(2026, 8, 12),
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        updated_at=datetime(2026, 8, 12, tzinfo=UTC),
        status=status,
        snapshot_sha256=bytes(32),
    )


class TestDownload:
    @pytest.mark.asyncio
    async def test_returns_the_bytes_with_the_extension_appended(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        contract = _contract()
        document = make_contract_document(
            contract_id=contract.id, file_sha256=hashlib.sha256(_CONTENT).digest()
        )
        uow.contracts.rows = {contract.id: contract}
        uow.contract_documents.rows = {document.id: document}

        result = await DownloadContractDocumentUseCase(
            uow, _Vault(), clock  # type: ignore[arg-type]
        ).execute(contract.id)

        assert result.content == _CONTENT
        assert result.file_name == "Mẫu 01A - VÕ HUỲNH NGÂN GIAO.docx"

    @pytest.mark.asyncio
    async def test_a_tampered_file_is_refused(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        """⚠️ Checked on the way out, before the user signs it."""
        contract = _contract()
        document = make_contract_document(
            contract_id=contract.id, file_sha256=b"\x01" * 32
        )
        uow.contracts.rows = {contract.id: contract}
        uow.contract_documents.rows = {document.id: document}

        with pytest.raises(DocumentIntegrityError):
            await DownloadContractDocumentUseCase(
                uow, _Vault(), clock  # type: ignore[arg-type]
            ).execute(contract.id)

    @pytest.mark.asyncio
    async def test_a_voided_contract_is_not_downloadable(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        contract = _contract(ContractStatus.VOIDED)
        uow.contracts.rows = {contract.id: contract}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await DownloadContractDocumentUseCase(
                uow, _Vault(), clock  # type: ignore[arg-type]
            ).execute(contract.id)
        assert exc_info.value.code == "CONTRACT_VOIDED"

    @pytest.mark.asyncio
    async def test_a_contract_with_no_document_yet(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        contract = _contract(ContractStatus.GENERATING)
        uow.contracts.rows = {contract.id: contract}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await DownloadContractDocumentUseCase(
                uow, _Vault(), clock  # type: ignore[arg-type]
            ).execute(contract.id)
        assert exc_info.value.code == "DOCUMENT_NOT_READY"

    @pytest.mark.asyncio
    async def test_unknown_contract(self, uow: FakeUnitOfWork, clock: FakeClock) -> None:
        with pytest.raises(EntityNotFound):
            await DownloadContractDocumentUseCase(
                uow, _Vault(), clock  # type: ignore[arg-type]
            ).execute(uuid.UUID(int=404))
