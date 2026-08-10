"""The 23 `V-OCR-*` rules (§8.4) — one class per rule, ≥1 pass + 2 fail cases (§8.11)."""
from __future__ import annotations

import pytest

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.gender import Gender
from cocas.domain.services.field_fusion_service import FLAG_CARD_MISMATCH, FLAG_SOURCE_CONFLICT
from cocas.domain.validation import (
    RuleSetKey,
    Severity,
    ValidationEngine,
    ValidationReport,
)
from cocas.domain.value_objects.id_card_dates import NO_EXPIRY_TEXT
from tests.unit.domain.validation.conftest import context, read, target

ENGINE = ValidationEngine()


def check(a_target: object, **context_overrides: object) -> ValidationReport:
    return ENGINE.validate(a_target, RuleSetKey.OCR_RESULT, context(**context_overrides))


def codes(report: ValidationReport) -> set[str]:
    return set(report.codes())


def severity_of(report: ValidationReport, code: str) -> Severity:
    return next(issue.severity for issue in report.issues if issue.code == code)


class TestTheCleanCard:
    def test_a_good_card_raises_nothing_at_all(self) -> None:
        """⭐ The baseline every other test in this file deviates from by one field."""
        report = check(target())
        assert report.issues == ()
        assert report.is_valid is True


class TestV001BothImages:
    def test_both_images_present_passes(self) -> None:
        assert "V-OCR-001" not in codes(check(target()))

    def test_missing_front_is_an_error(self) -> None:
        report = check(target(has_front_image=False))
        assert "V-OCR-001" in codes(report)
        assert "mặt trước" in report.errors[0].message_vi
        assert report.is_valid is False

    def test_missing_back_is_an_error(self) -> None:
        report = check(target(has_back_image=False))
        assert "mặt sau" in report.errors[0].message_vi

    def test_both_missing_reports_both(self) -> None:
        report = check(target(has_front_image=False, has_back_image=False))
        assert len([i for i in report.issues if i.code == "V-OCR-001"]) == 2


class TestV002DuplicateSide:
    def test_two_different_sides_pass(self) -> None:
        assert "V-OCR-002" not in codes(check(target()))

    def test_duplicate_side_is_an_error(self) -> None:
        report = check(target(duplicate_side=True))
        assert "V-OCR-002" in codes(report)
        assert severity_of(report, "V-OCR-002") is Severity.ERROR

    def test_duplicate_side_blocks(self) -> None:
        assert check(target(duplicate_side=True)).is_valid is False


class TestV003IdNumberShape:
    def test_twelve_digits_pass(self) -> None:
        assert "V-OCR-003" not in codes(check(target()))

    def test_eleven_digits_is_an_error(self) -> None:
        assert "V-OCR-003" in codes(check(target(id_number=read("00119901234"))))

    def test_letters_are_an_error(self) -> None:
        assert "V-OCR-003" in codes(check(target(id_number=read("00119901234A"))))

    def test_a_missing_id_is_left_to_v017(self) -> None:
        report = check(target(id_number=read(None)))
        assert "V-OCR-003" not in codes(report)
        assert "V-OCR-017" in codes(report)


class TestV004NameWords:
    def test_three_words_pass(self) -> None:
        assert "V-OCR-004" not in codes(check(target()))

    def test_one_word_is_a_warning_not_an_error(self) -> None:
        report = check(target(full_name=read("AN")))
        assert severity_of(report, "V-OCR-004") is Severity.WARNING
        assert report.is_valid is True

    def test_a_missing_name_is_left_to_v017(self) -> None:
        report = check(target(full_name=read(None)))
        assert "V-OCR-004" not in codes(report)
        assert "V-OCR-017" in codes(report)


