"""⭐ The §9.7 formatting table — one function per declared variable kind.

Lives in Domain for the same reason `template_variables.py` does: "how a
Vietnamese contract writes a date" is business vocabulary, and three callers
need it without importing each other — `RenderContextBuilder` (§12.9 step 6),
the template preview endpoint (§9.10) and the Wizard's field hints (P4).

⭐ **The golden rule of §9.7, enforced in exactly one place:** `None` always
becomes the empty string — never `"None"`, never `"null"`, never a leftover
`{{ variable }}`. Every classic template bug of this family is a value that
found a second path to `str()`. Here there is one path: `format_value`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

#: Grouping/decimal marks are Vietnamese: `1.500.000` and `12,50` — the
#: opposite of the C locale, which is why no `f"{x:,}"` appears below.
_THOUSANDS_SEP = "."
_DECIMAL_SEP = ","

_UNITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
_SCALES = ("", " nghìn", " triệu", " tỷ")


def format_date(value: date) -> str:
    """`08/08/2026` — §9.7 kind `date`."""
    return f"{value.day:02d}/{value.month:02d}/{value.year:04d}"


def format_date_text(value: date) -> str:
    """`ngày 08 tháng 08 năm 2026` — §9.7 kind `date_text`."""
    return f"ngày {value.day:02d} tháng {value.month:02d} năm {value.year:04d}"


def format_currency(value: int) -> str:
    """`1.500.000` — §9.7 kind `currency`."""
    return _group_thousands(abs(int(value)), negative=int(value) < 0)


def format_number(value: int) -> str:
    """`1234` — §9.7 kind `number`. ⚠️ Deliberately **not** grouped: this kind
    counts things (parties, copies, pages), and `2.000 bản` reads as a decimal
    to a Vietnamese reader. Grouping is `currency`'s job."""
    return str(int(value))


def format_decimal(value: float | Decimal) -> str:
    """`12,50` — §9.7 kind `decimal`, two places, Vietnamese decimal comma."""
    return f"{float(value):.2f}".replace(".", _DECIMAL_SEP)


def format_percent(value: float | Decimal) -> str:
    """`50%` — §9.7 kind `percent`. Trailing `,00` is dropped: a contract
    that says `50,00%` where it means `50%` looks machine-generated."""
    text = format_decimal(value)
    return f"{text.removesuffix(f'{_DECIMAL_SEP}00')}%"


def format_boolean(value: bool) -> str:
    """`Có` / `Không` — §9.7 kind `boolean`."""
    return "Có" if value else "Không"


def format_currency_text(value: int) -> str:
    """`Một triệu năm trăm nghìn đồng` — §9.7 kind `currency_text`.

    ⭐ Written out rather than pulled from a library because no pinned
    dependency reads Vietnamese (§11.7 lists 38 libraries; none does numbers
    to words), and because the four irregularities below are the whole
    difficulty — a generic engine would still need every one of them:

    | Rule | Example |
    |---|---|
    | `1` after a tens digit becomes `mốt` | 21 → hai mươi **mốt** |
    | `5` after a tens digit becomes `lăm` | 15 → mười **lăm** |
    | `4` after a tens digit may be `tư` | 24 → hai mươi **tư** |
    | a zero tens digit inside a group is `linh` | 105 → một trăm **linh** năm |
    """
    amount = int(value)
    if amount == 0:
        return "Không đồng"
    words = _spell_number(abs(amount))
    # Only the first word of the sentence is capitalised — with a sign in
    # front, that word is `Âm`, not the number.
    return f"Âm {words} đồng" if amount < 0 else f"{words.capitalize()} đồng"


def format_value(value: object, kind: str) -> str:
    """Format one value per §9.7. ⭐ `None` → `""` for every kind but `boolean`.

    An unknown `kind` falls back to `text` rather than raising: kinds arrive
    from a template's `contract_fields` declaration (§4.5), and a typo there
    must not be able to abort contract generation for a customer who is
    sitting at the desk (P-08).
    """
    if kind == "boolean":
        return format_boolean(bool(value))
    if value is None:
        return ""
    if isinstance(value, str) and not value.strip():
        return ""

    match kind:
        case "date" | "date_text" if isinstance(value, date):
            return format_date(value) if kind == "date" else format_date_text(value)
        case "number" if isinstance(value, int):
            return format_number(value)
        case "decimal" if isinstance(value, int | float | Decimal):
            return format_decimal(value)
        case "currency" if isinstance(value, int | float | Decimal):
            return format_currency(int(value))
        case "currency_text" if isinstance(value, int | float | Decimal):
            return format_currency_text(int(value))
        case "percent" if isinstance(value, int | float | Decimal):
            return format_percent(value)

    return str(value).strip()


# ---------------------------------------------------------------- internals


def _group_thousands(magnitude: int, *, negative: bool) -> str:
    digits = str(magnitude)
    groups = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    return ("-" if negative else "") + _THOUSANDS_SEP.join(reversed(groups))


def _spell_units_after_tens(tens: int, units: int) -> list[str]:
    """The four irregular readings, in the only place they occur."""
    if not units:
        return []
    if tens == 1:
        return ["lăm"] if units == 5 else [_UNITS[units]]
    irregular = {1: "mốt", 4: "tư", 5: "lăm"}
    return [irregular.get(units, _UNITS[units])]


def _spell_group(group: int, *, full: bool) -> str:
    """Spell a 0–999 group. `full` = a higher-order group precedes it, so the
    hundreds digit must be spoken even when it is zero (`một triệu không trăm
    linh năm`), which is exactly how amounts are read aloud in Vietnamese."""
    hundreds, remainder = divmod(group, 100)
    tens, units = divmod(remainder, 10)
    parts: list[str] = []

    if hundreds or full:
        parts.append(f"{_UNITS[hundreds]} trăm")

    if tens == 0:
        if units and parts:
            parts.append("linh")
        if units:
            parts.append(_UNITS[units])
        return " ".join(parts)

    parts.append("mười" if tens == 1 else f"{_UNITS[tens]} mươi")
    parts.extend(_spell_units_after_tens(tens, units))
    return " ".join(parts)


def _spell_number(magnitude: int) -> str:
    groups: list[int] = []
    while magnitude:
        magnitude, group = divmod(magnitude, 1000)
        groups.append(group)

    spoken: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            continue
        # ⭐ `full` only from the second group onwards — `một trăm linh năm`,
        # but `một triệu không trăm linh năm`.
        spoken.append(_spell_group(group, full=index < len(groups) - 1) + _SCALES[index % 4])
    return " ".join(spoken)
