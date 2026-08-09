"""Domain enums — business vocabulary shared across all layers.

Mirrors the `VARCHAR + CHECK` enum catalogue in docs/design/04-co-so-du-lieu.md §4.3.3
(the database deliberately avoids native Postgres ENUM types — see DB-11/4.3.1 —
so these Python enums are the single source of truth for the allowed values).
"""
from cocas.domain.enums.activity_outcome import ActivityOutcome
from cocas.domain.enums.backup_status import BackupStatus
from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.doc_type import DocType
from cocas.domain.enums.entity_type import EntityType
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.enums.gender import Gender
from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.enums.template_validation_status import TemplateValidationStatus

__all__ = [
    "ActivityOutcome",
    "BackupStatus",
    "CardSide",
    "ContractStatus",
    "DataQuality",
    "DocType",
    "EntityType",
    "FieldKey",
    "FieldSource",
    "Gender",
    "JobStatus",
    "JobType",
    "OcrSessionStatus",
    "TemplateValidationStatus",
]
