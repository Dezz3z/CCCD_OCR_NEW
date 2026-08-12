"""Local Handshake Token middleware (§5.1.2, §5.5 #1) — `COCAS-1007`.

⭐ Was a stub through P1. This is **the** gate: P-11 says Windows is the
authentication layer, so there is no login and no session — the only thing
separating the API from any other process on the machine is that the token is
passed to the SPA out of band (Tauri env var → IPC) and never travels over the
network to anyone who did not already have it.

⚠️ Which is why it is checked FIRST and compared with `hmac.compare_digest`
(§5.5 #7). A `==` on a secret leaks its prefix through timing, and the one
process that would exploit that is a local process — exactly the attacker this
token exists to stop.
"""
from __future__ import annotations

import hmac
from collections.abc import Iterable
from datetime import UTC

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from cocas.presentation.middlewares.correlation_id import current_correlation_id

LOCAL_TOKEN_HEADER = "X-Local-Token"

#: Paths reachable without the token.
#:
#: ⭐ Only the bare liveness probe (§5.2 #1), which the Tauri supervisor polls
#: every 5 s to decide whether to restart the backend. It returns a fixed
#: `{"status": "ok"}` and reads nothing, so it discloses only that a process is
#: listening — which whoever can reach `127.0.0.1:8000` already knows.
#: `/api/v1/system/health` is **not** here: it reports versions, disk space and
#: component readiness.
DEFAULT_EXEMPT_PATHS = ("/health", "/docs", "/redoc", "/openapi.json")


class LocalTokenMiddleware(BaseHTTPMiddleware):
    """Reject any request that does not carry the expected local token."""

    def __init__(
        self,
        app: object,
        token: str = "",
        exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._token = token
        self._exempt = tuple(exempt_paths)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self._token and request.url.path not in self._exempt:
            supplied = request.headers.get(LOCAL_TOKEN_HEADER, "")
            if not hmac.compare_digest(supplied, self._token):
                return self._forbidden()
        return await call_next(request)

    @staticmethod
    def _forbidden() -> JSONResponse:
        # Built by hand rather than by raising: the exception handlers are
        # registered on the FastAPI app, and a middleware sits outside them.
        from datetime import datetime

        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "COCAS-1007",
                    "type": "FORBIDDEN",
                    "message": "Phiên làm việc không hợp lệ.",
                    "hint": "Hãy đóng và mở lại ứng dụng.",
                    "details": [],
                    "correlation_id": current_correlation_id(),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "retryable": False,
                }
            },
        )
