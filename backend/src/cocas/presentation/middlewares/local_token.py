"""Local handshake token middleware."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class LocalTokenMiddleware(BaseHTTPMiddleware):
    """Validate local handshake token for desktop app."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore
        """Process request with token validation."""
        # Implementation would go here
        response = await call_next(request)
        return response
