"""A card that passes all 23 rules, and the knobs to break exactly one of it."""
from __future__ import annotations

from datetime import date

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.enums.gender import Gender
from cocas.domain.services.field_fusion_service import FusedField
from cocas.domain.validation import OcrValidationTarget, RuleContext
from cocas.domain.value_objects.issue_place import BO_CONG_AN

TODAY = date(2026, 8, 10)

# `001 1 99 012345` — province 001, female, born 1999. Every structural check
# in V-OCR-021/022/023 is satisfied by this number together with CLEAN_FIELDS.
CLEAN_ID = "001199012345"
PROVINCE_CODES = frozenset({"001", "079", "048"})


def read(value: str | None, confidence: float = 1.0, flags: tuple[str, ...] = ()) -> FusedField:
    """One fused field, confident and unflagged unless told otherwise."""
    return FusedField(
        value=value,
        confidence=confidence if value is not None else 0.0,
        source=FieldSource.QR if value is not None else FieldSource.NONE,
        needs_review=False,
        flags=flags,
    )


def clean_fields() -> dict[FieldKey, FusedField]:
    return {
        FieldKey.ID_NUMBER: read(CLEAN_ID),
        FieldKey.FULL_NAME: read("NGUYỄN VĂN AN"),
        FieldKey.DATE_OF_BIRTH: read("1999-05-14"),
        FieldKey.ISSUE_DATE: read("2021-06-01"),
        FieldKey.EXPIRY_DATE: read("2031-06-01"),
        FieldKey.ISSUE_PLACE: read(BO_CONG_AN),
    }


def target(**overrides: object) -> OcrValidationTarget:
    """The clean card, with any field replaced by keyword.

    `target(expiry_date=read(None))` reads better in a rule's test than
    building the whole six-field dict again, and keeps each test's *one*
    deviation visible.
    """
    fields = clean_fields()
    # `gender` matches the clean id's 4th digit unless a test overrides it.
    kwargs: dict[str, object] = {"gender": Gender.NU}
    for name, value in overrides.items():
        try:
            fields[FieldKey(name)] = value  # type: ignore[assignment]
        except ValueError:
            kwargs[name] = value
    return OcrValidationTarget(fields=fields, **kwargs)  # type: ignore[arg-type]


def context(**overrides: object) -> RuleContext:
    values: dict[str, object] = {
        "today": TODAY,
        "review_threshold": 0.85,
        "known_province_codes": PROVINCE_CODES,
    }
    values.update(overrides)
    return RuleContext(**values)  # type: ignore[arg-type]
