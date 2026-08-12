"""System endpoints — §5.2 #1 `/health` and #2 `/api/v1/system/health`."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from cocas.presentation.dependencies import ContainerDep

#: §5.5 #8 — warn below 500 MB, refuse to write below 100 MB.
_WARN_FREE_BYTES = 500 * 1024 * 1024
_BLOCK_FREE_BYTES = 100 * 1024 * 1024

liveness_router = APIRouter(tags=["system"])
router = APIRouter(prefix="/system", tags=["system"])


@liveness_router.get("/health", summary="Liveness probe (no token required)")
async def liveness() -> dict[str, str]:
    """⭐ The one unauthenticated endpoint.

    The Tauri supervisor polls this every 5 s to decide whether to restart the
    backend, and it must answer before the container has finished warming
    anything — so it touches nothing: no database, no Vault, no OCR engine. A
    probe that can fail for a reason other than "the process is gone" causes
    restarts that make the real problem worse.
    """
    return {"status": "ok"}


@router.get("/health", summary="Detailed health (§5.3.11)")
async def system_health(container: ContainerDep) -> dict[str, Any]:
    """Component-by-component readiness, for the diagnostics screen."""
    database: dict[str, Any] = {"status": "unknown"}
    try:
        async with container.session_factory() as session:
            await session.execute(text("SELECT 1"))
        database = {"status": "ok"}
    except Exception as exc:
        # ⚠️ Type name only. A connection error's text carries the host, port
        # and user of the database (§5.5 #5), and this endpoint is reachable by
        # anything holding the local token.
        database = {"status": "error", "detail": type(exc).__name__}

    vault_root = Path(container.settings.vault_dir)
    probe = vault_root if vault_root.exists() else Path.cwd()
    usage = shutil.disk_usage(probe)
    if usage.free < _BLOCK_FREE_BYTES:
        disk_status = "critical"
    elif usage.free < _WARN_FREE_BYTES:
        disk_status = "warning"
    else:
        disk_status = "ok"

    templates_root = Path(container.settings.templates_dir)
    components = {
        "database": database,
        "vault": {"status": "ok" if vault_root.exists() else "missing"},
        "templates": {"status": "ok" if templates_root.exists() else "missing"},
        "disk": {
            "status": disk_status,
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        },
    }
    overall = (
        "ok"
        if all(part.get("status") == "ok" for part in components.values())
        else "degraded"
    )
    return {"status": overall, "version": "1.0.0", "components": components}
