"""`TemplateInspection` / `TemplateDiagnostic` — Port 20's return types (§12.8).

⭐ The postcondition these lock down is the one an implementation is most
likely to get subtly wrong: *`status` is `INVALID` iff there is at least one
ERROR diagnostic.* A `TemplateInspection` that reports `WARNING` while
carrying an error would let an SSTI template be registered.
"""
from __future__ import annotations

from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.ports.templates import (
    DiagnosticSeverity,
    TemplateDiagnostic,
    TemplateInspection,
)

ERROR = TemplateDiagnostic(
    code="COCAS-6014",
    severity=DiagnosticSeverity.ERROR,
    message="Mẫu chứa cấu trúc không được phép vì lý do an toàn.",
)
WARNING = TemplateDiagnostic(
    code="COCAS-6009",
    severity=DiagnosticSeverity.WARNING,
    message="Biến 'x' không xác định.",
    variable="x",
)


class TestStatusDerivation:
    def test_no_diagnostics_is_valid(self) -> None:
        assert TemplateInspection.status_for([]) is TemplateValidationStatus.VALID

    def test_only_warnings_is_warning(self) -> None:
        assert TemplateInspection.status_for([WARNING]) is TemplateValidationStatus.WARNING

    def test_one_error_among_warnings_is_invalid(self) -> None:
        status = TemplateInspection.status_for([WARNING, ERROR, WARNING])
        assert status is TemplateValidationStatus.INVALID


class TestRegistrability:
    def test_valid_and_warning_may_be_registered(self) -> None:
        for status in (TemplateValidationStatus.VALID, TemplateValidationStatus.WARNING):
            assert TemplateInspection(status=status).is_registrable is True

    def test_invalid_may_not(self) -> None:
        inspection = TemplateInspection(
            status=TemplateValidationStatus.INVALID, diagnostics=(ERROR,)
        )
        assert inspection.is_registrable is False

    def test_errors_filters_out_warnings(self) -> None:
        inspection = TemplateInspection(
            status=TemplateValidationStatus.INVALID, diagnostics=(WARNING, ERROR)
        )
        assert inspection.errors == (ERROR,)


class TestDefaults:
    def test_an_empty_inspection_carries_no_variables(self) -> None:
        """Every collection defaults to empty, so a partially built result can
        never look like "this template uses nothing" versus "not analysed"."""
        inspection = TemplateInspection(status=TemplateValidationStatus.VALID)
        assert (
            inspection.declared,
            inspection.required,
            inspection.optional,
            inspection.unknown,
            inspection.richtext_vars,
            inspection.diagnostics,
        ) == ((), (), (), (), (), ())

    def test_diagnostics_are_hashable_value_objects(self) -> None:
        """Frozen + slots, so a diagnostic can be de-duplicated in a set."""
        assert len({ERROR, ERROR, WARNING}) == 2
