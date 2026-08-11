"""Document rendering port (§12.11) — port 12 of 18.

⭐ D2.1 — `IPdfConverter` (port 13) và `PdfResult` đã bị gỡ cùng toàn bộ
khâu xuất PDF; xem §9.13 và §12.12. `IDocumentRenderer` là **điểm cuối**
của chuỗi sinh tài liệu: sau nó không còn bước chuyển đổi nào nữa.
"""
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
