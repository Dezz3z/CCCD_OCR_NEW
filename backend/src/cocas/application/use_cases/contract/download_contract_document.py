"""`DownloadContractDocumentUseCase` — §5.3.9 `GET /contracts/{id}/documents/docx`.

⭐ The client sends a **contract id**, never a path (§5.5 #3). The `file_path`
comes out of the database and goes through the Vault's own guard, so a caller
cannot name a file — not even one that exists.

⚠️ The SHA-256 is re-checked on the way out. §9.15's weekly job would catch a
corrupted document eventually; this catches it before it reaches the user,
which is the difference between "we told you" and "you signed it".
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from cocas.domain.entities.contract import Contract
from cocas.domain.entities.contract_document import ContractDocument
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.exceptions import (
    BusinessRuleViolation,
    DocumentIntegrityError,
    EntityNotFound,
)
from cocas.domain.ports.storage import IFileStorage, VaultCategory, VaultRef
from cocas.domain.ports.system import IClock


class IContractReader(Protocol):
    async def get(self, entity_id: object) -> Contract | None: ...


class IContractDocumentReader(Protocol):
    async def get_for_contract(
        self, contract_id: uuid.UUID
    ) -> ContractDocument | None: ...

    async def record_download(self, document_id: uuid.UUID, now: object) -> None: ...


class IDownloadUnitOfWork(Protocol):
    contracts: IContractReader
    contract_documents: IContractDocumentReader

    async def __aenter__(self) -> IDownloadUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class DownloadedDocument:
    content: bytes
    file_name: str
    """⭐ `contract.export_name` **plus the extension**.

    §9.14's pattern (`Mẫu 01A - {full_name}`) produces the stem only, and the
    column stores exactly that — the extension is a property of the format,
    not of the naming rule, and `01A_GDKQ` uses the same stem for a different
    `doc_type`. Adding it here rather than in the router means every consumer
    gets a name Word will actually open; the first end-to-end run downloaded
    `Mẫu 01A - VÕ HUỲNH NGÂN GIAO` with no extension at all.
    """

    sha256: bytes
    size_bytes: int


class DownloadContractDocumentUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], IDownloadUnitOfWork],
        file_storage: IFileStorage,
        clock: IClock,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._clock = clock

    async def execute(self, contract_id: uuid.UUID) -> DownloadedDocument:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(contract_id)
            if contract is None:
                raise EntityNotFound(
                    "Không tìm thấy hợp đồng.",
                    details={"contract_id": str(contract_id)},
                )
            if contract.status is ContractStatus.VOIDED:
                raise BusinessRuleViolation(
                    "Hợp đồng đã bị huỷ.",
                    code="CONTRACT_VOIDED",
                    hint="Sinh lại hợp đồng mới nếu cần bản thay thế.",
                )
            document = await uow.contract_documents.get_for_contract(contract_id)
            if document is None:
                raise BusinessRuleViolation(
                    "Tài liệu của hợp đồng chưa sẵn sàng.",
                    code="DOCUMENT_NOT_READY",
                    hint="Đợi hợp đồng chuyển sang trạng thái COMPLETED rồi tải lại.",
                )
            file_name = f"{contract.export_name}.{document.doc_type.value.lower()}"

        content = self._file_storage.load(
            VaultRef(
                category=VaultCategory.CONTRACT_DOCUMENT,
                relative_path=document.file_path,
            )
        )
        actual = hashlib.sha256(content).digest()
        if actual != document.file_sha256:
            raise DocumentIntegrityError(
                "File hợp đồng trên đĩa không khớp với bản đã ghi nhận.",
                details={"contract_id": str(contract_id)},
            )

        async with self._uow_factory() as uow:
            await uow.contract_documents.record_download(
                document.id, self._clock.now()
            )
            await uow.commit()

        return DownloadedDocument(
            content=content,
            file_name=file_name,
            sha256=actual,
            size_bytes=len(content),
        )
