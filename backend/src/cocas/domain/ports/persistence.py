"""Repository & Unit-of-Work ports (§12.14) — ports 8, 9, 10, 14 of 18.

⭐ Read and write are deliberately separate protocols (ISP). The payoff is
concrete: `IActivityLogRepository` is read + `append()` with **no** `update`,
which makes the append-only invariant of `activity_log` (DB-08) a *type*
error rather than a code-review comment.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")
# Read returns T, write consumes it — variance differs, so the two protocols
# need their own type variables (the combined one below stays invariant).
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)
TItem_co = TypeVar("TItem_co", covariant=True)


@dataclass(frozen=True, slots=True)
class Specification:
    """A query description handed to `list()`/`exists()`.

    Deliberately a plain record rather than a combinator DSL — with the
    query shapes v1.0 actually has, a full specification algebra would be
    structure without a payer (P-10 Radical Simplicity).
    """

    filters: dict[str, object] = field(default_factory=dict)
    order_by: tuple[str, ...] = ()
    page: int = 1
    page_size: int = 50
    include_deleted: bool = False


@dataclass(frozen=True, slots=True)
class Page(Generic[TItem_co]):
    """One page of results plus the total count for the query."""

    items: Sequence[TItem_co]
    total: int
    page: int
    page_size: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total


@runtime_checkable
class IReadRepository(Protocol[T_co]):
    """⭐ Port 8 — read side of a repository.

    ⭐ Always returns Domain entities, never ORM models. PII decryption
    happens *inside* the repository, so callers never learn that anything
    was ever encrypted.
    """

    async def get(self, entity_id: object) -> T_co | None: ...

    async def list(self, spec: Specification) -> Page[T_co]: ...

    async def exists(self, spec: Specification) -> bool: ...


@runtime_checkable
class IWriteRepository(Protocol[T_contra]):
    """⭐ Port 9 — write side of a repository.

    ⭐ Must translate infrastructure exceptions into domain ones:
    `IntegrityError` → `DuplicateEntityError`, `OperationalError` →
    `DatabaseUnavailableError`. A raw driver exception reaching a Use Case
    is an architecture leak.
    """

    async def add(self, entity: T_contra) -> None: ...

    async def update(self, entity: T_contra, expected_version: int | None = None) -> None:
        """Persist changes.

        `expected_version` may only be supplied for entities implementing
        `IVersionedEntity` — in v1.0 that is `Contract` alone (DB-09).

        Raises:
            OptimisticLockError: `expected_version` ≠ the stored version.
        """
        ...


@runtime_checkable
class IReadWriteRepository(IReadRepository[T], IWriteRepository[T], Protocol[T]):
    """Convenience composition for the common case needing both sides."""


@runtime_checkable
class IAliasRepository(Protocol):
    """⭐ Port 10 — normalization aliases, cached (§12.5).

    Backs `IssuePlaceNormalizer`'s tier-2 (alias) and tier-4 (keyword)
    lookups. Kept as its own port rather than a generic repository because
    it is read-mostly with an in-memory cache and a very specific query.
    """

    async def find_by_alias(
        self, document_type_code: str, field_key: str, alias_normalized: str
    ) -> AliasRecord | None: ...

    async def list_active(self, document_type_code: str, field_key: str) -> Sequence[AliasRecord]: ...


@dataclass(frozen=True, slots=True)
class AliasRecord:
    """One `normalization_alias` row as the domain sees it (§4.4.14)."""

    id: object
    field_key: str
    canonical_value: str
    match_tier: int
    assigned_confidence: float
    alias_normalized: str | None = None
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OcrFieldSnapshot:
    """One `ocr_field` row (§4.4.4), ready to be written.

    ⭐ Why this exists instead of passing `ExtractionResult` straight to a
    repository: `ExtractionResult` is an **Application** DTO, and
    Infrastructure sits below Application in the layer contract. A repository
    importing it would invert the dependency — caught by `import-linter`, but
    the reason is older than the tool: the persistence layer would then have to
    change every time the pipeline's return shape did.

    So the Use Case translates, and this is the vocabulary it translates into.
    `id` is client-generated (DB-01) so the caller knows the key before the
    INSERT — which is what lets the AAD bind to the row's own id.
    """

    id: object
    field_key: str
    value: str | None
    """The value fusion settled on. Written to **both** `normalized_value_enc`
    and `final_value_enc`: they only diverge once a user edits the field, and
    that divergence is what §14.7's improvement loop measures."""
    raw_value: str | None
    source: str
    confidence: float
    needs_review: bool
    bbox: dict[str, float] | None = None
    candidates: tuple[dict[str, object], ...] = ()
    normalization_tier: int | None = None


@dataclass(frozen=True, slots=True)
class OcrResultSnapshot:
    """One `ocr_result` row plus its 6 `ocr_field` children (§4.4.3)."""

    id: object
    ocr_session_id: object
    qr_available: bool
    mrz_available: bool
    channel_summary: Mapping[str, str]
    validation_report: Mapping[str, object]
    fields: tuple[OcrFieldSnapshot, ...]
    qr_raw: str | None = None
    mrz_raw: str | None = None
    """⭐ Untouched channel payloads, stored encrypted. Optional because the
    pipeline's result deliberately does not carry them — they are raw PII whose
    only consumer is someone reproducing a bad read (§10.9 redacts them from
    every log). `None` stores NULL and changes nothing else."""
    mrz_checksum_valid: bool | None = None
    mrz_corrections_applied: int | None = None
    """⚠️ `None` and `0` are different facts: `None` means there was no MRZ to
    read, `0` means one was read and needed no repair. §7.5's repair rate
    divides by the second."""
    cross_check_flags: tuple[str, ...] = ()


@runtime_checkable
class IUnitOfWork(Protocol):
    """⭐ Port 14 — transaction boundary (§12.14).

    Invariants:
      - one Use Case = one UoW = one transaction;
      - ⭐ leaving the `async with` block without `commit()` rolls back;
      - ⭐ file operations stay OUTSIDE the transaction — write to a temp
        path, commit, then rename.
    """

    async def __aenter__(self) -> IUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
