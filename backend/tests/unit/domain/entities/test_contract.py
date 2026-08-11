"""Tests for Contract entity (§4.4.10) — state machine + DB-03/DB-09 invariants."""
import uuid
from datetime import UTC, date, datetime

import pytest

from cocas.domain.entities.contract import Contract, IVersionedEntity
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.exceptions import BusinessRuleViolation

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> Contract:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "contract_no": "01A-GDN-202608-00042",
        "export_name": "Mẫu 01A - NGUYỄN VĂN AN",
        "primary_customer_id": uuid.uuid4(),
        "template_version_id": uuid.uuid4(),
        "created_by": "phthang",
        "contract_date": date(2026, 8, 9),
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(overrides)
    return Contract(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_defaults_to_draft(self) -> None:
        contract = _make()
        assert contract.status == ContractStatus.DRAFT
        assert contract.version == 1

    def test_self_supersede_rejected(self) -> None:
        contract_id = uuid.uuid4()
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(id=contract_id, supersedes_id=contract_id)
        assert exc_info.value.code == "SELF_SUPERSEDE"

    def test_implements_versioned_entity_protocol(self) -> None:
        assert isinstance(_make(), IVersionedEntity)


class TestHappyPathTransitions:
    def test_full_lifecycle_to_completed(self) -> None:
        """⭐ D2.1 — GENERATING goes straight to COMPLETED; no PDF stages."""
        contract = _make()
        contract.mark_generating(NOW)
        assert contract.status == ContractStatus.GENERATING
        contract.mark_completed(b"\x00" * 32, NOW)
        assert contract.status == ContractStatus.COMPLETED
        assert contract.is_completed is True

    def test_completed_records_the_docx_hash(self) -> None:
        """The only way into COMPLETED carries the snapshot hash with it."""
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_completed(b"\xab" * 32, NOW)
        assert contract.snapshot_sha256 == b"\xab" * 32

    def test_version_increments_on_each_transition(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        assert contract.version == 2
        contract.mark_completed(b"\x00" * 32, NOW)
        assert contract.version == 3


class TestFailurePaths:
    def test_generation_failed_records_error(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_generation_failed("RENDER_ERROR", "boom", NOW)
        assert contract.status == ContractStatus.GENERATION_FAILED
        assert contract.error_code == "RENDER_ERROR"

    def test_retry_generation_from_failed(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_generation_failed("RENDER_ERROR", "boom", NOW)
        contract.retry_generation(NOW)
        assert contract.status == ContractStatus.GENERATING

    def test_completed_clears_prior_error(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_generation_failed("RENDER_ERROR", "boom", NOW)
        contract.retry_generation(NOW)
        contract.mark_completed(b"\x00" * 32, NOW)
        assert contract.error_code is None
        assert contract.error_message is None


class TestInvalidTransitions:
    def test_draft_cannot_jump_to_completed(self) -> None:
        contract = _make()
        with pytest.raises(BusinessRuleViolation) as exc_info:
            contract.mark_completed(b"\x00" * 32, NOW)
        assert exc_info.value.code == "INVALID_CONTRACT_TRANSITION"

    def test_completed_cannot_transition_further(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_completed(b"\x00" * 32, NOW)
        with pytest.raises(BusinessRuleViolation):
            contract.mark_generating(NOW)


class TestVoid:
    def test_void_from_draft(self) -> None:
        contract = _make()
        contract.void("Khách hàng huỷ giao dịch", "phthang", NOW)
        assert contract.status == ContractStatus.VOIDED
        assert contract.voided_by == "phthang"

    def test_void_from_completed(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_completed(b"\x00" * 32, NOW)
        contract.void("Phát hiện sai thông tin khách hàng", "phthang", NOW)
        assert contract.status == ContractStatus.VOIDED

    def test_void_reason_too_short_rejected(self) -> None:
        contract = _make()
        with pytest.raises(BusinessRuleViolation) as exc_info:
            contract.void("short", "phthang", NOW)
        assert exc_info.value.code == "VOID_REASON_TOO_SHORT"

    def test_double_void_rejected(self) -> None:
        contract = _make()
        contract.void("Khách hàng huỷ giao dịch", "phthang", NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            contract.void("Khách hàng huỷ giao dịch lần nữa", "phthang", NOW)
        assert exc_info.value.code == "CONTRACT_NOT_VOIDABLE"


class TestSupersede:
    def test_supersede_completed(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_completed(b"\x00" * 32, NOW)
        contract.supersede(NOW)
        assert contract.status == ContractStatus.SUPERSEDED

    def test_supersede_non_completed_rejected(self) -> None:
        contract = _make()
        with pytest.raises(BusinessRuleViolation) as exc_info:
            contract.supersede(NOW)
        assert exc_info.value.code == "CONTRACT_NOT_SUPERSEDABLE"


class TestLockedForBusinessEdits:
    def test_draft_not_locked(self) -> None:
        assert _make().is_locked_for_business_edits is False

    def test_completed_is_locked(self) -> None:
        contract = _make()
        contract.mark_generating(NOW)
        contract.mark_completed(b"\x00" * 32, NOW)
        assert contract.is_locked_for_business_edits is True

    def test_voided_is_locked(self) -> None:
        contract = _make()
        contract.void("Khách hàng huỷ giao dịch", "phthang", NOW)
        assert contract.is_locked_for_business_edits is True
