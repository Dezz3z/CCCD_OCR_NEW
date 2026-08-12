"""FastAPI dependencies — the one bridge from a request to the Composition Root.

⭐ The `Container` is read off `app.state`, not off the module-level global in
`cocas.container`. Both exist, but only `app.state` is scoped to the running
application: tests build an app with their own settings, and a module global
would hand them whichever container was created first.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from cocas.container import Container


def get_container(request: Request) -> Container:
    """The container built by the `lifespan` handler in `main.create_app()`."""
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - only if lifespan did not run
        raise RuntimeError("Container chưa được khởi tạo.")
    assert isinstance(container, Container)
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


class Pagination:
    """`page` / `page_size` with §5.1.7's bounds enforced at the edge."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


PaginationDep = Annotated[Pagination, Depends(Pagination)]
