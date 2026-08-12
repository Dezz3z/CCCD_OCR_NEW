"""`JobRunner` — polls the `job` table every 500 ms (§12.15, pitfall #1).

⭐ There is no `asyncio.Queue`. The runner claims a row with
`SELECT … FOR UPDATE SKIP LOCKED`, runs it, and writes the outcome back. The
whole point is that the queue survives the process: the Tauri supervisor
restarts this backend on a failed health probe (P5), and an in-memory queue
would drop every pending OCR with no trace that anything was lost.

⚠️ **One job at a time, on purpose.** `ExtractionPipeline` already serialises
the recogniser because two concurrent passes produce `Insufficient memory`
*from inside OpenCV* on a 4-core/4 GB machine (constraint #9). Running two jobs
would put that failure back, one layer up and harder to read.

The polling interval is a compromise this design states explicitly: 500 ms is
below the threshold where a user notices the wizard stalling, and 2 queries/s
against a local PostgreSQL is nothing. It is a poll rather than
`LISTEN/NOTIFY` because a notification that arrives while the runner is
restarting is a notification nobody receives — the table can always be
re-read.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

from loguru import logger

from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.exceptions import DomainException
from cocas.domain.ports.system import IClock

#: §12.15 — how often to look for work.
POLL_INTERVAL_SECONDS = 0.5

#: A `RUNNING` job whose heartbeat is older than this is treated as abandoned.
#: ⭐ Comfortably longer than the slowest measured OCR pair (12.4 s p95,
#: constraint #8): reclaiming a job that is merely slow would run it twice.
STALE_AFTER = timedelta(minutes=5)

#: How often to look for abandoned jobs. Cheap, so it does not need to be rare;
#: rare enough that it is not competing with the dispatch query.
SWEEP_EVERY_SECONDS = 30.0

JobHandler = Callable[[uuid.UUID, dict[str, object]], Awaitable[None]]

#: Called when a job reaches a terminal failure, so the thing the job was about
#: can be moved out of its in-progress state.
#:
#: 🔴 **Without this the queue is a dead end.** Measured 2026-08-12 on the first
#: end-to-end run: an OCR job exhausted its three attempts and was marked
#: `FAILED`, while `ocr_session.status` stayed `PROCESSING` — so
#: `GET /ocr/{id}/progress` reported "đang xử lý" forever and the wizard could
#: never move on. A queue that records its own failure but leaves the subject
#: mid-flight has told nobody who needed to hear it.
FailureNotifier = Callable[[str, uuid.UUID, str, str], Awaitable[None]]


class JobRunner:
    """Runs queued jobs until stopped."""

    def __init__(
        self,
        uow_factory: Callable[[], object],
        clock: IClock,
        handlers: dict[JobType, JobHandler],
        *,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        on_terminal_failure: FailureNotifier | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._handlers = handlers
        self._poll_interval = poll_interval
        self._on_terminal_failure = on_terminal_failure
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        """Begin polling in the background."""
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="cocas-job-runner")
        logger.info("job runner started", poll_interval=self._poll_interval)

    async def stop(self) -> None:
        """Stop after the job in flight finishes.

        ⚠️ Waits rather than cancelling. A cancelled OCR leaves its session at
        `PROCESSING` and its job at `RUNNING`, and the only thing that would
        clean that up is the stale sweep five minutes later — on a shutdown
        path that could have simply waited.
        """
        if self._task is None:
            return
        self._stopping.set()
        try:
            await asyncio.wait_for(self._task, timeout=30.0)
        except TimeoutError:  # pragma: no cover - needs a wedged handler
            logger.warning("job runner did not stop in time; cancelling")
            self._task.cancel()
        finally:
            self._task = None
            logger.info("job runner stopped")

    async def _loop(self) -> None:
        seconds_since_sweep = 0.0
        while not self._stopping.is_set():
            try:
                worked = await self.run_once()
            except Exception as exc:  # pragma: no cover - the loop must not die
                logger.opt(exception=exc).error("job runner iteration failed")
                worked = False

            if seconds_since_sweep >= SWEEP_EVERY_SECONDS:
                seconds_since_sweep = 0.0
                try:
                    await self.sweep_stale()
                except Exception as exc:  # pragma: no cover
                    logger.opt(exception=exc).error("stale job sweep failed")

            if worked:
                # Straight back for the next row: a burst of queued work should
                # not be paced at one job per poll interval.
                continue
            seconds_since_sweep += self._poll_interval
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self._poll_interval
                )
            except TimeoutError:
                pass

    async def run_once(self) -> bool:
        """Claim and run at most one job. Returns whether one was found.

        ⭐ Three transactions, and the split matters: claiming commits
        immediately so no other worker can take the row, the handler runs with
        no transaction held (it opens its own — §12.14.1), and the outcome is
        written last. A single transaction around all three would hold a
        connection for the whole 9.5 s recognition and would roll the claim
        back on failure, putting the job straight back into the queue to fail
        again.
        """
        now = self._clock.now()
        async with self._uow_factory() as uow:  # type: ignore[attr-defined]
            claimed = await uow.jobs.claim_next(now)
            if claimed is None:
                return False
            job_id = claimed.id
            job_type = claimed.job_type
            payload = dict(claimed.payload or {})
            # ⭐ `target_id` is a column, not a payload key, but every handler
            # needs it — it is *what the job is about*. Merging it in here
            # keeps handlers from having to reach back into the job row (and
            # open a transaction) just to learn their own subject.
            if claimed.target_id is not None:
                payload.setdefault("target_id", str(claimed.target_id))
                payload.setdefault("target_type", claimed.target_type or "")
            target_id = claimed.target_id
            target_type = claimed.target_type or ""
            attempt = claimed.attempt_count
            max_attempts = claimed.max_attempts
            await uow.commit()

        handler = self._handlers.get(JobType(job_type)) if _is_known(job_type) else None
        if handler is None:
            await self._fail(
                job_id,
                target_type,
                target_id,
                error_code="NO_HANDLER",
                error_detail=f"Không có bộ xử lý cho loại công việc '{job_type}'.",
            )
            return True

        logger.info("job claimed", job_id=str(job_id), job_type=job_type, attempt=attempt)
        try:
            await handler(job_id, payload)
        except DomainException as exc:
            detail = _detail_of(exc)
            if attempt < max_attempts:
                await self._finish(
                    job_id,
                    JobStatus.QUEUED,
                    error_code=exc.code,
                    error_detail=detail,
                    retryable=True,
                )
            else:
                await self._fail(
                    job_id, target_type, target_id,
                    error_code=exc.code, error_detail=detail,
                )
        except Exception as exc:  # pragma: no cover - unexpected handler crash
            logger.opt(exception=exc).error("job handler crashed", job_id=str(job_id))
            await self._fail(
                job_id, target_type, target_id,
                error_code="HANDLER_CRASHED", error_detail=type(exc).__name__,
            )
        else:
            await self._finish(job_id, JobStatus.SUCCEEDED)
        return True

    async def _fail(
        self,
        job_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID | None,
        *,
        error_code: str,
        error_detail: str,
    ) -> None:
        """Mark the job failed for good, then release whatever it was about."""
        await self._finish(
            job_id,
            JobStatus.FAILED,
            error_code=error_code,
            error_detail=error_detail,
            retryable=False,
        )
        if self._on_terminal_failure is None or target_id is None:
            return
        try:
            await self._on_terminal_failure(
                target_type, target_id, error_code, error_detail
            )
        except Exception as exc:  # pragma: no cover - notification must not mask
            logger.opt(exception=exc).error(
                "could not release job target",
                job_id=str(job_id),
                target_type=target_type,
            )

    async def sweep_stale(self) -> int:
        """Requeue (or fail) jobs whose worker vanished."""
        now = self._clock.now()
        async with self._uow_factory() as uow:  # type: ignore[attr-defined]
            count = await uow.jobs.requeue_stale(now - STALE_AFTER, now)
            await uow.commit()
        if count:
            logger.warning("stale jobs reclaimed", count=count)
        return count

    async def _finish(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        async with self._uow_factory() as uow:  # type: ignore[attr-defined]
            await uow.jobs.finish(
                job_id,
                status=status,
                now=self._clock.now(),
                error_code=error_code,
                error_detail=error_detail,
                retryable=retryable,
            )
            await uow.commit()


def _is_known(job_type: str) -> bool:
    return job_type in {member.value for member in JobType}


def _detail_of(exc: DomainException) -> str:
    """`job.error_detail` — the message plus whatever context was attached.

    ⚠️ `str(exc)` alone is not enough here. Every `DomainException` message is
    written in Vietnamese *for the end user*, so it is deliberately vague about
    mechanism: "dữ liệu vi phạm ràng buộc" is the right thing to show someone
    creating a contract and useless to whoever has to fix it. The `context`
    carries the specifics (which constraint, which id), and `job.error_detail`
    is a diagnostics column, not a user-facing string.
    """
    context = getattr(exc, "context", None)
    if not isinstance(context, dict) or not context:
        return str(exc)
    extras = " · ".join(f"{key}={value}" for key, value in sorted(context.items()))
    return f"{exc} [{extras}]"
