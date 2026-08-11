"""Template-inspection port (§12.8 `TemplateInspector`) — ⭐ port 20.

⭐ **Added in P3 module 3** (§12.19.2). The inspector had been specified as
plain Infrastructure, but three Use Cases call it directly
(`RegisterTemplateUseCase`, `ValidateTemplateUseCase`,
`AddTemplateVersionUseCase`) and the import-linter contract forbids
`cocas.application` from importing `docxtpl`. Without a port, either
Application imports the render library or the decision to reject a template
moves up into Presentation — business logic in the wrong layer.

The port's return types live here rather than in `application/dto/` for the
same reason `OcrResultSnapshot` does (§12.14): Infrastructure sits *below*
Application in the layer contract and may not import its DTOs.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from cocas.domain.enums.template_validation_status import TemplateValidationStatus


class DiagnosticSeverity(str, Enum):
    """Severity of one template diagnostic (§9.3: 🔴 ERROR / 🟡 WARNING).

    Not part of the §4.3.3 database enum catalogue — diagnostics are stored
    inside `template_version.validation_report` (JSONB), never as a column.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class TemplateDiagnostic:
    """One finding from §9.3's catalogue.

    ⭐ Only 8 of the 10 codes can appear here. `COCAS-6002` (not a DOCX) and
    `COCAS-6003` (Jinja2 syntax) are *raised*, because in those two cases
    there is nothing to report — see §12.8.1.
    """

    code: str
    """`COCAS-6008` … `COCAS-6016`."""

    severity: DiagnosticSeverity

    message: str
    """⭐ Vietnamese, ready to show the user (§9.3 wording)."""

    variable: str | None = None
    """The variable the finding is about, when it is about one."""

    paragraph: int | None = None
    """⭐ 1-based ordinal of the `<w:p>` element, **counting paragraphs inside
    tables** — see §12.8.3. `.docx` has no notion of a line."""

    part: str | None = None
    """Which part of the package it was found in (`word/document.xml`,
    `word/footer1.xml`, …). Paragraph ordinals restart per part."""


@dataclass(frozen=True, slots=True)
class TemplateInspection:
    """Result of inspecting one uploaded `.docx` (§12.8).

    Postcondition (§12.8): `status` is `INVALID` **iff** `diagnostics`
    contains at least one `ERROR`, and `WARNING` iff it contains at least one
    `WARNING` and no `ERROR`. `from_diagnostics()` is the only constructor
    that can get this wrong, so it is the only one that computes it.
    """

    status: TemplateValidationStatus
    declared: tuple[str, ...] = ()
    """Every variable the file actually uses, sorted, dotted paths intact."""

    required: tuple[str, ...] = ()
    """Declared ∩ the keys `party_schema`/`contract_fields` mark required."""

    optional: tuple[str, ...] = ()
    """Declared ∩ known, minus `required`."""

    unknown: tuple[str, ...] = ()
    """Declared but not known. Renders empty; warns with `COCAS-6009`."""

    richtext_vars: tuple[str, ...] = ()
    """⭐ Variables written `{{r key }}`. Cannot come from the AST — docxtpl
    erases the `r` before Jinja2 parses (§12.8.2)."""

    has_loops: bool = False
    has_conditionals: bool = False
    diagnostics: tuple[TemplateDiagnostic, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[TemplateDiagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity is DiagnosticSeverity.ERROR)

    @property
    def is_registrable(self) -> bool:
        """A template may be registered while WARNING, never while INVALID."""
        return self.status is not TemplateValidationStatus.INVALID

    @staticmethod
    def status_for(
        diagnostics: Sequence[TemplateDiagnostic],
    ) -> TemplateValidationStatus:
        """Derive `status` from the diagnostics, per §12.8's postcondition."""
        if any(d.severity is DiagnosticSeverity.ERROR for d in diagnostics):
            return TemplateValidationStatus.INVALID
        if diagnostics:
            return TemplateValidationStatus.WARNING
        return TemplateValidationStatus.VALID


@runtime_checkable
class ITemplateInspector(Protocol):
    """⭐ Port 20 — analyse a `.docx` template without rendering it (§12.8).

    Implementations: `DocxTemplateInspector` (production) ·
    `FakeTemplateInspector` (tests).

    Invariants every implementation must uphold:
      - ⭐ it **never renders** — inspection is parsing only, so a malicious
        template cannot execute anything by being inspected (§9.9);
      - variables are collected from the **Jinja2 AST**, never by pattern
        matching text (§9.2 step 5);
      - it reads header and footer parts too, not just `word/document.xml`
        (§12.8.2) — otherwise a variable in the footer counts as missing.
    """

    def inspect(
        self,
        file_bytes: bytes,
        party_schema: Sequence[Mapping[str, object]],
        contract_fields: Sequence[Mapping[str, object]] = (),
    ) -> TemplateInspection:
        """Inspect an uploaded template.

        Args:
            file_bytes: the raw `.docx`. Must not be empty.
            party_schema: `contract_template.party_schema` (§4.5). Left as
                loose JSON-shaped mappings on purpose — the grammar is only
                interpreted here and by the Wizard, so modelling it strictly
                would be structure ahead of need (P-10, see `Template`).
            contract_fields: `contract_template.contract_fields`. ⭐ Optional
                and defaulted to empty: both v1.0 templates declare none, but
                omitting it for a template that *does* declare them would
                warn `COCAS-6009` about variables the user declared correctly.

        Returns:
            The inspection, including every diagnostic that did not make
            analysis impossible.

        Raises:
            NotADocxFileError: bad magic bytes, not a ZIP, or no
                `word/document.xml` — `COCAS-6002`.
            TemplateSyntaxError: Jinja2 could not build an AST — `COCAS-6003`.
                `line` is the paragraph ordinal (§12.8.3).
        """
        ...
