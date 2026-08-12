"""Image upload — §5.3.2 `POST /upload/front` and `/upload/back`."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from cocas.application.use_cases.ingestion.upload_card_image import (
    UploadCardImageCommand,
)
from cocas.domain.enums.card_side import CardSide
from cocas.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/upload", tags=["upload"])


async def _upload(
    container: ContainerDep,
    response: Response,
    file: UploadFile,
    side: CardSide,
    uploaded_by: str,
    document_type_code: str | None,
) -> dict[str, Any]:
    # ⚠️ `file.content_type` and `file.filename` are read but never trusted —
    # `probe()` decides what this is from the bytes (§5.1.5 `COCAS-3003`).
    data = await file.read()
    result = await container.upload_card_image_use_case().execute(
        UploadCardImageCommand(
            data=data,
            side_hint=side,
            uploaded_by=uploaded_by,
            document_type_code=document_type_code,
        )
    )
    response.status_code = status.HTTP_201_CREATED
    response.headers["Location"] = f"/api/v1/images/{result.image_id}"
    return {
        "id": str(result.image_id),
        "side_hint": result.side_hint.value,
        "mime_type": result.mime_type,
        "width_px": result.width_px,
        "height_px": result.height_px,
        "size_bytes": result.size_bytes,
        "sha256": result.sha256,
    }


@router.post("/front", status_code=status.HTTP_201_CREATED, summary="Upload front image")
async def upload_front(
    container: ContainerDep,
    response: Response,
    file: Annotated[UploadFile, File()],
    uploaded_by: Annotated[str, Form()] = "desktop",
    document_type_code: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    return await _upload(
        container, response, file, CardSide.FRONT, uploaded_by, document_type_code
    )


@router.post("/back", status_code=status.HTTP_201_CREATED, summary="Upload back image")
async def upload_back(
    container: ContainerDep,
    response: Response,
    file: Annotated[UploadFile, File()],
    uploaded_by: Annotated[str, Form()] = "desktop",
    document_type_code: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    return await _upload(
        container, response, file, CardSide.BACK, uploaded_by, document_type_code
    )
