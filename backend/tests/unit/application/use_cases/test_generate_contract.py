"""§9.11 / §12.14.2 — `GenerateContractUseCase` end to end, on fakes.

⭐ The Vault here is the **real** `EncryptedFileVault` on `tmp_path`, not the
in-memory fake. Two of this module's invariants are about what lands on disk —
that no plaintext `.docx` is ever written, and that an orphaned `.enc` is
cleaned up — and a fake that stores bytes in a dict cannot show either.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType

import pytest

from cocas.application.dto.contract import GenerateContractCommand, PartyRequest
from cocas.application.render_context_builder import RenderContextBuilder
from cocas.application.use_cases.contract.generate_contract import (
    GenerateContractUseCase,
)
from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.contract import Contract
from cocas.domain.entities.contract_document import ContractDocument
from cocas.domain.entities.contract_party import ContractParty
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import EntityNotFound, RenderError, ValidationError
from cocas.domain.ports.storage import VaultCategory
from cocas.domain.services.contract_number_generator import ContractNumberGenerator
from cocas.domain.services.export_name_generator import ExportNameGenerator
from cocas.domain.validation.engine import ValidationEngine
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.styled_value import StyledValue
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone
from cocas.infrastructure.storage.encrypted_file_vault import EncryptedFileVault
from tests.fixtures.fake_ports import (
    FakeDocumentRenderer,
    FrozenClock,
    SequentialIdGenerator,
)

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
TODAY = date(2026, 8, 11)
TEMPLATE_SHA = b"\x11" * 32


# ------------------------------------------------------------------- fixtures


def make_customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "created_by": "nvnghiep",
        "full_name": PersonName.from_raw("NGUYỄN VĂN AN"),
        "id_number": CitizenId.from_raw("001199012345"),
        "date_of_birth": date(1990, 5, 14),
        "issue_place": IssuePlace(BO_CONG_AN),
        "id_card_dates": IdCardDates(issue_date=date(2021, 8, 20), expiry_date=date(2030, 5, 14)),
        "phone": VietnamesePhone.from_raw("0912345678"),
        "email": EmailAddress.from_raw("an.nguyen@example.com"),
        "address": "123 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội",
        "data_quality": DataQuality.OCR_VERIFIED,
        "created_at": NOW,
        "gender": Gender.NAM,
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


class _Store:
    """The slice of a repository this Use Case uses, backed by a dict."""

    def __init__(self, rows: dict[uuid.UUID, object] | None = None) -> None:
        self.rows: dict[uuid.UUID, object] = dict(rows or {})
        self.added: list[object] = []

    async def get(self, entity_id: object) -> object | None:
        return self.rows.get(entity_id)  # type: ignore[arg-type]

    async def add(self, entity: object) -> None:
        self.added.append(entity)
        self.rows[entity.id] = entity  # type: ignore[attr-defined]

    async def update(self, entity: object, expected_version: int | None = None) -> None:
        self.rows[entity.id] = entity  # type: ignore[attr-defined]


class FakeTemplateStore(_Store):
    def __init__(self, template: Template) -> None:
        super().__init__({template.id: template})
        self.locked: list[uuid.UUID] = []

    async def get_for_update(self, template_id: uuid.UUID) -> Template | None:
        self.locked.append(template_id)
        return self.rows.get(template_id)  # type: ignore[return-value]


class FakeContractStore(_Store):
    def __init__(self) -> None:
        super().__init__()
        self.snapshots: list[dict[str, object]] = []
        self.fail_on_update = False

    def stage_snapshot(self, snapshot: dict[str, object]) -> None:
        self.snapshots.append(snapshot)

    async def update(self, entity: object, expected_version: int | None = None) -> None:
        if self.fail_on_update:
            raise RuntimeError("cơ sở dữ liệu mất kết nối")
        await super().update(entity, expected_version)


class FakeUnitOfWork:
    """One shared set of stores across every `async with` — the fake stands in
    for a database, and a database does not forget between transactions."""

    def __init__(self, template: Template, version: TemplateVersion) -> None:
        self.templates = FakeTemplateStore(template)
        self.template_versions = _Store({version.id: version})
        self.customers = _Store()
        self.bank_accounts = _Store()
        self.contracts = FakeContractStore()
        self.contract_parties = _Store()
        self.contract_documents = _Store()
        self.commits = 0
        self.rollbacks = 0
        self._committed = False

    def __call__(self) -> FakeUnitOfWork:
        self._committed = False
        return self

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._committed:
            self.rollbacks += 1

    async def commit(self) -> None:
        self.commits += 1
        self._committed = True

    # Convenience for assertions.
    @property
    def contract(self) -> Contract:
        return next(iter(self.contracts.rows.values()))  # type: ignore[return-value]

    @property
    def parties(self) -> Sequence[ContractParty]:
        return list(self.contract_parties.rows.values())  # type: ignore[return-value]

    @property
    def documents(self) -> Sequence[ContractDocument]:
        return list(self.contract_documents.rows.values())  # type: ignore[return-value]


class Harness:
    """Everything one generation needs, assembled and inspectable."""

    def __init__(self, tmp_path: Path, template: Template, version: TemplateVersion) -> None:
        self.template = template
        self.version = version
        self.uow = FakeUnitOfWork(template, version)
        self.renderer = FakeDocumentRenderer()
        self.templates_dir = tmp_path / "templates"
        (self.templates_dir / "01A_HD_GDN").mkdir(parents=True)
        (self.templates_dir / version.file_path).write_bytes(b"PK\x03\x04 not really")
        self.vault_root = tmp_path / "vault"
        self.storage = EncryptedFileVault(
            root=self.vault_root,
            vault_key=secrets.token_bytes(32),
            clock=FrozenClock(NOW),
            id_generator=SequentialIdGenerator(),
        )
        self.use_case = GenerateContractUseCase(
            uow_factory=self.uow,
            context_builder=RenderContextBuilder(),
            context_adapter=_PassThroughAdapter(),
            renderer=self.renderer,
            file_storage=self.storage,
            validator=ValidationEngine(),
            contract_numbers=ContractNumberGenerator(),
            export_names=ExportNameGenerator(),
            templates_dir=self.templates_dir,
            clock=FrozenClock(NOW),
            id_generator=SequentialIdGenerator(),
        )

    def register(self, customer: Customer, bank: BankAccount | None = None) -> None:
        self.uow.customers.rows[customer.id] = customer
        if bank is not None:
            self.uow.bank_accounts.rows[bank.id] = bank


class _PassThroughAdapter:
    """`DocxContextAdapter` without docxtpl — Application only promised a copy."""

    def adapt(self, context: object) -> dict[str, object]:
        return {
            key: (value.text if isinstance(value, StyledValue) else value)
            for key, value in context.items()  # type: ignore[union-attr]
        }


@pytest.fixture
def template() -> Template:
    return Template(
        id=uuid.uuid4(),
        code="01A_HD_GDN",
        name="Mẫu 01A/HĐ-GĐN",
        party_schema=[
            {
                "key": "holder",
                "label": "Khách hàng",
                "entity_type": "INDIVIDUAL",
                "min": 1,
                "max": 1,
                "is_primary": True,
                "collect": ["contact", "bank_account"],
            }
        ],
        contract_no_pattern="01A-GDN-{yyyy}{MM}-{seq:05d}",
        export_name_pattern="Mẫu 01A - {full_name}",
        created_at=NOW,
        suppressed_variables=["contract_date", "contract_date_text", "day", "month", "year"],
        contract_no_seq=41,
    )


@pytest.fixture
def version(template: Template) -> TemplateVersion:
    created = TemplateVersion(
        id=uuid.uuid4(),
        template_id=template.id,
        version_no=1,
        file_path="01A_HD_GDN/v1.docx",
        file_sha256=TEMPLATE_SHA,
        file_size_bytes=900_000,
        original_filename="01A_HD_GDN.docx",
        declared_variables=["full_name", "id_number", "contract_date"],
        required_variables=["full_name", "id_number", "contract_date"],
        optional_variables=[],
        validation_status=TemplateValidationStatus.VALID,
        created_by="nvnghiep",
        created_at=NOW,
    )
    template.active_version_id = created.id
    return created


@pytest.fixture
def harness(tmp_path: Path, template: Template, version: TemplateVersion) -> Harness:
    return Harness(tmp_path, template, version)


@pytest.fixture
def customer() -> Customer:
    return make_customer()


@pytest.fixture
def bank(customer: Customer) -> BankAccount:
    return BankAccount(
        id=uuid.uuid4(),
        customer_id=customer.id,
        account_number=BankAccountNumber.from_raw("1234567890"),
        bank_name="Ngân hàng TMCP Ngoại thương Việt Nam",
        branch="Chi nhánh Hà Nội",
        created_at=NOW,
        bank_code="VCB",
    )


def command(customer: Customer, bank: BankAccount | None = None, **overrides: object):
    defaults: dict[str, object] = {
        "template_id": None,
        "parties": [
            PartyRequest(
                party_key="holder",
                customer_id=customer.id,
                bank_account_id=bank.id if bank else None,
            )
        ],
        "created_by": "nvnghiep",
        "created_by_name": "Nguyễn Văn Nghiệp",
    }
    return GenerateContractCommand(**{**defaults, **overrides})  # type: ignore[arg-type]


# ------------------------------------------------------------------ happy path


@pytest.mark.asyncio
async def test_writes_contract_party_and_document(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    harness.register(customer, bank)

    result = await harness.use_case.execute(
        command(customer, bank, template_id=harness.template.id)
    )

    assert harness.uow.contract.status is ContractStatus.COMPLETED
    assert len(harness.uow.parties) == 1
    assert len(harness.uow.documents) == 1
    assert result.contract_no == "01A-GDN-202608-00042"
    assert result.export_name == "Mẫu 01A - NGUYỄN VĂN AN"


@pytest.mark.asyncio
async def test_the_document_is_in_the_vault_and_reads_back(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    harness.register(customer, bank)

    result = await harness.use_case.execute(
        command(customer, bank, template_id=harness.template.id)
    )

    stored = harness.storage.load(
        _ref(VaultCategory.CONTRACT_DOCUMENT, result.vault_path)
    )
    assert result.file_size_bytes == len(stored)
    assert hashlib.sha256(stored).digest() == result.file_sha256
    # ⭐ §9.15 — the recorded hash is of the plaintext document, so it matches
    # what a download hands back. The ciphertext on disk hashes to something
    # else entirely, and would differ again on every re-encryption.
    ciphertext = (harness.vault_root / result.vault_path).read_bytes()
    assert hashlib.sha256(ciphertext).digest() != result.file_sha256
    assert b"NGUY" in stored


@pytest.mark.asyncio
async def test_no_plaintext_docx_is_ever_written(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """⭐ §12.11.2 — the reason `render_to_bytes` exists at all."""
    harness.register(customer, bank)

    await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    assert list(harness.vault_root.rglob("*.docx")) == []
    assert [p.suffix for p in harness.vault_root.rglob("*") if p.is_file()] == [".enc"]
    # The renderer was asked for bytes, never for a path.
    assert harness.renderer.calls[0][2] == ""


@pytest.mark.asyncio
async def test_the_template_checksum_is_handed_to_the_renderer(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """V-CTR-002's checksum half is enforced inside the renderer (§12.11)."""
    harness.register(customer, bank)

    await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    assert harness.renderer.expected_hashes == [TEMPLATE_SHA]


