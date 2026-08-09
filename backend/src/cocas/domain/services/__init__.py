"""Domain Services — stateless business logic that doesn't belong to one entity.

5 services per docs/design/12-dac-ta-module.md: `IssuePlaceNormalizer`,
`FieldFusionService`, `CardValidityPolicy`, `ContractNumberGenerator`,
`ExportNameGenerator`.
"""
from cocas.domain.services.card_validity_policy import (
    CardValidityPolicy,
    CardValidityReport,
    CardValidityStatus,
)
from cocas.domain.services.contract_number_generator import ContractNumberGenerator
from cocas.domain.services.export_name_generator import ExportNameGenerator
from cocas.domain.services.field_fusion_service import (
    Candidate,
    FieldFusionService,
    FusedField,
    FusionContext,
)
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer, NormalizationOutcome

__all__ = [
    "Candidate",
    "CardValidityPolicy",
    "CardValidityReport",
    "CardValidityStatus",
    "ContractNumberGenerator",
    "ExportNameGenerator",
    "FieldFusionService",
    "FusedField",
    "FusionContext",
    "IssuePlaceNormalizer",
    "NormalizationOutcome",
]
