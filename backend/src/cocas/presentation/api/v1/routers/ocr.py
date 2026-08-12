"""OCR endpoints — §5.3.3 through §5.3.6, plus confirm (§5.2 #15)."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from cocas.application.use_cases.ocr.manage_ocr_session import (
    CreateOcrSessionCommand,
    FieldCorrection,
    OcrSessionView,
)
from cocas.presentation.dependencies import ContainerDep
from cocas.presentation.middlewares.correlation_id import current_correlation_id

router = APIRouter(prefix="/ocr", tags=["ocr"])


class CreateSessionRequest(BaseModel):
    front_image_id: uuid.UUID
    back_image_id: uuid.UUID
    created_by: str = "desktop"


class FieldCorrectionRequest(BaseModel):
    field_id: uuid.UUID
    value: Annotated[str, Field(min_length=1, max_length=200)]


class CorrectionsRequest(BaseModel):
    fields: Annotated[list[FieldCorrectionRequest], Field(min_length=1, max_length=20)]


def _view_payload(view: OcrSessionView) -> dict[str, Any]:
    """§5.3.4's body.

    ⭐ Full PII, not the `_masked` columns — pitfall #6. The masked columns
    exist for logs and list views; this response is what the user is about to
    check against the card in their hand, so a masked value would make the
    check impossible.
    """
    session = view.session
    result = view.result
    return {
        "id": str(session.id),
        "status": session.status.value,
        "front_image_id": str(view.front_image_id),
        "back_image_id": str(view.back_image_id),
        "auto_swapped": session.auto_swapped,
        # ⚠️ `.value`, not `float(...)`. `ConfidenceScore` is a frozen dataclass
        # with no `__float__`, and `if session.overall_confidence` would also
        # read a legitimate 0.0 as absent — so the check is against `None`.
        "overall_confidence": (
            session.overall_confidence.value
            if session.overall_confidence is not None
            else None
        ),
        "duration_ms": session.duration_ms,
        "engine": session.engine_name,
        "error_code": session.error_code,
        "error_message": session.error_message,
        "created_at": session.created_at.isoformat(),
        "completed_at": (
            session.completed_at.isoformat() if session.completed_at else None
        ),
        "channels": dict(result.channel_summary) if result else {},
        "qr_available": result.qr_available if result else False,
        "mrz_available": result.mrz_available if result else False,
        "cross_check_flags": list(result.cross_check_flags) if result else [],
        "validation": dict(result.validation_report) if result else {},
        "fields": [
            {
                "id": str(field.id),
                "field_key": field.field_key,
                "value": field.value,
                "source": field.source,
                "confidence": field.confidence,
                "needs_review": field.needs_review,
                "normalization_tier": field.normalization_tier,
                "bbox": field.bbox,
            }
            for field in (result.fields if result else ())
        ],
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="§5.3.3 queue a session")
async def create_session(
    body: CreateSessionRequest,
    container: ContainerDep,
    response: Response,
    request: Request,
) -> dict[str, Any]:
    """⭐ `202`, not `201`. Recognition happens in `JobRunner`, not here."""
    queued = await container.create_ocr_session_use_case().execute(
        CreateOcrSessionCommand(
            front_image_id=body.front_image_id,
            back_image_id=body.back_image_id,
            created_by=body.created_by,
            correlation_id=getattr(
                request.state, "correlation_id", current_correlation_id()
            ),
        )
    )
    location = f"/api/v1/ocr/{queued.session_id}"
    response.headers["Location"] = location
    return {
        "session_id": str(queued.session_id),
        "job_id": str(queued.job_id),
        "status": queued.status.value,
        "poll_url": f"{location}/progress",
    }


@router.get("/{session_id}/progress", summary="§5.3.5 lightweight poll")
async def session_progress(
    session_id: uuid.UUID, container: ContainerDep
) -> dict[str, Any]:
    progress = await container.get_ocr_session_use_case().progress(session_id)
    return {
        "session_id": str(progress.session_id),
        "status": progress.status.value,
        "percent": progress.percent,
        "message": progress.message,
    }


@router.get("/{session_id}", summary="§5.3.4 full result")
async def get_session(session_id: uuid.UUID, container: ContainerDep) -> dict[str, Any]:
    view = await container.get_ocr_session_use_case().execute(session_id)
    return _view_payload(view)


@router.patch("/{session_id}/fields", summary="§5.3.6 correct fields")
async def patch_fields(
    session_id: uuid.UUID, body: CorrectionsRequest, container: ContainerDep
) -> dict[str, Any]:
    applied = await container.update_ocr_fields_use_case().execute(
        session_id,
        [
            FieldCorrection(field_id=item.field_id, value=item.value)
            for item in body.fields
        ],
    )
    view = await container.get_ocr_session_use_case().execute(session_id)
    return {"updated": applied, **_view_payload(view)}


@router.post("/{session_id}/confirm", summary="§5.2 #15 accept the values")
async def confirm_session(
    session_id: uuid.UUID, container: ContainerDep
) -> dict[str, Any]:
    view = await container.confirm_ocr_session_use_case().execute(session_id)
    return {"confirmed": True, **_view_payload(view)}