class TestV005BirthDateIsReal:
    def test_a_real_date_passes(self) -> None:
        assert "V-OCR-005" not in codes(check(target()))

    def test_a_non_date_is_an_error(self) -> None:
        assert "V-OCR-005" in codes(check(target(date_of_birth=read("khong ro"))))

    def test_february_30_is_an_error(self) -> None:
        assert "V-OCR-005" in codes(check(target(date_of_birth=read("1999-02-30"))))

    def test_leap_day_2024_is_accepted(self) -> None:
        """⭐ Mandatory edge case (§8.11) — 2024 is a leap year, 2023 is not."""
        assert "V-OCR-005" not in codes(
            check(target(date_of_birth=read("2004-02-29"), issue_date=read("2021-06-01")))
        )

    def test_leap_day_2023_is_rejected(self) -> None:
        assert "V-OCR-005" in codes(check(target(date_of_birth=read("2023-02-29"))))


class TestV006IssueDateIsReal:
    def test_a_real_date_passes(self) -> None:
        assert "V-OCR-006" not in codes(check(target()))

    def test_a_non_date_is_an_error(self) -> None:
        assert "V-OCR-006" in codes(check(target(issue_date=read("01/06/2021"))))

    def test_an_impossible_date_is_an_error(self) -> None:
        assert "V-OCR-006" in codes(check(target(issue_date=read("2021-13-01"))))


class TestV007ExpiryIsRealOrLifelong:
    def test_a_real_date_passes(self) -> None:
        assert "V-OCR-007" not in codes(check(target()))

    def test_no_expiry_passes(self) -> None:
        """⭐ Mandatory edge case: `KHÔNG THỜI HẠN` is a value, not a missing date."""
        report = check(target(expiry_date=read(NO_EXPIRY_TEXT)))
        assert "V-OCR-007" not in codes(report)
        assert report.is_valid is True

    def test_a_non_date_is_an_error(self) -> None:
        assert "V-OCR-007" in codes(check(target(expiry_date=read("het han"))))

    def test_an_impossible_date_is_an_error(self) -> None:
        assert "V-OCR-007" in codes(check(target(expiry_date=read("2031-02-31"))))

    def test_a_missing_expiry_is_allowed(self) -> None:
        """`expiry_date` is nullable in `customer` — absence is not an error."""
        assert check(target(expiry_date=read(None))).is_valid is True


class TestV008IssueBeforeExpiry:
    def test_issue_before_expiry_passes(self) -> None:
        assert "V-OCR-008" not in codes(check(target()))

    def test_equal_dates_pass(self) -> None:
        """⭐ Mandatory edge case: the boundary is `<=`, not `<`."""
        assert "V-OCR-008" not in codes(
            check(target(issue_date=read("2031-06-01"), expiry_date=read("2031-06-01")))
        )

    def test_issue_after_expiry_is_an_error(self) -> None:
        assert "V-OCR-008" in codes(check(target(expiry_date=read("2020-06-01"))))

    def test_no_expiry_cannot_violate_it(self) -> None:
        assert "V-OCR-008" not in codes(check(target(expiry_date=read(NO_EXPIRY_TEXT))))


class TestV009BirthBeforeIssue:
    def test_birth_before_issue_passes(self) -> None:
        assert "V-OCR-009" not in codes(check(target()))

    def test_birth_after_issue_is_an_error(self) -> None:
        assert "V-OCR-009" in codes(check(target(date_of_birth=read("2022-05-14"))))

    def test_birth_equal_to_issue_is_an_error(self) -> None:
        assert "V-OCR-009" in codes(check(target(date_of_birth=read("2021-06-01"))))


class TestV010AgeAtIssue:
    def test_issued_at_22_passes(self) -> None:
        assert "V-OCR-010" not in codes(check(target()))

    def test_issued_at_13_is_a_warning(self) -> None:
        report = check(target(date_of_birth=read("2008-06-02")))
        assert severity_of(report, "V-OCR-010") is Severity.WARNING
        assert report.is_valid is True

    def test_issued_the_day_before_turning_14_is_a_warning(self) -> None:
        assert "V-OCR-010" in codes(check(target(date_of_birth=read("2007-06-02"))))

    def test_issued_exactly_on_the_14th_birthday_passes(self) -> None:
        assert "V-OCR-010" not in codes(check(target(date_of_birth=read("2007-06-01"))))


