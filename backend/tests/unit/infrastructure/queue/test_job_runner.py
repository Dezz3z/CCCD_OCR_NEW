"""`JobRunner` — claim, run, record, and release the subject on final failure."""
from __future__ import annotations

import uuid

import pytest

from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.infrastructure.queue.job_runner import JobRunner
from tests.unit.application.use_cases.conftest import NOW, FakeClock, FakeUnitOfWork

_SESSION_ID = uuid.UUID(int=0x5E)


async def _enqueue(uow: FakeUnitOfWork, job_id: uuid.UUID) -> None:
    await uow.jobs.enqueue(
        job_id=job_id,
        job_type=JobType.OCR,
        correlation_id="corr",
        now=NOW,
        target_id=_SESSION_ID,
        target_type="ocr_session",
        payload={"front_image_id": "a", "back_image_id": "b"},
    )


class TestRunOnce:
    @pytest.mark.asyncio
    async def test_returns_false_on_an_empty_queue(self) -> None:
        uow = FakeUnitOfWork()
        runner = JobRunner(uow, FakeClock(), handlers={})
        assert await runner.run_once() is False

    @pytest.mark.asyncio
    async def test_runs_the_handler_and_marks_the_job_succeeded(self) -> None:
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)
        seen: list[dict[str, object]] = []

        async def handler(_job: uuid.UUID, payload: dict[str, object]) -> None:
            seen.append(payload)

        runner = JobRunner(uow, FakeClock(), handlers={JobType.OCR: handler})
        assert await runner.run_once() is True
        assert uow.jobs.rows[job_id].status == JobStatus.SUCCEEDED.value
        assert len(seen) == 1

    @pytest.mark.asyncio
    async def test_the_handler_is_told_what_the_job_is_about(self) -> None:
        """⭐ `target_id` is a column; the handler needs it as payload."""
        uow = FakeUnitOfWork()
        await _enqueue(uow, uuid.UUID(int=1))
        captured: dict[str, object] = {}

        async def handler(_job: uuid.UUID, payload: dict[str, object]) -> None:
            captured.update(payload)

        await JobRunner(uow, FakeClock(), handlers={JobType.OCR: handler}).run_once()
        assert captured["target_id"] == str(_SESSION_ID)
        assert captured["target_type"] == "ocr_session"

    @pytest.mark.asyncio
    async def test_a_job_type_with_no_handler_fails_rather_than_spinning(self) -> None:
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)
        await JobRunner(uow, FakeClock(), handlers={}).run_once()
        row = uow.jobs.rows[job_id]
        assert row.status == JobStatus.FAILED.value
        assert row.error_code == "NO_HANDLER"


class TestRetries:
    @pytest.mark.asyncio
    async def test_a_domain_error_requeues_while_attempts_remain(self) -> None:
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise BusinessRuleViolation("nổ", code="BOOM")

        await JobRunner(uow, FakeClock(), handlers={JobType.OCR: handler}).run_once()
        row = uow.jobs.rows[job_id]
        assert row.status == JobStatus.QUEUED.value
        assert row.is_retryable_error is True

    @pytest.mark.asyncio
    async def test_the_last_attempt_fails_for_good(self) -> None:
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise BusinessRuleViolation("nổ", code="BOOM")

        runner = JobRunner(uow, FakeClock(), handlers={JobType.OCR: handler})
        for _ in range(3):
            await runner.run_once()
        assert uow.jobs.rows[job_id].status == JobStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_the_error_detail_carries_the_context_not_just_the_message(
        self,
    ) -> None:
        """⚠️ The Vietnamese message is for the user; the column is for whoever
        has to fix it (measured: 'vi phạm ràng buộc' with no constraint name)."""
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise BusinessRuleViolation(
                "dữ liệu vi phạm ràng buộc", code="BOOM", constraint="ck_x__y"
            )

        await JobRunner(uow, FakeClock(), handlers={JobType.OCR: handler}).run_once()
        assert "ck_x__y" in (uow.jobs.rows[job_id].error_detail or "")

    @pytest.mark.asyncio
    async def test_an_unexpected_crash_does_not_retry(self) -> None:
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise RuntimeError("segfault-ish")

        await JobRunner(uow, FakeClock(), handlers={JobType.OCR: handler}).run_once()
        row = uow.jobs.rows[job_id]
        assert row.status == JobStatus.FAILED.value
        assert row.error_code == "HANDLER_CRASHED"


class TestTerminalFailureRelease:
    """🔴 The gap the first end-to-end run exposed: a `FAILED` job left the
    session at `PROCESSING`, so the client polled forever."""

    @pytest.mark.asyncio
    async def test_the_subject_is_released_when_the_job_gives_up(self) -> None:
        uow = FakeUnitOfWork()
        await _enqueue(uow, uuid.UUID(int=1))
        released: list[tuple[str, uuid.UUID, str]] = []

        async def notify(
            target_type: str, target_id: uuid.UUID, code: str, _detail: str
        ) -> None:
            released.append((target_type, target_id, code))

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise RuntimeError("boom")

        await JobRunner(
            uow,
            FakeClock(),
            handlers={JobType.OCR: handler},
            on_terminal_failure=notify,
        ).run_once()

        assert released == [("ocr_session", _SESSION_ID, "HANDLER_CRASHED")]

    @pytest.mark.asyncio
    async def test_nothing_is_released_while_retries_remain(self) -> None:
        uow = FakeUnitOfWork()
        await _enqueue(uow, uuid.UUID(int=1))
        released: list[str] = []

        async def notify(*_args: object) -> None:
            released.append("called")

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise BusinessRuleViolation("nổ", code="BOOM")

        await JobRunner(
            uow,
            FakeClock(),
            handlers={JobType.OCR: handler},
            on_terminal_failure=notify,
        ).run_once()
        assert released == []

    @pytest.mark.asyncio
    async def test_a_failing_notifier_does_not_mask_the_job_outcome(self) -> None:
        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)

        async def notify(*_args: object) -> None:
            raise RuntimeError("notifier is broken too")

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            raise RuntimeError("boom")

        await JobRunner(
            uow,
            FakeClock(),
            handlers={JobType.OCR: handler},
            on_terminal_failure=notify,
        ).run_once()
        assert uow.jobs.rows[job_id].status == JobStatus.FAILED.value


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_then_stop_is_clean(self) -> None:
        uow = FakeUnitOfWork()
        runner = JobRunner(uow, FakeClock(), handlers={}, poll_interval=0.01)
        runner.start()
        runner.start()  # idempotent
        await runner.stop()
        await runner.stop()  # idempotent

    @pytest.mark.asyncio
    async def test_the_loop_picks_work_up(self) -> None:
        import asyncio

        uow = FakeUnitOfWork()
        job_id = uuid.UUID(int=1)
        await _enqueue(uow, job_id)
        done = asyncio.Event()

        async def handler(_job: uuid.UUID, _payload: dict[str, object]) -> None:
            done.set()

        runner = JobRunner(
            uow, FakeClock(), handlers={JobType.OCR: handler}, poll_interval=0.01
        )
        runner.start()
        try:
            await asyncio.wait_for(done.wait(), timeout=5.0)
        finally:
            await runner.stop()
        assert uow.jobs.rows[job_id].status == JobStatus.SUCCEEDED.value
