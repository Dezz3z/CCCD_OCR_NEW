"""`SqlAlchemyOcrResultRepository` — writes `ocr_result` + `ocr_field` (§4.4.3, §4.4.4).

⭐ **A write-only repository with no Domain entity behind it, on purpose.**
`ocr_result`/`ocr_field` are the *trace* of one pipeline run: nothing mutates
them after the run except a user correction, and neither table has an invariant
a Domain entity would protect. Their shape is already stated once, as
`OcrResultSnapshot` in the persistence port — restating it as two entities would
mean three places to keep in step for zero enforcement. It implements
`IWriteRepository[OcrResultSnapshot]` (Port 9), so no new port number is needed.

⭐ **Every extracted value is encrypted** (DB-06): `full_name`, `id_number`,
`dob` and the rest are exactly the PII the encryption layer exists for, and a
card sitting in `ocr_field` is no less identifying than one in `customer`. Only
the trace *around* the values — confidence, source, tier, bbox, candidate
provenance — is stored as plaintext, because none of it names anybody.

⚠️ **The AAD binds to `ocr_field.id`, not to the session or the field key.** Any
coarser binding would let a ciphertext be moved between the 6 rows of the same
result: `dob` pasted over `id_number` would then decrypt cleanly and the
contract would carry someone's birthday as their citizen number.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.exceptions import DatabaseUnavailableError, DuplicateEntityError
from cocas.domain.ports.crypto import AadContext, ICryptoService
from cocas.domain.ports.persistence import OcrFieldSnapshot, OcrResultSnapshot
from cocas.infrastructure.persistence.models.ocr_field import OcrFieldModel
from cocas.infrastructure.persistence.models.ocr_result import OcrResultModel

_RESULT_TABLE = "ocr_result"
_FIELD_TABLE = "ocr_field"


class SqlAlchemyOcrResultRepository:
    """Persists one `OcrResultSnapshot` as 1 `ocr_result` + N `ocr_field` rows."""

    def __init__(self, session: AsyncSession, crypto: ICryptoService) -> None:
        self._session = session
        self._crypto = crypto

    async def add(self, entity: OcrResultSnapshot) -> None:
        """Insert the result and its fields. Ids come from the caller (DB-01)."""
        result_row = OcrResultModel(
            id=entity.id,
            ocr_session_id=entity.ocr_session_id,
            qr_available=entity.qr_available,
            mrz_available=entity.mrz_available,
            mrz_checksum_valid=entity.mrz_checksum_valid,
            mrz_corrections_applied=entity.mrz_corrections_applied,
            channel_summary=dict(entity.channel_summary),
            validation_report=dict(entity.validation_report),
            cross_check_flags=list(entity.cross_check_flags) or None,
        )
        result_row.qr_raw_enc = self._encrypt(
            entity.qr_raw, entity.id, _RESULT_TABLE, "qr_raw_enc"
        )
        result_row.mrz_raw_enc = self._encrypt(
            entity.mrz_raw, entity.id, _RESULT_TABLE, "mrz_raw_enc"
        )
        self._session.add(result_row)

        for snapshot in entity.fields:
            self._session.add(self._field_row(entity.id, snapshot))

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateEntityError(
                "Phiên OCR này đã có kết quả được lưu.", code="DUPLICATE_OCR_RESULT"
            ) from exc
        except OperationalError as exc:  # pragma: no cover - needs a dead DB
            raise DatabaseUnavailableError("Không kết nối được cơ sở dữ liệu.") from exc

    async def update(
        self, entity: OcrResultSnapshot, expected_version: int | None = None
    ) -> None:
        """Not supported — an OCR result is written once and never rewritten.

        A user correction is an `ocr_field` edit (`user_corrected`,
        `user_value_enc`), not a rewrite of the run that produced it: §14.7's
        improvement loop compares the two, so overwriting the machine's answer
        would destroy the only evidence that it was wrong.
        """
        raise NotImplementedError(
            "ocr_result is append-only; correct a field instead of rewriting the run."
        )

    def _field_row(self, ocr_result_id: object, snapshot: OcrFieldSnapshot) -> OcrFieldModel:
        row = OcrFieldModel(
            id=snapshot.id,
            ocr_result_id=ocr_result_id,
            field_key=snapshot.field_key,
            source=snapshot.source,
            confidence=snapshot.confidence,
            needs_review=snapshot.needs_review,
            user_corrected=False,
            bbox=dict(snapshot.bbox) if snapshot.bbox is not None else None,
            candidates=[dict(c) for c in snapshot.candidates] or None,
            normalization_tier=snapshot.normalization_tier,
        )
        row.raw_value_enc = self._encrypt(
            snapshot.raw_value, snapshot.id, _FIELD_TABLE, "raw_value_enc"
        )
        row.normalized_value_enc = self._encrypt(
            snapshot.value, snapshot.id, _FIELD_TABLE, "normalized_value_enc"
        )
        row.final_value_enc = self._encrypt(
            snapshot.value, snapshot.id, _FIELD_TABLE, "final_value_enc"
        )
        return row

    def _encrypt(
        self, value: str | None, entity_id: object, table: str, column: str
    ) -> bytes | None:
        if value is None:
            return None
        return self._crypto.encrypt(
            value.encode(),
            AadContext(entity_id=str(entity_id), table_name=table, column_name=column),
        )