class TestV011CurrentAge:
    def test_age_27_passes(self) -> None:
        assert "V-OCR-011" not in codes(check(target()))

    def test_age_over_120_is_a_warning(self) -> None:
        report = check(target(date_of_birth=read("1900-01-01")))
        assert severity_of(report, "V-OCR-011") is Severity.WARNING

    def test_age_under_14_is_a_warning(self) -> None:
        assert "V-OCR-011" in codes(check(target(date_of_birth=read("2020-01-01"))))


class TestV012IssueNotInTheFuture:
    def test_a_past_issue_date_passes(self) -> None:
        assert "V-OCR-012" not in codes(check(target()))

    def test_today_passes(self) -> None:
        assert "V-OCR-012" not in codes(check(target(issue_date=read("2026-08-10"))))

    def test_tomorrow_is_an_error(self) -> None:
        report = check(target(issue_date=read("2026-08-11")))
        assert "V-OCR-012" in codes(report)
        assert report.is_valid is False

    def test_next_year_is_an_error(self) -> None:
        assert "V-OCR-012" in codes(check(target(issue_date=read("2027-01-01"))))


class TestV013CardExpired:
    def test_a_valid_card_passes(self) -> None:
        assert "V-OCR-013" not in codes(check(target()))

    def test_an_expired_card_is_a_warning_not_a_block(self) -> None:
        """🟡 on purpose — an expired CCCD is still the customer's identity."""
        report = check(target(expiry_date=read("2025-01-01")))
        assert severity_of(report, "V-OCR-013") is Severity.WARNING
        assert report.is_valid is True

    def test_the_message_names_the_date(self) -> None:
        report = check(target(expiry_date=read("2025-01-01")))
        assert "01/01/2025" in next(i for i in report.issues if i.code == "V-OCR-013").message_vi

    def test_a_lifelong_card_never_expires(self) -> None:
        assert "V-OCR-013" not in codes(check(target(expiry_date=read(NO_EXPIRY_TEXT))))


class TestV014ExpiringSoon:
    def test_a_far_off_expiry_says_nothing(self) -> None:
        assert "V-OCR-014" not in codes(check(target()))

    def test_expiring_in_30_days_is_info(self) -> None:
        report = check(target(expiry_date=read("2026-09-09")))
        assert severity_of(report, "V-OCR-014") is Severity.INFO
        assert report.is_valid is True

    def test_already_expired_is_v013_not_v014(self) -> None:
        report = check(target(expiry_date=read("2026-08-09")))
        assert "V-OCR-014" not in codes(report)
        assert "V-OCR-013" in codes(report)

    def test_expiring_in_91_days_says_nothing(self) -> None:
        assert "V-OCR-014" not in codes(check(target(expiry_date=read("2026-11-09"))))


class TestV015LifelongHint:
    def test_a_young_holder_gets_no_hint(self) -> None:
        assert "V-OCR-015" not in codes(check(target()))

    def test_issued_at_60_hints_at_a_lifelong_card(self) -> None:
        report = check(target(date_of_birth=read("1961-05-14")))
        assert severity_of(report, "V-OCR-015") is Severity.INFO

    def test_no_hint_when_the_card_already_says_lifelong(self) -> None:
        assert "V-OCR-015" not in codes(
            check(target(date_of_birth=read("1961-05-14"), expiry_date=read(NO_EXPIRY_TEXT)))
        )


