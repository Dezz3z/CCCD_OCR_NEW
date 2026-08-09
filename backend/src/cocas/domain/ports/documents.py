"""Document rendering & PDF conversion ports (§12.11, §12.12) — ports 12–13 of 18."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Outcome of rendering a `.docx` from a template."""

    output_path: str
    sha256: bytes
    size_bytes: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PdfResult:
    """Outcome of converting a `.docx` to PDF."""

    output_path: str
    sha256: bytes
    size_bytes: int
    page_count: int
    duration_ms: int
    generator_version: str


@runtime_checkable
class IDocumentRenderer(Protocol):
    """⭐ Port 12 — render a template to `.docx` (§12.11).

    The context passed in contains only primitives and already-adapted
    rich-text objects; building it is `RenderContextBuilder`'s job
    (Application) and adapting `StyledValue` is `DocxContextAdapter`'s
    (Infrastructure). This port never sees a `StyledValue`.

    Invariant: write-temp → verify → rename, so a half-written `.docx`
    never exists at `output_path`.
    """

    def render(
        self, template_path: str, context: dict[str, object], output_path: str
    ) -> RenderResult:
        """Render and return the result.

        Raises:
            TemplateNotFoundError: template file missing.
            TemplateChecksumMismatchError: on-disk SHA-256 ≠ recorded value.
            RenderError: rendering failed.
            InsufficientStorageError: less than the required free space.
        """
        ...


@runtime_checkable
class IPdfConverter(Protocol):
    """⭐ Port 13 — convert `.docx` to PDF (§12.12).

    Implementations: `LibreOfficePdfConverter` · `NullConverter`.

    ⭐ Never retries internally — retry policy belongs to `JobRunner`
    (max 3 attempts, backoff 5s/25s/125s). A timeout must kill the whole
    process tree so no orphan `soffice` survives.
    """

    def convert(self, docx_path: str, output_dir: str, timeout_sec: int) -> PdfResult:
        """Convert and return the result.

        Raises:
            LibreOfficeUnavailableError: converter binary unreachable.
            PdfConversionTimeoutError: exceeded `timeout_sec`.
            InvalidPdfOutputError: produced file is not a valid PDF.
        """
        ...
