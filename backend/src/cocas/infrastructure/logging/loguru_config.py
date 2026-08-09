"""Loguru sink & correlation-id wiring (§10.8, §10.10) — the only place `logger.configure()` runs.

⭐ `diagnose=False` on both file sinks is deliberate, not a default left alone: Loguru's
diagnose mode prints local-variable values inside tracebacks, which bypasses the
`pii_filter` patcher below entirely (it only rewrites `record["message"]` and
`record["extra"]`, never the exception-traceback renderer) and could otherwise leak
raw PII sitting in a crashed function's locals straight into `error.log`.

⭐ `serialize=True` uses Loguru's own built-in JSON serializer (stdlib `json`, safe
brace-escaping) instead of a hand-rolled orjson formatter. A callable `format=` in
Loguru returns a *template* that Loguru itself re-runs through `str.format()` — a raw
JSON string handed back that way would have its own `{`/`}` mis-parsed as format
placeholders. `serialize=True` sidesteps that whole class of bug for the same result:
one structured JSON object per line, still parked in `record["extra"]` and therefore
still fully PII-masked before it is serialized.
"""
from __future__ import annotations

import getpass
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

from cocas.infrastructure.logging.pii_filter import redact_context, redact_text

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> <level>{level: <8}</level> "
    "<cyan>{extra[correlation_id]}</cyan> <level>{message}</level>"
)


def bind_correlation_id(correlation_id: str | None = None) -> str:
    """Set the correlation id for the current async context (§10.10); returns it.

    Propagates automatically across `await` boundaries via `contextvars` — callers
    never need to pass it down manually.
    """
    cid = correlation_id or str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def _redact_exception_value(exc: BaseException | None, seen: set[int] | None = None) -> None:
    """Mutate `exc.args` in place so its rendered `str()` is PII-safe too.

    ⭐ Needed because `record["message"]` is *not* where an exception's own text
    comes from — `logger.exception(...)`/`backtrace=True` render `str(exc.value)`
    straight from the exception object, bypassing the message-only redaction
    above. A raised `ValueError(f"... {raw_cccd} ...")` would otherwise leak
    through untouched. Mutating `args` (not reconstructing the exception) keeps
    this safe for custom constructors like `TemplateSyntaxError(line, detail)`
    that don't accept a single message argument.
    """
    if exc is None:
        return
    seen = seen if seen is not None else set()
    if id(exc) in seen:
        return
    seen.add(id(exc))
    if exc.args:
        exc.args = tuple(redact_text(a) if isinstance(a, str) else a for a in exc.args)
    _redact_exception_value(exc.__cause__, seen)
    _redact_exception_value(exc.__context__, seen)


def _redact_record(record: Record) -> None:
    """Loguru patcher (§10.9) — runs once per record, before any sink."""
    record["message"] = redact_text(record["message"])
    record["extra"] = redact_context(record["extra"])
    record["extra"].setdefault("correlation_id", get_correlation_id())
    record["extra"].setdefault("user", getpass.getuser())
    if record["exception"] is not None:
        _redact_exception_value(record["exception"].value)


def configure_logging(
    *,
    log_dir: str | Path,
    log_level: str = "INFO",
    console: bool = True,
) -> None:
    """Wire the 3 sinks required by §10.8.1. Idempotent — safe to call more than once."""
    logger.remove()
    logger.configure(patcher=_redact_record)

    if console:
        logger.add(sys.stderr, level=log_level, colorize=True, format=_CONSOLE_FORMAT)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path / "app.log",
        level="INFO",
        serialize=True,
        rotation="1 day",
        retention="30 days",
        compression="zip",
        diagnose=False,
        enqueue=True,
    )
    logger.add(
        log_path / "error.log",
        level="ERROR",
        serialize=True,
        rotation="1 week",
        retention="90 days",
        compression="zip",
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )
