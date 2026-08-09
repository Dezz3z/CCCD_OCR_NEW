"""OCR-pipeline ports and their data types (§7.3, §12.2, §12.4).

⭐ Ports 1–7 of the 18. These are the engine-replacement seam (P-03): the
whole OCR stack can be swapped by supplying different implementations, and
every port has a fake/null implementation used in tests.

`ImageData` and `PreprocessedImageSet` are declared as `Protocol`s rather
than concrete classes on purpose — the real objects are numpy-backed and
built by `OpenCvPreprocessor` (Infrastructure). Domain names the shape it
needs without ever importing numpy or cv2 (P-02).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey

# ============================================================================
# Data types
# ============================================================================


@dataclass(frozen=True, slots=True)
class RelativeBox:
    """A bounding box in relative (0..1) image coordinates.

    ⭐ Always relative, never pixels — so a box stays meaningful after the
    image is resized or warped, and the UI can draw it on any rendition.
    """

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True, slots=True)
class TextRegion:
    """One recognized piece of text and where it sits on the image."""

    bbox: RelativeBox
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class OcrOptions:
    """Per-call tuning for `IOcrEngine.recognize()`."""

    use_angle_cls: bool = True
    charset_hint: str | None = None
    min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class EngineInfo:
    """Identity and readiness of a concrete OCR engine."""

    name: str
    version: str
    languages: list[str]
    is_ready: bool
    model_path: str


@dataclass(frozen=True, slots=True)
class ImageQuality:
    """Quality assessment produced during preprocessing."""

    score: float
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PreprocessProfile:
    """Named preprocessing tuning profile (`default`, `low_light`, `high_glare`)."""

    name: str = "default"
    target_long_edge: int = 1600
    perspective_enabled: bool = True
    denoise_method: str = "bilateral"
    deglare_enabled: bool = False


@dataclass(frozen=True, slots=True)
class DocumentTypeSpec:
    """The `document_type` row driving extraction, as seen by the OCR pipeline.

    ⭐ Everything the pipeline needs to support a new document kind lives in
    this record (NFR-10): adding GPLX/Passport support is a new row, not new
    pipeline code.
    """

    code: str
    name: str
    field_schema: list[dict[str, object]]
    zone_map: dict[str, object]
    anchor_patterns: dict[str, object]
    has_qr: bool
    has_mrz: bool
    is_ocr_supported: bool
    expected_aspect_ratio: float


class SideVerdict(str, Enum):
    """Outcome of side classification (§7.3 `ICardSideClassifier`)."""

    RESOLVED = "RESOLVED"
    DUPLICATE_SIDE = "DUPLICATE_SIDE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class SideClassification:
    """Which of the two uploaded images is the front, and which is the back."""

    front_index: int
    back_index: int
    confidence_a: float
    confidence_b: float
    swapped: bool
    verdict: SideVerdict
    signals: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QrExtractionResult:
    """Outcome of the QR channel.

    ⭐ `layout_recognized=False` is the designed-in escape hatch: when the
    card's QR payload layout changes, the channel degrades to "no fields"
    instead of producing garbage (§7.3 `IQrDecoder`).
    """

    available: bool
    raw_payload: str | None = None
    fields: dict[FieldKey, str] = field(default_factory=dict)
    layout_recognized: bool = False
    attempts: int = 0


@dataclass(frozen=True, slots=True)
class MrzExtractionResult:
    """Outcome of the MRZ (TD1) channel — see `Td1MrzReader` (§7.4.4)."""

    available: bool
    raw_lines: list[str] = field(default_factory=list)
    fields: dict[FieldKey, str] = field(default_factory=dict)
    checksum_valid: bool | None = None
    corrections_applied: int = 0
    confidence: float = 0.0


class ExtractionStrategy(str, Enum):
    """How a field's text was located on the card (§7.3 `IFieldExtractor`)."""

    ZONE = "ZONE"
    ANCHOR = "ANCHOR"


@dataclass(frozen=True, slots=True)
class RawFieldValue:
    """A field's text as first located on the image, before normalization."""

    text: str
    confidence: float
    bbox: RelativeBox | None
    strategy: ExtractionStrategy


# ============================================================================
# Protocols for image objects (implemented by Infrastructure, numpy-backed)
# ============================================================================


class ImageData(Protocol):
    """An in-memory decoded image. Opaque to Domain — only its size matters here."""

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...


