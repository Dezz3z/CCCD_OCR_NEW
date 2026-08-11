"""Fake / null implementations of all 19 Ports.

⭐ Architecture acceptance criterion (§12.19): *"Mỗi Port phải có ít nhất một
hiện thực fake/null dùng trong test."* This module is where that criterion is
met. Every layer above Domain must be testable with these alone — if a test
needs a real database, a real OCR engine, or a real LibreOffice, that is a
signal the port boundary leaked.

These are deliberately dumb: they record calls and return canned values. Any
"clever" fake grows into a second implementation nobody trusts.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from types import TracebackType
from typing import Any

from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.ports.crypto import AadContext, BidxField
from cocas.domain.ports.documents import PdfResult, RenderResult
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    EngineInfo,
    ImageData,
    ImageQuality,
    MrzExtractionResult,
    OcrOptions,
    PreprocessedImageSet,
    PreprocessProfile,
    QrExtractionResult,
    RawFieldValue,
    RelativeBox,
    SideClassification,
    SideVerdict,
    TextRegion,
)
from cocas.domain.ports.persistence import AliasRecord, Page, Specification
from cocas.domain.ports.queue import JobSnapshot, JobTarget
from cocas.domain.ports.storage import VaultCategory, VaultRef

# ============================================================================
# Image stand-ins
# ============================================================================


class FakeImageData:
    """A pixel-free `ImageData` — Domain only ever asks for the dimensions."""

    def __init__(self, width: int = 1600, height: int = 1000) -> None:
        self._width = width
        self._height = height

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height


class FakePreprocessedImageSet:
    """All five variants are the same object — enough for every non-OCR test.

    Tracks which variants were touched so a test can assert the ⭐ lazy-build
    contract (§12.4): a channel must not materialize variants it never uses.
    """

    def __init__(
        self,
        image: ImageData | None = None,
        *,
        warp_succeeded: bool = True,
        quality: ImageQuality | None = None,
    ) -> None:
        self._image = image or FakeImageData()
        self._warp_succeeded = warp_succeeded
        self._quality = quality or ImageQuality(score=0.9)
        self.accessed: list[str] = []

    def _variant(self, name: str) -> ImageData:
        self.accessed.append(name)
        return self._image

    @property
    def v0(self) -> ImageData:
        return self._variant("v0")

    @property
    def v1(self) -> ImageData:
        return self._variant("v1")

    @property
    def v2(self) -> ImageData:
        return self._variant("v2")

    @property
    def v3(self) -> ImageData:
        return self._variant("v3")

    @property
    def v4(self) -> ImageData:
        return self._variant("v4")

    @property
    def transform_matrix(self) -> Sequence[Sequence[float]] | None:
        return None

    @property
    def warp_succeeded(self) -> bool:
        return self._warp_succeeded

    @property
    def quality(self) -> ImageQuality:
        return self._quality


# ============================================================================
# Ports 1–7 — OCR pipeline
# ============================================================================


class FakeOcrEngine:
    """Port 1+2 — returns a fixed script of regions (§12.2: *"Toàn bộ test tầng
    trên phải chạy được với `FakeOcrEngine` trả dữ liệu cố định"*).
    """

    def __init__(self, regions: list[TextRegion] | None = None) -> None:
        self.regions = regions if regions is not None else []
        self.warm_up_calls = 0
        self.is_ready = False

    def recognize(self, image: ImageData, options: OcrOptions) -> list[TextRegion]:
        return [r for r in self.regions if r.confidence >= options.min_confidence]

    def recognize_region(
        self, image: ImageData, bbox: RelativeBox, charset_hint: str | None
    ) -> TextRegion | None:
        return self.regions[0] if self.regions else None

    def warm_up(self) -> None:
        self.warm_up_calls += 1
        self.is_ready = True

    def get_info(self) -> EngineInfo:
        return EngineInfo(
            name="fake",
            version="1.0",
            languages=["vi"],
            is_ready=self.is_ready,
            model_path="<memory>",
        )


class NullOcrEngine(FakeOcrEngine):
    """Port 1 — the degraded-mode engine (P-08): always reads nothing.

    Standing in for `NullOcrAdapter`, used to prove the pipeline still
    completes (with empty fields) when the engine is dead.
    """

    def recognize(self, image: ImageData, options: OcrOptions) -> list[TextRegion]:
        return []

    def recognize_region(
        self, image: ImageData, bbox: RelativeBox, charset_hint: str | None
    ) -> TextRegion | None:
        return None


class FakeImagePreprocessor:
    """Port 3."""

    def __init__(self, image_set: PreprocessedImageSet | None = None) -> None:
        self._image_set = image_set or FakePreprocessedImageSet()
        self.calls: list[tuple[int, PreprocessProfile]] = []

    def prepare(
        self, image_bytes: bytes, exif_orientation: int | None, profile: PreprocessProfile
    ) -> PreprocessedImageSet:
        self.calls.append((len(image_bytes), profile))
        return self._image_set


class FakeCardSideClassifier:
    """Port 4."""

    def __init__(self, classification: SideClassification | None = None) -> None:
        self._classification = classification or SideClassification(
            front_index=0,
            back_index=1,
            confidence_a=0.95,
            confidence_b=0.93,
            swapped=False,
            verdict=SideVerdict.RESOLVED,
        )

    def classify(
        self,
        image_a: PreprocessedImageSet,
        image_b: PreprocessedImageSet,
        doc_type: DocumentTypeSpec,
    ) -> SideClassification:
        return self._classification


class FakeQrDecoder:
    """Port 5 — defaults to "no QR found", which must never be an error."""

    def __init__(self, result: QrExtractionResult | None = None) -> None:
        self._result = result or QrExtractionResult(available=False)

    def decode(self, image_set: PreprocessedImageSet) -> QrExtractionResult:
        return self._result


class FakeMrzReader:
    """Port 6 — defaults to "no MRZ found"."""

    def __init__(self, result: MrzExtractionResult | None = None) -> None:
        self._result = result or MrzExtractionResult(available=False)

    def read(
        self, image_set: PreprocessedImageSet, doc_type: DocumentTypeSpec
    ) -> MrzExtractionResult:
        return self._result


class FakeFieldExtractor:
    """Port 7.

    Returns the same fields for either side unless `by_side` is given — most
    tests only care that extraction happened, but the ones about lever 2 need
    the front and the back to differ.
    """

    def __init__(
        self,
        fields: dict[FieldKey, RawFieldValue] | None = None,
        by_side: dict[CardSide, dict[FieldKey, RawFieldValue]] | None = None,
    ) -> None:
        self._fields = fields or {}
        self._by_side = by_side
        self.calls: list[tuple[CardSide, str]] = []

    def extract(
        self,
        regions: list[TextRegion],
        side: CardSide,
        doc_type: DocumentTypeSpec,
        warp_succeeded: bool,
    ) -> dict[FieldKey, RawFieldValue]:
        self.calls.append((side, doc_type.code))
        if self._by_side is not None:
            return dict(self._by_side.get(side, {}))
        return dict(self._fields)


class FakeDocumentTypeSelector:
    """Port 19 — answers with a fixed choice, or None for "cannot tell"."""

    def __init__(self, choice: DocumentTypeSpec | None = None) -> None:
        self.choice = choice
        self.calls: list[int] = []

    def select(
        self, regions: list[TextRegion], candidates: Sequence[DocumentTypeSpec]
    ) -> DocumentTypeSpec | None:
        self.calls.append(len(regions))
        return self.choice


# ============================================================================
# Ports 8, 9, 10, 14 — persistence
# ============================================================================


class InMemoryRepository:
    """Ports 8+9 — a dict-backed repository.

    Entities are matched by their `id` attribute. `filters` are applied as
    plain equality on attribute names, which covers every query v1.0 makes
    of a fake.
    """

    def __init__(self, entities: list[Any] | None = None) -> None:
        self.items: dict[Any, Any] = {e.id: e for e in (entities or [])}
        self.added: list[Any] = []
        self.updated: list[tuple[Any, int | None]] = []

    async def get(self, entity_id: object) -> Any | None:
        return self.items.get(entity_id)

    def _matches(self, entity: Any, spec: Specification) -> bool:
        if not spec.include_deleted and getattr(entity, "deleted_at", None) is not None:
            return False
        return all(getattr(entity, key, None) == value for key, value in spec.filters.items())

    async def list(self, spec: Specification) -> Page[Any]:
        matched = [e for e in self.items.values() if self._matches(e, spec)]
        start = (spec.page - 1) * spec.page_size
        return Page(
            items=matched[start : start + spec.page_size],
            total=len(matched),
            page=spec.page,
            page_size=spec.page_size,
        )

    async def exists(self, spec: Specification) -> bool:
        return any(self._matches(e, spec) for e in self.items.values())

    async def add(self, entity: Any) -> None:
        self.items[entity.id] = entity
        self.added.append(entity)

    async def update(self, entity: Any, expected_version: int | None = None) -> None:
        self.items[entity.id] = entity
        self.updated.append((entity, expected_version))


class FakeAliasRepository:
    """Port 10."""

    def __init__(self, records: list[AliasRecord] | None = None) -> None:
        self.records = records or []

    async def find_by_alias(
        self, document_type_code: str, field_key: str, alias_normalized: str
    ) -> AliasRecord | None:
        for record in self.records:
            if record.field_key == field_key and record.alias_normalized == alias_normalized:
                return record
        return None

    async def list_active(
        self, document_type_code: str, field_key: str
    ) -> Sequence[AliasRecord]:
        return [r for r in self.records if r.field_key == field_key]


class FakeUnitOfWork:
    """Port 14 — records commit/rollback so tests can assert the ⭐ auto-rollback
    contract: leaving the `async with` block without committing must roll back.
    """

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.entered = False

    async def __aenter__(self) -> FakeUnitOfWork:
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


# ============================================================================
# Port 11 — storage
# ============================================================================


class InMemoryFileStorage:
    """Port 11 — stands in for `EncryptedFileVault`, keeping the UUID-filename
    and relative-path invariants so path handling stays exercised.
    """

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(self, data: bytes, category: VaultCategory) -> VaultRef:
        ref = VaultRef(
            category=category,
            relative_path=f"{category.value}/2026/08/09/{uuid.uuid4()}.enc",
        )
        self.files[ref.relative_path] = data
        return ref

    def load(self, ref: VaultRef) -> bytes:
        from cocas.domain.exceptions import VaultFileNotFoundError

        if ref.relative_path not in self.files:
            raise VaultFileNotFoundError(f"Không tìm thấy tệp: {ref.relative_path}")
        return self.files[ref.relative_path]

    def delete(self, ref: VaultRef) -> None:
        self.files.pop(ref.relative_path, None)

    def exists(self, ref: VaultRef) -> bool:
        return ref.relative_path in self.files


# ============================================================================
# Ports 12, 13 — documents
# ============================================================================


class FakeDocumentRenderer:
    """Port 12."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def render(
        self, template_path: str, context: dict[str, object], output_path: str
    ) -> RenderResult:
        self.calls.append((template_path, context, output_path))
        payload = repr(sorted(context.items())).encode()
        return RenderResult(
            output_path=output_path,
            sha256=hashlib.sha256(payload).digest(),
            size_bytes=len(payload),
            duration_ms=1,
        )


