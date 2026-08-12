"""§8.6 — the 10 `V-CTR-*` rules and the severity split that defines them."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.validation.contract_rules import (
    CONTRACT_GENERATION_RULES,
    MIN_FREE_DISK_BYTES,
    ContractCandidate,
    PartyCandidate,
)
from cocas.domain.validation.engine import ValidationEngine
from cocas.domain.validation.report import Severity
from cocas.domain.validation.rule import RuleContext, RuleSetKey
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
TODAY = date(2026, 8, 11)
CONTEXT = RuleContext(today=TODAY)


def make_customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "created_by": "nvnghiep",
        "full_name": PersonName.from_raw("NGUYỄN VĂN AN"),
        "id_number": CitizenId.from_raw("001199012345"),
        "date_of_birth": date(1990, 5, 14),
        "issue_place": IssuePlace(BO_CONG_AN),
        "id_card_dates": IdCardDates(issue_date=date(2021, 8, 20), expiry_date=date(2030, 5, 14)),
        "phone": VietnamesePhone.from_raw("0912345678"),
        "email": EmailAddress.from_raw("an.nguyen@example.com"),
        "address": "123 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội",
        "data_quality": DataQuality.OCR_VERIFIED,
        "created_at": NOW,
        "gender": Gender.NAM,
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_template(**overrides: object) -> Template:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "code": "01A_HD_GDN",
        "name": "Giao dịch ký quỹ",
        "party_schema": [
            {
                "key": "holder",
                "label": "Khách hàng",
                "entity_type": "INDIVIDUAL",
                "min": 1,
                "max": 1,
                "is_primary": True,
                "collect": ["contact", "bank_account"],
            }
        ],
        "contract_no_pattern": "01A-GDN-{yyyy}{MM}-{seq:05d}",
        "export_name_pattern": "Mẫu 01A - {full_name}",
        "created_at": NOW,
    }
    return Template(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_version(**overrides: object) -> TemplateVersion:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "template_id": uuid.uuid4(),
        "version_no": 1,
        "file_path": "01A_HD_GDN/v1.docx",
        "file_sha256": b"\x11" * 32,
        "file_size_bytes": 900_000,
        "original_filename": "01A_HD_GDN.docx",
        "declared_variables": ["full_name"],
        "required_variables": ["full_name"],
        "optional_variables": [],
        "validation_status": TemplateValidationStatus.VALID,
        "created_by": "nvnghiep",
        "created_at": NOW,
    }
    return TemplateVersion(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_candidate(**overrides: object) -> ContractCandidate:
    customer = make_customer()
    defaults: dict[str, object] = {
        "template": make_template(),
        "version": make_version(),
        "parties": (
            PartyCandidate(party_key="holder", customer=customer, has_bank_account=True),
        ),
    }
    return ContractCandidate(**{**defaults, **overrides})  # type: ignore[arg-type]


def run(candidate: ContractCandidate) -> tuple[str, ...]:
    return ValidationEngine().validate(
        candidate, RuleSetKey.CONTRACT_GENERATION, CONTEXT
    ).codes()


# ------------------------------------------------------------------ the shape


def test_all_ten_rules_are_registered() -> None:
    assert ValidationEngine().rules_in(RuleSetKey.CONTRACT_GENERATION) == tuple(
        f"V-CTR-{n:03d}" for n in range(1, 11)
    )


def test_nine_of_ten_block() -> None:
    """⭐ The inverse of the OCR set, and deliberately so: a contract rule
    checks the system's own state, where being wrong produces a wrong legal
    document. Only V-CTR-010 judges the world."""
    blocking = [
        rule.code
        for rule in CONTRACT_GENERATION_RULES
        if rule.code != "V-CTR-010"
    ]
    assert len(blocking) == 9


def test_a_complete_candidate_passes_clean() -> None:
    report = ValidationEngine().validate(
        make_candidate(), RuleSetKey.CONTRACT_GENERATION, CONTEXT
    )

    assert report.is_valid
    assert report.issues == ()


# -------------------------------------------------------------- V-CTR-001/002


def test_no_active_version_blocks() -> None:
    assert "COCAS-6005" in run(make_candidate(version=None))


def test_archived_version_blocks() -> None:
    version = make_version()
    version.archive(NOW)

    assert "COCAS-6005" in run(make_candidate(version=version))


def test_missing_template_file_blocks() -> None:
    assert "COCAS-6006" in run(make_candidate(template_file_exists=False))


def test_checksum_mismatch_blocks() -> None:
    assert "COCAS-6007" in run(make_candidate(template_checksum_matches=False))


def test_a_missing_version_does_not_also_report_a_missing_file() -> None:
    """⚠️ Two codes for one cause reads as two problems to fix."""
    codes = run(make_candidate(version=None, template_file_exists=False))

    assert "COCAS-6005" in codes
    assert "COCAS-6006" not in codes


# ------------------------------------------------------------------ V-CTR-003


def test_missing_required_variables_are_reported_with_labels() -> None:
    report = ValidationEngine().validate(
        make_candidate(missing_required_variables=("securities_account_no",)),
        RuleSetKey.CONTRACT_GENERATION,
        CONTEXT,
    )

    issue = next(i for i in report.issues if i.code == "COCAS-7002")
    assert issue.field == "securities_account_no"
    assert "Số tài khoản chứng khoán" in issue.message_vi


def test_every_missing_variable_gets_its_own_issue() -> None:
    """§12.7 — the engine never stops at the first error, and the `422` body
    lists each field so the operator fixes them in one pass."""
    codes = run(make_candidate(missing_required_variables=("phone", "email")))

    assert codes.count("COCAS-7002") == 2


# ------------------------------------------------------------------ V-CTR-004


def test_too_few_parties_blocks() -> None:
    assert "COCAS-7010" in run(make_candidate(parties=()))


def test_too_many_parties_blocks() -> None:
    parties = (
        PartyCandidate("holder", make_customer(), has_bank_account=True),
        PartyCandidate("holder", make_customer(), has_bank_account=True),
    )

    assert "COCAS-7010" in run(make_candidate(parties=parties))


def test_a_party_the_schema_never_declared_blocks() -> None:
    """⚠️ It would otherwise pass silently — no schema entry means no min/max
    to violate — and still be written to `contract_party`."""
    parties = (
        PartyCandidate("holder", make_customer(), has_bank_account=True),
        PartyCandidate("guarantor", make_customer(), has_bank_account=True),
    )

    assert run(make_candidate(parties=parties)).count("COCAS-7010") == 1


# -------------------------------------------------------------- V-CTR-005/006


def test_entity_type_mismatch_blocks() -> None:
    template = make_template(
        party_schema=[
            {"key": "holder", "label": "Khách hàng", "entity_type": "ORGANIZATION"}
        ]
    )

    assert "COCAS-7011" in run(make_candidate(template=template))


def test_entity_type_any_accepts_anything() -> None:
    template = make_template(
        party_schema=[{"key": "holder", "label": "Khách hàng", "entity_type": "ANY"}]
    )

    assert "COCAS-7011" not in run(make_candidate(template=template))


def test_declared_bank_account_but_none_supplied_blocks() -> None:
    parties = (PartyCandidate("holder", make_customer(), has_bank_account=False),)

    assert "COCAS-7012" in run(make_candidate(parties=parties))


def test_a_template_not_collecting_bank_accounts_does_not_ask_for_one() -> None:
    """`01A_GDKQ` declares `collect: ["contact"]` only (§4.5)."""
    template = make_template(
        party_schema=[
            {
                "key": "holder",
                "label": "Khách hàng",
                "entity_type": "INDIVIDUAL",
                "collect": ["contact"],
            }
        ]
    )
    parties = (PartyCandidate("holder", make_customer(), has_bank_account=False),)

    assert "COCAS-7012" not in run(make_candidate(template=template, parties=parties))


# -------------------------------------------------------------- V-CTR-007/009


def test_one_subject_cannot_hold_two_roles() -> None:
    customer = make_customer()
    template = make_template(
        party_schema=[
            {"key": "holder", "label": "Khách hàng", "entity_type": "INDIVIDUAL"},
            {"key": "co_holder", "label": "Đồng sở hữu", "entity_type": "INDIVIDUAL"},
        ]
    )
    parties = (
        PartyCandidate("holder", customer),
        PartyCandidate("co_holder", customer),
    )

    assert "COCAS-7013" in run(make_candidate(template=template, parties=parties))


def test_a_soft_deleted_customer_blocks() -> None:
    customer = make_customer()
    customer.soft_delete(NOW)

    assert "COCAS-5001" in run(
        make_candidate(parties=(PartyCandidate("holder", customer, has_bank_account=True),))
    )


# ------------------------------------------------------------------ V-CTR-008


def test_low_disk_space_blocks() -> None:
    codes = run(make_candidate(free_disk_bytes=MIN_FREE_DISK_BYTES - 1))

    assert "COCAS-8003" in codes


def test_exactly_the_floor_is_enough() -> None:
    assert "COCAS-8003" not in run(
        make_candidate(free_disk_bytes=MIN_FREE_DISK_BYTES)
    )


# ------------------------------------------------------------------ V-CTR-010


def test_an_expired_card_warns_but_never_blocks() -> None:
    """⭐ P-08. Refusing does not renew the card; it only means the customer
    standing at the desk goes home without a contract."""
    customer = make_customer(
        id_card_dates=IdCardDates(
            issue_date=date(2016, 1, 5), expiry_date=date(2025, 5, 14)
        )
    )
    report = ValidationEngine().validate(
        make_candidate(parties=(PartyCandidate("holder", customer, has_bank_account=True),)),
        RuleSetKey.CONTRACT_GENERATION,
        CONTEXT,
    )

    assert report.is_valid
    assert [issue.severity for issue in report.issues] == [Severity.WARNING]
    assert "NGUYỄN VĂN AN" in report.issues[0].message_vi


@pytest.mark.parametrize(
    "expiry", [date(2030, 5, 14), None], ids=["still-valid", "no-expiry"]
)
def test_a_usable_card_produces_no_issue(expiry: date | None) -> None:
    customer = make_customer(
        id_card_dates=IdCardDates(issue_date=date(2021, 8, 20), expiry_date=expiry)
    )

    assert run(
        make_candidate(parties=(PartyCandidate("holder", customer, has_bank_account=True),))
    ) == ()
