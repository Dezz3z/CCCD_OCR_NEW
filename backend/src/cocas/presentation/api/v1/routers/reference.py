"""Reference data — §5.2 #45 `GET /reference/banks`."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from cocas.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/banks", summary="Bank directory, optionally filtered")
async def list_banks(
    container: ContainerDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    """§5.4 step 12. `q` is diacritic-insensitive — see the repository."""
    async with container.unit_of_work() as uow:
        entries = await uow.banks.search(q, limit)
    return {
        "items": [
            {
                "code": entry.code,
                "short_name": entry.short_name,
                "full_name": entry.full_name,
                "bin": entry.bin,
                "account_min_len": entry.account_min_len,
                "account_max_len": entry.account_max_len,
            }
            for entry in entries
        ]
    }
