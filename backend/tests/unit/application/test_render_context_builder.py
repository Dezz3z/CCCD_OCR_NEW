"""§9.6 / §12.9 — the eight context-building steps and their invariants."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from cocas.application.dto.contract import ContractDraft, PartyDraft
from cocas.application.render_context_builder import RenderContextBuilder, assert_render_safe
from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import NO_EXPIRY_TEXT, IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.styled_value import StyledValue
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
TODAY = date(2026, 8, 11)


def make_customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "created_by": "nvnghiep",
        "full_name": PersonName.from_raw("NGUYỄN VĂN AN"),
        "id_number": CitizenId.from_raw("001199012345"),
        "date_of_birth": date(1990, 5, 14),
        "issue_place": IssuePlace(CUC_CANH_SAT_QLHC_TTXH),
        "id_card_dates": IdCardDates(issue_date=date(2021, 8, 20), expiry_date=date(2030, 5, 14)),
        "phone": VietnamesePhone.from_raw("0912345678"),
        "email": EmailAddress.from_raw("an.nguyen@example.com"),
        "address": "123 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội",
        "data_quality": DataQuality.OCR_VERIFIED,
        "created_at": NOW,
        "gender": Gender.NAM,
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_bank(customer_id: uuid.UUID) -> BankAccount:
    return BankAccount(
        id=uuid.uuid4(),
        customer_id=customer_id,
        account_number=BankAccountNumber.from_raw("1234567890"),
        bank_name="Ngân hàng TMCP Ngoại thương Việt Nam",
        branch="Chi nhánh Hà Nội",
        created_at=NOW,
        bank_code="VCB",
    )


def make_template(**overrides: object) -> Template:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "code": "01A_GDKQ",
        "name": "Giao dịch ký quỹ",
        "party_schema": [
            {
                "key": "holder",
                "label": "Khách hàng",
                "entity_type": "INDIVIDUAL",
                "min": 1,
                "max": 1,
                "is_primary": True,
                "collect": ["contact"],
                "extra_fields": [
                    {
                        "key": "securities_account_no",
                        "label": "Số tài khoản chứng khoán",
                        "type": "securities_account",
                        "required": True,
                        "render_style": {"bold": True},
                    }
                ],
            }
        ],
        "contract_no_pattern": "01A-KQ-{yyyymm}-{seq:05d}",
        "export_name_pattern": "Mẫu 01A-GDKQ - {full_name}",
        "created_at": NOW,
        "suppressed_variables": ["contract_date", "contract_date_text", "day", "month", "year"],
    }
    return Template(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_draft(customer: Customer, **overrides: object) -> ContractDraft:
    defaults: dict[str, object] = {
        "contract_no": "01A-KQ-202608-00042",
        "created_by_name": "nvnghiep",
        "today": TODAY,
        "parties": (
            PartyDraft(
                "holder",
                customer,
                make_bank(customer.id),
                {"securities_account_no": "008C123456"},
            ),
        ),
    }
    return ContractDraft(**{**defaults, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def builder() -> RenderContextBuilder:
    return RenderContextBuilder()


class TestFlattening:
    """§9.6 step 3."""

    def test_primary_party_keys_appear_at_both_levels(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        holder = context["holder"]
        assert isinstance(holder, dict)
        assert context["full_name"] == holder["full_name"] == "NGUYỄN VĂN AN"

    def test_party_sub_dictionary_is_not_the_same_object_as_the_root(
        self, builder: RenderContextBuilder
    ) -> None:
        """⚠️ Step 8 writes into both; sharing one dict would make suppressing
        a root key silently suppress it inside every party too — and the day a
        second party arrives, suppressing one would suppress all."""
        context = builder.build(make_draft(make_customer()), make_template())
        holder = context["holder"]
        assert isinstance(holder, dict)
        assert holder is not context


class TestCardVariables:
    def test_id_number_is_also_offered_in_groups_of_four(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert context["id_number"] == "001199012345"
        assert context["id_number_spaced"] == "0011 9901 2345"

    def test_dates_render_in_both_numeric_and_spelled_form(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert context["dob"] == "14/05/1990"
        assert context["dob_text"] == "ngày 14 tháng 05 năm 1990"
        assert context["issue_date"] == "20/08/2021"

    def test_no_expiry_is_a_value_not_a_blank(self, builder: RenderContextBuilder) -> None:
        """⭐ `None` here means "the card does not expire", not "unreadable" —
        the same distinction the fusion stage makes (§7.6). Rendering "" would
        print a contract that says nothing about expiry at all."""
        customer = make_customer(
            date_of_birth=date(1950, 5, 14),
            id_card_dates=IdCardDates(issue_date=date(2021, 8, 20), expiry_date=None),
        )
        context = builder.build(make_draft(customer), make_template())
        assert context["expiry_date"] == NO_EXPIRY_TEXT

    @pytest.mark.parametrize(
        ("canonical", "short"),
        [(BO_CONG_AN, "BCA"), (CUC_CANH_SAT_QLHC_TTXH, "CỤC CS QLHC VỀ TTXH")],
    )
    def test_issue_place_has_an_abbreviated_twin(
        self, builder: RenderContextBuilder, canonical: str, short: str
    ) -> None:
        customer = make_customer(issue_place=IssuePlace(canonical))
        context = builder.build(make_draft(customer), make_template())
        assert context["issue_place"] == canonical
        assert context["issue_place_short"] == short

    def test_gender_renders_title_case_not_the_enum_name(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer(gender=Gender.NU)), make_template())
        assert context["gender"] == "Nữ"

    def test_unknown_gender_is_blank_rather_than_the_word_unknown(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(
            make_draft(make_customer(gender=Gender.UNKNOWN)), make_template()
        )
        assert context["gender"] == ""


class TestBankVariables:
    def test_present_account_fills_every_bank_key(self, builder: RenderContextBuilder) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert context["bank_account"] == "1234567890"
        assert context["bank_short_name"] == "VCB"
        assert context["branch"] == "Chi nhánh Hà Nội"

    def test_account_holder_defaults_to_the_customer(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert context["account_holder_name"] == "NGUYỄN VĂN AN"

    def test_missing_account_still_declares_every_key_as_empty(
        self, builder: RenderContextBuilder
    ) -> None:
        """⭐ A template referencing `{{bank_name}}` on a contract with no bank
        account must render nothing there — not `{{bank_name}}` (§9.8)."""
        customer = make_customer()
        draft = make_draft(customer, parties=(PartyDraft("holder", customer, None),))
        context = builder.build(draft, make_template())
        for key in ("bank_account", "bank_name", "bank_short_name", "branch"):
            assert context[key] == ""


class TestExtraFields:
    def test_declared_bold_extra_becomes_a_styled_value(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert context["securities_account_no"] == StyledValue("008C123456", bold=True)

    def test_declared_extra_is_also_visible_under_the_party_key(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        holder = context["holder"]
        assert isinstance(holder, dict)
        assert holder["securities_account_no"] == StyledValue("008C123456", bold=True)

    def test_undeclared_party_extra_is_dropped(self, builder: RenderContextBuilder) -> None:
        """⚠️ An undeclared value has no declared type, and guessing one is
        how a raw `date` reaches a document as `2026-08-11`."""
        customer = make_customer()
        draft = make_draft(
            customer,
            parties=(PartyDraft("holder", customer, None, {"secret_note": "xin chào"}),),
        )
        context = builder.build(draft, make_template())
        assert "secret_note" not in context

    def test_contract_level_extras_are_formatted_by_their_declared_type(
        self, builder: RenderContextBuilder
    ) -> None:
        template = make_template(
            contract_fields=[{"key": "deposit", "label": "Ký quỹ", "type": "currency"}]
        )
        draft = make_draft(make_customer(), extra_variables={"deposit": 1500000})
        context = builder.build(draft, template)
        assert context["deposit"] == "1.500.000"

    def test_empty_styled_value_stays_a_plain_string(
        self, builder: RenderContextBuilder
    ) -> None:
        """⭐ `StyledValue("")` would become an empty bold run — invisible in
        Word but a real change to the XML, which the golden-file test exists
        to catch (§9.18)."""
        customer = make_customer()
        draft = make_draft(customer, parties=(PartyDraft("holder", customer, None, {}),))
        context = builder.build(draft, make_template())
        assert context["securities_account_no"] == ""


class TestSystemVariablesAndSuppression:
    def test_contract_number_and_today_are_present(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert context["contract_no"] == "01A-KQ-202608-00042"
        assert context["today"] == "11/08/2026"
        assert context["created_by_name"] == "nvnghiep"

    def test_suppressed_variables_are_blank_even_when_a_value_exists(
        self, builder: RenderContextBuilder
    ) -> None:
        """⭐ §9.6 step 8 — the operator signs the date by hand."""
        draft = make_draft(make_customer(), contract_date=date(2026, 8, 11))
        context = builder.build(draft, make_template())
        for key in ("contract_date", "contract_date_text", "day", "month", "year"):
            assert context[key] == ""

    def test_without_suppression_the_same_values_do_render(
        self, builder: RenderContextBuilder
    ) -> None:
        draft = make_draft(make_customer(), contract_date=date(2026, 8, 11))
        context = builder.build(draft, make_template(suppressed_variables=[]))
        assert context["contract_date"] == "11/08/2026"
        assert context["contract_date_text"] == "ngày 11 tháng 08 năm 2026"
        assert (context["day"], context["month"], context["year"]) == ("11", "08", "2026")

    def test_suppression_reaches_inside_the_party_sub_dictionary(
        self, builder: RenderContextBuilder
    ) -> None:
        template = make_template(suppressed_variables=["full_name"])
        context = builder.build(make_draft(make_customer()), template)
        holder = context["holder"]
        assert isinstance(holder, dict)
        assert context["full_name"] == "" and holder["full_name"] == ""


class TestRenderSafety:
    """⭐ Pitfall #7 — the last line of SSTI defence (§12.9 postcondition)."""

    def test_a_real_context_passes(self, builder: RenderContextBuilder) -> None:
        assert_render_safe(builder.build(make_draft(make_customer()), make_template()))

    def test_an_entity_in_the_context_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Customer"):
            assert_render_safe({"customer": make_customer()})

    def test_a_nested_object_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="holder.card"):
            assert_render_safe({"holder": {"card": IssuePlace(BO_CONG_AN)}})

    def test_an_object_inside_a_list_is_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"parties\.\[1\]"):
            assert_render_safe({"parties": ["ok", object()]})

    def test_a_non_string_key_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="Khoá ngữ cảnh"):
            assert_render_safe({1: "value"})

    def test_styled_value_and_none_are_allowed(self) -> None:
        assert_render_safe({"a": StyledValue("x", bold=True), "b": None, "c": [1, 2.5, True]})

    def test_builder_never_emits_a_customer_entity(
        self, builder: RenderContextBuilder
    ) -> None:
        context = builder.build(make_draft(make_customer()), make_template())
        assert all(not hasattr(v, "__dict__") or isinstance(v, StyledValue)
                   for v in context.values() if not isinstance(v, dict | str))


