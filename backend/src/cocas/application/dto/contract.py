"""What `RenderContextBuilder` consumes and produces (§12.9), plus the
request/response pair of `GenerateContractUseCase` (§9.11).

⭐ `ContractDraft` carries **entities already loaded and already decrypted**.
The builder never touches a repository: §12.9 step 1 says "nạp bên · giải mã
PII", and that decryption happens inside the repository (§12.14), so by the
time a draft exists the plaintext is in hand. Keeping the builder pure is what
lets the template-preview endpoint (§9.10) reuse it with invented data.

⭐ `GenerateContractCommand`, by contrast, carries **ids only** — it is what
arrives from `POST /contracts` (§5.3.8), where the client knows nothing but
UUIDs. Resolving those to entities is the Use Case's first transaction.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.customer import Customer
from cocas.domain.enums.entity_type import EntityType
from cocas.domain.validation.report import ValidationReport

RenderContext = dict[str, object]
"""⭐ Primitives and `StyledValue` only — see `assert_render_safe` (§12.9).

Deliberately a plain `dict` rather than a wrapper class: it is handed to
Jinja2 as the template's global namespace, and pitfall #7 is precisely that
*anything with methods* in there is an SSTI foothold. A wrapper would be one
more object with methods.
"""


@dataclass(frozen=True, slots=True)
class PartyDraft:
    """One party's slot, resolved to entities (§4.4.11 `contract_party`)."""

    party_key: str
    customer: Customer
    bank_account: BankAccount | None = None
    party_extra: Mapping[str, object] = field(default_factory=dict)
    """`contract_party.party_extra` — values for the template's `extra_fields`
    (§4.5), e.g. `{"securities_account_no": "008C123456"}`."""


@dataclass(frozen=True, slots=True)
class ContractDraft:
    """Everything a contract needs to render, before any row is written."""

    contract_no: str
    created_by_name: str
    today: date
    parties: tuple[PartyDraft, ...]
    contract_date: date | None = None
    extra_variables: Mapping[str, object] = field(default_factory=dict)
    """`contract.extra_variables` — values for the template's `contract_fields`
    (§4.5), which belong to the contract rather than to any one party."""

    @property
    def primary(self) -> PartyDraft:
        """⭐ v1.0 always has exactly one party (`party_schema` pinned to
        `min = max = 1`, §4.5), so "the primary party" and "the only party"
        coincide — but the flattening rule in §9.6 step 3 is written in terms
        of the primary one, and that is the reading that survives a second
        party being added."""
        return self.parties[0]


@dataclass(frozen=True, slots=True)
class PartyRequest:
    """One party as `POST /contracts` states it — ids, not entities (§5.3.8)."""

    party_key: str
    customer_id: uuid.UUID
    party_index: int = 0
    entity_type: EntityType = EntityType.INDIVIDUAL
    bank_account_id: uuid.UUID | None = None
    ocr_session_id: uuid.UUID | None = None
    is_primary: bool = True
    party_extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerateContractCommand:
    """The input of `GenerateContractUseCase` (§5.3.8 request body)."""

    template_id: uuid.UUID
    parties: Sequence[PartyRequest]
    created_by: str
    """The Windows account name (P-11 — there is no application login)."""
    created_by_name: str = ""
    """Display name for `{{created_by_name}}`; falls back to `created_by`."""
    contract_date: date | None = None
    extra_variables: Mapping[str, object] = field(default_factory=dict)
    supersedes_id: uuid.UUID | None = None
    revision_no: int = 1


@dataclass(frozen=True, slots=True)
class GeneratedContract:
    """The output of a successful generation (§5.3.8 `201` body)."""

    contract_id: uuid.UUID
    contract_no: str
    export_name: str
    document_id: uuid.UUID
    vault_path: str
    file_sha256: bytes
    file_size_bytes: int
    generation_ms: int
    created_at: datetime
    warnings: ValidationReport = field(default_factory=ValidationReport)
    """⭐ 🟡 findings that did not block — `V-CTR-010` (expired card) is the
    only one in v1.0. They travel with the success response because the
    operator still needs to see them (§8.2)."""
