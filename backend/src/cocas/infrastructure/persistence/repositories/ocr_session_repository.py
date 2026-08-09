"""`SqlAlchemyOcrSessionRepository`."""
from __future__ import annotations

from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.value_objects.confidence_score import ConfidenceScore
from cocas.infrastructure.persistence.models.ocr_session import OcrSessionModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyOcrSessionRepository(SqlAlchemyRepository[OcrSession, OcrSessionModel]):
    model = OcrSessionModel

    def _to_domain(self, row: OcrSessionModel) -> OcrSession:
        return OcrSession(
            id=row.id,
            created_by=row.created_by,
            document_type_id=row.document_type_id,
            front_image_id=row.front_image_id,
            back_image_id=row.back_image_id,
            correlation_id=row.correlation_id,
            created_at=row.created_at,
            status=OcrSessionStatus(row.status),
            party_key=row.party_key,
            party_index=row.party_index if row.party_index is not None else 0,
            auto_swapped=row.auto_swapped,
            overall_confidence=ConfidenceScore(row.overall_confidence) if row.overall_confidence is not None else None,
            engine_name=row.engine_name,
            engine_version=row.engine_version,
            preprocessing_profile=row.preprocessing_profile,
            duration_ms=row.duration_ms,
            diagnostics=dict(row.diagnostics) if row.diagnostics else {},
            error_code=row.error_code,
            error_message=row.error_message,
            completed_at=row.completed_at,
        )

    def _apply_to_row(self, entity: OcrSession, row: OcrSessionModel) -> None:
        row.id = entity.id
        row.created_by = entity.created_by
        row.document_type_id = entity.document_type_id
        row.front_image_id = entity.front_image_id
        row.back_image_id = entity.back_image_id
        row.correlation_id = entity.correlation_id
        row.created_at = entity.created_at
        row.status = entity.status.value
        row.party_key = entity.party_key
        row.party_index = entity.party_index
        row.auto_swapped = entity.auto_swapped
        row.overall_confidence = entity.overall_confidence.value if entity.overall_confidence else None
        row.engine_name = entity.engine_name
        row.engine_version = entity.engine_version
        row.preprocessing_profile = entity.preprocessing_profile
        row.duration_ms = entity.duration_ms
        row.diagnostics = dict(entity.diagnostics)
        row.error_code = entity.error_code
        row.error_message = entity.error_message
        row.completed_at = entity.completed_at
