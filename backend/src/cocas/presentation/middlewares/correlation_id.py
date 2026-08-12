"""Correlation-ID middleware (§5.1.2).

⭐ Was a stub through P1 ("Implementation would go here"). It cannot stay one:
§5.1.4 makes `correlation_id` a **required** field of every error envelope, and
§5.5 #5 says the user-facing message must carry no paths, table names or stack
traces — the correlation id is the only thread from what the user was shown
back to the log line that says what actually happened.

The value is kept in a `ContextVar` rather than only on `request.state` so the
exception handlers and the Loguru sinks can reach it without being handed the
request object.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def current_correlation_id() -> str:
    """The current request's correlation id, or a fresh one outside a request.

    ⭐ Never returns empty. A missing correlation id in an error envelope is a
    support ticket nobody can answer, so the degenerate case gets a real id
    rather than `None` — it just will not match any request log.
    """
    value = _correlation_id.get()
    return value or str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Accept the client's correlation id, or mint one; always echo it back."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get(CORRELATION_ID_HEADER, "").strip()
        # ⚠️ Validated as a UUID, not passed through. The value lands in log
        # files and in a response header; accepting arbitrary client text would
        # let a caller inject newlines into the log (§10 log-forging) and
        # header-delimiter characters into the response.
        try:
            correlation_id = str(uuid.UUID(incoming))
        except ValueError:
            correlation_id = str(uuid.uuid4())

        token = _correlation_id.set(correlation_id)
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        finally:
            _correlation_id.reset(token)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
