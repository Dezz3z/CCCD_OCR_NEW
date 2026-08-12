"""The four OCR endpoints around the pipeline (§5.3.3–§5.3.6, §5.2 #15)."""
from __future__ import annotations

import uuid

import pytest

from cocas.application.use_cases.ocr.manage_ocr_session import (
    OCR_TARGET_TYPE,
    ConfirmOcrSessionUseCase,
    CreateOcrSessionCommand,
    CreateOcrSessionUseCase,
    FailOcrSessionUseCase,
    FieldCorrection,
    GetOcrSessionUseCase,
    UpdateOcrFieldsUseCase,
)
from cocas.domain.entities.card_image import CardImage
from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import BusinessRuleViolation, EntityNotFound
from cocas.domain.ports.persistence import OcrFieldSnapshot, OcrResultSnapshot

from .conftest import NOW, FakeClock, FakeUnitOfWork, SequentialIds

_DOC_TYPE = uuid.UUID(int=0xC0CA)


def _image(image_id: uuid.UUID, side: CardSide, doc_type: uuid.UUID = _DOC_TYPE) -> CardImage:
    return CardImage(
        id=image_id,
        uploaded_by="tester",
        document_type_id=doc_type,
        side_hint=side,
        vault_path=f"card_image/2026/08/12/{image_id}.enc",
        mime_type="image/jpeg",
        width_px=1280,
        height_px=800,
        size_bytes=4096,
        sha256=bytes(32),
        created_at=NOW,
    )


def _session(session_id: uuid.UUID, status: OcrSessionStatus) -> OcrSession:
    completed = NOW if status in {
        OcrSessionStatus.COMPLETED,
        OcrSessionStatus.COMPLETED_WITH_WARNINGS,
        OcrSessionStatus.FAILED,
    } else None
    return OcrSession(
        id=session_id,
        created_by="tester",
        document_type_id=_DOC_TYPE,
        front_image_id=uuid.UUID(int=11),
        back_image_id=uuid.UUID(int=12),
        correlation_id="corr",
        created_at=NOW,
        status=status,
        completed_at=completed,
    )


def _result(session_id: uuid.UUID, *, needs_review: bool = False) -> OcrResultSnapshot:
    return OcrResultSnapshot(
        id=uuid.UUID(int=99),
        ocr_session_id=session_id,
        qr_available=True,
        mrz_available=True,
        channel_summary={"qr_available": "True"},
        validation_report={},
        fields=(
            OcrFieldSnapshot(
                id=uuid.UUID(int=101),
                field_key="id_number",
                value="048179002546",
                raw_value="048179002546",
                source="QR",
                confidence=1.0,
                needs_review=needs_review,
            ),
        ),
        created_at=NOW,
    )


