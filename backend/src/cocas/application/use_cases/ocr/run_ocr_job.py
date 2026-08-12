"""`RunOcrJobUseCase` — what `JobRunner` calls for a `JobType.OCR` row.

The thin piece between the queue and `ProcessOcrSessionUseCase`: load the two
images back out of the Vault, run the pipeline, report progress into the job
row so `GET /ocr/{id}/progress` has something real to return.

⭐ Images are loaded here rather than passed through the job payload. The
payload is JSONB in a table that is read by the diagnostics screen and dumped
into support bundles — two 900 KB base64 photographs of someone's ID card do
not belong in it (P-13, §10.9). The payload carries UUIDs; the bytes come from
the encrypted Vault at the moment they are needed.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from types import TracebackType
from typing import Protocol

from loguru import logger

from cocas.application.dto.extraction import ExtractionResult
from cocas.application.use_cases.ocr.process_ocr_session import ProcessOcrSessionUseCase
from cocas.domain.entities.card_image import CardImage
from cocas.domain.exceptions import BusinessRuleViolation, EntityNotFound
from cocas.domain.ports.storage import IFileStorage, VaultCategory, VaultRef
from cocas.domain.ports.system import IClock


class ICardImageReader(Protocol):
    async def get(self, entity_id: object) -> CardImage | None: ...


class IJobProgressWriter(Protocol):
    async def report_progress(
        self, job_id: uuid.UUID, percent: int, message: str, now: object
    ) -> None: ...


class IOcrJobUnitOfWork(Protocol):
    card_images: ICardImageReader
    jobs: IJobProgressWriter

    async def __aenter__(self) -> IOcrJobUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class RunOcrJobUseCase:
    """Execute one queued OCR job."""

    def __init__(
        self,
        uow_factory: Callable[[], IOcrJobUnitOfWork],
        process_session: ProcessOcrSessionUseCase,
        file_storage: IFileStorage,
        clock: IClock,
    ) -> None:
        self._uow_factory = uow_factory
        self._process_session = process_session
        self._file_storage = file_storage
        self._clock = clock

    async def execute(
        self, job_id: uuid.UUID, payload: dict[str, object]
    ) -> ExtractionResult:
        # `target_id` is the `ocr_session.id` — merged into the payload by
        # `JobRunner.run_once()`, which reads it off the job row's column.
        session_id = _uuid(payload, "target_id")
        front_id = _uuid(payload, "front_image_id")
        back_id = _uuid(payload, "back_image_id")
        if session_id is None:
            raise BusinessRuleViolation(
                "Công việc OCR không gắn với phiên nào.",
                code="OCR_JOB_WITHOUT_SESSION",
                details={"job_id": str(job_id)},
            )
        if front_id is None or back_id is None:
            raise BusinessRuleViolation(
                "Công việc OCR thiếu mã ảnh.", code="OCR_JOB_PAYLOAD_INCOMPLETE"
            )

        async with self._uow_factory() as uow:
            front = await self._require(uow, front_id)
            back = await self._require(uow, back_id)

        front_bytes = self._load(front)
        back_bytes = self._load(back)

        async def report(percent: int, message: str) -> None:
            async with self._uow_factory() as uow:
                await uow.jobs.report_progress(
                    job_id, percent, message, self._clock.now()
                )
                await uow.commit()

        await report(10, "Đang chuẩn bị ảnh")
        result = await self._process_session.execute(
            session_id, front_bytes, back_bytes
        )
        await report(100, "Hoàn tất")

        logger.info(
            "ocr job finished",
            job_id=str(job_id),
            session_id=str(session_id),
            status=result.status.value if hasattr(result.status, "value") else result.status,
        )
        return result

    def _load(self, image: CardImage) -> bytes:
        return self._file_storage.load(
            VaultRef(
                category=VaultCategory.CARD_IMAGE, relative_path=image.vault_path
            )
        )

    @staticmethod
    async def _require(uow: IOcrJobUnitOfWork, image_id: uuid.UUID) -> CardImage:
        image = await uow.card_images.get(image_id)
        if image is None:
            raise EntityNotFound(
                "Không tìm thấy ảnh cần nhận dạng.",
                details={"image_id": str(image_id)},
            )
        if image.is_purged:
            raise BusinessRuleViolation(
                "Ảnh đã bị xoá theo chính sách lưu trữ.", code="IMAGE_PURGED"
            )
        return image


def _uuid(payload: dict[str, object], key: str) -> uuid.UUID | None:
    raw = payload.get(key)
    if isinstance(raw, uuid.UUID):
        return raw
    if isinstance(raw, str):
        try:
            return uuid.UUID(raw)
        except ValueError:
            return None
    return None
