"""Application pipelines — multi-stage orchestrations that own no state."""
from cocas.application.pipelines.extraction_pipeline import (
    CORROBORATION_FLOOR,
    ExtractionPipeline,
)

__all__ = ["CORROBORATION_FLOOR", "ExtractionPipeline"]