class TestCreate:
    @pytest.mark.asyncio
    async def test_queues_a_session_and_a_job(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        front, back = uuid.UUID(int=1), uuid.UUID(int=2)
        uow.card_images.rows = {
            front: _image(front, CardSide.FRONT),
            back: _image(back, CardSide.BACK),
        }
        result = await CreateOcrSessionUseCase(uow, clock, ids).execute(
            CreateOcrSessionCommand(front, back, "tester", "corr-1")
        )

        assert result.status is OcrSessionStatus.QUEUED
        job = uow.jobs.rows[result.job_id]
        assert job.job_type == JobType.OCR.value
        assert job.status == JobStatus.QUEUED.value
        assert job.target_id == result.session_id
        assert job.target_type == OCR_TARGET_TYPE
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_the_payload_carries_image_ids_not_image_bytes(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """⭐ P-13: `job.payload` is JSONB that lands in diagnostics bundles."""
        front, back = uuid.UUID(int=1), uuid.UUID(int=2)
        uow.card_images.rows = {
            front: _image(front, CardSide.FRONT),
            back: _image(back, CardSide.BACK),
        }
        result = await CreateOcrSessionUseCase(uow, clock, ids).execute(
            CreateOcrSessionCommand(front, back, "tester", "corr-1")
        )
        payload = uow.jobs.rows[result.job_id].payload or {}
        assert payload == {
            "front_image_id": str(front),
            "back_image_id": str(back),
        }

    @pytest.mark.asyncio
    async def test_a_missing_image_is_named(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        front = uuid.UUID(int=1)
        uow.card_images.rows = {front: _image(front, CardSide.FRONT)}
        with pytest.raises(EntityNotFound):
            await CreateOcrSessionUseCase(uow, clock, ids).execute(
                CreateOcrSessionCommand(front, uuid.UUID(int=2), "tester", "c")
            )

    @pytest.mark.asyncio
    async def test_a_purged_image_cannot_start_a_session(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        front, back = uuid.UUID(int=1), uuid.UUID(int=2)
        purged = _image(front, CardSide.FRONT)
        purged.purge("retention", NOW)
        uow.card_images.rows = {front: purged, back: _image(back, CardSide.BACK)}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await CreateOcrSessionUseCase(uow, clock, ids).execute(
                CreateOcrSessionCommand(front, back, "tester", "c")
            )
        assert exc_info.value.code == "IMAGE_PURGED"

    @pytest.mark.asyncio
    async def test_images_of_two_different_document_types_are_rejected(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        front, back = uuid.UUID(int=1), uuid.UUID(int=2)
        uow.card_images.rows = {
            front: _image(front, CardSide.FRONT),
            back: _image(back, CardSide.BACK, uuid.UUID(int=0xBEEF)),
        }
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await CreateOcrSessionUseCase(uow, clock, ids).execute(
                CreateOcrSessionCommand(front, back, "tester", "c")
            )
        assert exc_info.value.code == "MIXED_DOCUMENT_TYPES"


class TestRead:
    @pytest.mark.asyncio
    async def test_returns_the_session_and_its_fields(
        self, uow: FakeUnitOfWork
    ) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}
        uow.ocr_results.by_session = {session_id: _result(session_id)}

        view = await GetOcrSessionUseCase(uow).execute(session_id)
        assert view.result is not None
        assert view.result.fields[0].value == "048179002546"

    @pytest.mark.asyncio
    async def test_progress_reports_a_number_even_before_the_runner_starts(
        self, uow: FakeUnitOfWork
    ) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.QUEUED)}
        progress = await GetOcrSessionUseCase(uow).progress(session_id)
        assert progress.percent == 0
        assert progress.status is OcrSessionStatus.QUEUED

    @pytest.mark.asyncio
    async def test_a_completed_session_reports_one_hundred(
        self, uow: FakeUnitOfWork
    ) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}
        assert (await GetOcrSessionUseCase(uow).progress(session_id)).percent == 100

    @pytest.mark.asyncio
    async def test_unknown_session(self, uow: FakeUnitOfWork) -> None:
        with pytest.raises(EntityNotFound):
            await GetOcrSessionUseCase(uow).execute(uuid.UUID(int=404))


class TestCorrections:
    @pytest.mark.asyncio
    async def test_applies_a_correction(self, uow: FakeUnitOfWork) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}
        uow.ocr_results.by_session = {session_id: _result(session_id)}

        applied = await UpdateOcrFieldsUseCase(uow).execute(
            session_id, [FieldCorrection(uuid.UUID(int=101), "048179002547")]
        )
        assert applied == 1
        assert uow.ocr_results.corrections == [(uuid.UUID(int=101), "048179002547")]

    @pytest.mark.asyncio
    async def test_a_field_from_another_session_is_refused(
        self, uow: FakeUnitOfWork
    ) -> None:
        """⚠️ Without this, owning one session lets you rewrite any field row."""
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}
        uow.ocr_results.by_session = {session_id: _result(session_id)}

        with pytest.raises(EntityNotFound):
            await UpdateOcrFieldsUseCase(uow).execute(
                session_id, [FieldCorrection(uuid.UUID(int=999), "x")]
            )
        assert uow.ocr_results.corrections == []

    @pytest.mark.asyncio
    async def test_correcting_before_a_result_exists(self, uow: FakeUnitOfWork) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.PROCESSING)}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await UpdateOcrFieldsUseCase(uow).execute(
                session_id, [FieldCorrection(uuid.UUID(int=101), "x")]
            )
        assert exc_info.value.code == "OCR_RESULT_NOT_READY"


class TestConfirm:
    @pytest.mark.asyncio
    async def test_confirms_a_completed_session(self, uow: FakeUnitOfWork) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}
        uow.ocr_results.by_session = {session_id: _result(session_id)}
        view = await ConfirmOcrSessionUseCase(uow).execute(session_id)
        assert view.result is not None

    @pytest.mark.asyncio
    async def test_refuses_while_a_field_still_needs_review(
        self, uow: FakeUnitOfWork
    ) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}
        uow.ocr_results.by_session = {session_id: _result(session_id, needs_review=True)}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await ConfirmOcrSessionUseCase(uow).execute(session_id)
        assert exc_info.value.code == "FIELDS_NEED_REVIEW"

    @pytest.mark.asyncio
    async def test_refuses_a_session_still_running(self, uow: FakeUnitOfWork) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.PROCESSING)}
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await ConfirmOcrSessionUseCase(uow).execute(session_id)
        assert exc_info.value.code == "OCR_SESSION_NOT_COMPLETED"


class TestFailRelease:
    """🔴 The gap the first end-to-end run exposed."""

    @pytest.mark.asyncio
    async def test_a_stuck_processing_session_is_released(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.PROCESSING)}

        await FailOcrSessionUseCase(uow, clock).execute(session_id, "BOOM", "nổ")

        stored = uow.ocr_sessions.rows[session_id]
        assert stored.status is OcrSessionStatus.FAILED
        assert stored.error_code == "BOOM"
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_a_terminal_session_is_left_alone(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        """Idempotent: the runner may call this after a race or a sweep."""
        session_id = uuid.UUID(int=7)
        uow.ocr_sessions.rows = {session_id: _session(session_id, OcrSessionStatus.COMPLETED)}

        await FailOcrSessionUseCase(uow, clock).execute(session_id, "BOOM", "nổ")

        assert uow.ocr_sessions.rows[session_id].status is OcrSessionStatus.COMPLETED
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_an_unknown_session_is_not_an_error(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        await FailOcrSessionUseCase(uow, clock).execute(uuid.UUID(int=404), "B", "n")
        assert uow.commits == 0
