"""`SqlAlchemyContractRepository` — ⭐ the last P1 repository, unblocked by module 4.

It was deferred on purpose: `contract.render_snapshot_enc` is NOT NULL and
holds the render context, so there was no way to write a row before
`RenderContextBuilder` existed (§12.9). It exists now, so this does too.

⭐ `Contract` is the only entity with an optimistic-lock `version` (DB-09);
the generic base already honours `expected_version`, so nothing about that
appears here.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.entities.contract import Contract
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.ports.crypto import AadContext, ICryptoService
from cocas.infrastructure.persistence.models.contract import ContractModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository

_TABLE = "contract"
_SNAPSHOT_COLUMN = "render_snapshot_enc"


class SqlAlchemyContractRepository(SqlAlchemyRepository[Contract, ContractModel]):
    """Persist `Contract`, encrypting the render snapshot on the way in."""

    model = ContractModel

    def __init__(self, session: AsyncSession, crypto: ICryptoService) -> None:
        super().__init__(session)
        self._crypto = crypto
        self._pending_snapshot: dict[str, object] | None = None

    def _aad(self, entity_id: object) -> AadContext:
        return AadContext(
            entity_id=str(entity_id), table_name=_TABLE, column_name=_SNAPSHOT_COLUMN
        )

    def stage_snapshot(self, snapshot: dict[str, object]) -> None:
        """Hand the render context in before `add()` (§9.6, P-09).

        ⭐ It travels out-of-band rather than on the entity because a
        `Contract` is a business record, and the snapshot is 20–40 KB of
        rendering detail that no caller of `get()` wants materialised — the
        list screen would decrypt it once per row.
        """
        self._pending_snapshot = snapshot

    def _to_domain(self, row: ContractModel) -> Contract:
        return Contract(
            id=row.id,
            contract_no=row.contract_no,
            export_name=row.export_name,
            primary_customer_id=row.primary_customer_id,
            template_version_id=row.template_version_id,
            created_by=row.created_by,
            contract_date=row.contract_date,
            created_at=row.created_at,
            updated_at=row.updated_at,
            status=ContractStatus(row.status),
            supersedes_id=row.supersedes_id,
            revision_no=row.revision_no,
            party_count=row.party_count,
            snapshot_sha256=row.snapshot_sha256,
            extra_variables=dict(row.extra_variables) if row.extra_variables else None,
            void_reason=row.void_reason,
            voided_at=row.voided_at,
            voided_by=row.voided_by,
            error_code=row.error_code,
            error_message=row.error_message,
            version=row.version,
        )

    def _apply_to_row(self, entity: Contract, row: ContractModel) -> None:
        # ⚠️ `snapshot_sha256` is NOT NULL in the CSDL (§4.4.10) but nullable
        # on the entity, because a `Contract` is representable in memory
        # before its snapshot is hashed. Letting `None` reach the driver
        # surfaces as an `IntegrityError`, which `_base` translates to
        # `DuplicateEntityError` — "bản ghi đã tồn tại" for a row that was
        # never written. Fail here, where the sentence is true.
        if entity.snapshot_sha256 is None:
            raise BusinessRuleViolation(
                "Hợp đồng phải có snapshot ngữ cảnh render trước khi lưu.",
                code="CONTRACT_SNAPSHOT_REQUIRED",
                field="snapshot_sha256",
            )

        row.id = entity.id
        row.contract_no = entity.contract_no
        row.export_name = entity.export_name
        row.primary_customer_id = entity.primary_customer_id
        row.template_version_id = entity.template_version_id
        row.created_by = entity.created_by
        row.contract_date = entity.contract_date
        row.created_at = entity.created_at
        row.updated_at = entity.updated_at
        row.status = entity.status.value
        row.supersedes_id = entity.supersedes_id
        row.revision_no = entity.revision_no
        row.party_count = entity.party_count
        row.snapshot_sha256 = entity.snapshot_sha256
        row.extra_variables = dict(entity.extra_variables) if entity.extra_variables else None
        row.void_reason = entity.void_reason
        row.voided_at = entity.voided_at
        row.voided_by = entity.voided_by
        row.error_code = entity.error_code
        row.error_message = entity.error_message
        row.version = entity.version

        if self._pending_snapshot is not None:
            row.render_snapshot_enc = self._encrypt_snapshot(entity, self._pending_snapshot)
            self._pending_snapshot = None

    def _encrypt_snapshot(self, entity: Contract, snapshot: dict[str, object]) -> bytes:
        """⭐ AAD binds the ciphertext to *this* contract's id.

        Same reasoning as `ocr_field` (§12.17): without it, a snapshot blob
        moved between two contract rows still decrypts cleanly, and the
        "in lại sau 5 năm giống bản gốc" guarantee of P-09 becomes "prints
        somebody's contract".
        """
        plaintext = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self._crypto.encrypt(plaintext, self._aad(entity.id))

    def decrypt_snapshot(self, contract_id: uuid.UUID, blob: bytes) -> dict[str, object]:
        """Read a stored snapshot back (regeneration, diagnostics, P-09 audit)."""
        plaintext = self._crypto.decrypt(blob, self._aad(contract_id))
        loaded: dict[str, object] = json.loads(plaintext.decode("utf-8"))
        return loaded