class NullPdfConverter:
    """Port 13 — the P-08 degraded path: PDF conversion unavailable.

    Always raises, so tests can prove a dead converter still leaves the user
    with a usable DOCX instead of failing the whole contract.
    """

    def convert(self, docx_path: str, output_dir: str, timeout_sec: int) -> PdfResult:
        from cocas.domain.exceptions import LibreOfficeUnavailableError

        raise LibreOfficeUnavailableError("Không có trình chuyển đổi PDF trong môi trường test.")


class FakePdfConverter:
    """Port 13 — the happy path."""

    def __init__(self, page_count: int = 2) -> None:
        self.page_count = page_count
        self.calls: list[str] = []

    def convert(self, docx_path: str, output_dir: str, timeout_sec: int) -> PdfResult:
        self.calls.append(docx_path)
        return PdfResult(
            output_path=f"{output_dir}/out.pdf",
            sha256=hashlib.sha256(docx_path.encode()).digest(),
            size_bytes=1024,
            page_count=self.page_count,
            duration_ms=1,
            generator_version="fake 1.0",
        )


# ============================================================================
# Port 15 — job queue
# ============================================================================


class InMemoryJobQueue:
    """Port 15 — records enqueued jobs without any polling loop.

    Note this fake does NOT model the `job` table; it only satisfies the port
    so callers can be tested. The real polling semantics are exercised against
    a real PostgreSQL in the integration suite.
    """

    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, JobSnapshot] = {}
        self.started = False

    async def enqueue(
        self,
        job_type: JobType,
        target: JobTarget | None = None,
        payload: dict[str, object] | None = None,
        priority: int = 100,
    ) -> uuid.UUID:
        job_id = uuid.uuid4()
        self.jobs[job_id] = JobSnapshot(
            id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            attempt_count=0,
            max_attempts=3,
            target=target,
            payload=payload or {},
        )
        return job_id

    async def cancel(self, job_id: uuid.UUID) -> bool:
        snapshot = self.jobs.get(job_id)
        if snapshot is None or snapshot.status.is_terminal:
            return False
        self.jobs[job_id] = JobSnapshot(
            id=snapshot.id,
            job_type=snapshot.job_type,
            status=JobStatus.CANCELLED,
            attempt_count=snapshot.attempt_count,
            max_attempts=snapshot.max_attempts,
            target=snapshot.target,
            payload=snapshot.payload,
        )
        return True

    async def get_status(self, job_id: uuid.UUID) -> JobSnapshot | None:
        return self.jobs.get(job_id)

    async def start(self) -> None:
        self.started = True

    async def stop(self, graceful_timeout: float) -> None:
        self.started = False


