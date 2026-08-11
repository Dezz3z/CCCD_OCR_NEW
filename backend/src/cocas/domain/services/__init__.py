"""Domain Services — stateless business logic that doesn't belong to one entity.

The 7 of docs/design/12-dac-ta-module.md and §7.2: `FieldNormalizer`,
`IssuePlaceNormalizer`, `FieldFusionService`, `ConfidenceCalculator`,
`CardValidityPolicy`, `ContractNumberGenerator`, `ExportNameGenerator`.
"""
from cocas.domain.services.card_validity_policy import (
    CardValidityPolicy,
    CardValidityReport,
    CardValidityStatus,
)
from cocas.domain.services.confidence_calculator import FIELD_WEIGHTS, ConfidenceCalculator
from cocas.domain.services.contract_number_generator import ContractNumberGenerator
from cocas.domain.services.export_name_generator import ExportNameGenerator
from cocas.domain.services.field_fusion_service import (
    Candidate,
    FieldFusionService,
    FusedField,
    FusionContext,
)
from cocas.domain.services.field_normalizer import FieldNormalizer, NormalizedValue
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer, NormalizationOutcome
from cocas.domain.services.issue_place_shape import ShapeVerdict, discriminate

__all__ = [
    "FIELD_WEIGHTS",
    "Candidate",
    "CardValidityPolicy",
    "CardValidityReport",
    "CardValidityStatus",
    "ConfidenceCalculator",
    "ContractNumberGenerator",
    "ExportNameGenerator",
    "FieldFusionService",
    "FieldNormalizer",
    "FusedField",
    "FusionContext",
    "IssuePlaceNormalizer",
    "NormalizationOutcome",
    "NormalizedValue",
    "ShapeVerdict",
    "discriminate",
]
