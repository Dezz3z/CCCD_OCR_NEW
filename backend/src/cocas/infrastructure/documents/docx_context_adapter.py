"""`DocxContextAdapter` (§12.10) — the only place `StyledValue` meets `docxtpl`.

⭐ Pitfall #4 in one file: Application says *what* is bold by producing a
`StyledValue`; this adapter says it in `docxtpl`'s words. Swapping the render
library (or rendering to HTML) means rewriting this file and nothing else.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from docxtpl import RichText

from cocas.domain.value_objects.styled_value import StyledValue

#: `RichText` takes the font size in **half-points** (`size=28` is 14 pt),
#: matching OOXML's `w:sz`. `StyledValue.size` is in points, because that is
#: what a template author reads off Word's toolbar.
_POINTS_TO_HALF_POINTS = 2


class DocxContextAdapter:
    """Recursively replace every `StyledValue` with a `docxtpl.RichText`."""

    def adapt(self, context: Mapping[str, object]) -> dict[str, object]:
        """Return a copy of `context` ready to hand to the renderer.

        ⭐ Copies rather than mutates: the un-adapted context is what gets
        encrypted into `contract.render_snapshot_enc` for P-09 determinism,
        and a `RichText` does not survive JSON serialisation. Mutating in
        place would corrupt the snapshot of every contract.
        """
        return {key: self._adapt_value(value) for key, value in context.items()}

    def _adapt_value(self, value: object) -> object:
        if isinstance(value, StyledValue):
            return self._to_rich_text(value)
        if isinstance(value, Mapping):
            return {key: self._adapt_value(item) for key, item in value.items()}
        # ⚠️ `str`/`bytes` are Sequences. Checking them first is not a style
        # choice — without it every string is rebuilt as a list of characters.
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return [self._adapt_value(item) for item in value]
        return value

    def _to_rich_text(self, value: StyledValue) -> RichText:
        return RichText(
            value.text,
            bold=value.bold,
            italic=value.italic,
            underline=value.underline,
            color=value.color,
            size=value.size * _POINTS_TO_HALF_POINTS if value.size else None,
            font=value.font,
        )
