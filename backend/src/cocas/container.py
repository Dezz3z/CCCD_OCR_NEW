"""Dependency injection container — Composition Root.

⭐ CRITICAL: This is the ONLY file allowed to import from all 4 layers.
All other files must respect the Dependency Rule (enforced by import-linter).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.config.settings import Settings


class Container:
    """Dependency injection container.

    Holds all application dependencies and provides access to them.
    Initialized once at application startup.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize container with settings."""
        self.settings = settings

        # Database initialization would go here
        # self.db_engine = create_async_engine(...)
        # self.db_session_factory = sessionmaker(...)

    async def get_session(self) -> AsyncSession:
        """Get database session."""
        # Implementation would go here
        raise NotImplementedError

    async def close(self) -> None:
        """Close all resources on shutdown."""
        # Implementation would go here
        pass


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