class TestV016IssuePlaceIsCanonical:
    def test_a_canonical_place_passes(self) -> None:
        assert "V-OCR-016" not in codes(check(target()))

    def test_a_third_value_is_an_error(self) -> None:
        report = check(target(issue_place=read("CÔNG AN TỈNH HÀ NAM")))
        assert "V-OCR-016" in codes(report)
        assert report.is_valid is False

    def test_a_near_miss_is_still_an_error(self) -> None:
        """The normalizer's job is to fix spelling; by here it is exact-match only."""
        assert "V-OCR-016" in codes(check(target(issue_place=read("BO CONG AN"))))

    def test_a_missing_place_is_left_to_v017(self) -> None:
        report = check(target(issue_place=read(None)))
        assert "V-OCR-016" not in codes(report)
        assert "V-OCR-017" in codes(report)


class TestV017RequiredFields:
    def test_a_complete_card_passes(self) -> None:
        assert "V-OCR-017" not in codes(check(target()))

    @pytest.mark.parametrize(
        "key",
        [
            FieldKey.ID_NUMBER,
            FieldKey.FULL_NAME,
            FieldKey.DATE_OF_BIRTH,
            FieldKey.ISSUE_DATE,
            FieldKey.ISSUE_PLACE,
        ],
    )
    def test_each_required_field_is_enforced(self, key: FieldKey) -> None:
        report = check(target(**{key.value: read(None)}))
        assert "V-OCR-017" in codes(report)
        assert report.is_valid is False

    def test_expiry_is_not_required(self) -> None:
        assert "V-OCR-017" not in codes(check(target(expiry_date=read(None))))

    def test_the_message_uses_the_vietnamese_label(self) -> None:
        report = check(target(issue_place=read(None)))
        assert "Nơi cấp" in next(i for i in report.issues if i.code == "V-OCR-017").message_vi


class TestV018LowConfidence:
    def test_confident_fields_say_nothing(self) -> None:
        assert "V-OCR-018" not in codes(check(target()))

    def test_a_field_below_the_threshold_is_a_warning(self) -> None:
        report = check(target(full_name=read("NGUYỄN VĂN AN", confidence=0.60)))
        assert severity_of(report, "V-OCR-018") is Severity.WARNING
        assert report.is_valid is True

    def test_the_message_states_the_percentage(self) -> None:
        report = check(target(full_name=read("NGUYỄN VĂN AN", confidence=0.62)))
        assert "62%" in next(i for i in report.issues if i.code == "V-OCR-018").message_vi

    def test_one_warning_per_field_not_one_per_card(self) -> None:
        report = check(
            target(
                full_name=read("NGUYỄN VĂN AN", confidence=0.6),
                issue_date=read("2021-06-01", confidence=0.6),
            )
        )
        assert len([i for i in report.issues if i.code == "V-OCR-018"]) == 2

    def test_the_threshold_comes_from_the_context(self) -> None:
        low = target(full_name=read("NGUYỄN VĂN AN", confidence=0.60))
        assert "V-OCR-018" not in codes(check(low, review_threshold=0.5))

    def test_an_unread_field_is_not_a_low_confidence_warning(self) -> None:
        report = check(target(expiry_date=read(None)))
        assert "V-OCR-018" not in codes(report)


class TestV019CardMismatch:
    def test_a_matching_card_passes(self) -> None:
        assert "V-OCR-019" not in codes(check(target()))

    def test_the_flag_blocks_hard(self) -> None:
        """⭐ The one OCR finding that stops the wizard (§03 ALT-06)."""
        report = check(target(id_number=read("001199012345", flags=(FLAG_CARD_MISMATCH,))))
        assert severity_of(report, "V-OCR-019") is Severity.ERROR
        assert report.is_valid is False

    def test_the_flag_on_another_field_does_not_trigger_it(self) -> None:
        report = check(target(full_name=read("NGUYỄN VĂN AN", flags=(FLAG_CARD_MISMATCH,))))
        assert "V-OCR-019" not in codes(report)


