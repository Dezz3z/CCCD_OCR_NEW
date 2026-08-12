"""The `/api/v1` router tree.

⭐ **16 of §5.2's 62 endpoints**, chosen as exactly the set §5.4's end-to-end
flow calls. The other 46 are administration, listing and diagnostics: real
work, but none of it on the path from two photographs to a signed `.docx`.
Naming the subset here keeps "not built yet" distinguishable from "forgotten".

Implemented: `/health` · `/system/health` · `/templates` ·
`/templates/{id}/requirements` · `/upload/front` · `/upload/back` · `/ocr` ·
`/ocr/{id}` · `/ocr/{id}/progress` · `/ocr/{id}/fields` · `/ocr/{id}/confirm` ·
`/customers` (GET + POST) · `/reference/banks` · `/contracts/generate` ·
`/contracts/{id}/documents/docx`.
"""
from fastapi import APIRouter

from cocas.presentation.api.v1.routers import (
    contracts,
    customers,
    ocr,
    reference,
    system,
    templates,
    uploads,
)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(system.router)
api_v1_router.include_router(templates.router)
api_v1_router.include_router(uploads.router)
api_v1_router.include_router(ocr.router)
api_v1_router.include_router(customers.router)
api_v1_router.include_router(reference.router)
api_v1_router.include_router(contracts.router)

__all__ = ["api_v1_router", "system"]
