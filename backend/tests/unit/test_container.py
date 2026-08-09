"""Unit tests for the Composition Root (`container.py`).

No real database connection is required — `create_async_engine` is lazy (it
never connects until a session actually runs a query), so these tests only
need a syntactically valid `database_url`. DPAPI key creation is real (this
environment is Windows), scoped to `tmp_path`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import cocas.container as container_module
from cocas.config.settings import Settings
from cocas.container import Container, get_container, init_container
from cocas.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from cocas.infrastructure.security.crypto import DpapiCryptoService
from cocas.infrastructure.system.clock import SystemClock
from cocas.infrastructure.system.id_generator import Uuid7Generator


@pytest.fixture(autouse=True)
def _reset_global_container() -> None:
    container_module._container = None
    yield
    container_module._container = None


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:1/nonexistent",
        log_dir=str(tmp_path / "logs"),
        dpapi_key_path=str(tmp_path / "keys" / "master.key.dpapi"),
    )


class TestContainerWiring:
    @pytest.mark.asyncio
    async def test_wires_crypto_clock_id_generator(self, tmp_path: Path) -> None:
        container = Container(_settings(tmp_path))
        try:
            assert isinstance(container.crypto, DpapiCryptoService)
            assert isinstance(container.clock, SystemClock)
            assert isinstance(container.id_generator, Uuid7Generator)
            assert isinstance(container.engine, AsyncEngine)
        finally:
            await container.close()

    def test_creates_the_dpapi_key_file(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        Container(settings)
        assert Path(settings.dpapi_key_path).exists()

    def test_reusing_settings_reuses_the_same_kek(self, tmp_path: Path) -> None:
        """Two containers built from the same settings must decrypt each other's data."""
        from cocas.domain.ports.crypto import BidxField

        settings = _settings(tmp_path)
        first = Container(settings)
        second = Container(settings)
        first_bidx = first.crypto.blind_index("001199012345", BidxField.ID_NUMBER)
        second_bidx = second.crypto.blind_index("001199012345", BidxField.ID_NUMBER)
        assert first_bidx == second_bidx


class TestUnitOfWorkFactory:
    @pytest.mark.asyncio
    async def test_unit_of_work_returns_sqlalchemy_uow(self, tmp_path: Path) -> None:
        container = Container(_settings(tmp_path))
        try:
            uow = container.unit_of_work()
            assert isinstance(uow, SqlAlchemyUnitOfWork)
        finally:
            await container.close()

    @pytest.mark.asyncio
    async def test_each_call_returns_a_fresh_instance(self, tmp_path: Path) -> None:
        container = Container(_settings(tmp_path))
        try:
            first = container.unit_of_work()
            second = container.unit_of_work()
            assert first is not second
        finally:
            await container.close()


class TestModuleLevelSingleton:
    def test_get_container_before_init_raises(self) -> None:
        with pytest.raises(RuntimeError):
            get_container()

    @pytest.mark.asyncio
    async def test_init_then_get_returns_same_instance(self, tmp_path: Path) -> None:
        initialized = init_container(_settings(tmp_path))
        try:
            assert get_container() is initialized
        finally:
            await initialized.close()
