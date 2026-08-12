"""The four OCR endpoints that are not the pipeline itself (§5.3.3–§5.3.6).

`ProcessOcrSessionUseCase` (module 2) runs the recognition. These four are what
surround it: create the session and queue the work, report progress, hand back
the result, take a correction, and confirm.

⭐ **Creating a session does not run OCR.** §5.3.3 answers `202` with a
`job_id`, and `JobRunner` picks the row up within 500 ms. That split is why a
9.5-second recognition does not hold an HTTP connection open, and why a
backend restart mid-run loses nothing — the `job` row is still `QUEUED`
(pitfall #1).
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from loguru import logger

from cocas.domain.entities.card_image import CardImage
from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.enums.job_type import JobType
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import BusinessRuleViolation, EntityNotFound
from cocas.domain.ports.persistence import OcrResultSnapshot
from cocas.domain.ports.system import IClock, IIdGenerator

__all__ = [
    "OCR_TARGET_TYPE",
    "ConfirmOcrSessionUseCase",
    "CreateOcrSessionCommand",
    "CreateOcrSessionUseCase",
    "FailOcrSessionUseCase",
    "FieldCorrection",
    "GetOcrSessionUseCase",
    "OcrProgress",
    "OcrSessionView",
    "QueuedOcrSession",
    "UpdateOcrFieldsUseCase",
]

#: `job.target_type` for an OCR job — the string `JobRunner` dispatches on.
OCR_TARGET_TYPE = "ocr_session"

#: What `GET /ocr/{id}/progress` reports for a session that has not started.
#: ⭐ Not `None`: the SPA renders a progress bar, and "no number yet" and "0%"
#: look identical to a user but take different code paths in a UI.
_QUEUED_PERCENT = 0


class ICardImageReader(Protocol):
    async def get(self, entity_id: object) -> CardImage | None: ...


class IOcrSessionStore(Protocol):
    async def get(self, entity_id: object) -> OcrSession | None: ...

    async def add(self, entity: OcrSession) -> None: ...

    async def update(self, entity: OcrSession, expected_version: int | None = None) -> None: ...


class IOcrResultReader(Protocol):
    async def get_by_session(self, session_id: uuid.UUID) -> OcrResultSnapshot | None: ...

    async def correct_field(
        self, field_id: uuid.UUID, value: str, *, corrected: bool = True
    ) -> bool: ...


class IJobQueue(Protocol):
    async def enqueue(
        self,
        *,
        job_id: uuid.UUID,
        job_type: JobType,
        correlation_id: str,
        now: object,
        target_id: uuid.UUID | None = None,
        target_type: str | None = None,
        payload: dict[str, object] | None = None,
        priority: int = 100,
    ) -> uuid.UUID: ...

    async def get(self, job_id: uuid.UUID) -> object | None: ...


class IOcrUnitOfWork(Protocol):
    card_images: ICardImageReader
    ocr_sessions: IOcrSessionStore
    ocr_results: IOcrResultReader
    jobs: IJobQueue

    async def __aenter__(self) -> IOcrUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CreateOcrSessionCommand:
    front_image_id: uuid.UUID
    back_image_id: uuid.UUID
    created_by: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class QueuedOcrSession:
    session_id: uuid.UUID
    job_id: uuid.UUID
    status: OcrSessionStatus


@dataclass(frozen=True, slots=True)
class OcrProgress:
    session_id: uuid.UUID
    status: OcrSessionStatus
    percent: int
    message: str | None


@dataclass(frozen=True, slots=True)
class OcrSessionView:
    """`GET /ocr/{id}` (§5.3.4) — the session, its fields, its diagnostics."""

    session: OcrSession
    result: OcrResultSnapshot | None
    front_image_id: uuid.UUID
    back_image_id: uuid.UUID


class CreateOcrSessionUseCase:
    """§5.3.3 `POST /ocr` — create the session and queue the recognition."""

    def __init__(
        self,
        uow_factory: Callable[[], IOcrUnitOfWork],
        clock: IClock,
        id_generator: IIdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, command: CreateOcrSessionCommand) -> QueuedOcrSession:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            front = await self._require_image(uow, command.front_image_id, "front")
            back = await self._require_image(uow, command.back_image_id, "back")

            # ⚠️ Both images must belong to the same declared document type, or
            # `card_image.document_type_id` would disagree with itself inside
            # one session. The pipeline still re-decides the generation (§7.4.7);
            # this only rejects a pair that was never assembled together.
            if front.document_type_id != back.document_type_id:
                raise BusinessRuleViolation(
                    "Hai ảnh không thuộc cùng một loại giấy tờ.",
                    code="MIXED_DOCUMENT_TYPES",
                )

            session = OcrSession(
                id=self._id_generator.new_id(),
                created_by=command.created_by,
                document_type_id=front.document_type_id,
                front_image_id=front.id,
                back_image_id=back.id,
                correlation_id=command.correlation_id,
                created_at=now,
                status=OcrSessionStatus.QUEUED,
            )
            await uow.ocr_sessions.add(session)

            job_id = await uow.jobs.enqueue(
                job_id=self._id_generator.new_id(),
                job_type=JobType.OCR,
                correlation_id=command.correlation_id,
                now=now,
                target_id=session.id,
                target_type=OCR_TARGET_TYPE,
                payload={
                    "front_image_id": str(front.id),
                    "back_image_id": str(back.id),
                },
                priority=10,
            )
            await uow.commit()

        logger.info(
            "ocr session queued", session_id=str(session.id), job_id=str(job_id)
        )
        return QueuedOcrSession(
            session_id=session.id, job_id=job_id, status=session.status
        )

    @staticmethod
    async def _require_image(
        uow: IOcrUnitOfWork, image_id: uuid.UUID, side: str
    ) -> CardImage:
        image = await uow.card_images.get(image_id)
        if image is None:
            raise EntityNotFound(
                f"Không tìm thấy ảnh mặt {'trước' if side == 'front' else 'sau'}.",
                details={"image_id": str(image_id)},
            )
        if image.is_purged:
            raise BusinessRuleViolation(
                "Ảnh đã bị xoá theo chính sách lưu trữ, hãy tải lại.",
                code="IMAGE_PURGED",
            )
        return image


class GetOcrSessionUseCase:
    """§5.3.4 `GET /ocr/{id}` and §5.3.5 `GET /ocr/{id}/progress`."""

    #: Rough progress for a session the runner has picked up but not finished.
    #: ⭐ Deliberately coarse. The runner reports real percentages into
    #: `job.progress_percent`; this is the fallback for a session whose job row
    #: has already been cleaned up, and inventing precision there would be a
    #: number with nothing behind it.
    _STATUS_PERCENT: Mapping[OcrSessionStatus, int] = {
        OcrSessionStatus.CREATED: _QUEUED_PERCENT,
        OcrSessionStatus.QUEUED: _QUEUED_PERCENT,
        OcrSessionStatus.PROCESSING: 50,
        OcrSessionStatus.COMPLETED: 100,
        OcrSessionStatus.COMPLETED_WITH_WARNINGS: 100,
        OcrSessionStatus.FAILED: 100,
    }

    def __init__(self, uow_factory: Callable[[], IOcrUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, session_id: uuid.UUID) -> OcrSessionView:
        async with self._uow_factory() as uow:
            session = await self._require_session(uow, session_id)
            result = await uow.ocr_results.get_by_session(session_id)
        return OcrSessionView(
            session=session,
            result=result,
            front_image_id=session.front_image_id,
            back_image_id=session.back_image_id,
        )

    async def progress(self, session_id: uuid.UUID) -> OcrProgress:
        async with self._uow_factory() as uow:
            session = await self._require_session(uow, session_id)
        return OcrProgress(
            session_id=session.id,
            status=session.status,
            percent=self._STATUS_PERCENT.get(session.status, _QUEUED_PERCENT),
            message=session.error_message,
        )

    @staticmethod
    async def _require_session(uow: IOcrUnitOfWork, session_id: uuid.UUID) -> OcrSession:
        session = await uow.ocr_sessions.get(session_id)
        if session is None:
            raise EntityNotFound(
                "Không tìm thấy phiên nhận dạng.",
                details={"session_id": str(session_id)},
            )
        return session


@dataclass(frozen=True, slots=True)
class FieldCorrection:
    field_id: uuid.UUID
    value: str


class UpdateOcrFieldsUseCase:
    """§5.3.6 `PATCH /ocr/{id}/fields` — record the user's corrections."""

    def __init__(self, uow_factory: Callable[[], IOcrUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, session_id: uuid.UUID, corrections: Sequence[FieldCorrection]
    ) -> int:
        async with self._uow_factory() as uow:
            session = await uow.ocr_sessions.get(session_id)
            if session is None:
                raise EntityNotFound(
                    "Không tìm thấy phiên nhận dạng.",
                    details={"session_id": str(session_id)},
                )
            result = await uow.ocr_results.get_by_session(session_id)
            if result is None:
                raise BusinessRuleViolation(
                    "Phiên chưa có kết quả để sửa.", code="OCR_RESULT_NOT_READY"
                )

            # ⚠️ Field ids are checked against **this** session's result before
            # anything is written. Without it, a caller could pass any
            # `ocr_field.id` in the database and overwrite another customer's
            # extracted value through a session they legitimately own.
            owned = {field.id for field in result.fields}
            applied = 0
            for correction in corrections:
                if correction.field_id not in owned:
                    raise EntityNotFound(
                        "Trường không thuộc phiên nhận dạng này.",
                        details={"field_id": str(correction.field_id)},
                    )
                if await uow.ocr_results.correct_field(
                    correction.field_id, correction.value
                ):
                    applied += 1
            await uow.commit()

        logger.info(
            "ocr fields corrected", session_id=str(session_id), fields=applied
        )
        return applied


class FailOcrSessionUseCase:
    """Move a session out of `PROCESSING` when its job gave up (§12.15).

    🔴 Added 2026-08-12 after the first end-to-end run left a session at
    `PROCESSING` permanently: the job had exhausted three attempts and was
    correctly `FAILED`, but nothing carried that back, so
    `GET /ocr/{id}/progress` answered "đang xử lý" indefinitely. The queue
    knowing a thing failed is not the same as the user's screen knowing.

    ⚠️ Idempotent, and silent on a session that has already reached a terminal
    state. The runner can call this after a `SKIP LOCKED` race or a stale-job
    sweep, and turning that into an exception would fail a job whose real work
    already succeeded.
    """

    def __init__(
        self, uow_factory: Callable[[], IOcrUnitOfWork], clock: IClock
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self, session_id: uuid.UUID, error_code: str, error_message: str
    ) -> None:
        async with self._uow_factory() as uow:
            session = await uow.ocr_sessions.get(session_id)
            if session is None or session.status.is_terminal:
                return
            session.transition_to(
                OcrSessionStatus.FAILED,
                self._clock.now(),
                error_code=error_code[:50],
                error_message=error_message[:500],
            )
            await uow.ocr_sessions.update(session)
            await uow.commit()
        logger.warning(
            "ocr session failed", session_id=str(session_id), error_code=error_code
        )


class ConfirmOcrSessionUseCase:
    """§5.2 #15 `POST /ocr/{id}/confirm` — the user accepts the values.

    ⭐ Confirmation is not a status change on `ocr_session`: §4.4.3's status
    describes the *run*, and a completed run stays completed no matter what the
    user then decides. What confirmation actually establishes is that the
    values may be used to create a customer, which the next call does.
    So this verifies rather than mutates — and says so, instead of inventing a
    seventh status to have something to write.
    """

    def __init__(self, uow_factory: Callable[[], IOcrUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, session_id: uuid.UUID) -> OcrSessionView:
        async with self._uow_factory() as uow:
            session = await uow.ocr_sessions.get(session_id)
            if session is None:
                raise EntityNotFound(
                    "Không tìm thấy phiên nhận dạng.",
                    details={"session_id": str(session_id)},
                )
            if session.status not in {
                OcrSessionStatus.COMPLETED,
                OcrSessionStatus.COMPLETED_WITH_WARNINGS,
            }:
                raise BusinessRuleViolation(
                    "Phiên nhận dạng chưa hoàn tất.",
                    code="OCR_SESSION_NOT_COMPLETED",
                )
            result = await uow.ocr_results.get_by_session(session_id)
            if result is None:
                raise BusinessRuleViolation(
                    "Phiên chưa có kết quả.", code="OCR_RESULT_NOT_READY"
                )
            unresolved = [f.field_key for f in result.fields if f.needs_review]

        if unresolved:
            raise BusinessRuleViolation(
                "Còn trường cần kiểm tra lại trước khi xác nhận.",
                code="FIELDS_NEED_REVIEW",
                details={"fields": ", ".join(sorted(unresolved))},
            )
        return OcrSessionView(
            session=session,
            result=result,
            front_image_id=session.front_image_id,
            back_image_id=session.back_image_id,
        )
