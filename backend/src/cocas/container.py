"""Dependency injection container — Composition Root.

⭐ CRITICAL: This is the ONLY file allowed to import from all 4 layers (the
import-linter "Container exception" contract exists specifically for this file).
Every other module must respect the Dependency Rule: Presentation → Application
→ Domain, with Infrastructure wired in here and nowhere else.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from cocas.config.settings import Settings
from cocas.domain.ports.crypto import ICryptoService
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.infrastructure.logging.loguru_config import configure_logging
from cocas.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from cocas.infrastructure.security.crypto import DpapiCryptoService
from cocas.infrastructure.security.dpapi import DpapiKeyManager
from cocas.infrastructure.system.clock import SystemClock
from cocas.infrastructure.system.id_generator import Uuid7Generator


class Container:
    """Wires every Port to its production Infrastructure implementation once at
    startup — nothing built here is optional or swapped conditionally at
    runtime (P-11: the app has exactly one deployment target, Windows).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # Logging first — every line below this point is worth capturing.
        configure_logging(log_dir=settings.log_dir, log_level=settings.log_level)

        kek = DpapiKeyManager(Path(settings.dpapi_key_path)).load_or_create_kek()
        self.crypto: ICryptoService = DpapiCryptoService(kek)

        self.clock: IClock = SystemClock()
        self.id_generator: IIdGenerator = Uuid7Generator()

        self.engine: AsyncEngine = create_async_engine(
            settings.database_url, echo=settings.database_echo
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """A fresh `IUnitOfWork` per call — one transaction, one `async with` block (§12.14)."""
        return SqlAlchemyUnitOfWork(self.session_factory, self.crypto)

    async def close(self) -> None:
        """Release the DB connection pool on shutdown."""
        await self.engine.dispose()


# Global container instance
_container: Container | None = None


def get_container() -> Container:
    """Get the global container instance."""
    if _container is None:
        raise RuntimeError("Container not initialized. Call init_container() first.")
    return _container


def init_container(settings: Settings) -> Container:
    """Initialize the global container."""
    global _container
    _container = Container(settings)
    return _container
