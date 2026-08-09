"""Fixtures for repository/UnitOfWork integration tests — REAL PostgreSQL, no mocking.

⭐ Gated on `COCAS_TEST_DATABASE_URL` so the test file never contains a
credential and CI/dev opt in explicitly. Point it at a throwaway database —
these tests `DROP`/`CREATE` the whole schema every test.

    export COCAS_TEST_DATABASE_URL="postgresql+asyncpg://user:pass@127.0.0.1:5432/cocas_repo_test"

⭐ The engine is function-scoped (recreated per test), not session-scoped.
A session-scoped asyncpg engine binds its connection pool to whichever event
loop is active when the fixture first runs; pytest-asyncio gives each test
its own loop by default, so a later test crashes with "Future attached to a
different loop". Function scope trades a bit of speed (schema is rebuilt
per test) for being immune to that whole class of loop-scope mismatch —
worth it for a 16-test suite.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Importing the package (not just `base`) triggers every model module's
# import, so `Base.metadata` knows about all 19 tables before create_all().
from cocas.infrastructure.persistence.models import Base

DATABASE_URL_ENV_VAR = "COCAS_TEST_DATABASE_URL"

pytestmark = pytest.mark.integration


def _require_database_url() -> str:
    url = os.environ.get(DATABASE_URL_ENV_VAR)
    if not url:
        pytest.skip(f"{DATABASE_URL_ENV_VAR} not set — skipping real-PostgreSQL integration tests.")
    return url


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    url = _require_database_url()
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # migration 001 — create_all() bypasses migrations entirely, so the
        # extensions it enables (needed for gin_trgm_ops / gen_random_uuid)
        # have to be created here too.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def pg_session_factory(pg_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(pg_engine, expire_on_commit=False)
