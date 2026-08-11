"""The §9.5 system variable dictionary.

⭐ These are mostly *counting* tests, and that is the point. The design header
claimed 25 variables for three revisions while the tables underneath listed 28
— the kind of number that stays wrong until something asserts it.
"""
from __future__ import annotations

from cocas.domain.services.template_variables import (
    BOLD_VARIABLE_KEYS,
    SYSTEM_VARIABLE_KEYS,
    SYSTEM_VARIABLES,
    SYSTEM_VARIABLES_BY_KEY,
)

#: §9.7 — the render kinds a `VariableSpec` may declare.
KNOWN_KINDS = {
    "text",
    "date",
    "date_text",
    "number",
    "decimal",
    "currency",
    "currency_text",
    "percent",
    "boolean",
    "enum",
    "securities_account",
}


class TestDictionaryShape:
    def test_holds_28_variables(self) -> None:
        """⭐ 11 + 3 + 5 + 1 + 8. The `day / month / year` row declares three."""
        assert len(SYSTEM_VARIABLES) == 28

    def test_keys_are_unique(self) -> None:
        assert len(SYSTEM_VARIABLES_BY_KEY) == len(SYSTEM_VARIABLES)

    def test_every_kind_is_one_the_formatter_knows(self) -> None:
        """A kind outside §9.7 would render as the wrong type, silently."""
        assert {v.kind for v in SYSTEM_VARIABLES} <= KNOWN_KINDS

    def test_every_variable_has_a_vietnamese_label(self) -> None:
        """The label is what `COCAS-7002` shows when a required value is missing."""
        assert all(v.label.strip() for v in SYSTEM_VARIABLES)

    def test_keys_are_the_index_of_the_specs(self) -> None:
        assert SYSTEM_VARIABLE_KEYS == frozenset(v.key for v in SYSTEM_VARIABLES)


class TestStyledVariables:
    def test_only_the_securities_account_is_bold(self) -> None:
        """§9.5 — the one variable v1.0 renders styled, hence `{{r … }}`."""
        assert BOLD_VARIABLE_KEYS == frozenset({"securities_account_no"})

    def test_the_bold_variable_declares_its_own_kind(self) -> None:
        spec = SYSTEM_VARIABLES_BY_KEY["securities_account_no"]
        assert (spec.kind, spec.bold) == ("securities_account", True)


class TestNoVariableIsAList:
    def test_no_kind_implies_a_sequence(self) -> None:
        """⚠️ `min = max = 1` in v1.0 (§4.5), so a `{% for %}` over any key here
        is an authoring mistake — that is exactly what `COCAS-6012` reports.
        If a list-valued kind is ever added, `_warn_non_iterable` must learn
        about it in the same commit.
        """
        list_like = {"list", "array", "table", "repeat"}
        assert {v.kind for v in SYSTEM_VARIABLES} & list_like == set()


class TestTheTemplatesActuallyShipped:
    """The variables §4.5 says each real template uses must all exist."""

    GDN = (
        "full_name id_number dob issue_date issue_place expiry_date "
        "address phone email bank_account bank_name branch"
    ).split()
    GDKQ = (
        "full_name id_number dob issue_date issue_place expiry_date "
        "address phone email securities_account_no"
    ).split()

    def test_gdn_uses_12_known_variables(self) -> None:
        assert len(self.GDN) == 12
        assert set(self.GDN) <= SYSTEM_VARIABLE_KEYS

    def test_gdkq_variables_are_known(self) -> None:
        assert set(self.GDKQ) <= SYSTEM_VARIABLE_KEYS
