"""`ProcessOcrSessionUseCase` — run the pipeline for one session and store it.

This is the seam between `ExtractionPipeline` (which knows nothing about the
database) and the two callers that will exist: `POST /ocr` (§5.2 #17) and the
`OCR` job the `JobRunner` picks up (§12.15). Both need exactly the same six
steps, so neither gets to own them.

## ⭐ Two transactions, not one — a deliberate exception to §12.14

§12.14 states "one Use Case = one UoW = one transaction". This Use Case uses
**two short transactions with the OCR run between them**, and §12.14 now
records the exception rather than being quietly broken by it.

The reason is measured, not stylistic: a run takes ~9.5 s per pair on the
reference machine (§7.4.6). One transaction spanning it would hold a pooled
connection open for those 9.5 s while doing nothing with it — on a deployment
with **one** Uvicorn worker and a job runner polling `job` every 500 ms, that
is the connection pool. It would also mean a crash mid-OCR rolls back the
`PROCESSING` status, leaving the session at `QUEUED` while the progress
endpoint (§5.3.5) reports that nothing has started.

⚠️ The cost of the split is real and worth naming: a crash *between* the two
transactions leaves the session `PROCESSING` forever. That is what §12.15's
stuck-job recovery is for, and it is the same trade every long-running job in
this system makes.

## The pipeline never raises, so neither does the happy path

`ExtractionPipeline` reports failure through `status` + `error_code` (§12.3).
This Use Case keeps that contract: it returns the `ExtractionResult` whatever
the card turned out to be, and only lets *database* failures propagate —
those are not about this card, and retrying the same photo will not fix them.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType
from typing import Protocol

from cocas.application.dto.extraction import (
    Diagnostic,
    ExtractedField,
    ExtractionResult,
    ProgressCallback,
    empty_fields,
    noop_progress,
)
from cocas.application.pipelines.extraction_pipeline import ExtractionPipeline
from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import EntityNotFound
from cocas.domain.ports.ocr import DocumentTypeSpec, PreprocessProfile
from cocas.domain.ports.persistence import OcrFieldSnapshot, OcrResultSnapshot
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.domain.validation.report import ValidationReport
from cocas.domain.value_objects.confidence_score import ConfidenceScore


class IDocumentTypeCatalog(Protocol):
    """The active card generations. `SqlAlchemyDocumentTypeRepository` in prod."""

    async def list_extractable(self) -> Sequence[DocumentTypeSpec]: ...


class IOcrSessionStore(Protocol):
    """The slice of `IReadWriteRepository[OcrSession]` this Use Case needs."""

    async def get(self, entity_id: object) -> OcrSession | None: ...

    async def update(self, entity: OcrSession, expected_version: int | None = None) -> None: ...


class IOcrResultWriter(Protocol):
    """The slice of `IWriteRepository[OcrResultSnapshot]` this Use Case needs."""

    async def add(self, entity: OcrResultSnapshot) -> None: ...


class IOcrUnitOfWork(Protocol):
    """`IUnitOfWork` (Port 14) plus the two repositories used here.

    Declared in Application rather than reusing the Domain port directly
    because the Domain port deliberately says nothing about *which*
    repositories a UoW exposes — that is per-Use-Case knowledge.
    """

    ocr_sessions: IOcrSessionStore
    ocr_results: IOcrResultWriter

    async def __aenter__(self) -> IOcrUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ProcessOcrSessionUseCase:
    """Run S3→S11 for an existing `ocr_session` row and persist the outcome."""

    def __init__(
        self,
        pipeline: ExtractionPipeline,
        document_types: IDocumentTypeCatalog,
        uow_factory: Callable[[], IOcrUnitOfWork],
        id_generator: IIdGenerator,
        clock: IClock,
    ) -> None:
        self._pipeline = pipeline
        self._document_types = document_types
        self._uow_factory = uow_factory
        self._ids = id_generator
        self._clock = clock

    async def execute(
        self,
        session_id: uuid.UUID,
        front_image: bytes,
        back_image: bytes,
        *,
        progress: ProgressCallback = noop_progress,
        profile: PreprocessProfile | None = None,
        known_province_codes: frozenset[str] = frozenset(),
        force_full_ocr: bool = False,
        qr_raw: str | None = None,
        mrz_raw: str | None = None,
    ) -> ExtractionResult:
        """Returns the run's `ExtractionResult`; raises only on database failure."""
        doc_types = await self._document_types.list_extractable()
        if not doc_types:
            # ⚠️ Not the pipeline's own `NO_DOCUMENT_TYPE`. That one means the
            # caller passed an empty list, which is a bug in the caller. This
            # one means the `document_type` table has no extractable row — a
            # deployment or migration problem — and the two must not share a
            # code, or the log sends the reader to the wrong file.
            return _failed(
                "NO_ACTIVE_DOCUMENT_TYPE",
                "Chưa có loại giấy tờ nào được bật để nhận dạng.",
            )

        await self._mark_processing(session_id)

        result = await self._pipeline.execute(
            front_image,
            back_image,
            doc_types,
            progress,
            profile=profile,
            known_province_codes=known_province_codes,
            force_full_ocr=force_full_ocr,
        )

        await self._store(session_id, result, qr_raw=qr_raw, mrz_raw=mrz_raw)
        return result

    # -- transaction 1 --------------------------------------------------

    async def _mark_processing(self, session_id: uuid.UUID) -> None:
        async with self._uow_factory() as uow:
            session = await uow.ocr_sessions.get(session_id)
            if session is None:
                raise EntityNotFound(
                    "Không tìm thấy phiên OCR.", code="OCR_SESSION_NOT_FOUND"
                )
            # ⭐ A terminal session must not be re-run: `ocr_result` is unique
            # per session, so the second run would fail at flush time, after
            # paying the full OCR cost. Failing here costs nothing and says why.
            session.transition_to(OcrSessionStatus.PROCESSING, self._clock.now())
            await uow.ocr_sessions.update(session)
            await uow.commit()

    # -- transaction 2 --------------------------------------------------

    async def _store(
        self,
        session_id: uuid.UUID,
        result: ExtractionResult,
        *,
        qr_raw: str | None,
        mrz_raw: str | None,
    ) -> None:
        async with self._uow_factory() as uow:
            session = await uow.ocr_sessions.get(session_id)
            if session is None:  # pragma: no cover - transaction 1 proved it exists
                raise EntityNotFound(
                    "Không tìm thấy phiên OCR.", code="OCR_SESSION_NOT_FOUND"
                )

            if result.status is not OcrSessionStatus.FAILED:
                # ⭐ §4.4.3: a FAILED session has **no** `ocr_result` row.
                # Writing one full of nulls would make "the run produced
                # nothing" indistinguishable from "the card was blank".
                await uow.ocr_results.add(
                    self._snapshot(session_id, result, qr_raw=qr_raw, mrz_raw=mrz_raw)
                )

            session.auto_swapped = result.auto_swapped
            session.duration_ms = result.duration_ms
            session.diagnostics = {d.code: d.message_vi for d in result.diagnostics}
            session.overall_confidence = ConfidenceScore(result.overall_confidence)
            session.transition_to(
                result.status, self._clock.now(), error_code=result.error_code
            )
            await uow.ocr_sessions.update(session)
            await uow.commit()

    # -- ExtractionResult (Application) -> snapshots (Domain) -------------

    def _snapshot(
        self,
        session_id: uuid.UUID,
        result: ExtractionResult,
        *,
        qr_raw: str | None,
        mrz_raw: str | None,
    ) -> OcrResultSnapshot:
        summary = result.channel_summary
        return OcrResultSnapshot(
            id=self._ids.new_id(),
            ocr_session_id=session_id,
            qr_available=summary.qr_available,
            mrz_available=summary.mrz_available,
            qr_raw=qr_raw,
            mrz_raw=mrz_raw,
            mrz_checksum_valid=summary.mrz_checksum_valid,
            # ⚠️ NULL when no MRZ was read at all — 0 would claim "read
            # cleanly" and skew §7.5's repair rate downwards.
            mrz_corrections_applied=(
                summary.mrz_corrections_applied if summary.mrz_available else None
            ),
            channel_summary=_channel_summary_json(result),
            validation_report=_validation_json(result.validation_report),
            cross_check_flags=tuple(
                sorted({flag for f in result.fields.values() for flag in f.flags})
            ),
            fields=tuple(self._field_snapshot(key, result.fields[key]) for key in FieldKey),
            created_at=self._clock.now(),
        )

    def _field_snapshot(self, key: FieldKey, extracted: ExtractedField) -> OcrFieldSnapshot:
        bbox = extracted.bbox
        return OcrFieldSnapshot(
            id=self._ids.new_id(),
            field_key=key.value,
            value=extracted.value,
            raw_value=extracted.raw_value,
            source=extracted.source.value,
            confidence=extracted.confidence,
            needs_review=extracted.needs_review,
            bbox=(
                {"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h}
                if bbox is not None
                else None
            ),
            candidates=tuple(
                {
                    "source": candidate.source.value,
                    "confidence": candidate.confidence,
                    "agrees": candidate.agrees,
                }
                for candidate in extracted.candidates
            ),
            normalization_tier=extracted.normalization_tier,
        )


def _channel_summary_json(result: ExtractionResult) -> Mapping[str, str]:
    """§4.4.3 types this column as a flat string map, so values are stringified."""
    summary = result.channel_summary
    return {
        "qr_available": str(summary.qr_available),
        "qr_layout_recognized": str(summary.qr_layout_recognized),
        "qr_attempts": str(summary.qr_attempts),
        "mrz_available": str(summary.mrz_available),
        "mrz_checksum_valid": str(summary.mrz_checksum_valid),
        "mrz_corrections_applied": str(summary.mrz_corrections_applied),
        "ocr_available": str(summary.ocr_available),
        "ocr_regions_detected": str(summary.ocr_regions_detected),
        "text_passes": str(summary.text_passes),
        # ⭐ Which generation the run settled on, kept next to the channel
        # counts because that is where anyone debugging a bad read looks first.
        "card_generation": str(result.card_generation),
    }


def _validation_json(report: ValidationReport) -> Mapping[str, object]:
    return {
        "is_valid": report.is_valid,
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "message_vi": issue.message_vi,
                "field": issue.field,
                "hint": issue.hint,
            }
            for issue in report.issues
        ],
    }


def _failed(code: str, message_vi: str) -> ExtractionResult:
    return ExtractionResult(
        status=OcrSessionStatus.FAILED,
        fields=empty_fields(),
        diagnostics=(Diagnostic(stage="S0", code=code, message_vi=message_vi),),
        error_code=code,
    )