# ============================================================================
# Ports 16, 17 — system
# ============================================================================


class FrozenClock:
    """Port 16 — time stands still unless a test advances it."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.date()

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)


class SequentialIdGenerator:
    """Port 17 — deterministic ids, so assertions can name them."""

    def __init__(self) -> None:
        self.counter = 0

    def new_id(self) -> uuid.UUID:
        self.counter += 1
        return uuid.UUID(int=self.counter)


# ============================================================================
# Port 18 — crypto
# ============================================================================


class NullCryptoService:
    """Port 18 — reversible obfuscation, NOT encryption.

    ⚠️ Test/dev only. It still binds the AAD into the output so a test can
    prove the ⭐ cell-permutation defence (§12.17): a ciphertext decrypted
    with a different AAD must fail.
    """

    _PEPPER = b"test-pepper"

    def encrypt(self, plaintext: bytes, aad: AadContext) -> bytes:
        return b"\x01" + aad.as_bytes() + b"\x00" + plaintext

    def decrypt(self, ciphertext: bytes, aad: AadContext) -> bytes:
        from cocas.domain.exceptions import DecryptionError

        prefix = b"\x01" + aad.as_bytes() + b"\x00"
        if not ciphertext.startswith(prefix):
            raise DecryptionError("Giải mã thất bại: AAD không khớp.")
        return ciphertext[len(prefix) :]

    def blind_index(self, value: str, field: BidxField) -> bytes:
        digest = hashlib.sha256(self._PEPPER + field.value.encode() + value.encode())
        return digest.digest()[:16]
