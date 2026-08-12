"""COCAS FastAPI application entry point."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cocas.config.settings import Settings
from cocas.container import init_container
from cocas.presentation.api.v1.routers import api_v1_router, system
from cocas.presentation.errors import register_exception_handlers
from cocas.presentation.middlewares import (
    CorrelationIdMiddleware,
    LocalTokenMiddleware,
    SecurityHeadersMiddleware,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application."""
    if settings is None:
        settings = Settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle — build the Composition Root once at startup."""
        container = init_container(settings)
        _app.state.container = container
        # ⭐ The queue starts with the app and stops with it. `container.close()`
        # stops the runner first, then disposes the pool.
        container.job_runner().start()
        yield
        await container.close()

    app = FastAPI(
        title="COCAS API",
        description="Hệ thống tự động tạo hợp đồng từ ảnh CCCD",
        version="1.0.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ⚠️ Starlette runs middleware in **reverse** registration order, so the
    # last one added is the outermost. §5.5 #1 requires the token check first,
    # so `LocalTokenMiddleware` is added last — and `CorrelationIdMiddleware`
    # is added after the security headers so a rejected request still gets a
    # correlation id in its envelope.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LocalTokenMiddleware, token=settings.local_token_secret)
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(system.liveness_router)
    app.include_router(api_v1_router)

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        workers=1,  # ⭐ CRITICAL: Single worker only
    )
