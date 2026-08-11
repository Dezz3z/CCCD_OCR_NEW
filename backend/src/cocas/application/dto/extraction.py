"""What `ExtractionPipeline` hands back (§12.3), shaped for the body of §5.3.4.

⭐ These are plain data — no ORM rows, no port objects, no images. The pipeline
runs inside a background job and its result has to survive being written to
`ocr_result`/`ocr_field` and read back weeks later, so anything that cannot be
serialized has no business in here.

⚠️ `ExtractionResult` carries an `error_code`, not an exception. §12.3 makes
"never raises" an invariant of the pipeline: a stage that dies reports itself
through `status` + `error_code` and the job worker stays alive. Every consumer
should therefore branch on `status`, never on a `try`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.ports.ocr import RelativeBox
from cocas.domain.services.field_fusion_service import FusedField
from cocas.domain.validation.report import ValidationReport

ProgressCallback = Callable[[int, str], None]
"""Called `(percent, message_vi)` at least once per stage (§12.3, §5.3.5).

Synchronous and expected to be cheap — the pipeline calls it while holding no
lock and does not await it. A caller that needs to persist progress should
queue the write, not perform it here.
"""


def noop_progress(percent: int, message_vi: str) -> None:
    """Default callback — a pipeline run with nobody watching is still valid."""


# ⭐ The five statuses S3–S11 can produce. The other six members of
# `OcrSessionStatus` (CREATED, QUEUED, PROCESSING, CONFIRMED, CONSUMED,
# CANCELLED) belong to the session's lifecycle around the pipeline, not to the
# pipeline itself, and `ExtractionResult` rejects them in `__post_init__` so a
# use case can never mistake one layer's vocabulary for the other's.
PIPELINE_STATUSES: frozenset[OcrSessionStatus] = frozenset(
    {
        OcrSessionStatus.COMPLETED,
        OcrSessionStatus.COMPLETED_WITH_WARNINGS,
        OcrSessionStatus.NEEDS_REUPLOAD,
        OcrSessionStatus.NEEDS_MANUAL_ASSIGN,
        OcrSessionStatus.FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class CandidateTrace:
    """One channel's offer for a field, kept for the "candidates" list of §5.3.4.

    ⭐ Retained even for the channels that lost. It is what lets the UI explain
    *why* a field is uncertain ("QR says X, OCR says Y") instead of only showing
    a low number, and it is the raw material for §14.7's alias-suggestion loop.
    """

    source: FieldSource
    confidence: float
    agrees: bool
    """This candidate's value equals the one that won."""


@dataclass(frozen=True, slots=True)
class ExtractedField:
    """A fused field plus the provenance `ocr_field` (§4.4.4) stores alongside it.

    Composition rather than more attributes on `FusedField`: fusion's invariants
    (`value is None ⇒ confidence == 0`) are Domain's and stay there, while bbox,
    raw text and match tier are trace data that only exists because a *pipeline*
    ran.
    """

    fused: FusedField
    raw_value: str | None = None
    """What the text channel read before normalization — `None` when no text
    channel contributed, which is the normal case for a QR-sourced field."""
    bbox: RelativeBox | None = None
    normalization_tier: int | None = None
    """`issue_place` only (§12.5) — which of the 5 tiers matched."""
    candidates: tuple[CandidateTrace, ...] = ()

    @property
    def value(self) -> str | None:
        return self.fused.value

    @property
    def confidence(self) -> float:
        return self.fused.confidence

    @property
    def source(self) -> FieldSource:
        return self.fused.source

    @property
    def needs_review(self) -> bool:
        return self.fused.needs_review

    @property
    def flags(self) -> tuple[str, ...]:
        return self.fused.flags


EMPTY_FUSED = FusedField(
    value=None, confidence=0.0, source=FieldSource.NONE, needs_review=True
)


@dataclass(frozen=True, slots=True)
class ChannelSummary:
    """Per-channel outcome, as `channels` in §5.3.4.

    Aggregated across both images: "the QR channel worked" is a fact about the
    card, and the caller already knows which side carries the QR from
    `document_type`.
    """

    qr_available: bool = False
    qr_layout_recognized: bool = False
    qr_attempts: int = 0
    mrz_available: bool = False
    mrz_checksum_valid: bool | None = None
    mrz_corrections_applied: int = 0
    ocr_available: bool = False
    ocr_regions_detected: int = 0
    text_passes: int = 0
    """⭐ How many whole-card recognition passes were actually paid for — 0, 1
    or 2. The number the p95 budget lives or dies by (§7.4.6 finding 20), so it
    is reported rather than inferred."""

    @property
    def any_channel_worked(self) -> bool:
        return self.qr_available or self.mrz_available or self.ocr_available


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One thing worth telling the user or the log about how the run went.

    Separate from `ValidationReport`: validation judges the *card*, diagnostics
    describe the *run*. "The engine timed out on the back image" is not a
    property of anyone's identity document.
    """

    stage: str
    code: str
    message_vi: str
    side: CardSide | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """The whole outcome of one S3→S11 run (§12.3).

    Invariants, all enforced below:

    * `status` is one of `PIPELINE_STATUSES`
    * `fields` has all 6 `FieldKey` members — a field nobody read is present
      with `value=None`, never absent
    * `error_code` is set if and only if `status is FAILED`
    """

    status: OcrSessionStatus
    fields: Mapping[FieldKey, ExtractedField]
    channel_summary: ChannelSummary = field(default_factory=ChannelSummary)
    validation_report: ValidationReport = field(default_factory=ValidationReport)
    diagnostics: tuple[Diagnostic, ...] = ()
    overall_confidence: float = 0.0
    auto_swapped: bool = False
    duration_ms: int = 0
    error_code: str | None = None
    card_generation: str | None = None
    """`document_type.code` the run settled on — it can differ from the one
    passed in, because the two generations are told apart from the text
    recognized at S7 (§7.4.7)."""
    detected_sides: Mapping[int, CardSide] = field(default_factory=dict)
    """Which uploaded image (0 or 1) was judged which side — what the
    `NEEDS_REUPLOAD` body of §5.3.4 shows as `detected_sides`."""

    def __post_init__(self) -> None:
        if self.status not in PIPELINE_STATUSES:
            raise ValueError(f"{self.status.value} is not a status the pipeline can produce")
        missing = [key.value for key in FieldKey if key not in self.fields]
        if missing:
            raise ValueError(f"ExtractionResult is missing field keys: {missing}")
        if (self.error_code is not None) != (self.status is OcrSessionStatus.FAILED):
            raise ValueError("error_code must be set exactly when status is FAILED")

    def value(self, key: FieldKey) -> str | None:
        return self.fields[key].value

    @property
    def fields_read(self) -> int:
        return sum(1 for extracted in self.fields.values() if extracted.value is not None)


def empty_fields() -> dict[FieldKey, ExtractedField]:
    """All 6 keys, nothing read — the shape every failure path returns."""
    return {key: ExtractedField(fused=EMPTY_FUSED) for key in FieldKey}
