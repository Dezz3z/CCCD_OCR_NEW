"""`SqlAlchemyContractDocumentRepository` (§4.4.12).

No encryption here: every column is metadata *about* the file. The file's
own bytes are encrypted inside the Vault (§12.13), and `file_path` is a
UUID-based Vault reference that says nothing about the customer.
"""
from __future__ import annotations

from cocas.domain.entities.contract_document import ContractDocument
from cocas.domain.enums.doc_type import DocType
from cocas.infrastructure.persistence.models.contract_document import ContractDocumentModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyContractDocumentRepository(
    SqlAlchemyRepository[ContractDocument, ContractDocumentModel]
):
    model = ContractDocumentModel

    def _to_domain(self, row: ContractDocumentModel) -> ContractDocument:
        return ContractDocument(
            id=row.id,
            contract_id=row.contract_id,
            file_path=row.file_path,
            file_sha256=row.file_sha256,
            file_size_bytes=row.file_size_bytes,
            generator=row.generator,
            generation_ms=row.generation_ms,
            created_at=row.created_at,
            doc_type=DocType(row.doc_type),
            download_count=row.download_count,
            last_downloaded_at=row.last_downloaded_at,
        )

    def _apply_to_row(self, entity: ContractDocument, row: ContractDocumentModel) -> None:
        row.id = entity.id
        row.contract_id = entity.contract_id
        row.doc_type = entity.doc_type.value
        row.file_path = entity.file_path
        row.file_sha256 = entity.file_sha256
        row.file_size_bytes = entity.file_size_bytes
        row.generator = entity.generator
        row.generation_ms = entity.generation_ms
        row.download_count = entity.download_count
        row.last_downloaded_at = entity.last_downloaded_at
        row.created_at = entity.created_at
