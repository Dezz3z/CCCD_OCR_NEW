"""Tests for StyledValue — only primitives, no docxtpl dependency."""
import dataclasses

import pytest

from cocas.domain.value_objects.styled_value import StyledValue


class TestConstruction:
    def test_defaults_to_plain_text(self) -> None:
        sv = StyledValue("008C123456")
        assert sv.text == "008C123456"
        assert sv.bold is False
        assert sv.italic is False
        assert sv.underline is False
        assert sv.color is None
        assert sv.size is None
        assert sv.font is None

    def test_bold_for_securities_account(self) -> None:
        sv = StyledValue("008C123456", bold=True)
        assert sv.bold is True

    def test_all_style_attributes(self) -> None:
        sv = StyledValue("X", bold=True, italic=True, underline=True, color="FF0000", size=12, font="Arial")
        assert (sv.bold, sv.italic, sv.underline, sv.color, sv.size, sv.font) == (
            True, True, True, "FF0000", 12, "Arial",
        )

    def test_str_returns_text(self) -> None:
        assert str(StyledValue("hello")) == "hello"

    def test_only_primitive_fields(self) -> None:
        """⭐ Every field must be a primitive — no methods/objects allowed in render context."""
        for field in dataclasses.fields(StyledValue):
            assert field.type in {"str", "bool", "str | None", "int | None"}

    def test_immutable(self) -> None:
        sv = StyledValue("x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            sv.text = "y"  # type: ignore[misc]
