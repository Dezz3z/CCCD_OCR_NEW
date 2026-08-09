"""Generic SQLAlchemy repository base (§12.14).

Concrete repositories only implement `_to_domain()`/`_apply_to_row()` — the
query mechanics (paging, exception translation, optimistic locking) live
here exactly once.

⭐ Hard invariants from the Port docstrings, enforced here:
  - `get()`/`list()` always return Domain entities, never ORM rows;
  - driver exceptions never escape — `IntegrityError` → `DuplicateEntityError`,
    `OperationalError` → `DatabaseUnavailableError`;
  - `expected_version` is honored with `WHERE version = :expected` and raises
    `OptimisticLockError` on a zero-row update.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.exceptions import (
    DatabaseUnavailableError,
    DuplicateEntityError,
    OptimisticLockError,
)
from cocas.domain.ports.persistence import Page, Specification


class _HasId(Protocol):
    id: Any


TEntity = TypeVar("TEntity", bound=_HasId)
TModel = TypeVar("TModel")


class SqlAlchemyRepository(ABC, Generic[TEntity, TModel]):
    """Base for every `SqlAlchemy*Repository` — implements `IReadRepository`
    and `IWriteRepository` in one class (most concrete repositories need both).
    """

    model: type[TModel]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- abstract mapping, implemented per entity -----------------------

    @abstractmethod
    def _to_domain(self, row: TModel) -> TEntity:
        """ORM row -> Domain entity. Decryption (if any) happens here."""

    @abstractmethod
    def _apply_to_row(self, entity: TEntity, row: TModel) -> None:
        """Copy Domain entity fields onto an ORM row (new or existing).
        Encryption/blind-index computation (if any) happens here.
        """

    # -- IReadRepository --------------------------------------------------

    async def get(self, entity_id: Any) -> TEntity | None:
        row = await self._session.get(self.model, entity_id)
        return self._to_domain(row) if row is not None else None

    async def list(self, spec: Specification) -> Page[TEntity]:
        try:
            stmt = self._build_select(spec)
            count_stmt = self._build_select(spec, count_only=True)
            total = (await self._session.execute(count_stmt)).scalar_one()
            offset = (spec.page - 1) * spec.page_size
            rows = (
                await self._session.execute(stmt.offset(offset).limit(spec.page_size))
            ).scalars().all()
        except OperationalError as exc:
            raise DatabaseUnavailableError("Không thể kết nối cơ sở dữ liệu.") from exc
        return Page(
            items=[self._to_domain(row) for row in rows],
            total=total,
            page=spec.page,
            page_size=spec.page_size,
        )

    async def exists(self, spec: Specification) -> bool:
        try:
            stmt = self._build_select(spec, count_only=True)
            total = (await self._session.execute(stmt)).scalar_one()
        except OperationalError as exc:
            raise DatabaseUnavailableError("Không thể kết nối cơ sở dữ liệu.") from exc
        return bool(total)

    def _build_select(self, spec: Specification, *, count_only: bool = False) -> Any:
        stmt = select(func.count()).select_from(self.model) if count_only else select(self.model)
        for attr_name, value in spec.filters.items():
            stmt = stmt.where(getattr(self.model, attr_name) == value)
        deleted_at_column = getattr(self.model, "deleted_at", None)
        if not spec.include_deleted and deleted_at_column is not None:
            stmt = stmt.where(deleted_at_column.is_(None))
        if not count_only:
            for order_key in spec.order_by:
                descending = order_key.startswith("-")
                column = getattr(self.model, order_key.lstrip("-"))
                stmt = stmt.order_by(column.desc() if descending else column.asc())
        return stmt

    # -- IWriteRepository ---------------------------------------------------

    async def add(self, entity: TEntity) -> None:
        row = self.model()
        self._apply_to_row(entity, row)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateEntityError(
                "Bản ghi đã tồn tại hoặc vi phạm ràng buộc duy nhất."
            ) from exc
        except OperationalError as exc:
            raise DatabaseUnavailableError("Không thể kết nối cơ sở dữ liệu.") from exc

    async def update(self, entity: TEntity, expected_version: int | None = None) -> None:
        row = await self._session.get(self.model, entity.id)
        if row is None:
            raise DuplicateEntityError(f"Không tìm thấy bản ghi để cập nhật: {entity.id}")

        if expected_version is not None:
            current_version = getattr(row, "version", None)
            if current_version != expected_version:
                raise OptimisticLockError(
                    f"Bản ghi đã bị thay đổi bởi thao tác khác "
                    f"(mong đợi version={expected_version}, thực tế={current_version})."
                )

        self._apply_to_row(entity, row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateEntityError(
                "Cập nhật vi phạm ràng buộc duy nhất."
            ) from exc
        except OperationalError as exc:
            raise DatabaseUnavailableError("Không thể kết nối cơ sở dữ liệu.") from exc