@pytest.mark.asyncio
async def test_the_snapshot_is_staged_unadapted(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """§9.6 / P-09 — `render_snapshot_enc` holds the context as Application
    built it, so the same contract reprints identically in five years."""
    harness.register(customer, bank)

    await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    snapshot = harness.uow.contracts.snapshots[0]
    assert snapshot["full_name"] == "NGUYỄN VĂN AN"
    assert snapshot["contract_no"] == "01A-GDN-202608-00042"
    assert snapshot["bank_account"] == "1234567890"


@pytest.mark.asyncio
async def test_the_sequence_advances_and_the_template_row_is_updated(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    harness.register(customer, bank)

    await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    assert harness.template.contract_no_seq == 42
    assert harness.uow.templates.locked == [harness.template.id]


@pytest.mark.asyncio
async def test_two_transactions_not_one(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """⭐ §12.14.2 — the split is the design, so it is asserted."""
    harness.register(customer, bank)

    await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    assert harness.uow.commits == 2


@pytest.mark.asyncio
async def test_a_suppressed_required_variable_does_not_block(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """⚠️ Both real templates make `contract_date` required *and* suppressed.
    Counting it as missing would block every contract."""
    harness.register(customer, bank)

    result = await harness.use_case.execute(
        command(customer, bank, template_id=harness.template.id)
    )

    assert result.contract_id == harness.uow.contract.id


@pytest.mark.asyncio
async def test_warnings_travel_with_the_success(
    harness: Harness, bank: BankAccount
) -> None:
    expired = make_customer(
        id_card_dates=IdCardDates(issue_date=date(2016, 1, 5), expiry_date=date(2025, 5, 14))
    )
    bank.customer_id = expired.id
    harness.register(expired, bank)

    result = await harness.use_case.execute(
        command(expired, bank, template_id=harness.template.id)
    )

    assert result.warnings.codes() == ("CARD_EXPIRED",)
    assert harness.uow.contract.status is ContractStatus.COMPLETED


# ------------------------------------------------------------- rejected input


@pytest.mark.asyncio
async def test_a_blocking_rule_writes_nothing_and_burns_no_number(
    harness: Harness, customer: Customer
) -> None:
    """⭐ A rejected request must not consume a `contract_no`: the column is
    UNIQUE and the gaps would be unexplainable in an audit."""
    harness.register(customer)  # no bank account, but the template collects one

    with pytest.raises(ValidationError) as caught:
        await harness.use_case.execute(command(customer, template_id=harness.template.id))

    assert caught.value.code == "COCAS-7002"
    assert harness.uow.contracts.rows == {}
    assert harness.uow.rollbacks == 1


@pytest.mark.asyncio
async def test_an_unknown_template_is_not_found(
    harness: Harness, customer: Customer
) -> None:
    harness.register(customer)

    with pytest.raises(EntityNotFound):
        await harness.use_case.execute(command(customer, template_id=uuid.uuid4()))


@pytest.mark.asyncio
async def test_an_unknown_customer_is_not_found(harness: Harness, customer: Customer) -> None:
    with pytest.raises(EntityNotFound):
        await harness.use_case.execute(command(customer, template_id=harness.template.id))


# ------------------------------------------------------------ failure records


@pytest.mark.asyncio
async def test_a_render_failure_leaves_generation_failed(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """⭐⭐ The reason §12.14.2 exists: §9.16 requires this row to survive."""
    harness.register(customer, bank)
    harness.renderer.error = RenderError("Lỗi trong mẫu hợp đồng.")

    with pytest.raises(RenderError):
        await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    contract = harness.uow.contract
    assert contract.status is ContractStatus.GENERATION_FAILED
    assert contract.error_code == "RENDER_ERROR"
    assert harness.uow.documents == []
    assert list(harness.vault_root.rglob("*.enc")) == []


@pytest.mark.asyncio
async def test_a_bookkeeping_failure_removes_the_orphaned_vault_file(
    harness: Harness, customer: Customer, bank: BankAccount
) -> None:
    """⚠️ §12.14.2's second cost, compensated: with no `contract_document`
    row, that `.enc` is encrypted garbage that would show up as a phantom
    discrepancy in §9.15's weekly reconciliation."""
    harness.register(customer, bank)
    harness.uow.contracts.fail_on_update = True

    with pytest.raises(RuntimeError):
        await harness.use_case.execute(command(customer, bank, template_id=harness.template.id))

    assert list(harness.vault_root.rglob("*.enc")) == []


def _ref(category: VaultCategory, relative_path: str):
    from cocas.domain.ports.storage import VaultRef

    return VaultRef(category=category, relative_path=relative_path)
