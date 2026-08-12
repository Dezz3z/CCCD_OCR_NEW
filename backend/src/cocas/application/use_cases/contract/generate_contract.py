"""`GenerateContractUseCase` — the whole of §9.11 as one call.

Four pieces already existed and none of them knew about each other:
`RenderContextBuilder` (§12.9), `DocxContextAdapter` (§12.10), `DocxRenderer`
(§12.11) and `EncryptedFileVault` (§12.13). This is the transaction that
strings them together and writes the three rows that make a contract real.

## ⭐⭐ Two transactions, because the FAILURE record has to survive

§12.14 says one Use Case = one transaction, and §12.14.1 already records one
exception (`ProcessOcrSessionUseCase`, split because a 9.5 s OCR run should
not hold a pooled connection). This is a **second** exception with a
different reason, and the reason is worth stating exactly:

§9.16 requires that a failed render leaves the contract at
`GENERATION_FAILED`. In a single transaction that is impossible — the
exception rolls back the `INSERT`, so there is no row left to carry the
status. The `GENERATING` state in §9.11's diagram is therefore not
decoration: it exists precisely because the row must be **committed before
the risky work starts**.

    T1   lock template -> contract_no -> V-CTR-001..010 -> INSERT contract
         (GENERATING) + contract_party + render_snapshot_enc -> commit
    ---  render_to_bytes() -> EncryptedFileVault.save()   [no transaction]
    T2   INSERT contract_document -> mark_completed()     -> commit
     or  mark_generation_failed() -> commit -> re-raise

§12.14 independently requires the file write to sit outside the transaction
("Thao tác file **không nằm trong** transaction"), so the split is doubly
mandated.

⚠️ Two costs, named rather than discovered later:
  1. A crash *between* T1 and T2 leaves the contract `GENERATING` forever —
     §12.15's stuck-job recovery, same as every long operation here.
  2. A Vault write that succeeds before T2 fails leaves an orphan `.enc`.
     Compensated by deleting it when the bookkeeping transaction fails: with
     no `contract_document` row, that file is encrypted garbage, not a legal
     record. If the delete *also* fails, §9.15's weekly reconciliation is the
     last net.
"""
from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from types import TracebackType
from typing import Protocol

from loguru import logger

from cocas.application.dto.contract import (
    ContractDraft,
    GenerateContractCommand,
    GeneratedContract,
    PartyDraft,
    PartyRequest,
    RenderContext,
)
from cocas.application.render_context_builder import RenderContextBuilder
from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.contract import Contract
from cocas.domain.entities.contract_document import ContractDocument
from cocas.domain.entities.contract_party import ContractParty
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.exceptions import (
    DomainException,
    EntityNotFound,
    ValidationError,
)
from cocas.domain.ports.documents import IDocumentRenderer
from cocas.domain.ports.storage import IFileStorage, VaultCategory, VaultRef
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.domain.services.contract_number_generator import ContractNumberGenerator
from cocas.domain.services.export_name_generator import ExportNameGenerator
from cocas.domain.validation.contract_rules import ContractCandidate, PartyCandidate
from cocas.domain.validation.engine import ValidationEngine
from cocas.domain.validation.report import ValidationReport
from cocas.domain.validation.rule import RuleContext, RuleSetKey

GENERATOR_NAME = "docxtpl"
"""`contract_document.generator` — which renderer produced the file."""


class IRenderContextAdapter(Protocol):
    """`DocxContextAdapter` (§12.10), seen from Application.

    Declared here rather than imported because `DocxContextAdapter` lives in
    Infrastructure and returns `docxtpl.RichText` objects — pitfall #4 is
    exactly that Application must never name that type.
    """

    def adapt(self, context: Mapping[str, object]) -> dict[str, object]: ...


class ITemplateStore(Protocol):
    async def get_for_update(self, template_id: uuid.UUID) -> Template | None: ...

    async def update(self, entity: Template, expected_version: int | None = None) -> None: ...


class ITemplateVersionStore(Protocol):
    async def get(self, entity_id: object) -> TemplateVersion | None: ...


class ICustomerStore(Protocol):
    async def get(self, entity_id: object) -> Customer | None: ...


class IBankAccountStore(Protocol):
    async def get(self, entity_id: object) -> BankAccount | None: ...


class IContractStore(Protocol):
    def stage_snapshot(self, snapshot: dict[str, object]) -> None: ...

    async def get(self, entity_id: object) -> Contract | None: ...

    async def add(self, entity: Contract) -> None: ...

    async def update(self, entity: Contract, expected_version: int | None = None) -> None: ...


class IContractPartyWriter(Protocol):
    async def add(self, entity: ContractParty) -> None: ...


class IContractDocumentWriter(Protocol):
    async def add(self, entity: ContractDocument) -> None: ...


