"""Response shapes shared by more than one router (§5.1.3)."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for every response model.

    `from_attributes` lets a router return a domain entity directly where the
    field names already line up, without a hand-written mapping that would go
    stale the first time a field is renamed.
    """

    model_config = ConfigDict(from_attributes=True)


class PageResponse(ApiModel, Generic[T]):
    """§5.1.3's paginated envelope — the only wrapper the API uses."""

    items: list[T]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool

    @classmethod
    def of(
        cls, items: list[T], *, page: int, page_size: int, total_items: int
    ) -> PageResponse[T]:
        total_pages = (total_items + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
        )
