"""Integration test for the generic (non-crypto) repository path — REAL PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.entities.card_image import CardImage
from cocas.domain.enums.card_side import CardSide
from cocas.domain.value_objects.confidence_score import ConfidenceScore
from cocas.infrastructure.persistence.models.document_type import DocumentTypeModel
from cocas.infrastructure.persistence.repositories.card_image_repository import (
    SqlAlchemyCardImageRepository,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 9, tzinfo=UTC)


@pytest_asyncio.fixture
async def document_type_id(pg_session: AsyncSession) -> uuid.UUID:
    """`card_image.document_type_id` is a real FK — needs a row to point at."""
    row = DocumentTypeModel(
        id=uuid.uuid4(),
        code="CCCD_CHIP",
        name="Căn cước công dân gắn chip",
        field_schema=[],
        zone_map={},
        anchor_patterns={},
        has_qr=True,
        has_mrz=True,
        is_ocr_supported=True,
        expected_aspect_ratio=1.585,
        created_at=NOW,
    )
    pg_session.add(row)
    await pg_session.flush()
    return row.id


@pytest_asyncio.fixture
async def repo(pg_session: AsyncSession) -> SqlAlchemyCardImageRepository:
    return SqlAlchemyCardImageRepository(pg_session)


def _make_card_image(document_type_id: uuid.UUID, **overrides: object) -> CardImage:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "uploaded_by": "phthang",
        "document_type_id": document_type_id,
        "side_hint": CardSide.FRONT,
        "vault_path": "card_image/2026/08/09/abc.enc",
        "mime_type": "image/jpeg",
        "width_px": 1600,
        "height_px": 1000,
        "size_bytes": 2_000_000,
        "sha256": bytes(range(32)),
        "created_at": NOW,
    }
    defaults.update(overrides)
    return CardImage(**defaults)  # type: ignore[arg-type]


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_add_then_get(
        self,
        pg_session: AsyncSession,
        repo: SqlAlchemyCardImageRepository,
        document_type_id: uuid.UUID,
    ) -> None:
        image = _make_card_image(document_type_id)
        await repo.add(image)
        await pg_session.commit()

        loaded = await repo.get(image.id)
        assert loaded is not None
        assert loaded.side_hint == CardSide.FRONT
        assert loaded.vault_path == image.vault_path
        assert loaded.sha256 == image.sha256

    @pytest.mark.asyncio
    async def test_update_persists_side_resolution(
        self,
        pg_session: AsyncSession,
        repo: SqlAlchemyCardImageRepository,
        document_type_id: uuid.UUID,
    ) -> None:
        image = _make_card_image(document_type_id, side_hint=CardSide.UNKNOWN)
        await repo.add(image)
        await pg_session.commit()

        image.resolve_side(CardSide.BACK, ConfidenceScore(0.91))
        await repo.update(image)
        await pg_session.commit()

        loaded = await repo.get(image.id)
        assert loaded is not None
        assert loaded.side_resolved == CardSide.BACK
        assert loaded.side_confidence is not None
        assert loaded.side_confidence.value == pytest.approx(0.91)

    @pytest.mark.asyncio
    async def test_purge_persists(
        self,
        pg_session: AsyncSession,
        repo: SqlAlchemyCardImageRepository,
        document_type_id: uuid.UUID,
    ) -> None:
        image = _make_card_image(document_type_id)
        await repo.add(image)
        await pg_session.commit()

        image.purge("RETENTION_POLICY", NOW)
        await repo.update(image)
        await pg_session.commit()

        loaded = await repo.get(image.id)
        assert loaded is not None
        assert loaded.is_purged is True
        assert loaded.purge_reason == "RETENTION_POLICY"


class TestConstraints:
    @pytest.mark.asyncio
    async def test_width_out_of_range_rejected_before_hitting_db(self) -> None:
        """The domain entity's own invariant fires first — never reaches SQL."""
        from cocas.domain.exceptions import BusinessRuleViolation

        with pytest.raises(BusinessRuleViolation):
            _make_card_image(uuid.uuid4(), width_px=100)
