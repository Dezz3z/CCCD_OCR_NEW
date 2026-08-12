"""`RunOcrJobUseCase` — the bridge from the queue to the pipeline."""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from cocas.application.use_cases.ocr.run_ocr_job import RunOcrJobUseCase
from cocas.domain.entities.card_image import CardImage
from cocas.domain.enums.card_side import CardSide
from cocas.domain.exceptions import BusinessRuleViolation, EntityNotFound
from cocas.domain.ports.storage import VaultCategory, VaultRef

from .conftest import NOW, FakeClock, FakeUnitOfWork

_JOB_ID = uuid.UUID(int=0x10B)
_SESSION_ID = uuid.UUID(int=0x5E)
_FRONT = uuid.UUID(int=1)
_BACK = uuid.UUID(int=2)


def _image(image_id: uuid.UUID, side: CardSide) -> CardImage:
    return CardImage(
        id=image_id,
        uploaded_by="tester",
        document_type_id=uuid.UUID(int=0xC0CA),
        side_hint=side,
        vault_path=f"card_image/2026/08/12/{image_id}.enc",
        mime_type="image/jpeg",
        width_px=1280,
        height_px=800,
        size_bytes=4096,
        sha256=bytes(32),
        created_at=NOW,
    )


class _Vault:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    def load(self, ref: VaultRef) -> bytes:
        self.loaded.append(ref.relative_path)
        return b"image-bytes-" + ref.relative_path.encode()

    def save(self, data: bytes, category: VaultCategory) -> VaultRef:  # pragma: no cover
        raise NotImplementedError

    def delete(self, ref: VaultRef) -> None:  # pragma: no cover
        raise NotImplementedError

    def exists(self, ref: VaultRef) -> bool:  # pragma: no cover
        return True


class _Pipeline:
    """Stands in for `ProcessOcrSessionUseCase`."""

    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, bytes, bytes]] = []

    async def execute(
        self, session_id: uuid.UUID, front: bytes, back: bytes
    ) -> Any:
        self.calls.append((session_id, front, back))

        class _Result:
            status = "COMPLETED"

        return _Result()


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "target_id": str(_SESSION_ID),
        "target_type": "ocr_session",
        "front_image_id": str(_FRONT),
        "back_image_id": str(_BACK),
    }
    payload.update(overrides)
    return payload


def _ready(uow: FakeUnitOfWork) -> None:
    uow.card_images.rows = {
        _FRONT: _image(_FRONT, CardSide.FRONT),
        _BACK: _image(_BACK, CardSide.BACK),
    }


class TestExecution:
    @pytest.mark.asyncio
    async def test_loads_both_images_from_the_vault_and_runs_the_pipeline(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        _ready(uow)
        vault, pipeline = _Vault(), _Pipeline()
        await RunOcrJobUseCase(uow, pipeline, vault, clock).execute(  # type: ignore[arg-type]
            _JOB_ID, _payload()
        )
        assert len(vault.loaded) == 2
        assert pipeline.calls[0][0] == _SESSION_ID

    @pytest.mark.asyncio
    async def test_progress_is_reported_against_the_job_row(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        _ready(uow)
        await RunOcrJobUseCase(uow, _Pipeline(), _Vault(), clock).execute(  # type: ignore[arg-type]
            _JOB_ID, _payload()
        )
        percents = [percent for _job, percent, _msg in uow.jobs.progress]
        assert percents == [10, 100]

    @pytest.mark.asyncio
    async def test_the_payload_never_carries_image_bytes(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        """⭐ P-13: `job.payload` reaches diagnostics bundles; photos must not."""
        _ready(uow)
        payload = _payload()
        await RunOcrJobUseCase(uow, _Pipeline(), _Vault(), clock).execute(  # type: ignore[arg-type]
            _JOB_ID, payload
        )
        assert all(isinstance(value, str) for value in payload.values())
        assert all(len(str(value)) < 64 for value in payload.values())


class TestBadPayloads:
    @pytest.mark.asyncio
    async def test_a_job_with_no_session(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        _ready(uow)
        broken = _payload()
        del broken["target_id"]
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await RunOcrJobUseCase(uow, _Pipeline(), _Vault(), clock).execute(  # type: ignore[arg-type]
                _JOB_ID, broken
            )
        assert exc_info.value.code == "OCR_JOB_WITHOUT_SESSION"

    @pytest.mark.asyncio
    async def test_a_job_missing_an_image_id(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        _ready(uow)
        broken = _payload()
        del broken["back_image_id"]
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await RunOcrJobUseCase(uow, _Pipeline(), _Vault(), clock).execute(  # type: ignore[arg-type]
                _JOB_ID, broken
            )
        assert exc_info.value.code == "OCR_JOB_PAYLOAD_INCOMPLETE"

    @pytest.mark.asyncio
    async def test_an_image_row_that_vanished(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        with pytest.raises(EntityNotFound):
            await RunOcrJobUseCase(uow, _Pipeline(), _Vault(), clock).execute(  # type: ignore[arg-type]
                _JOB_ID, _payload()
            )

    @pytest.mark.asyncio
    async def test_a_purged_image_stops_the_job(
        self, uow: FakeUnitOfWork, clock: FakeClock
    ) -> None:
        _ready(uow)
        uow.card_images.rows[_FRONT].purge("retention", NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            await RunOcrJobUseCase(uow, _Pipeline(), _Vault(), clock).execute(  # type: ignore[arg-type]
                _JOB_ID, _payload()
            )
        assert exc_info.value.code == "IMAGE_PURGED"