class IContractUnitOfWork(Protocol):
    """`IUnitOfWork` (Port 14) plus the repositories this Use Case touches."""

    templates: ITemplateStore
    template_versions: ITemplateVersionStore
    customers: ICustomerStore
    bank_accounts: IBankAccountStore
    contracts: IContractStore
    contract_parties: IContractPartyWriter
    contract_documents: IContractDocumentWriter

    async def __aenter__(self) -> IContractUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class GenerateContractUseCase:
    """Generate one contract end to end (§9.11, §12.14.2)."""

    def __init__(
        self,
        uow_factory: Callable[[], IContractUnitOfWork],
        context_builder: RenderContextBuilder,
        context_adapter: IRenderContextAdapter,
        renderer: IDocumentRenderer,
        file_storage: IFileStorage,
        validator: ValidationEngine,
        contract_numbers: ContractNumberGenerator,
        export_names: ExportNameGenerator,
        templates_dir: Path,
        clock: IClock,
        id_generator: IIdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._context_builder = context_builder
        self._context_adapter = context_adapter
        self._renderer = renderer
        self._storage = file_storage
        self._validator = validator
        self._contract_numbers = contract_numbers
        self._export_names = export_names
        self._templates_dir = Path(templates_dir)
        self._clock = clock
        self._ids = id_generator

    async def execute(self, command: GenerateContractCommand) -> GeneratedContract:
        """Run §9.11 and return the finished contract.

        Raises:
            EntityNotFound: template, version, customer or bank account missing.
            ValidationError: one or more 🔴 `V-CTR-*` rules failed; `context`
                carries `issues`, the list the `422` body renders (§5.3.8).
            RenderError / TemplateNotFoundError / TemplateChecksumMismatchError:
                the render failed — the contract row survives as
                `GENERATION_FAILED`.
            InsufficientStorageError: the Vault write could not be started.
        """
        prepared = await self._reserve(command)
        try:
            document_ref, sha256, size_bytes, generation_ms = await self._produce(
                prepared
            )
        except DomainException as exc:
            await self._mark_failed(prepared.contract_id, exc)
            raise

        try:
            created_at = await self._finalize(
                prepared, document_ref, sha256, size_bytes, generation_ms
            )
        except Exception as exc:
            # ⚠️ The file is written but nothing references it. Drop it: an
            # unreferenced `.enc` is encrypted garbage, and leaving it makes
            # §9.15's weekly reconciliation report a discrepancy that is not
            # one. Best effort — if this fails too, that report is the net.
            self._discard(document_ref)
            await self._mark_failed(prepared.contract_id, exc)
            raise

        return GeneratedContract(
            contract_id=prepared.contract_id,
            contract_no=prepared.contract_no,
            export_name=prepared.export_name,
            document_id=prepared.document_id,
            vault_path=document_ref.relative_path,
            file_sha256=sha256,
            file_size_bytes=size_bytes,
            generation_ms=generation_ms,
            created_at=created_at,
            warnings=prepared.warnings,
        )

    # ---------------------------------------------------------- transaction 1

    async def _reserve(self, command: GenerateContractCommand) -> _PreparedContract:
        """Validate, allocate a number, and commit the `GENERATING` row."""
        async with self._uow_factory() as uow:
            template = await uow.templates.get_for_update(command.template_id)
            if template is None or template.is_deleted:
                raise EntityNotFound(
                    "Không tìm thấy mẫu hợp đồng.", code="COCAS-6001"
                )

            version = (
                await uow.template_versions.get(template.active_version_id)
                if template.active_version_id is not None
                else None
            )
            parties = await self._resolve_parties(uow, command.parties)

            today = self._clock.today()
            contract_no = self._contract_numbers.generate(
                template.contract_no_pattern, today, template.next_contract_sequence()
            )
            draft = _draft(command, parties, contract_no, today)
            context = self._context_builder.build(draft, template)

            report = self._validate(template, version, parties, context, today)
            if not report.is_valid:
                # ⭐ Raised before any row is written, so the rollback leaves
                # nothing behind — including the sequence increment, which is
                # exactly right: a rejected request must not burn a contract
                # number (§9.14.1 "Duy nhất? ✅ Bắt buộc UNIQUE").
                raise ValidationError(
                    _summary(report),
                    code="COCAS-7002",
                    issues=list(report.errors),
                )

            assert version is not None  # V-CTR-001 proved it.
            export_name = self._export_names.generate(
                template.export_name_pattern, dict(context), set()
            )
            contract = self._new_contract(command, version, parties, export_name, draft)

            uow.contracts.stage_snapshot(dict(context))
            await uow.contracts.add(contract)
            for index, (request, party) in enumerate(zip(command.parties, parties, strict=True)):
                await uow.contract_parties.add(
                    self._new_party(contract.id, index, request, party, template)
                )
            await uow.templates.update(template)
            await uow.commit()

        logger.info(
            "Reserved contract {} ({}) on template {}",
            contract.id,
            contract_no,
            template.code,
        )
        return _PreparedContract(
            contract_id=contract.id,
            contract_no=contract_no,
            export_name=export_name,
            document_id=self._ids.new_id(),
            template_path=self._templates_dir / version.file_path,
            template_sha256=version.file_sha256,
            context=context,
            warnings=ValidationReport(issues=report.warnings + report.infos),
        )

    # ------------------------------------------------- outside any transaction

    async def _produce(
        self, prepared: _PreparedContract
    ) -> tuple[VaultRef, bytes, int, int]:
        """⭐ Render to memory and store encrypted — no plaintext on disk.

        `render_to_bytes` rather than `render` is the whole point (§12.11.2):
        the only way to feed `render()`'s output to `save()` is via a
        temporary file, and that file would be an unencrypted contract on a
        filesystem where deletion is recoverable.
        """
        document = self._renderer.render_to_bytes(
            str(prepared.template_path),
            self._context_adapter.adapt(prepared.context),
            prepared.template_sha256,
        )
        ref = self._storage.save(document.content, VaultCategory.CONTRACT_DOCUMENT)
        return ref, document.sha256, document.size_bytes, document.duration_ms

    # ---------------------------------------------------------- transaction 2

    async def _finalize(
        self,
        prepared: _PreparedContract,
        ref: VaultRef,
        sha256: bytes,
        size_bytes: int,
        generation_ms: int,
    ) -> datetime:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(prepared.contract_id)
            if contract is None:  # pragma: no cover - T1 committed it
                raise EntityNotFound(
                    "Không tìm thấy hợp đồng vừa tạo.", code="CONTRACT_NOT_FOUND"
                )
            now = self._clock.now()
            await uow.contract_documents.add(
                ContractDocument(
                    id=prepared.document_id,
                    contract_id=contract.id,
                    file_path=ref.relative_path,
                    file_sha256=sha256,
                    file_size_bytes=size_bytes,
                    generator=GENERATOR_NAME,
                    generation_ms=generation_ms,
                    created_at=now,
                )
            )
            contract.mark_completed(sha256, now)
            await uow.contracts.update(contract, expected_version=contract.version - 1)
            await uow.commit()
            return contract.created_at

    async def _mark_failed(self, contract_id: uuid.UUID, error: BaseException) -> None:
        """Record `GENERATION_FAILED` — the reason §12.14.2 exists.

        ⚠️ Swallows its own failures on purpose. This runs while an exception
        is already propagating, and replacing "the render failed" with
        "the database is down" would hide the thing the user needs to see.
        """
        code = getattr(error, "code", "COCAS-7003")
        message = str(error)
        try:
            async with self._uow_factory() as uow:
                contract = await uow.contracts.get(contract_id)
                if contract is None:
                    return
                contract.mark_generation_failed(code, message, self._clock.now())
                await uow.contracts.update(contract)
                await uow.commit()
        except Exception:
            logger.exception("Could not record GENERATION_FAILED for {}", contract_id)

    def _discard(self, ref: VaultRef) -> None:
        try:
            self._storage.delete(ref)
        except Exception:
            logger.exception("Could not remove orphaned Vault file {}", ref.relative_path)

    # ------------------------------------------------------------- assembling

    async def _resolve_parties(
        self, uow: IContractUnitOfWork, requests: Sequence[PartyRequest]
    ) -> tuple[_ResolvedParty, ...]:
        resolved: list[_ResolvedParty] = []
        for request in requests:
            customer = await uow.customers.get(request.customer_id)
            if customer is None:
                raise EntityNotFound(
                    "Không tìm thấy khách hàng.", code="COCAS-5001"
                )
            bank_account = (
                await uow.bank_accounts.get(request.bank_account_id)
                if request.bank_account_id is not None
                else None
            )
            if request.bank_account_id is not None and bank_account is None:
                raise EntityNotFound(
                    "Không tìm thấy tài khoản ngân hàng.", code="COCAS-4008"
                )
            resolved.append(_ResolvedParty(request, customer, bank_account))
        return tuple(resolved)

    def _validate(
        self,
        template: Template,
        version: TemplateVersion | None,
        parties: Sequence[_ResolvedParty],
        context: RenderContext,
        today: date,
    ) -> ValidationReport:
        template_path = (
            self._templates_dir / version.file_path if version is not None else None
        )
        candidate = ContractCandidate(
            template=template,
            version=version,
            parties=tuple(
                PartyCandidate(
                    party_key=party.request.party_key,
                    customer=party.customer,
                    entity_type=party.request.entity_type,
                    has_bank_account=party.bank_account is not None,
                )
                for party in parties
            ),
            missing_required_variables=tuple(
                self._context_builder.missing_required_variables(
                    context, version, template
                )
            )
            if version is not None
            else (),
            template_file_exists=template_path is not None and template_path.is_file(),
            # ⚠️ Reading the file to hash it here would double the I/O of
            # every generation. `DocxRenderer` hashes it anyway on the way in
            # (its cache key is `(path, sha256)`) and raises
            # `TemplateChecksumMismatchError` — so V-CTR-002's checksum half
            # is enforced there, and this flag only reports what is already
            # known to be false.
            template_checksum_matches=True,
            free_disk_bytes=self._free_bytes(),
        )
        return self._validator.validate(
            candidate,
            RuleSetKey.CONTRACT_GENERATION,
            RuleContext(today=today),
        )

    def _free_bytes(self) -> int:
        probe = self._templates_dir if self._templates_dir.exists() else Path.cwd()
        return shutil.disk_usage(probe).free

    def _new_contract(
        self,
        command: GenerateContractCommand,
        version: TemplateVersion,
        parties: Sequence[_ResolvedParty],
        export_name: str,
        draft: ContractDraft,
    ) -> Contract:
        now = self._clock.now()
        primary = next(
            (party for party in parties if party.request.is_primary), parties[0]
        )
        contract = Contract(
            id=self._ids.new_id(),
            contract_no=draft.contract_no,
            export_name=export_name,
            primary_customer_id=primary.customer.id,
            template_version_id=version.id,
            created_by=command.created_by,
            # ⚠️ NOT NULL in §4.4.10, but `suppressed_variables` blanks the
            # rendered `{{contract_date}}` for both real templates. The column
            # records when the contract was made; the document leaves the line
            # empty for a handwritten date. Two different questions.
            contract_date=command.contract_date or draft.today,
            created_at=now,
            updated_at=now,
            supersedes_id=command.supersedes_id,
            revision_no=command.revision_no,
            party_count=len(parties),
            extra_variables=dict(command.extra_variables) or None,
        )
        contract.mark_generating(now)
        return contract

    def _new_party(
        self,
        contract_id: uuid.UUID,
        index: int,
        request: PartyRequest,
        party: _ResolvedParty,
        template: Template,
    ) -> ContractParty:
        schema = next(
            (
                entry
                for entry in template.party_schema
                if entry.get("key") == request.party_key
            ),
            {},
        )
        return ContractParty(
            id=self._ids.new_id(),
            contract_id=contract_id,
            party_key=request.party_key,
            party_index=request.party_index or index,
            party_label=str(schema.get("label", request.party_key)),
            entity_type=request.entity_type,
            customer_id=party.customer.id,
            sort_order=index,
            created_at=self._clock.now(),
            bank_account_id=request.bank_account_id,
            ocr_session_id=request.ocr_session_id,
            is_primary=request.is_primary,
            party_extra=dict(request.party_extra),
        )


# ---------------------------------------------------------------- internals


class _ResolvedParty:
    """A `PartyRequest` with its entities loaded."""

    __slots__ = ("bank_account", "customer", "request")

    def __init__(
        self, request: PartyRequest, customer: Customer, bank_account: BankAccount | None
    ) -> None:
        self.request = request
        self.customer = customer
        self.bank_account = bank_account


class _PreparedContract:
    """What survives transaction 1 and the render needs."""

    __slots__ = (
        "context",
        "contract_id",
        "contract_no",
        "document_id",
        "export_name",
        "template_path",
        "template_sha256",
        "warnings",
    )

    def __init__(
        self,
        contract_id: uuid.UUID,
        contract_no: str,
        export_name: str,
        document_id: uuid.UUID,
        template_path: Path,
        template_sha256: bytes,
        context: RenderContext,
        warnings: ValidationReport,
    ) -> None:
        self.contract_id = contract_id
        self.contract_no = contract_no
        self.export_name = export_name
        self.document_id = document_id
        self.template_path = template_path
        self.template_sha256 = template_sha256
        self.context = context
        self.warnings = warnings


def _draft(
    command: GenerateContractCommand,
    parties: Sequence[_ResolvedParty],
    contract_no: str,
    today: date,
) -> ContractDraft:
    return ContractDraft(
        contract_no=contract_no,
        created_by_name=command.created_by_name or command.created_by,
        today=today,
        parties=tuple(
            PartyDraft(
                party_key=party.request.party_key,
                customer=party.customer,
                bank_account=party.bank_account,
                party_extra=party.request.party_extra,
            )
            for party in parties
        ),
        contract_date=command.contract_date,
        extra_variables=command.extra_variables,
    )


def _summary(report: ValidationReport) -> str:
    errors = report.errors
    if len(errors) == 1:
        return errors[0].message_vi
    return f"Không thể tạo hợp đồng — có {len(errors)} vấn đề cần xử lý."
