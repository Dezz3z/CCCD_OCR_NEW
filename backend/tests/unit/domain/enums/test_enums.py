"""Tests for domain enums (§4.3.3 — the CSDL enum catalogue)."""
from cocas.domain.enums import (
    ActivityOutcome,
    BackupStatus,
    CardSide,
    ContractStatus,
    DataQuality,
    DocType,
    EntityType,
    FieldKey,
    FieldSource,
    Gender,
    JobStatus,
    JobType,
    OcrSessionStatus,
    TemplateValidationStatus,
)


class TestMemberValues:
    """Every member's value must match the exact string in §4.3.3 (used in CHECK constraints)."""

    def test_card_side(self) -> None:
        assert {m.value for m in CardSide} == {"FRONT", "BACK", "UNKNOWN"}

    def test_ocr_session_status(self) -> None:
        assert {m.value for m in OcrSessionStatus} == {
            "CREATED", "QUEUED", "PROCESSING", "COMPLETED", "COMPLETED_WITH_WARNINGS",
            "NEEDS_REUPLOAD", "NEEDS_MANUAL_ASSIGN", "FAILED", "CONFIRMED", "CONSUMED", "CANCELLED",
        }

    def test_field_key_has_exactly_6_members(self) -> None:
        """⭐ ExtractionResult must always have exactly these 6 keys (§12.3)."""
        assert {m.value for m in FieldKey} == {
            "full_name", "id_number", "date_of_birth", "issue_date", "expiry_date", "issue_place",
        }
        assert len(FieldKey) == 6

    def test_field_source(self) -> None:
        assert {m.value for m in FieldSource} == {"QR", "MRZ", "OCR", "MANUAL", "NONE"}

    def test_job_type(self) -> None:
        assert {m.value for m in JobType} == {
            "OCR", "PDF_CONVERT", "BACKUP", "RETENTION_PURGE", "ORPHAN_SWEEP", "TEMPLATE_VALIDATE",
        }

    def test_job_status(self) -> None:
        assert {m.value for m in JobStatus} == {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"}

    def test_contract_status(self) -> None:
        assert {m.value for m in ContractStatus} == {
            "DRAFT", "GENERATING", "DOCX_READY", "PDF_CONVERTING", "COMPLETED",
            "GENERATION_FAILED", "PDF_FAILED", "SUPERSEDED", "VOIDED",
        }

    def test_entity_type_v1_only_individual(self) -> None:
        """⭐ v1.0 CHECK IN ('INDIVIDUAL') — ORGANIZATION is a deliberate future hinge, not present yet."""
        assert {m.value for m in EntityType} == {"INDIVIDUAL"}

    def test_doc_type(self) -> None:
        assert {m.value for m in DocType} == {"DOCX", "PDF"}

    def test_gender(self) -> None:
        assert {m.value for m in Gender} == {"NAM", "NỮ", "KHÁC", "UNKNOWN"}

    def test_data_quality(self) -> None:
        assert {m.value for m in DataQuality} == {"OCR_VERIFIED", "MANUAL", "MIXED"}

    def test_template_validation_status(self) -> None:
        assert {m.value for m in TemplateValidationStatus} == {"VALID", "WARNING", "INVALID"}

    def test_activity_outcome(self) -> None:
        assert {m.value for m in ActivityOutcome} == {"SUCCESS", "FAILURE"}

    def test_backup_status(self) -> None:
        assert {m.value for m in BackupStatus} == {
            "RUNNING", "SUCCEEDED", "FAILED", "VERIFIED", "CORRUPTED",
        }


class TestStrEnumBehavior:
    """Every enum is a `str` subclass so it serializes cleanly to JSON/JSONB without extra adapters."""

    def test_contract_status_is_str(self) -> None:
        assert ContractStatus.DRAFT == "DRAFT"
        assert isinstance(ContractStatus.DRAFT, str)

    def test_field_key_is_str(self) -> None:
        assert FieldKey.FULL_NAME == "full_name"


class TestOcrSessionStatusTerminal:
    def test_completed_is_terminal(self) -> None:
        assert OcrSessionStatus.COMPLETED.is_terminal is True

    def test_processing_is_not_terminal(self) -> None:
        assert OcrSessionStatus.PROCESSING.is_terminal is False

    def test_failed_is_terminal(self) -> None:
        assert OcrSessionStatus.FAILED.is_terminal is True


class TestJobStatusTerminal:
    def test_succeeded_is_terminal(self) -> None:
        assert JobStatus.SUCCEEDED.is_terminal is True

    def test_queued_is_not_terminal(self) -> None:
        assert JobStatus.QUEUED.is_terminal is False

    def test_running_is_not_terminal(self) -> None:
        assert JobStatus.RUNNING.is_terminal is False
