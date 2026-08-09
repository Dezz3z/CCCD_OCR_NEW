"""Tests for TemplateVersion entity (§4.4.9)."""
import uuid
from datetime import UTC, datetime

import pytest

from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import BusinessRuleViolation

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> TemplateVersion:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "template_id": uuid.uuid4(),
        "version_no": 1,
        "file_path": "templates/01A_HD_GDN/v1.docx",
        "file_sha256": b"\x00" * 32,
        "file_size_bytes": 500_000,
        "original_filename": "01A_HD_GDN.docx",
        "declared_variables": ["full_name", "id_number"],
        "required_variables": ["full_name", "id_number"],
        "optional_variables": [],
        "validation_status": TemplateValidationStatus.VALID,
        "created_by": "phthang",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return TemplateVersion(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_valid(self) -> None:
        version = _make()
        assert version.is_archived is False
        assert version.is_usable is True

    def test_file_too_large_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(file_size_bytes=30_000_000)
        assert exc_info.value.code == "TEMPLATE_FILE_TOO_LARGE"

    def test_version_no_below_1_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(version_no=0)
        assert exc_info.value.code == "INVALID_VERSION_NO"

    def test_boundary_max_size_allowed(self) -> None:
        _make(file_size_bytes=20 * 1024 * 1024)


class TestUsability:
    def test_invalid_status_not_usable(self) -> None:
        version = _make(validation_status=TemplateValidationStatus.INVALID)
        assert version.is_usable is False

    def test_warning_status_still_usable(self) -> None:
        version = _make(validation_status=TemplateValidationStatus.WARNING)
        assert version.is_usable is True

    def test_archived_not_usable(self) -> None:
        version = _make()
        version.archive(NOW)
        assert version.is_usable is False


class TestArchive:
    def test_archive_sets_timestamp(self) -> None:
        version = _make()
        version.archive(NOW)
        assert version.archived_at == NOW

    def test_double_archive_rejected(self) -> None:
        version = _make()
        version.archive(NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            version.archive(NOW)
        assert exc_info.value.code == "ALREADY_ARCHIVED"
