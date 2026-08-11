"""⭐ The v1.0 system variable dictionary (§9.5) — 28 variables.

This is business vocabulary, not infrastructure: the same table is read by
`TemplateInspector` (to classify what a `.docx` uses), by
`RenderContextBuilder` (to format each value per §9.7) and by
`GET /templates/variables`. It lives in Domain so all three can name it
without any of them importing the others.

⭐ **28 variables, not the 25 the design header used to claim.** Counting
the five §9.5 tables row by row gives 11 + 3 + 5 + 1 + 8 = 28; even counting
*rows* gives 26, because the row spelling `{{day}} / {{month}} / {{year}}`
declares three variables in one cell. Corrected in the design doc on
2026-08-11.

⚠️ **No variable here is a list.** `party_schema` is pinned to `min = max = 1`
in v1.0 (§4.5), so a `{% for %}` over any key in this table is a template
authoring mistake — that is what `COCAS-6012` reports.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Render kinds from the §9.7 formatting table. Kept as plain strings rather
#: than an enum: the table is the authority, `RenderContextBuilder` is its
#: only consumer, and a wrong value cannot reach the database (the dictionary
#: is a constant, not user input).
VariableKind = str


@dataclass(frozen=True, slots=True)
class VariableSpec:
    """One row of the §9.5 dictionary."""

    key: str
    label: str
    kind: VariableKind
    bold: bool = False
    """⭐ `render_style.bold` — the template must write `{{r key }}`, not
    `{{ key }}`, or the value renders unstyled (`COCAS-6008`)."""


# ---------------------------------------------------------------- from CCCD (11)
_CARD: tuple[VariableSpec, ...] = (
    VariableSpec("full_name", "Họ và tên", "text"),
    VariableSpec("id_number", "Số CCCD", "text"),
    VariableSpec("id_number_spaced", "Số CCCD (nhóm 4)", "text"),
    VariableSpec("dob", "Ngày sinh", "date"),
    VariableSpec("dob_text", "Ngày sinh (chữ)", "date_text"),
    VariableSpec("issue_date", "Ngày cấp", "date"),
    VariableSpec("issue_date_text", "Ngày cấp (chữ)", "date_text"),
    VariableSpec("expiry_date", "Ngày hết hạn", "date"),
    VariableSpec("issue_place", "Nơi cấp", "enum"),
    VariableSpec("issue_place_short", "Nơi cấp (viết tắt)", "enum"),
    VariableSpec("gender", "Giới tính", "enum"),
)

# ------------------------------------------------------------------ contact (3)
_CONTACT: tuple[VariableSpec, ...] = (
    VariableSpec("phone", "Số điện thoại", "text"),
    VariableSpec("email", "Email", "text"),
    VariableSpec("address", "Địa chỉ", "text"),
)

# --------------------------------------------------------------------- bank (5)
_BANK: tuple[VariableSpec, ...] = (
    VariableSpec("bank_account", "Số tài khoản ngân hàng", "text"),
    VariableSpec("bank_name", "Tên ngân hàng", "text"),
    VariableSpec("bank_short_name", "Tên NH viết tắt", "text"),
    VariableSpec("branch", "Chi nhánh", "text"),
    VariableSpec("account_holder_name", "Chủ tài khoản", "text"),
)

# --------------------------------------------------------------- securities (1)
_SECURITIES: tuple[VariableSpec, ...] = (
    VariableSpec(
        "securities_account_no",
        "Số tài khoản chứng khoán",
        "securities_account",
        bold=True,
    ),
)

# ------------------------------------------------------------------- system (8)
_SYSTEM: tuple[VariableSpec, ...] = (
    VariableSpec("contract_no", "Số hợp đồng", "text"),
    VariableSpec("contract_date", "Ngày hợp đồng", "date"),
    VariableSpec("contract_date_text", "Ngày HĐ (chữ)", "date_text"),
    VariableSpec("today", "Ngày hiện tại", "date"),
    VariableSpec("day", "Ngày", "text"),
    VariableSpec("month", "Tháng", "text"),
    VariableSpec("year", "Năm", "text"),
    VariableSpec("created_by_name", "Người lập", "text"),
)

SYSTEM_VARIABLES: tuple[VariableSpec, ...] = _CARD + _CONTACT + _BANK + _SECURITIES + _SYSTEM
"""All 28 variables a template author may use without declaring anything."""

SYSTEM_VARIABLES_BY_KEY: dict[str, VariableSpec] = {v.key: v for v in SYSTEM_VARIABLES}

SYSTEM_VARIABLE_KEYS: frozenset[str] = frozenset(SYSTEM_VARIABLES_BY_KEY)

BOLD_VARIABLE_KEYS: frozenset[str] = frozenset(v.key for v in SYSTEM_VARIABLES if v.bold)
"""Keys that must be written `{{r key }}` in the `.docx` (§9.5, `COCAS-6008`)."""
