"""§12.10 — `StyledValue` → `docxtpl.RichText`, and nothing else touched."""
from __future__ import annotations

from docxtpl import RichText

from cocas.domain.value_objects.styled_value import StyledValue
from cocas.infrastructure.documents.docx_context_adapter import DocxContextAdapter


class TestAdapt:
    def test_styled_value_becomes_rich_text(self) -> None:
        adapted = DocxContextAdapter().adapt({"stk": StyledValue("008C123456", bold=True)})
        value = adapted["stk"]
        assert isinstance(value, RichText)
        assert "008C123456" in value.xml
        assert "<w:b/>" in value.xml

    def test_primitives_pass_through_untouched(self) -> None:
        original = {"name": "AN", "count": 3, "ratio": 1.5, "ok": True, "nothing": None}
        assert DocxContextAdapter().adapt(original) == original

    def test_nested_dictionaries_are_walked(self) -> None:
        adapted = DocxContextAdapter().adapt(
            {"holder": {"stk": StyledValue("008C123456", bold=True)}}
        )
        holder = adapted["holder"]
        assert isinstance(holder, dict)
        assert isinstance(holder["stk"], RichText)

    def test_styled_values_inside_lists_are_walked(self) -> None:
        adapted = DocxContextAdapter().adapt({"rows": [StyledValue("A"), "B"]})
        rows = adapted["rows"]
        assert isinstance(rows, list)
        assert isinstance(rows[0], RichText)
        assert rows[1] == "B"

    def test_strings_are_not_exploded_into_characters(self) -> None:
        """⚠️ `str` is a `Sequence`. Without the explicit check, every string
        in the context comes out as a list of one-character strings."""
        adapted = DocxContextAdapter().adapt({"name": "NGUYỄN VĂN AN"})
        assert adapted["name"] == "NGUYỄN VĂN AN"

    def test_source_context_is_not_mutated(self) -> None:
        """⭐ The un-adapted context is what gets encrypted into
        `render_snapshot_enc` for P-09; a `RichText` cannot be serialised to
        JSON, so mutating in place would corrupt every snapshot."""
        original: dict[str, object] = {"stk": StyledValue("008C123456", bold=True)}
        DocxContextAdapter().adapt(original)
        assert isinstance(original["stk"], StyledValue)

    def test_every_style_attribute_reaches_the_run(self) -> None:
        styled = StyledValue(
            "X", bold=True, italic=True, underline=True, color="FF0000", size=14, font="Arial"
        )
        xml = DocxContextAdapter().adapt({"x": styled})["x"].xml  # type: ignore[union-attr]
        assert "<w:b/>" in xml
        assert "<w:i/>" in xml
        assert "FF0000" in xml
        assert "Arial" in xml

    def test_size_is_converted_from_points_to_half_points(self) -> None:
        """`StyledValue.size` is in points (what Word's toolbar shows);
        OOXML's `w:sz` counts half-points."""
        xml = DocxContextAdapter().adapt(
            {"x": StyledValue("X", size=14)}
        )["x"].xml  # type: ignore[union-attr]
        assert 'w:val="28"' in xml
