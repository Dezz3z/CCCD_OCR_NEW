"""The 23 `V-OCR-*` rules of §8.4 — S11 of the pipeline.

⭐ **These rules read; they never write.** Fusion has already chosen each
field's value and raised its flags; this layer decides only what the user is
told and what is allowed to proceed. The split matters: fusion must not know
what blocks (§12.6), and validation must not repair what it dislikes (§12.7).

⭐ **Severity is the design, not a detail.** Only 9 of the 23 block. A card that
expired last month, a citizen who reads as 13 at issue, a province code the
directory does not list — every one of those is a 🟡, because every one of them
has a legitimate explanation and the user is looking at the card. Blocking on a
suspicion leaves someone unable to file a contract for a customer standing in
front of them (P-08).

The rules are functions, wrapped as `FunctionRule` objects for the registry.
Each is small enough to read at a glance, which is the point: a validation rule
nobody can check by eye is a validation rule nobody trusts.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.gender import Gender
from cocas.domain.exceptions import ValidationError
from cocas.domain.services.card_validity_policy import (
    CardValidityPolicy,
    CardValidityReport,
    CardValidityStatus,
)
from cocas.domain.services.field_fusion_service import (
    FLAG_CARD_MISMATCH,
    FLAG_SOURCE_CONFLICT,
    FusedField,
)
from cocas.domain.validation.report import Severity, ValidationIssue
from cocas.domain.validation.rule import FunctionRule, Rule, RuleContext
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.id_card_dates import (
    MIN_AGE_AT_ISSUE,
    NO_EXPIRY_TEXT,
    IdCardDates,
)
from cocas.domain.value_objects.issue_place import ALLOWED_VALUES as CANONICAL_ISSUE_PLACES
from cocas.domain.value_objects.person_name import MIN_WORD_COUNT

# Labels as the wizard prints them (§06 wireframe 2) — these strings reach the
# user inside "Trường '{label}' không được để trống."
FIELD_LABELS_VI: Mapping[FieldKey, str] = {
    FieldKey.ID_NUMBER: "Số CCCD",
    FieldKey.FULL_NAME: "Họ và tên",
    FieldKey.DATE_OF_BIRTH: "Ngày sinh",
    FieldKey.ISSUE_DATE: "Ngày cấp",
    FieldKey.EXPIRY_DATE: "Ngày hết hạn",
    FieldKey.ISSUE_PLACE: "Nơi cấp",
}

# ⭐ `expiry_date` is missing on purpose: `customer.expiry_date` is nullable and
# `no_expiry` is a real state (§4.4.2). Requiring it would block every lifelong
# card, which is exactly the population least able to get a new one.
REQUIRED_FIELDS: tuple[FieldKey, ...] = (
    FieldKey.ID_NUMBER,
    FieldKey.FULL_NAME,
    FieldKey.DATE_OF_BIRTH,
    FieldKey.ISSUE_DATE,
    FieldKey.ISSUE_PLACE,
)

MAX_PLAUSIBLE_AGE = 120


@dataclass(frozen=True, slots=True)
class OcrValidationTarget:
    """What S11 validates: the fused fields, plus what only S1–S4 could know.

    The image-level facts (`has_front_image`, `duplicate_side`) travel here
    rather than being re-derived, because by S11 the images are long gone and
    V-OCR-001/002 are about the upload, not the card.
    """

    fields: Mapping[FieldKey, FusedField] = field(default_factory=dict)
    has_front_image: bool = True
    has_back_image: bool = True
    duplicate_side: bool = False
    gender: Gender | None = None
    """From the QR payload or the form. `None` ⇒ V-OCR-022 has nothing to compare."""

    def value(self, key: FieldKey) -> str | None:
        fused = self.fields.get(key)
        return fused.value if fused is not None else None

    def confidence(self, key: FieldKey) -> float:
        fused = self.fields.get(key)
        return fused.confidence if fused is not None else 0.0

    def flags(self, key: FieldKey) -> tuple[str, ...]:
        fused = self.fields.get(key)
        return fused.flags if fused is not None else ()

    def date_of(self, key: FieldKey) -> date | None:
        """A normalized `YYYY-MM-DD` value as a `date`, or None if it is not one."""
        return _parse_iso(self.value(key))

    @property
    def is_no_expiry(self) -> bool:
        return self.value(FieldKey.EXPIRY_DATE) == NO_EXPIRY_TEXT

    @property
    def citizen_id(self) -> CitizenId | None:
        raw = self.value(FieldKey.ID_NUMBER)
        if raw is None:
            return None
        try:
            return CitizenId(raw)
        except ValidationError:
            return None

    @property
    def card_dates(self) -> IdCardDates | None:
        """`IdCardDates` when the pair is coherent — None when V-OCR-006/008 will fire."""
        issue = self.date_of(FieldKey.ISSUE_DATE)
        if issue is None:
            return None
        expiry = None if self.is_no_expiry else self.date_of(FieldKey.EXPIRY_DATE)
        try:
            return IdCardDates(issue_date=issue, expiry_date=expiry)
        except ValidationError:
            return None


# ============================================================================
# Rules
# ============================================================================


def _v001(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Both sides uploaded."""
    missing = []
    if not target.has_front_image:
        missing.append("mặt trước")
    if not target.has_back_image:
        missing.append("mặt sau")
    return [
        _error("V-OCR-001", f"Thiếu ảnh {side}.", field="images", hint="Tải lên đủ hai mặt thẻ.")
        for side in missing
    ]