class PreprocessedImageSet(Protocol):
    """The 5 lazily-built preprocessing variants of one source image (§12.4).

    ⭐ Accessing `.v1`..`.v4` builds that variant on first use and caches it;
    `.v0` (re-encoded original) is always available and never modified.
    """

    @property
    def v0(self) -> ImageData: ...

    @property
    def v1(self) -> ImageData: ...

    @property
    def v2(self) -> ImageData: ...

    @property
    def v3(self) -> ImageData: ...

    @property
    def v4(self) -> ImageData: ...

    @property
    def transform_matrix(self) -> Sequence[Sequence[float]] | None: ...

    @property
    def warp_succeeded(self) -> bool: ...

    @property
    def quality(self) -> ImageQuality: ...


# ============================================================================
# Ports
# ============================================================================


@runtime_checkable
class IRegionRecognizer(Protocol):
    """⭐ Port 2 — narrow port: recognize text inside ONE region of an image.

    Split out from `IOcrEngine` per ISP so `Td1MrzReader` can depend on just
    this one method instead of the whole engine (§12.2).
    """

    def recognize_region(
        self, image: ImageData, bbox: RelativeBox, charset_hint: str | None
    ) -> TextRegion | None:
        """Recognize text within `bbox`, or None if nothing was read.

        ⚠️ `charset_hint` is a POST-PROCESSING hint only, never a decoding
        constraint — PaddleOCR cannot restrict its charset at decode time
        (CLAUDE.md pitfall #3).
        """
        ...


@runtime_checkable
class IOcrEngine(IRegionRecognizer, Protocol):
    """⭐ Port 1 — the engine-replacement seam (§12.2).

    Knows nothing about "full name" / "citizen id" / "issue place": it takes
    an image and returns text plus positions. That narrowness is what makes
    swapping PaddleOCR for anything else trivial.
    """

    def recognize(self, image: ImageData, options: OcrOptions) -> list[TextRegion]:
        """Recognize all text in the image, in reading order.

        ⭐ Never returns None — an unreadable image yields an empty list.
        Every `TextRegion.text` is Unicode NFC-normalized and every `bbox`
        is in relative 0..1 coordinates.

        Raises:
            OcrEngineUnavailableError: engine not reachable / not warmed up.
            OcrTimeoutError: recognition exceeded its time budget.
            ImageDecodeError: the image could not be decoded.
        """
        ...

    def warm_up(self) -> None:
        """Load models into memory. Must succeed before `recognize()` is called."""
        ...

    def get_info(self) -> EngineInfo:
        """Report engine identity and readiness."""
        ...


@runtime_checkable
class IImagePreprocessor(Protocol):
    """⭐ Port 3 — turn raw image bytes into the set of channel-tuned variants (§12.4)."""

    def prepare(
        self,
        image_bytes: bytes,
        exif_orientation: int | None,
        profile: PreprocessProfile,
    ) -> PreprocessedImageSet:
        """Build the (lazy) variant set for one image.

        Raises:
            ImageDecodeError: bytes are not a decodable image.
            ImageTooSmallError: the short edge is below the usable minimum.
        """
        ...


@runtime_checkable
class ICardSideClassifier(Protocol):
    """⭐ Port 4 — decide which uploaded image is the front and which the back (§7.3).

    Invariant: never returns `verdict=RESOLVED` when both images score below 0.60.
    """

    def classify(
        self,
        image_a: PreprocessedImageSet,
        image_b: PreprocessedImageSet,
        doc_type: DocumentTypeSpec,
    ) -> SideClassification: ...


@runtime_checkable
class IQrDecoder(Protocol):
    """⭐ Port 5 — locate and decode the card's QR code (§7.3).

    ⭐ Never raises: a missing or unreadable QR is a normal outcome, reported
    as `available=False`.
    """

    def decode(self, image_set: PreprocessedImageSet) -> QrExtractionResult: ...


@runtime_checkable
class IMrzReader(Protocol):
    """⭐ Port 6 — locate, read, and checksum-validate the TD1 MRZ block (§7.4.4).

    Like `IQrDecoder`, absence of a readable MRZ is reported, not raised.
    """

    def read(
        self,
        image_set: PreprocessedImageSet,
        doc_type: DocumentTypeSpec,
    ) -> MrzExtractionResult: ...


@runtime_checkable
class IFieldExtractor(Protocol):
    """⭐ Port 7 — map recognized text regions onto the 6 business fields (§7.3).

    Runs both the ZONE and ANCHOR strategies and keeps, per field, whichever
    produced the higher confidence.
    """

    def extract(
        self,
        regions: list[TextRegion],
        side: CardSide,
        doc_type: DocumentTypeSpec,
        warp_succeeded: bool,
    ) -> dict[FieldKey, RawFieldValue]: ...