class TestV020SourceConflict:
    def test_no_conflict_passes(self) -> None:
        assert "V-OCR-020" not in codes(check(target()))

    def test_a_conflict_is_a_warning_the_user_resolves(self) -> None:
        report = check(target(date_of_birth=read("1999-05-14", flags=(FLAG_SOURCE_CONFLICT,))))
        assert severity_of(report, "V-OCR-020") is Severity.WARNING
        assert report.is_valid is True

    def test_conflicts_on_two_fields_produce_two_warnings(self) -> None:
        report = check(
            target(
                date_of_birth=read("1999-05-14", flags=(FLAG_SOURCE_CONFLICT,)),
                issue_place=read("BỘ CÔNG AN", flags=(FLAG_SOURCE_CONFLICT,)),
            )
        )
        assert len([i for i in report.issues if i.code == "V-OCR-020"]) == 2


class TestV021ProvinceCode:
    def test_a_known_province_passes(self) -> None:
        assert "V-OCR-021" not in codes(check(target()))

    def test_an_unknown_province_is_a_warning(self) -> None:
        report = check(target(id_number=read("999199012345")))
        assert severity_of(report, "V-OCR-021") is Severity.WARNING
        assert report.is_valid is True

    def test_all_zeroes_is_flagged(self) -> None:
        """⭐ Mandatory edge case (§8.11): 12 digits, but no such province."""
        report = check(target(id_number=read("000000000000")))
        assert "V-OCR-021" in codes(report)

    def test_the_check_is_skipped_without_a_directory(self) -> None:
        assert "V-OCR-021" not in codes(
            check(target(id_number=read("999199012345")), known_province_codes=frozenset())
        )


class TestV022GenderDigit:
    def test_a_matching_gender_passes(self) -> None:
        assert "V-OCR-022" not in codes(check(target()))

    def test_a_contradicting_gender_is_a_warning(self) -> None:
        report = check(target(gender=Gender.NAM))
        assert severity_of(report, "V-OCR-022") is Severity.WARNING
        assert "NỮ" in next(i for i in report.issues if i.code == "V-OCR-022").message_vi

    def test_an_unknown_gender_is_not_compared(self) -> None:
        assert "V-OCR-022" not in codes(check(target(gender=Gender.UNKNOWN)))

    def test_no_gender_at_all_is_not_compared(self) -> None:
        assert "V-OCR-022" not in codes(check(target(gender=None)))


class TestV023BirthYearDigits:
    def test_a_matching_birth_year_passes(self) -> None:
        assert "V-OCR-023" not in codes(check(target()))

    def test_a_contradicting_year_is_a_warning(self) -> None:
        """⭐ Catches one misread digit in the middle of the number."""
        report = check(target(date_of_birth=read("1987-03-13"), issue_date=read("2021-06-01")))
        assert severity_of(report, "V-OCR-023") is Severity.WARNING
        assert "1999" in next(i for i in report.issues if i.code == "V-OCR-023").message_vi

    def test_the_right_two_digits_in_the_wrong_century_is_a_warning(self) -> None:
        report = check(target(date_of_birth=read("2099-05-14")))
        assert "V-OCR-023" in codes(report)

    def test_no_birth_date_means_no_verdict(self) -> None:
        assert "V-OCR-023" not in codes(check(target(date_of_birth=read(None))))


class TestRunsEveryRule:
    def test_a_card_wrong_in_many_ways_reports_all_of_them_at_once(self) -> None:
        """⭐ §12.7's postcondition: never stop at the first error."""
        report = check(
            target(
                id_number=read("123", flags=(FLAG_CARD_MISMATCH,)),
                full_name=read(None),
                issue_place=read("SỞ TƯ PHÁP"),
                issue_date=read("2027-01-01"),
            )
        )
        assert {"V-OCR-003", "V-OCR-012", "V-OCR-016", "V-OCR-017", "V-OCR-019"} <= codes(report)
        assert len(report.errors) >= 5

    def test_warnings_never_make_a_report_invalid(self) -> None:
        report = check(target(gender=Gender.NAM, expiry_date=read("2025-01-01")))
        assert report.warnings
        assert report.is_valid is True
