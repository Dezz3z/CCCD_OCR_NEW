"""Smoke test: `create_app()`'s lifespan actually builds and tears down the
Composition Root, end-to-end, the way Uvicorn would trigger it at real startup.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import cocas.container as container_module
from cocas.config.settings import Settings
from cocas.container import Container
from cocas.main import create_app


@pytest.fixture(autouse=True)
def _reset_global_container() -> None:
    container_module._container = None
    yield
    container_module._container = None


def test_lifespan_builds_and_closes_the_container(tmp_path: Path) -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:1/nonexistent",
        log_dir=str(tmp_path / "logs"),
        dpapi_key_path=str(tmp_path / "keys" / "master.key.dpapi"),
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert isinstance(client.app.state.container, Container)

    # After the `with` block exits, lifespan's shutdown half has run —
    # engine.dispose() must not raise even though nothing ever connected.
