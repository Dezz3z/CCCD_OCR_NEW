"""The 10 `V-CTR-*` rules of §8.6 — the gate in front of contract generation.

⭐ **Nine of ten block.** That ratio is the opposite of the OCR set (§8.4:
9 of 23) and it is not an inconsistency. An OCR rule looks at a photograph and
guesses; blocking on a guess strands the operator with a customer in front of
them (P-08). A contract rule looks at facts the system itself established —
does the template have an active version, does the file on disk still hash to
what was registered, is this customer soft-deleted — and being wrong about any
of those produces a **legal document that is wrong**. The only 🟡 is
`V-CTR-010` (expired card), which is a judgement about the world, not about
the system's own state.

⭐ **Everything a rule needs arrives in the target.** Free disk space, whether
the template file exists, which required variables came out empty — all of it
is measured by the caller and passed in, never read here. Same reason
`RuleContext.today` is passed rather than read from a clock: a rule that
touches the filesystem is a rule whose tests depend on the machine they run
on, and a rule that cannot be pinned down cannot be trusted.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.entity_type import EntityType
from cocas.domain.services.card_validity_policy import (
    CardValidityPolicy,
    CardValidityStatus,
)
from cocas.domain.services.template_variables import SYSTEM_VARIABLES_BY_KEY
from cocas.domain.validation.report import Severity, ValidationIssue
from cocas.domain.validation.rule import FunctionRule, Rule, RuleContext

#: §V-CTR-008 — the floor §10.4.1 #10 sets for any write.
MIN_FREE_DISK_BYTES = 100 * 1024 * 1024

#: §4.5 — `collect` entries recognised in v1.0.
COLLECT_BANK_ACCOUNT = "bank_account"

_VALIDITY = CardValidityPolicy()


@dataclass(frozen=True, slots=True)
class PartyCandidate:
    """One proposed party, resolved from ids to entities by the Use Case."""

    party_key: str
    customer: Customer
    entity_type: EntityType = EntityType.INDIVIDUAL
    has_bank_account: bool = False


@dataclass(frozen=True, slots=True)
class ContractCandidate:
    """Everything §8.6 needs to answer "may this contract be generated?".

    ⚠️ `missing_required_variables` is computed by
    `RenderContextBuilder.missing_required_variables` and handed in, not
    recomputed: the render context is an Application concept, and it already
    knows to exclude `suppressed_variables` — a detail that, if re-derived
    here and got wrong, would block **every** contract for both real
    templates (both suppress `contract_date`, which is also required).
    """

    template: Template
    version: TemplateVersion | None = None
    parties: tuple[PartyCandidate, ...] = ()
    missing_required_variables: tuple[str, ...] = ()
    template_file_exists: bool = True
    template_checksum_matches: bool = True
    free_disk_bytes: int = MIN_FREE_DISK_BYTES

    def schema_for(self, party_key: str) -> Mapping[str, object] | None:
        for entry in self.template.party_schema:
            if entry.get("key") == party_key:
                return entry
        return None


# ---------------------------------------------------------------- the 10 rules


def _v_ctr_001(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """Template has an active, usable version."""
    if target.version is None:
        return (
            ValidationIssue(
                code="COCAS-6005",
                severity=Severity.ERROR,
                message_vi="Mẫu hợp đồng chưa có phiên bản đang kích hoạt.",
                hint="Quản trị viên cần đăng ký và kích hoạt một phiên bản mẫu.",
            ),
        )
    if not target.version.is_usable:
        return (
            ValidationIssue(
                code="COCAS-6005",
                severity=Severity.ERROR,
                message_vi=(
                    "Phiên bản mẫu đang kích hoạt đã bị lưu trữ hoặc không hợp lệ."
                ),
                hint="Quản trị viên cần kích hoạt một phiên bản mẫu khác.",
            ),
        )
    return ()


def _v_ctr_002(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """Template file is on disk and still hashes to what was registered."""
    if target.version is None:
        # V-CTR-001 already said so; saying it twice makes the user think
        # there are two problems.
        return ()
    if not target.template_file_exists:
        return (
            ValidationIssue(
                code="COCAS-6006",
                severity=Severity.ERROR,
                message_vi="Không tìm thấy file mẫu hợp đồng trên đĩa.",
                hint="Liên hệ quản trị viên để đăng ký lại mẫu.",
            ),
        )
    if not target.template_checksum_matches:
        return (
            ValidationIssue(
                code="COCAS-6007",
                severity=Severity.ERROR,
                message_vi="File mẫu hợp đồng đã bị thay đổi so với lúc đăng ký.",
                hint="Liên hệ quản trị viên để đăng ký lại mẫu.",
            ),
        )
    return ()


def _v_ctr_003(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ Every `required_variables` entry has a non-empty value (§9.8)."""
    return tuple(
        ValidationIssue(
            code="COCAS-7002",
            severity=Severity.ERROR,
            message_vi=f"Thiếu thông tin bắt buộc: '{_label_of(key)}'.",
            field=key,
            hint="Vui lòng bổ sung trường này rồi tạo lại hợp đồng.",
        )
        for key in target.missing_required_variables
    )


