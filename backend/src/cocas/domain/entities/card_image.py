"""CardImage entity (§4.4.1 `card_image`)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cocas.domain.enums.card_side import CardSide
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.confidence_score import ConfidenceScore

MIN_EDGE_PX = 320
MAX_EDGE_PX = 12000
MAX_SIZE_BYTES = 10 * 1024 * 1024


@dataclass(slots=True)
class CardImage:
    """A single uploaded CCCD photo (front or back), stored in the Vault.

    ⭐ P-05 Data Minimization: `purge()` clears the file from disk (via
    `IFileStorage`) once no longer needed — this entity's `purged_at` marks
    that the row survives (for audit) but the bytes are gone.
    """

    id: uuid.UUID
    uploaded_by: str
    document_type_id: uuid.UUID
    side_hint: CardSide
    vault_path: str
    mime_type: str
    width_px: int
    height_px: int
    size_bytes: int
    sha256: bytes
    created_at: datetime
    side_resolved: CardSide | None = None
    side_confidence: ConfidenceScore | None = None
    exif_orientation: int | None = None
    quality_score: ConfidenceScore | None = None
    quality_flags: list[str] = field(default_factory=list)
    thumbnail_path: str | None = None
    purged_at: datetime | None = None
    purge_reason: str | None = None

    def __post_init__(self) -> None:
        if not (MIN_EDGE_PX <= self.width_px <= MAX_EDGE_PX):
            raise BusinessRuleViolation(
                f"Chiều rộng ảnh phải trong khoảng {MIN_EDGE_PX}-{MAX_EDGE_PX}px.",
                code="INVALID_IMAGE_WIDTH",
            )
        if not (MIN_EDGE_PX <= self.height_px <= MAX_EDGE_PX):
            raise BusinessRuleViolation(
                f"Chiều cao ảnh phải trong khoảng {MIN_EDGE_PX}-{MAX_EDGE_PX}px.",
                code="INVALID_IMAGE_HEIGHT",
            )
        if self.size_bytes > MAX_SIZE_BYTES:
            raise BusinessRuleViolation(
                f"Dung lượng ảnh không được vượt quá {MAX_SIZE_BYTES} byte.",
                code="IMAGE_TOO_LARGE",
            )

    @property
    def is_purged(self) -> bool:
        return self.purged_at is not None

    @property
    def resolved_side(self) -> CardSide:
        """The classifier's answer if available, else the upload-time hint."""
        return self.side_resolved if self.side_resolved is not None else self.side_hint

    def resolve_side(self, side: CardSide, confidence: ConfidenceScore) -> None:
        """Record the `ICardSideClassifier` outcome (S4)."""
        self.side_resolved = side
        self.side_confidence = confidence

    def purge(self, reason: str, now: datetime) -> None:
        if self.is_purged:
            raise BusinessRuleViolation("Ảnh đã được xoá trước đó.", code="ALREADY_PURGED")
        self.purged_at = now
        self.purge_reason = reason