def _v002(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """The two uploads are not the same side."""
    if not target.duplicate_side:
        return []
    return [
        _error(
            "V-OCR-002",
            "Bạn đã tải hai ảnh của cùng một mặt.",
            field="images",
            hint="Mặt trước có ảnh chân dung; mặt sau có vân tay hoặc dãy ký tự ở đáy thẻ.",
        )
    ]


def _v003(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Citizen id is exactly 12 digits — §8.3.1."""
    raw = target.value(FieldKey.ID_NUMBER)
    if raw is None or target.citizen_id is not None:
        return []  # absence is V-OCR-017's business
    # Digits, not characters: `00119901234A` is 12 characters but 11 digits, and
    # "Hiện có 12 chữ số" on a value the rule just rejected reads as a bug.
    digits = sum(ch.isdigit() for ch in raw)
    return [
        _error(
            "V-OCR-003",
            f"Số CCCD phải có đúng 12 chữ số. Hiện có {digits} chữ số.",
            field=FieldKey.ID_NUMBER.value,
            hint="Kiểm tra lại trường 'Số CCCD'. Nếu ảnh mờ, hãy chụp lại mặt trước.",
        )
    ]


def _v004(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Name present, and at least two words — a one-word name is 🟡, not 🔴."""
    name = target.value(FieldKey.FULL_NAME)
    if not name:
        return []  # V-OCR-017
    if len(name.split()) >= MIN_WORD_COUNT:
        return []
    return [
        _warning(
            "V-OCR-004",
            "Họ và tên chỉ có một từ — kiểm tra lại xem đã đủ họ và tên đệm chưa.",
            field=FieldKey.FULL_NAME.value,
        )
    ]


def _v005(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Date of birth is a real calendar date."""
    return _bad_date(target, FieldKey.DATE_OF_BIRTH, "V-OCR-005", "Ngày sinh không hợp lệ.")


def _v006(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Issue date is a real calendar date."""
    return _bad_date(target, FieldKey.ISSUE_DATE, "V-OCR-006", "Ngày cấp không hợp lệ.")


def _v007(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Expiry is a real date **or** the words `KHÔNG THỜI HẠN`."""
    if target.is_no_expiry:
        return []
    return _bad_date(target, FieldKey.EXPIRY_DATE, "V-OCR-007", "Ngày hết hạn không hợp lệ.")


def _v008(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ issue_date <= expiry_date. The boundary (equal) is valid."""
    issue = target.date_of(FieldKey.ISSUE_DATE)
    expiry = None if target.is_no_expiry else target.date_of(FieldKey.EXPIRY_DATE)
    if issue is None or expiry is None or issue <= expiry:
        return []
    return [
        _error(
            "V-OCR-008",
            "Ngày cấp phải trước hoặc bằng ngày hết hạn.",
            field=FieldKey.EXPIRY_DATE.value,
        )
    ]


def _v009(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """date_of_birth < issue_date."""
    birth = target.date_of(FieldKey.DATE_OF_BIRTH)
    issue = target.date_of(FieldKey.ISSUE_DATE)
    if birth is None or issue is None or birth < issue:
        return []
    return [
        _error(
            "V-OCR-009",
            "Ngày sinh phải trước ngày cấp.",
            field=FieldKey.DATE_OF_BIRTH.value,
        )
    ]


def _v010(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Age at issue >= 14 — the age a CCCD is first issued."""
    age = _age_at_issue(target)
    if age is None or age >= MIN_AGE_AT_ISSUE:
        return []
    return [
        _warning(
            "V-OCR-010",
            f"Công dân dưới {MIN_AGE_AT_ISSUE} tuổi không được cấp CCCD. "
            "Kiểm tra lại ngày sinh/ngày cấp.",
            field=FieldKey.DATE_OF_BIRTH.value,
        )
    ]


def _v011(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """Current age within [14, 120]."""
    birth = target.date_of(FieldKey.DATE_OF_BIRTH)
    if birth is None:
        return []
    age = _years_between(birth, context.today)
    if MIN_AGE_AT_ISSUE <= age <= MAX_PLAUSIBLE_AGE:
        return []
    return [
        _warning(
            "V-OCR-011",
            f"Tuổi tính ra là {age} — có vẻ bất thường.",
            field=FieldKey.DATE_OF_BIRTH.value,
        )
    ]


def _v012(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """issue_date is not in the future."""
    issue = target.date_of(FieldKey.ISSUE_DATE)
    if issue is None or issue <= context.today:
        return []
    return [
        _error(
            "V-OCR-012",
            "Ngày cấp không thể ở tương lai.",
            field=FieldKey.ISSUE_DATE.value,
        )
    ]


def _v013(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """Card still valid — 🟡, an expired CCCD is still the person's identity."""
    report = _validity(target, context)
    if report is None or report.status is not CardValidityStatus.CARD_EXPIRED:
        return []
    return [
        _warning("V-OCR-013", report.message_vi, field=FieldKey.EXPIRY_DATE.value)
    ]


def _v014(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """Expiring within 90 days — 🔵, purely informational."""
    report = _validity(target, context)
    if report is None or report.status is not CardValidityStatus.CARD_EXPIRING_SOON:
        return []
    return [
        ValidationIssue(
            code="V-OCR-014",
            severity=Severity.INFO,
            message_vi=report.message_vi,
            field=FieldKey.EXPIRY_DATE.value,
        )
    ]


def _v015(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ Issued at 60+ — such cards are normally lifelong, so an expiry date is odd."""
    report = _validity(target, context)
    if report is None or not report.should_have_no_expiry_hint or target.is_no_expiry:
        return []
    return [
        ValidationIssue(
            code="V-OCR-015",
            severity=Severity.INFO,
            message_vi="Công dân đủ 60 tuổi khi cấp — thẻ thường có giá trị không thời hạn.",
            field=FieldKey.EXPIRY_DATE.value,
        )
    ]


def _v016(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ Issue place is one of exactly two values — §8.3.9.

    Belt and braces over `IssuePlaceNormalizer`'s own invariant: this is the
    third of the three layers §03 S9 requires (VO, API, DB) seen from the rule
    side, and the one that would catch a value injected past the normalizer.
    """
    place = target.value(FieldKey.ISSUE_PLACE)
    if place is None or place in CANONICAL_ISSUE_PLACES:
        return []
    return [
        _error(
            "V-OCR-016",
            "Nơi cấp phải là một trong hai giá trị chuẩn.",
            field=FieldKey.ISSUE_PLACE.value,
            hint="Chọn 'BỘ CÔNG AN' hoặc 'CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI'.",
        )
    ]


def _v017(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """Every required field carries a value."""
    return [
        _error(
            "V-OCR-017",
            f"Trường '{FIELD_LABELS_VI[key]}' không được để trống.",
            field=key.value,
        )
        for key in REQUIRED_FIELDS
        if not target.value(key)
    ]


def _v018(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """Confidence below the review threshold — one 🟡 per field, not one for the card."""
    issues = []
    for key in FieldKey:
        if target.value(key) is None:
            continue
        confidence = target.confidence(key)
        if confidence >= context.review_threshold:
            continue
        issues.append(
            _warning(
                "V-OCR-018",
                f"Trường '{FIELD_LABELS_VI[key]}' được nhận dạng với độ tin cậy "
                f"{round(confidence * 100)}%.",
                field=key.value,
                hint="Đối chiếu với ảnh thẻ trước khi tiếp tục.",
            )
        )
    return issues


def _v019(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ `CARD_MISMATCH` — the one OCR finding that hard-blocks (§03 ALT-06)."""
    if FLAG_CARD_MISMATCH not in target.flags(FieldKey.ID_NUMBER):
        return []
    return [
        _error(
            "V-OCR-019",
            "Hai ảnh có vẻ không thuộc cùng một thẻ (số CCCD từ QR khác từ MRZ).",
            field=FieldKey.ID_NUMBER.value,
            hint="Kiểm tra lại xem hai ảnh có phải của cùng một thẻ không.",
        )
    ]


def _v020(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """`SOURCE_CONFLICT` still unresolved — the user picks, so 🟡."""
    return [
        _warning(
            "V-OCR-020",
            f"Hai nguồn cho giá trị khác nhau ở trường '{FIELD_LABELS_VI[key]}'. "
            "Vui lòng chọn.",
            field=key.value,
        )
        for key in FieldKey
        if FLAG_SOURCE_CONFLICT in target.flags(key)
    ]


def _v021(target: OcrValidationTarget, context: RuleContext) -> Sequence[ValidationIssue]:
    """First 3 digits are a real province code — skipped when no directory was loaded."""
    citizen_id = target.citizen_id
    if citizen_id is None or not context.known_province_codes:
        return []
    if citizen_id.province_code in context.known_province_codes:
        return []
    return [
        _warning(
            "V-OCR-021",
            f"Mã tỉnh '{citizen_id.province_code}' trong số CCCD không có trong danh mục.",
            field=FieldKey.ID_NUMBER.value,
        )
    ]


def _v022(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """4th digit encodes gender — compare with what was recorded."""
    citizen_id = target.citizen_id
    if citizen_id is None or target.gender is None:
        return []
    inferred = citizen_id.inferred_gender
    expected = _GENDER_BY_CODE.get(inferred) if inferred else None
    if expected is None or target.gender not in (Gender.NAM, Gender.NU):
        return []
    if expected is target.gender:
        return []
    return [
        _warning(
            "V-OCR-022",
            f"Số CCCD cho thấy giới tính {expected.value}, nhưng đã ghi {target.gender.value}.",
            field=FieldKey.ID_NUMBER.value,
        )
    ]


def _v023(target: OcrValidationTarget, _context: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ Digits 5–6 are the birth year — the check `^\\d{12}$` can never make."""
    citizen_id = target.citizen_id
    birth = target.date_of(FieldKey.DATE_OF_BIRTH)
    if citizen_id is None or birth is None:
        return []
    century = citizen_id.inferred_birth_year_range
    suffix_matches = f"{birth.year % 100:02d}" == citizen_id.birth_year_suffix
    century_matches = century is None or century[0] <= birth.year <= century[1]
    if suffix_matches and century_matches:
        return []
    implied = _implied_year(citizen_id)
    return [
        _warning(
            "V-OCR-023",
            f"Số CCCD cho thấy năm sinh {implied}, nhưng đã ghi {birth.year}.",
            field=FieldKey.DATE_OF_BIRTH.value,
        )
    ]


# ⭐ Registration order is display order — the wizard shows issues top to bottom,
# so the upload-level problems come before the field-level ones.
OCR_RESULT_RULES: tuple[Rule[OcrValidationTarget], ...] = (
    FunctionRule("V-OCR-001", _v001),
    FunctionRule("V-OCR-002", _v002),
    FunctionRule("V-OCR-003", _v003),
    FunctionRule("V-OCR-004", _v004),
    FunctionRule("V-OCR-005", _v005),
    FunctionRule("V-OCR-006", _v006),
    FunctionRule("V-OCR-007", _v007),
    FunctionRule("V-OCR-008", _v008),
    FunctionRule("V-OCR-009", _v009),
    FunctionRule("V-OCR-010", _v010),
    FunctionRule("V-OCR-011", _v011),
    FunctionRule("V-OCR-012", _v012),
    FunctionRule("V-OCR-013", _v013),
    FunctionRule("V-OCR-014", _v014),
    FunctionRule("V-OCR-015", _v015),
    FunctionRule("V-OCR-016", _v016),
    FunctionRule("V-OCR-017", _v017),
    FunctionRule("V-OCR-018", _v018),
    FunctionRule("V-OCR-019", _v019),
    FunctionRule("V-OCR-020", _v020),
    FunctionRule("V-OCR-021", _v021),
    FunctionRule("V-OCR-022", _v022),
    FunctionRule("V-OCR-023", _v023),
)


# ============================================================================
# Helpers
# ============================================================================

_GENDER_BY_CODE = {"MALE": Gender.NAM, "FEMALE": Gender.NU}
_VALIDITY = CardValidityPolicy()


def _error(code: str, message: str, *, field: str, hint: str | None = None) -> ValidationIssue:
    return ValidationIssue(
        code=code, severity=Severity.ERROR, message_vi=message, field=field, hint=hint
    )


def _warning(code: str, message: str, *, field: str, hint: str | None = None) -> ValidationIssue:
    return ValidationIssue(
        code=code, severity=Severity.WARNING, message_vi=message, field=field, hint=hint
    )


def _bad_date(
    target: OcrValidationTarget, key: FieldKey, code: str, message: str
) -> Sequence[ValidationIssue]:
    """An ERROR only when a value is present but is not a date — absence is V-OCR-017."""
    if target.value(key) is None or target.date_of(key) is not None:
        return []
    return [_error(code, message, field=key.value)]


def _validity(target: OcrValidationTarget, context: RuleContext) -> CardValidityReport | None:
    """`CardValidityPolicy`'s verdict, when the dates support one.

    Reused rather than reimplemented: §07 D5 makes this service the owner of
    V-OCR-013/014/015, and two copies of "is this card expired" is one copy too
    many.
    """
    dates = target.card_dates
    birth = target.date_of(FieldKey.DATE_OF_BIRTH)
    if dates is None or birth is None:
        return None
    return _VALIDITY.evaluate(dates, birth, context.today)


def _age_at_issue(target: OcrValidationTarget) -> int | None:
    birth = target.date_of(FieldKey.DATE_OF_BIRTH)
    issue = target.date_of(FieldKey.ISSUE_DATE)
    if birth is None or issue is None:
        return None
    return _years_between(birth, issue)


def _years_between(born: date, on: date) -> int:
    years = on.year - born.year
    if (on.month, on.day) < (born.month, born.day):
        years -= 1
    return years


def _implied_year(citizen_id: CitizenId) -> str:
    century = citizen_id.inferred_birth_year_range
    if century is None:
        return f"..{citizen_id.birth_year_suffix}"
    return f"{century[0] // 100}{citizen_id.birth_year_suffix}"


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
