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

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.exceptions import (
    DatabaseUnavailableError,
    DuplicateEntityError,
    PersistenceError,
)
from cocas.domain.ports.crypto import AadContext, ICryptoService
from cocas.domain.ports.persistence import OcrFieldSnapshot, OcrResultSnapshot
from cocas.infrastructure.persistence.models.ocr_field import OcrFieldModel
from cocas.infrastructure.persistence.models.ocr_result import OcrResultModel

_RESULT_TABLE = "ocr_result"
_FIELD_TABLE = "ocr_field"

#: asyncpg exposes `constraint_name` directly; the fallback parses the text for
#: the drivers and wrapper layers that do not.
_CONSTRAINT_IN_TEXT = re.compile(r'constraint "([^"]+)"')


def _constraint_from(text: str) -> str | None:
    match = _CONSTRAINT_IN_TEXT.search(text)
    return match.group(1) if match else None


class SqlAlchemyOcrResultRepository:
    """Persists one `OcrResultSnapshot` as 1 `ocr_result` + N `ocr_field` rows."""

    def __init__(self, session: AsyncSession, crypto: ICryptoService) -> None:
        self._session = session
        self._crypto = crypto

    async def add(self, entity: OcrResultSnapshot) -> None:
        """Insert the result and its fields. Ids come from the caller (DB-01).

        🔴 **The parent is flushed on its own, before the children are added.**
        Measured 2026-08-12 on the first real run: adding all rows and flushing
        once emitted `INSERT INTO ocr_field` **first** and never reached
        `INSERT INTO ocr_result` — the FK blew up on statement one and aborted
        the flush. SQLAlchemy's unit of work orders inserts by *mapper*
        dependency, and these two mappers have none: `ocr_field.ocr_result_id`
        is a bare `ForeignKey` column with no `relationship()` between the
        classes, so there is nothing for the sorter to sort by.

        Two flushes rather than a `relationship()` because the relationship
        would exist purely to teach the ORM an ordering — no code would ever
        traverse it — and this way the ordering is stated where it matters
        instead of inferred from a mapping nobody reads.
        """
        if entity.created_at is None:
            # ⚠️ No wall-clock fallback. `ocr_result.created_at` is NOT NULL
            # with no server default, and every timestamp in this system comes
            # from the injected `IClock` (P-09 determinism: a test with a frozen
            # clock must produce a reproducible row). Quietly substituting
            # `datetime.now()` here would make that hold everywhere except the
            # one table nobody looked at.
            raise PersistenceError(
                "Thiếu thời điểm tạo cho kết quả nhận dạng.",
                code="OCR_RESULT_MISSING_CREATED_AT",
            )

        result_row = OcrResultModel(
            created_at=entity.created_at,
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

        try:
            await self._session.flush()

            for snapshot in entity.fields:
                self._session.add(self._field_row(entity.id, snapshot))
            await self._session.flush()
        except IntegrityError as exc:
            # ⚠️ Not every `IntegrityError` here is a duplicate. This INSERT
            # also carries five CHECK constraints (`field_key`, `source`,
            # `confidence`, `normalization_tier`) and a handful of NOT NULLs,
            # and mapping all of them to "this session already has a result"
            # sent a real investigation looking for a row that did not exist
            # (measured 2026-08-12, first end-to-end run). The constraint name
            # is the one fact that distinguishes them, so it travels with the
            # error.
            constraint = getattr(getattr(exc, "orig", None), "constraint_name", None)
            if constraint is None:
                constraint = _constraint_from(str(exc.orig or exc))
            if constraint and "uq_" not in constraint:
                raise PersistenceError(
                    "Không lưu được kết quả nhận dạng: dữ liệu vi phạm ràng buộc.",
                    code="OCR_RESULT_CONSTRAINT_VIOLATION",
                    constraint=constraint,
                ) from exc
            raise DuplicateEntityError(
                "Phiên OCR này đã có kết quả được lưu.",
                code="DUPLICATE_OCR_RESULT",
                constraint=constraint or "unknown",
            ) from exc
        except OperationalError as exc:  # pragma: no cover - needs a dead DB
            raise DatabaseUnavailableError("Không kết nối được cơ sở dữ liệu.") from exc

    async def get_by_session(self, session_id: uuid.UUID) -> OcrResultSnapshot | None:
        """Read back one run, decrypting every value (§5.3.4).

        ⭐ `value` is the **effective** value: `user_value_enc` when the user
        corrected the field, otherwise `final_value_enc`. §5.3.4 shows the user
        what the contract will actually carry, and pitfall #6 already settled
        that the API returns full PII rather than the `_masked` columns — those
        are for logs and list views.

        ⚠️ `user_corrected` is kept alongside, not folded away. §14.7's
        improvement loop needs to know the machine was overruled; a response
        that only carries the winning string erases that.
        """
        statement = select(OcrResultModel).where(
            OcrResultModel.ocr_session_id == session_id
        )
        result_row = (await self._session.execute(statement)).scalar_one_or_none()
        if result_row is None:
            return None

        field_rows = (
            (
                await self._session.execute(
                    select(OcrFieldModel)
                    .where(OcrFieldModel.ocr_result_id == result_row.id)
                    .order_by(OcrFieldModel.field_key)
                )
            )
            .scalars()
            .all()
        )

        fields = tuple(
            OcrFieldSnapshot(
                id=row.id,
                field_key=row.field_key,
                value=self._decrypt(
                    row.user_value_enc if row.user_corrected else row.final_value_enc,
                    row.id,
                    _FIELD_TABLE,
                    "user_value_enc" if row.user_corrected else "final_value_enc",
                ),
                raw_value=self._decrypt(
                    row.raw_value_enc, row.id, _FIELD_TABLE, "raw_value_enc"
                ),
                source=row.source,
                confidence=row.confidence,
                needs_review=row.needs_review,
                bbox=dict(row.bbox) if row.bbox else None,
                candidates=tuple(row.candidates or ()),
                normalization_tier=row.normalization_tier,
            )
            for row in field_rows
        )

        return OcrResultSnapshot(
            id=result_row.id,
            ocr_session_id=result_row.ocr_session_id,
            qr_available=result_row.qr_available,
            mrz_available=result_row.mrz_available,
            channel_summary=dict(result_row.channel_summary or {}),
            validation_report=dict(result_row.validation_report or {}),
            fields=fields,
            mrz_checksum_valid=result_row.mrz_checksum_valid,
            mrz_corrections_applied=result_row.mrz_corrections_applied,
            cross_check_flags=tuple(result_row.cross_check_flags or ()),
        )

    async def correct_field(
        self, field_id: uuid.UUID, value: str, *, corrected: bool = True
    ) -> bool:
        """Apply a user edit to one `ocr_field` (§5.3.6). Returns False if absent.

        ⚠️ Writes `user_value_enc` and leaves `final_value_enc` alone — see
        `update()`'s docstring. The machine's answer is evidence, not a draft.
        """
        row = await self._session.get(OcrFieldModel, field_id)
        if row is None:
            return False
        row.user_value_enc = self._encrypt(value, row.id, _FIELD_TABLE, "user_value_enc")
        row.user_corrected = corrected
        # A field the user has just set is, by definition, no longer in doubt.
        row.needs_review = False
        await self._session.flush()
        return True

    def _decrypt(
        self, blob: bytes | None, entity_id: object, table: str, column: str
    ) -> str | None:
        if blob is None:
            return None
        return self._crypto.decrypt(
            blob,
            AadContext(entity_id=str(entity_id), table_name=table, column_name=column),
        ).decode("utf-8")

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
