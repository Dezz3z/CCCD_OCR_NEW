"""Tests for ExportNameGenerator (§12.18)."""
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.services.export_name_generator import (
    _RESERVED_NAMES,
    MAX_LENGTH,
    ExportNameGenerator,
)

GEN = ExportNameGenerator()
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _is_valid_windows_filename(name: str) -> bool:
    if not name or len(name) > MAX_LENGTH:
        return False
    if _FORBIDDEN.search(name):
        return False
    if name.upper() in _RESERVED_NAMES:
        return False
    return name[-1] not in (".", " ")


class TestBasicGeneration:
    def test_matches_design_doc_example(self) -> None:
        result = GEN.generate("Mẫu 01A - {full_name}", {"full_name": "NGUYỄN VĂN AN"}, set())
        assert result == "Mẫu 01A - NGUYỄN VĂN AN"

    def test_keeps_diacritics_by_default(self) -> None:
        result = GEN.generate("{full_name}", {"full_name": "NGUYỄN VĂN AN"}, set())
        assert result == "NGUYỄN VĂN AN"

    def test_strips_diacritics_when_flagged(self) -> None:
        result = GEN.generate(
            "{full_name}", {"full_name": "NGUYỄN VĂN AN"}, set(), strip_diacritics_flag=True
        )
        assert result == "NGUYEN VAN AN"

    def test_missing_context_key_becomes_empty(self) -> None:
        result = GEN.generate("A-{missing}-B", {}, set())
        assert result == "A--B"


class TestForbiddenCharacters:
    @pytest.mark.parametrize("bad_char", list('\\/:*?"<>|'))
    def test_removed_from_output(self, bad_char: str) -> None:
        result = GEN.generate("{name}", {"name": f"A{bad_char}B"}, set())
        assert bad_char not in result

    def test_control_characters_removed(self) -> None:
        result = GEN.generate("{name}", {"name": "A\x00\x1fB"}, set())
        assert _is_valid_windows_filename(result)


class TestReservedNames:
    @pytest.mark.parametrize("reserved", ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"])
    def test_reserved_name_disambiguated(self, reserved: str) -> None:
        result = GEN.generate("{name}", {"name": reserved}, set())
        assert result.upper() != reserved
        assert _is_valid_windows_filename(result)

    def test_reserved_name_case_insensitive(self) -> None:
        result = GEN.generate("{name}", {"name": "con"}, set())
        assert result.upper() != "CON"


class TestLength:
    def test_truncated_to_max_length(self) -> None:
        result = GEN.generate("{name}", {"name": "A" * 300}, set())
        assert len(result) <= MAX_LENGTH

    def test_exactly_max_length_untouched(self) -> None:
        name = "B" * MAX_LENGTH
        result = GEN.generate("{name}", {"name": name}, set())
        assert result == name


class TestDeduplication:
    def test_no_collision_returns_as_is(self) -> None:
        result = GEN.generate("{name}", {"name": "Báo cáo"}, {"Khác"})
        assert result == "Báo cáo"

    def test_first_collision_appends_2(self) -> None:
        result = GEN.generate("{name}", {"name": "Báo cáo"}, {"Báo cáo"})
        assert result == "Báo cáo (2)"

    def test_multiple_collisions_increment(self) -> None:
        existing = {"Báo cáo", "Báo cáo (2)", "Báo cáo (3)"}
        result = GEN.generate("{name}", {"name": "Báo cáo"}, existing)
        assert result == "Báo cáo (4)"


class TestErrors:
    def test_empty_pattern_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            GEN.generate("", {}, set())
        assert exc_info.value.code == "EMPTY_EXPORT_NAME_PATTERN"

    def test_pattern_resolving_to_nothing_gets_fallback(self) -> None:
        result = GEN.generate("{a}{b}", {}, set())
        assert result == "Tài liệu"


class TestMandatoryProperty:
    """⭐ §12.18: 'với mọi họ tên đầu vào, kết quả luôn là tên file hợp lệ trên Windows'."""

    @pytest.mark.parametrize(
        "name",
        [
            "NGUYỄN VĂN AN", "CON", "con.txt", "A" * 500, "", "///:::***",
            "Nguyễn/Văn\\An", "  leading and trailing  ", "a" * 179 + "..",
        ],
    )
    def test_always_valid_for_known_tricky_inputs(self, name: str) -> None:
        result = GEN.generate("Mẫu 01A - {full_name}", {"full_name": name}, set())
        assert _is_valid_windows_filename(result)

    @given(st.text(max_size=250))
    @settings(max_examples=200, deadline=None)
    def test_property_any_name_yields_valid_windows_filename(self, name: str) -> None:
        result = GEN.generate("Mẫu 01A - {full_name}", {"full_name": name}, set())
        assert _is_valid_windows_filename(result)
