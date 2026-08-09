"""COCAS FastAPI application entry point."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cocas.config.settings import Settings
from cocas.container import init_container
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
        yield
        await container.close()

    app = FastAPI(
        title="COCAS API",
        description="Hệ thống tự động tạo hợp đồng từ ảnh CCCD",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middlewares
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(LocalTokenMiddleware)

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
