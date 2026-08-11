"""Application-layer data transfer objects — plain, serializable, port-free."""
from cocas.application.dto.extraction import (
    EMPTY_FUSED,
    PIPELINE_STATUSES,
    CandidateTrace,
    ChannelSummary,
    Diagnostic,
    ExtractedField,
    ExtractionResult,
    ProgressCallback,
    empty_fields,
    noop_progress,
)

__all__ = [
    "EMPTY_FUSED",
    "PIPELINE_STATUSES",
    "CandidateTrace",
    "ChannelSummary",
    "Diagnostic",
    "ExtractedField",
    "ExtractionResult",
    "ProgressCallback",
    "empty_fields",
    "noop_progress",
]
