"""`RenderContextBuilder` — the eight steps of §9.6 / §12.9.

⭐ **This module must never import `docxtpl`.** That is the whole reason
`StyledValue` exists (pitfall #4): Application decides *that* the securities
account number is bold, `DocxContextAdapter` decides *how* to say so to the
render library. `import-linter` enforces the ban; `assert_render_safe` below
enforces the stronger property it protects — that nothing with methods
reaches Jinja2 (pitfall #7, the last line of SSTI defence).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from cocas.application.dto.contract import ContractDraft, PartyDraft, RenderContext
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.services.template_variables import SYSTEM_VARIABLES_BY_KEY
from cocas.domain.services.value_formatter import (
    format_date,
    format_date_text,
    format_value,
)
from cocas.domain.value_objects.id_card_dates import NO_EXPIRY_TEXT
from cocas.domain.value_objects.issue_place import BO_CONG_AN
from cocas.domain.value_objects.styled_value import StyledValue

#: §9.5 — the abbreviated spelling of each canonical issuing authority. A
#: closed two-value domain, so a mapping rather than a rule.
_ISSUE_PLACE_SHORT = {
    BO_CONG_AN: "BCA",
    "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI": "CỤC CS QLHC VỀ TTXH",
}

#: §9.5 — `gender` renders as `Nam`/`Nữ`, not as the enum's `NAM`/`NỮ`.
_GENDER_LABELS = {"NAM": "Nam", "NỮ": "Nữ", "KHÁC": "Khác", "UNKNOWN": ""}

#: Types Jinja2 may safely be handed (§12.9 postcondition). `StyledValue` is
#: on the list because `DocxContextAdapter` replaces it before render time.
_SAFE_SCALARS = (str, int, float, bool, StyledValue)


class RenderContextBuilder:
    """Turn a `ContractDraft` into a dictionary of primitives (§12.9)."""

    def build(self, draft: ContractDraft, template: Template) -> RenderContext:
        """Run §9.6 steps 1–8 and return a render-safe context."""
        # Steps 1–2 — one sub-dictionary per party.
        parties: dict[str, RenderContext] = {
            party.party_key: self._party_values(party) for party in draft.parties
        }

        # Step 3 — ⭐ flatten the primary party to the root so a template may
        # write either `{{full_name}}` or `{{holder.full_name}}`.
        context: RenderContext = dict(parties[draft.primary.party_key])
        context.update(parties)

        # Step 4 — system variables.
        context.update(self._system_values(draft))

        # Step 5 — declared extras: contract-level first, then per-party, so a
        # party's own value wins for a key both happen to define.
        context.update(self._declared_extras(template.contract_fields, draft.extra_variables))
        for party in draft.parties:
            party_extras = self._declared_extras(
                _extra_field_specs(template.party_schema, party.party_key), party.party_extra
            )
            context.update(party_extras)
            parties[party.party_key].update(party_extras)

        # Steps 6–7 happen inside `_party_values` / `_declared_extras`, which
        # is why they are not separate passes: formatting a value twice is how
        # `1.500.000` becomes `1`.

        # Step 8 — ⭐ suppressed variables win over everything above.
        for key in template.suppressed_variables:
            context[key] = ""
            for values in parties.values():
                if key in values:
                    values[key] = ""

        assert_render_safe(context)
        return context

    def missing_required_variables(
        self, context: RenderContext, version: TemplateVersion, template: Template
    ) -> list[str]:
        """⭐ §9.8 — required variables with no value, for `COCAS-7002`.

        ⚠️ A variable listed in `suppressed_variables` is **not** reported:
        the empty string is what the operator asked for (`contract_date` is
        left blank to be filled in by hand), so calling it "missing" would
        make every contract un-generatable for the two real templates.
        """
        suppressed = set(template.suppressed_variables)
        return [
            key
            for key in version.required_variables
            if key not in suppressed and not str(context.get(key, "")).strip()
        ]

    # ------------------------------------------------------------------ steps

    def _party_values(self, party: PartyDraft) -> RenderContext:
        customer = party.customer
        dates = customer.id_card_dates
        issue_place = str(customer.issue_place)

        values: RenderContext = {
            "full_name": str(customer.full_name),
            "id_number": str(customer.id_number),
            "id_number_spaced": _group_of_four(str(customer.id_number)),
            "dob": format_date(customer.date_of_birth),
            "dob_text": format_date_text(customer.date_of_birth),
            "issue_date": format_date(dates.issue_date),
            "issue_date_text": format_date_text(dates.issue_date),
            # ⭐ `KHÔNG THỜI HẠN` is a *value*, not a missing one — the same
            # distinction the fusion stage makes (§7.6). Rendering "" here
            # would print a contract that says nothing about expiry.
            "expiry_date": (
                format_date(dates.expiry_date) if dates.expiry_date else NO_EXPIRY_TEXT
            ),
            "issue_place": issue_place,
            "issue_place_short": _ISSUE_PLACE_SHORT.get(issue_place, issue_place),
            "gender": _GENDER_LABELS.get(customer.gender.value, "") if customer.gender else "",
            "phone": str(customer.phone),
            "email": str(customer.email),
            "address": customer.address,
            "securities_account_no": _styled(
                str(customer.securities_account_no) if customer.securities_account_no else ""
            ),
        }
        values.update(self._bank_values(party))
        return values

    def _bank_values(self, party: PartyDraft) -> RenderContext:
        account = party.bank_account
        if account is None:
            return dict.fromkeys(
                ("bank_account", "bank_name", "bank_short_name", "branch",
                 "account_holder_name"),
                "",
            )
        return {
            "bank_account": str(account.account_number),
            "bank_name": account.bank_name,
            "bank_short_name": account.bank_code or "",
            "branch": account.branch,
            "account_holder_name": account.account_holder_name
            or str(party.customer.full_name),
        }

    def _system_values(self, draft: ContractDraft) -> RenderContext:
        contract_date = draft.contract_date
        return {
            "contract_no": draft.contract_no,
            "contract_date": format_date(contract_date) if contract_date else "",
            "contract_date_text": format_date_text(contract_date) if contract_date else "",
            "today": format_date(draft.today),
            "day": f"{contract_date.day:02d}" if contract_date else "",
            "month": f"{contract_date.month:02d}" if contract_date else "",
            "year": f"{contract_date.year:04d}" if contract_date else "",
            "created_by_name": draft.created_by_name,
        }

    def _declared_extras(
        self, specs: Sequence[Mapping[str, object]], values: Mapping[str, object]
    ) -> RenderContext:
        """Format each declared extra field per its own `type` (§4.5, §9.7).

        ⚠️ Only **declared** keys are emitted. A stray key in `party_extra`
        that no `extra_fields` entry names is dropped rather than passed
        through unformatted — an undeclared value has no declared type, and
        guessing one is how a raw `datetime.date` reaches a document as
        `2026-08-11`.
        """
        out: RenderContext = {}
        for spec in specs:
            key = str(spec.get("key", ""))
            if not key:
                continue
            kind = str(spec.get("type", "text"))
            text = format_value(values.get(key), kind)
            style = spec.get("render_style")
            bold = bool(style.get("bold")) if isinstance(style, Mapping) else False
            fallback = SYSTEM_VARIABLES_BY_KEY.get(key)
            out[key] = _styled(text) if bold or (fallback and fallback.bold) else text
        return out


def assert_render_safe(context: object, path: str = "") -> None:
    """⭐ §12.9 postcondition, checked rather than trusted (pitfall #7).

    Raises `TypeError` on anything that is not a primitive, a container of
    primitives, or a `StyledValue`. This is not defensive programming for its
    own sake: an ORM row placed in the context gives a template author
    `{{ customer.__class__ }}`, and every SSTI payload in §9.9.1 starts with
    exactly that kind of foothold.
    """
    if isinstance(context, dict):
        for key, value in context.items():
            if not isinstance(key, str):
                raise TypeError(f"Khoá ngữ cảnh phải là chuỗi: {path}{key!r}")
            assert_render_safe(value, f"{path}{key}.")
        return
    if isinstance(context, list | tuple):
        for index, value in enumerate(context):
            assert_render_safe(value, f"{path}[{index}].")
        return
    if context is None or isinstance(context, _SAFE_SCALARS):
        return
    raise TypeError(
        f"Ngữ cảnh render chỉ được chứa kiểu nguyên thuỷ và StyledValue — "
        f"{path.rstrip('.')} là {type(context).__name__}"
    )


# ---------------------------------------------------------------- internals


def _styled(text: str) -> StyledValue | str:
    """⭐ Empty stays a plain string. A `StyledValue("")` would become an empty
    bold `RichText` run — invisible in Word, but it changes the XML, and the
    golden-file test in §9.18 exists to notice exactly that kind of drift."""
    return StyledValue(text, bold=True) if text else ""


def _group_of_four(digits: str) -> str:
    """`001199012345` → `0011 9901 2345` (§9.5 `id_number_spaced`)."""
    return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def _extra_field_specs(
    party_schema: Sequence[Mapping[str, object]], party_key: str
) -> Sequence[Mapping[str, object]]:
    for party in party_schema:
        if party.get("key") == party_key:
            extras = party.get("extra_fields")
            if isinstance(extras, Sequence) and not isinstance(extras, str | bytes):
                return [spec for spec in extras if isinstance(spec, Mapping)]
    return ()
