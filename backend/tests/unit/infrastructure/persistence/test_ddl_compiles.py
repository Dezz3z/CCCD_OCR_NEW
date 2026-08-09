"""Compile every table (and its indexes) to real PostgreSQL DDL — no connection needed.

This exercises the exact code path Alembic uses to emit `CREATE TABLE` /
`CREATE INDEX` statements, catching type/constraint-generation errors (e.g.
an invalid `postgresql_where` expression, a malformed CHECK) well before
anyone has PostgreSQL available to run the real migration against.
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from cocas.infrastructure.persistence.models import Base

_DIALECT = postgresql.dialect()
_TABLE_NAMES = sorted(Base.metadata.tables.keys())


class TestTableDdlCompiles:
    @pytest.mark.parametrize("table_name", _TABLE_NAMES)
    def test_create_table_compiles(self, table_name: str) -> None:
        table = Base.metadata.tables[table_name]
        sql = str(CreateTable(table).compile(dialect=_DIALECT))
        assert sql.strip().startswith("\nCREATE TABLE") or "CREATE TABLE" in sql
        assert table_name in sql


class TestIndexDdlCompiles:
    @pytest.mark.parametrize("table_name", _TABLE_NAMES)
    def test_indexes_compile(self, table_name: str) -> None:
        table = Base.metadata.tables[table_name]
        for index in table.indexes:
            sql = str(CreateIndex(index).compile(dialect=_DIALECT))
            assert "CREATE" in sql and "INDEX" in sql


class TestPartialIndexWhereClauses:
    """⭐ Every partial index in §4.7 must actually emit its WHERE clause."""

    def test_customer_id_number_where_clause_present(self) -> None:
        table = Base.metadata.tables["customer"]
        index = next(ix for ix in table.indexes if ix.name == "uq_customer__id_number")
        sql = str(CreateIndex(index).compile(dialect=_DIALECT))
        assert "WHERE" in sql
        assert "deleted_at IS NULL" in sql

    def test_job_dispatch_where_clause_present(self) -> None:
        table = Base.metadata.tables["job"]
        index = next(ix for ix in table.indexes if ix.name == "ix_job__dispatch")
        sql = str(CreateIndex(index).compile(dialect=_DIALECT))
        assert "WHERE" in sql
        assert "QUEUED" in sql
