"""`ProcessOcrSessionUseCase` — the seam between the pipeline and the database.

The pipeline itself is covered by `test_extraction_pipeline.py`; these tests
are about the six things only this Use Case can get wrong:

1. the session is `PROCESSING` **before** OCR starts, not after;
2. a FAILED run writes no `ocr_result` row (§4.4.3);
3. every non-FAILED run writes exactly one result and six fields;
4. `mrz_corrections_applied` is NULL when there was no MRZ, 0 when there was;
5. an empty `document_type` table is reported as its own error, not the
   pipeline's `NO_DOCUMENT_TYPE`;
6. neither transaction is left uncommitted.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import pytest

from cocas.application.dto.extraction import (
    ChannelSummary,
    Diagnostic,
    ExtractedField,
    ExtractionResult,
    empty_fields,
)
from cocas.application.use_cases.ocr.process_ocr_session import ProcessOcrSessionUseCase
from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import EntityNotFound
from cocas.domain.ports.ocr import DocumentTypeSpec, RelativeBox
from cocas.domain.ports.persistence import OcrResultSnapshot
from cocas.domain.services.field_fusion_service import FusedField
from cocas.domain.validation.report import Severity, ValidationIssue, ValidationReport
from tests.fixtures.fake_ports import FrozenClock, InMemoryRepository, SequentialIdGenerator

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
SESSION_ID = uuid.UUID("0192f4c0-aaaa-7000-c333-444455556666")

DOC_TYPE = DocumentTypeSpec(
    code="CCCD_CHIP",
    name="Căn cước công dân gắn chip",
    field_schema=[],
    zone_map={},
    anchor_patterns={},
    has_qr=True,
    has_mrz=True,
    is_ocr_supported=True,
    expected_aspect_ratio=1.58,
)


# ---------------------------------------------------------------- fakes


class FakeCatalog:
    def __init__(self, types: Sequence[DocumentTypeSpec]) -> None:
        self.types = types

    async def list_extractable(self) -> Sequence[DocumentTypeSpec]:
        return self.types


class RecordingResultWriter:
    def __init__(self) -> None:
        self.saved: list[OcrResultSnapshot] = []

    async def add(self, entity: OcrResultSnapshot) -> None:
        self.saved.append(entity)


class FakeUow:
    """One UoW instance reused across both `async with` blocks of a run.

    Deliberately records **every** enter/commit rather than only the last, so
    a test can prove the Use Case opened two transactions and committed both —
    the invariant the two-transaction design lives on.
    """

    def __init__(self, sessions: InMemoryRepository) -> None:
        self.ocr_sessions = sessions
        self.ocr_results = RecordingResultWriter()
        self.enters = 0
        self.commits = 0

    async def __aenter__(self) -> FakeUow:
        self.enters += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class FakePipeline:
    """Returns a canned result and records the session status it observed.

    ⭐ Capturing the status *during* `execute` is the only way to test
    ordering: by the time the Use Case returns, the session has moved on and
    "was it PROCESSING while OCR ran?" is no longer answerable from the end
    state.
    """

    def __init__(self, result: ExtractionResult, session: OcrSession) -> None:
        self._result = result
        self._session = session
        self.status_during_run: OcrSessionStatus | None = None
        self.doc_types_seen: Sequence[DocumentTypeSpec] = ()

    async def execute(
        self,
        front_image: bytes,
        back_image: bytes,
        doc_types: Sequence[DocumentTypeSpec],
        progress: Any = None,
        **kwargs: Any,
    ) -> ExtractionResult:
        self.status_during_run = self._session.status
        self.doc_types_seen = doc_types
        return self._result


# ---------------------------------------------------------------- helpers


def _session(status: OcrSessionStatus = OcrSessionStatus.QUEUED) -> OcrSession:
    return OcrSession(
        id=SESSION_ID,
        created_by="nvnghiep",
        document_type_id=uuid.uuid4(),
        front_image_id=uuid.uuid4(),
        back_image_id=uuid.uuid4(),
        correlation_id="corr-1",
        created_at=NOW,
        status=status,
        # A terminal session must carry a completion time — the entity refuses
        # to exist without one, so a test building one has to supply it too.
        completed_at=NOW if status.is_terminal else None,
    )


def _result(
    status: OcrSessionStatus = OcrSessionStatus.COMPLETED,
    *,
    summary: ChannelSummary | None = None,
    error_code: str | None = None,
) -> ExtractionResult:
    fields = empty_fields()
    fields[FieldKey.ID_NUMBER] = ExtractedField(
        fused=FusedField(
            value="001199012345",
            confidence=0.99,
            source=FieldSource.QR,
            needs_review=False,
            flags=("SOURCE_CONFLICT",),
        ),
        raw_value="001199012345",
        bbox=RelativeBox(x=0.1, y=0.2, w=0.3, h=0.05),
        normalization_tier=None,
    )
    fields[FieldKey.ISSUE_PLACE] = ExtractedField(
        fused=FusedField(
            value="BỘ CÔNG AN", confidence=0.92, source=FieldSource.OCR, needs_review=False
        ),
        raw_value="BO CONG AN",
        normalization_tier=5,
    )
    return ExtractionResult(
        status=status,
        fields=fields,
        channel_summary=summary or ChannelSummary(qr_available=True, mrz_available=True),
        validation_report=ValidationReport(
            issues=(
                ValidationIssue(
                    code="V-OCR-021",
                    severity=Severity.WARNING,
                    message_vi="Mã tỉnh lạ.",
                    field="id_number",
                ),
            )
        ),
        diagnostics=(Diagnostic(stage="S7", code="LOW_QUALITY", message_vi="Ảnh mờ."),),
        overall_confidence=0.95,
        auto_swapped=True,
        duration_ms=9500,
        error_code=error_code,
        card_generation="CCCD_CHIP",
    )


def _build(
    result: ExtractionResult,
    *,
    session: OcrSession | None = None,
    types: Sequence[DocumentTypeSpec] = (DOC_TYPE,),
) -> tuple[ProcessOcrSessionUseCase, FakeUow, FakePipeline]:
    session = session or _session()
    uow = FakeUow(InMemoryRepository([session]))
    pipeline = FakePipeline(result, session)
    use_case = ProcessOcrSessionUseCase(
        pipeline=pipeline,  # type: ignore[arg-type]
        document_types=FakeCatalog(types),
        uow_factory=lambda: uow,  # type: ignore[arg-type,return-value]
        id_generator=SequentialIdGenerator(),
        clock=FrozenClock(NOW),
    )
    return use_case, uow, pipeline


# ---------------------------------------------------------------- tests


class TestOrdering:
    @pytest.mark.asyncio
    async def test_session_is_processing_while_ocr_runs(self) -> None:
        use_case, _, pipeline = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert pipeline.status_during_run is OcrSessionStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_both_transactions_are_committed(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert (uow.enters, uow.commits) == (2, 2)

    @pytest.mark.asyncio
    async def test_final_status_comes_from_the_pipeline(self) -> None:
        use_case, uow, _ = _build(_result(OcrSessionStatus.COMPLETED_WITH_WARNINGS))
        await use_case.execute(SESSION_ID, b"front", b"back")
        stored = await uow.ocr_sessions.get(SESSION_ID)
        assert stored.status is OcrSessionStatus.COMPLETED_WITH_WARNINGS
        assert stored.completed_at == NOW
        assert stored.auto_swapped is True
        assert stored.duration_ms == 9500
        assert stored.overall_confidence is not None
        assert stored.overall_confidence.value == pytest.approx(0.95)


class TestPersistence:
    @pytest.mark.asyncio
    async def test_writes_one_result_with_all_six_fields(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")

        assert len(uow.ocr_results.saved) == 1
        snapshot = uow.ocr_results.saved[0]
        assert {f.field_key for f in snapshot.fields} == {k.value for k in FieldKey}
        assert snapshot.ocr_session_id == SESSION_ID

    @pytest.mark.asyncio
    async def test_failed_run_writes_no_result_row(self) -> None:
        """§4.4.3 — a FAILED session has no `ocr_result` at all."""
        use_case, uow, _ = _build(_result(OcrSessionStatus.FAILED, error_code="ENGINE_DEAD"))
        await use_case.execute(SESSION_ID, b"front", b"back")

        assert uow.ocr_results.saved == []
        stored = await uow.ocr_sessions.get(SESSION_ID)
        assert stored.status is OcrSessionStatus.FAILED
        assert stored.error_code == "ENGINE_DEAD"

    @pytest.mark.asyncio
    async def test_field_trace_survives_the_translation(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")

        fields = {f.field_key: f for f in uow.ocr_results.saved[0].fields}
        id_number = fields[FieldKey.ID_NUMBER.value]
        assert id_number.value == "001199012345"
        assert id_number.raw_value == "001199012345"
        assert id_number.source == FieldSource.QR.value
        assert id_number.bbox == {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}
        assert fields[FieldKey.ISSUE_PLACE.value].normalization_tier == 5

    @pytest.mark.asyncio
    async def test_unread_field_is_stored_as_null_not_dropped(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")

        fields = {f.field_key: f for f in uow.ocr_results.saved[0].fields}
        full_name = fields[FieldKey.FULL_NAME.value]
        assert full_name.value is None
        assert full_name.confidence == 0.0
        assert full_name.needs_review is True

    @pytest.mark.asyncio
    async def test_cross_check_flags_are_collected_and_sorted(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert uow.ocr_results.saved[0].cross_check_flags == ("SOURCE_CONFLICT",)

    @pytest.mark.asyncio
    async def test_validation_report_is_serialized_whole(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")

        report = uow.ocr_results.saved[0].validation_report
        assert report["is_valid"] is True  # a WARNING never invalidates (§8.2)
        assert report["issues"] == [
            {
                "code": "V-OCR-021",
                "severity": "WARNING",
                "message_vi": "Mã tỉnh lạ.",
                "field": "id_number",
                "hint": None,
            }
        ]

    @pytest.mark.asyncio
    async def test_card_generation_is_kept_next_to_the_channel_counts(self) -> None:
        use_case, uow, _ = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert uow.ocr_results.saved[0].channel_summary["card_generation"] == "CCCD_CHIP"


class TestMrzCorrectionsNullVersusZero:
    """⚠️ NULL means "no MRZ to read"; 0 means "read, needed no repair"."""

    @pytest.mark.asyncio
    async def test_null_when_mrz_channel_never_produced_anything(self) -> None:
        summary = ChannelSummary(qr_available=True, mrz_available=False)
        use_case, uow, _ = _build(_result(summary=summary))
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert uow.ocr_results.saved[0].mrz_corrections_applied is None

    @pytest.mark.asyncio
    async def test_zero_when_mrz_was_read_cleanly(self) -> None:
        summary = ChannelSummary(mrz_available=True, mrz_corrections_applied=0)
        use_case, uow, _ = _build(_result(summary=summary))
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert uow.ocr_results.saved[0].mrz_corrections_applied == 0


class TestPreconditions:
    @pytest.mark.asyncio
    async def test_empty_document_type_table_is_its_own_error(self) -> None:
        use_case, uow, pipeline = _build(_result(), types=())
        result = await use_case.execute(SESSION_ID, b"front", b"back")

        assert result.status is OcrSessionStatus.FAILED
        assert result.error_code == "NO_ACTIVE_DOCUMENT_TYPE"
        # ⭐ Nothing was touched: no transaction, no OCR, no status change.
        assert uow.enters == 0
        assert pipeline.status_during_run is None

    @pytest.mark.asyncio
    async def test_missing_session_raises_before_any_ocr_work(self) -> None:
        use_case, _, pipeline = _build(_result())
        with pytest.raises(EntityNotFound):
            await use_case.execute(uuid.uuid4(), b"front", b"back")
        assert pipeline.status_during_run is None

    @pytest.mark.asyncio
    async def test_rerunning_a_finished_session_is_refused(self) -> None:
        """`ocr_result` is unique per session — catch it before paying for OCR."""
        finished = _session(OcrSessionStatus.COMPLETED)
        use_case, _, pipeline = _build(_result(), session=finished)

        with pytest.raises(Exception) as exc_info:
            await use_case.execute(SESSION_ID, b"front", b"back")
        assert "OCR_SESSION_ALREADY_TERMINAL" in str(getattr(exc_info.value, "code", ""))
        assert pipeline.status_during_run is None

    @pytest.mark.asyncio
    async def test_document_types_reach_the_pipeline_unchanged(self) -> None:
        use_case, _, pipeline = _build(_result())
        await use_case.execute(SESSION_ID, b"front", b"back")
        assert list(pipeline.doc_types_seen) == [DOC_TYPE]