def _v_ctr_004(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """Party count matches each `party_schema` entry's `min`/`max` (§4.5)."""
    issues: list[ValidationIssue] = []
    counts: dict[str, int] = {}
    for party in target.parties:
        counts[party.party_key] = counts.get(party.party_key, 0) + 1

    for entry in target.template.party_schema:
        key = str(entry.get("key", ""))
        actual = counts.pop(key, 0)
        minimum = _as_int(entry.get("min"), 1)
        maximum = _as_int(entry.get("max"), 1)
        if minimum <= actual <= maximum:
            continue
        label = str(entry.get("label", key))
        issues.append(
            ValidationIssue(
                code="COCAS-7010",
                severity=Severity.ERROR,
                message_vi=(
                    f"Mẫu yêu cầu {_count_phrase(minimum, maximum)} '{label}', "
                    f"đang có {actual}."
                ),
                field=key,
            )
        )

    # ⚠️ Anything left in `counts` is a party the schema never declared. It
    # would otherwise pass silently: no schema entry means no min/max to
    # violate, and its data would be written to `contract_party` anyway.
    issues.extend(
        ValidationIssue(
            code="COCAS-7010",
            severity=Severity.ERROR,
            message_vi=f"Mẫu hợp đồng không khai báo bên '{key}'.",
            field=key,
        )
        for key in counts
    )
    return tuple(issues)


def _v_ctr_005(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """Each party's `entity_type` matches its declaration (§4.5)."""
    issues: list[ValidationIssue] = []
    for party in target.parties:
        entry = target.schema_for(party.party_key)
        if entry is None:
            continue  # V-CTR-004 reports the undeclared party.
        declared = str(entry.get("entity_type", EntityType.INDIVIDUAL.value))
        if declared == "ANY" or declared == party.entity_type.value:
            continue
        issues.append(
            ValidationIssue(
                code="COCAS-7011",
                severity=Severity.ERROR,
                message_vi=(
                    f"Bên '{entry.get('label', party.party_key)}' phải là "
                    f"'{declared}', đang là '{party.entity_type.value}'."
                ),
                field=party.party_key,
            )
        )
    return tuple(issues)


def _v_ctr_006(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """A party declaring `collect: bank_account` must have one (§4.5)."""
    issues: list[ValidationIssue] = []
    for party in target.parties:
        entry = target.schema_for(party.party_key)
        if entry is None:
            continue
        collect = entry.get("collect")
        wants_bank = isinstance(collect, Sequence) and COLLECT_BANK_ACCOUNT in collect
        if not wants_bank or party.has_bank_account:
            continue
        issues.append(
            ValidationIssue(
                code="COCAS-7012",
                severity=Severity.ERROR,
                message_vi=(
                    f"Bên '{entry.get('label', party.party_key)}' cần có tài khoản "
                    f"ngân hàng."
                ),
                field="bank_account_id",
                hint="Chọn hoặc thêm tài khoản ngân hàng cho khách hàng này.",
            )
        )
    return tuple(issues)


def _v_ctr_007(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """⭐ One subject may not hold two roles in the same contract."""
    seen: set[object] = set()
    duplicates: list[str] = []
    for party in target.parties:
        customer_id = party.customer.id
        if customer_id in seen:
            duplicates.append(str(party.customer.full_name))
        seen.add(customer_id)
    return tuple(
        ValidationIssue(
            code="COCAS-7013",
            severity=Severity.ERROR,
            message_vi=f"'{name}' không thể đóng hai vai trong cùng một hợp đồng.",
        )
        for name in duplicates
    )


def _v_ctr_008(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """At least 100 MB free before starting a write (§10.4.1 #10)."""
    if target.free_disk_bytes >= MIN_FREE_DISK_BYTES:
        return ()
    return (
        ValidationIssue(
            code="COCAS-8003",
            severity=Severity.ERROR,
            message_vi=(
                f"Không đủ dung lượng đĩa để tạo hợp đồng "
                f"(còn {target.free_disk_bytes // (1024 * 1024)} MB, "
                f"cần {MIN_FREE_DISK_BYTES // (1024 * 1024)} MB)."
            ),
            hint="Giải phóng dung lượng rồi thử lại.",
        ),
    )


def _v_ctr_009(target: ContractCandidate, _: RuleContext) -> Sequence[ValidationIssue]:
    """No party may be a soft-deleted customer."""
    return tuple(
        ValidationIssue(
            code="COCAS-5001",
            severity=Severity.ERROR,
            message_vi=f"Khách hàng '{party.customer.full_name}' đã bị xoá.",
            field=party.party_key,
        )
        for party in target.parties
        if party.customer.is_deleted
    )


def _v_ctr_010(
    target: ContractCandidate, context: RuleContext
) -> Sequence[ValidationIssue]:
    """🟡 A party's ID card has expired — suspicious, never blocking.

    The card in the drawer is the one the customer has. Refusing to write the
    contract does not renew it; it only means the contract does not get
    written (P-08).
    """
    issues: list[ValidationIssue] = []
    for party in target.parties:
        report = _VALIDITY.evaluate(
            party.customer.id_card_dates,
            party.customer.date_of_birth,
            context.today,
        )
        if report.status is not CardValidityStatus.CARD_EXPIRED:
            continue
        issues.append(
            ValidationIssue(
                code=report.status.value,
                severity=Severity.WARNING,
                message_vi=f"{party.customer.full_name}: {report.message_vi}",
                field=party.party_key,
            )
        )
    return tuple(issues)


CONTRACT_GENERATION_RULES: tuple[Rule[ContractCandidate], ...] = (
    FunctionRule("V-CTR-001", _v_ctr_001),
    FunctionRule("V-CTR-002", _v_ctr_002),
    FunctionRule("V-CTR-003", _v_ctr_003),
    FunctionRule("V-CTR-004", _v_ctr_004),
    FunctionRule("V-CTR-005", _v_ctr_005),
    FunctionRule("V-CTR-006", _v_ctr_006),
    FunctionRule("V-CTR-007", _v_ctr_007),
    FunctionRule("V-CTR-008", _v_ctr_008),
    FunctionRule("V-CTR-009", _v_ctr_009),
    FunctionRule("V-CTR-010", _v_ctr_010),
)


# ---------------------------------------------------------------- internals


def _label_of(key: str) -> str:
    spec = SYSTEM_VARIABLES_BY_KEY.get(key)
    return spec.label if spec is not None else key


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _count_phrase(minimum: int, maximum: int) -> str:
    return f"{minimum} bên" if minimum == maximum else f"{minimum}–{maximum} bên"