class TestMissingRequiredVariables:
    def _version(self, required: list[str]) -> TemplateVersion:
        return TemplateVersion(
            id=uuid.uuid4(),
            template_id=uuid.uuid4(),
            version_no=1,
            file_path="templates/2026/01A.docx",
            file_sha256=b"\x00" * 32,
            file_size_bytes=1024,
            original_filename="01A.docx",
            declared_variables=["full_name", "contract_date"],
            required_variables=required,
            optional_variables=[],
            validation_status=TemplateValidationStatus.VALID,
            created_by="nvnghiep",
            created_at=NOW,
        )

    def test_a_filled_required_variable_is_not_reported(
        self, builder: RenderContextBuilder
    ) -> None:
        template = make_template()
        context = builder.build(make_draft(make_customer()), template)
        assert builder.missing_required_variables(
            context, self._version(["full_name"]), template
        ) == []

    def test_an_empty_required_variable_is_reported(
        self, builder: RenderContextBuilder
    ) -> None:
        template = make_template()
        customer = make_customer()
        draft = make_draft(customer, parties=(PartyDraft("holder", customer, None),))
        context = builder.build(draft, template)
        assert builder.missing_required_variables(
            context, self._version(["bank_account"]), template
        ) == ["bank_account"]

    def test_a_suppressed_required_variable_is_not_reported(
        self, builder: RenderContextBuilder
    ) -> None:
        """⚠️ `contract_date` is required *and* suppressed on both real
        templates. Reporting it would block every contract (§12.9.1)."""
        template = make_template()
        context = builder.build(make_draft(make_customer()), template)
        assert builder.missing_required_variables(
            context, self._version(["contract_date"]), template
        ) == []
