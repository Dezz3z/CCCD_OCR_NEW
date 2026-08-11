"""P3 module 2 against **real PostgreSQL** — alias / document type / OCR result.

⭐ These three repositories are exactly where a unit test cannot help, because
everything that can go wrong here is something only the database enforces:

* the `ck_ocr_field__tier_range` CHECK, which was still `1..4` for a day after
  tier 5 shipped (finding #36). Tier 5 is written here on purpose;
* `uq_ocr_field__result_key` — one row per field per result;
* JSONB round-tripping of `zone_map` / `identity_markers` / `candidates`;
* that `ocr_field` values arrive as unreadable binary, not text (DB-06).

Gated on `COCAS_TEST_DATABASE_URL` like every other integration test — see
`conftest.py`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cocas.domain.ports.crypto import AadContext
from cocas.domain.ports.persistence import OcrFieldSnapshot, OcrResultSnapshot
from cocas.infrastructure.persistence.models.card_image import CardImageModel
from cocas.infrastructure.persistence.models.document_type import DocumentTypeModel
from cocas.infrastructure.persistence.models.normalization_alias import NormalizationAliasModel
from cocas.infrastructure.persistence.models.ocr_session import OcrSessionModel
from cocas.infrastructure.persistence.repositories.alias_repository import (
    SqlAlchemyAliasRepository,
)
from cocas.infrastructure.persistence.repositories.document_type_repository import (
    SqlAlchemyDocumentTypeRepository,
)
from cocas.infrastructure.persistence.repositories.ocr_result_repository import (
    SqlAlchemyOcrResultRepository,
)
from tests.fixtures.fake_ports import NullCryptoService

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def seeded(pg_session: AsyncSession) -> dict[str, uuid.UUID]:
    """Two card generations, three aliases, one session ready to receive a result."""
    chip = DocumentTypeModel(
        id=uuid.uuid4(),
        code="CCCD_CHIP",
        name="Căn cước công dân gắn chip",
        field_schema=[{"key": "id_number"}],
        zone_map={"front": {"id_number": [0.1, 0.2, 0.5, 0.06]}},
        anchor_patterns={"id_number": ["Số"]},
        identity_markers=["CĂN CƯỚC CÔNG DÂN", "Quê quán"],
        has_qr=True,
        has_mrz=True,
        is_ocr_supported=True,
        expected_aspect_ratio=1.58,
        is_active=True,
        created_at=NOW,
    )
    can_cuoc = DocumentTypeModel(
        id=uuid.uuid4(),
        code="CAN_CUOC_2024",
        name="Căn cước 2024",
        field_schema=[],
        zone_map={},
        anchor_patterns={},
        identity_markers=["Số định danh cá nhân"],
        has_qr=True,
        has_mrz=True,
        is_ocr_supported=True,
        expected_aspect_ratio=1.58,
        is_active=True,
        created_at=NOW,
    )
    retired = DocumentTypeModel(
        id=uuid.uuid4(),
        code="CMND_9",
        name="CMND 9 số",
        field_schema=[],
        zone_map={},
        anchor_patterns={},
        identity_markers=[],
        has_qr=False,
        has_mrz=False,
        is_ocr_supported=False,
        expected_aspect_ratio=1.58,
        is_active=True,
        created_at=NOW,
    )
    pg_session.add_all([chip, can_cuoc, retired])

    pg_session.add_all(
        [
            NormalizationAliasModel(
                id=uuid.uuid4(),
                document_type_id=chip.id,
                field_key="issue_place",
                alias_normalized="BO CONG AN",
                canonical_value="BỘ CÔNG AN",
                match_tier=2,
                keywords=None,
                assigned_confidence=0.95,
                is_active=True,
                created_at=NOW,
            ),
            NormalizationAliasModel(
                id=uuid.uuid4(),
                document_type_id=chip.id,
                field_key="issue_place",
                alias_normalized=None,
                canonical_value="CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
                match_tier=4,
                keywords=["CUC", "CANH", "SAT"],
                assigned_confidence=0.85,
                is_active=True,
                created_at=NOW,
            ),
            NormalizationAliasModel(
                id=uuid.uuid4(),
                document_type_id=chip.id,
                field_key="issue_place",
                alias_normalized="BCA CU",
                canonical_value="BỘ CÔNG AN",
                match_tier=2,
                keywords=None,
                assigned_confidence=0.9,
                is_active=False,
                created_at=NOW,
            ),
        ]
    )

    front = CardImageModel(
        id=uuid.uuid4(),
        file_path="vault/front.enc",
        file_sha256=b"\x01" * 32,
        file_size_bytes=1000,
        mime_type="image/jpeg",
        width=1000,
        height=640,
        uploaded_by="nvnghiep",
        created_at=NOW,
    )
    back = CardImageModel(
        id=uuid.uuid4(),
        file_path="vault/back.enc",
        file_sha256=b"\x02" * 32,
        file_size_bytes=1000,
        mime_type="image/jpeg",
        width=1000,
        height=640,
        uploaded_by="nvnghiep",
        created_at=NOW,
    )
    pg_session.add_all([front, back])

    session_id = uuid.uuid4()
    pg_session.add(
        OcrSessionModel(
            id=session_id,
            created_by="nvnghiep",
            document_type_id=chip.id,
            front_image_id=front.id,
            back_image_id=back.id,
            correlation_id="corr-1",
            status="PROCESSING",
            party_key="holder",
            party_index=0,
            auto_swapped=False,
            diagnostics={},
            created_at=NOW,
        )
    )
    await pg_session.commit()
    return {"chip": chip.id, "session": session_id}


def _snapshot(session_id: uuid.UUID) -> OcrResultSnapshot:
    return OcrResultSnapshot(
        id=uuid.uuid4(),
        ocr_session_id=session_id,
        qr_available=True,
        mrz_available=True,
        qr_raw="001199012345|NGUYỄN VĂN AN|13031987",
        mrz_raw="IDVNM0011990123454<<<<<<<<<<<<<",
        mrz_checksum_valid=True,
        mrz_corrections_applied=0,
        channel_summary={"qr_available": "True", "card_generation": "CCCD_CHIP"},
        validation_report={"is_valid": True, "issues": []},
        cross_check_flags=("SOURCE_CONFLICT",),
        fields=(
            OcrFieldSnapshot(
                id=uuid.uuid4(),
                field_key="id_number",
                value="001199012345",
                raw_value="001199012345",
                source="QR",
                confidence=0.99,
                needs_review=False,
                bbox={"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05},
                candidates=({"source": "QR", "confidence": 0.99, "agrees": True},),
            ),
            OcrFieldSnapshot(
                id=uuid.uuid4(),
                field_key="issue_place",
                value="BỘ CÔNG AN",
                raw_value="BO CONG AN",
                source="OCR",
                confidence=0.92,
                needs_review=False,
                # ⭐ Tier 5 — the value the old CHECK constraint rejected.
                normalization_tier=5,
            ),
            OcrFieldSnapshot(
                id=uuid.uuid4(),
                field_key="full_name",
                value=None,
                raw_value=None,
                source="NONE",
                confidence=0.0,
                needs_review=True,
            ),
        ),
    )


class TestAliasRepository:
    @pytest.mark.asyncio
    async def test_lists_only_active_rows_for_this_type_and_field(
        self, pg_session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, uuid.UUID]
    ) -> None:
        repo = SqlAlchemyAliasRepository(pg_session_factory)
        records = await repo.list_active("CCCD_CHIP", "issue_place")
        assert len(records) == 2
        assert {r.canonical_value for r in records} == {
            "BỘ CÔNG AN",
            "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
        }

    @pytest.mark.asyncio
    async def test_keywords_survive_the_jsonb_round_trip(
        self, pg_session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, uuid.UUID]
    ) -> None:
        repo = SqlAlchemyAliasRepository(pg_session_factory)
        records = await repo.list_active("CCCD_CHIP", "issue_place")
        tier4 = next(r for r in records if r.match_tier == 4)
        assert tier4.keywords == ("CUC", "CANH", "SAT")
        assert tier4.alias_normalized is None

    @pytest.mark.asyncio
    async def test_find_by_alias_matches_the_exact_row(
        self, pg_session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, uuid.UUID]
    ) -> None:
        repo = SqlAlchemyAliasRepository(pg_session_factory)
        found = await repo.find_by_alias("CCCD_CHIP", "issue_place", "BO CONG AN")
        assert found is not None
        assert found.canonical_value == "BỘ CÔNG AN"

    @pytest.mark.asyncio
    async def test_another_document_type_sees_none_of_these_rows(
        self, pg_session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, uuid.UUID]
    ) -> None:
        """The join is on `document_type.code`, not a coincidence of field names."""
        repo = SqlAlchemyAliasRepository(pg_session_factory)
        assert await repo.list_active("CAN_CUOC_2024", "issue_place") == ()


class TestDocumentTypeRepository:
    @pytest.mark.asyncio
    async def test_returns_only_extractable_types(
        self, pg_session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, uuid.UUID]
    ) -> None:
        """⚠️ `is_ocr_supported = false` must never reach the pipeline."""
        repo = SqlAlchemyDocumentTypeRepository(pg_session_factory)
        codes = [spec.code for spec in await repo.list_extractable()]
        assert "CMND_9" not in codes
        assert set(codes) == {"CCCD_CHIP", "CAN_CUOC_2024"}

    @pytest.mark.asyncio
    async def test_zone_map_and_markers_survive_jsonb(
        self, pg_session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, uuid.UUID]
    ) -> None:
        repo = SqlAlchemyDocumentTypeRepository(pg_session_factory)
        chip = await repo.get_by_code("CCCD_CHIP")
        assert chip is not None
        assert chip.zone_map == {"front": {"id_number": [0.1, 0.2, 0.5, 0.06]}}
        assert chip.identity_markers == ("CĂN CƯỚC CÔNG DÂN", "Quê quán")


class TestOcrResultRepository:
    @pytest.mark.asyncio
    async def test_writes_result_and_fields(
        self, pg_session: AsyncSession, seeded: dict[str, uuid.UUID]
    ) -> None:
        repo = SqlAlchemyOcrResultRepository(pg_session, NullCryptoService())
        snapshot = _snapshot(seeded["session"])
        await repo.add(snapshot)
        await pg_session.commit()

        count = await pg_session.execute(
            text("SELECT count(*) FROM ocr_field WHERE ocr_result_id = :rid"),
            {"rid": snapshot.id},
        )
        assert count.scalar_one() == 3

    @pytest.mark.asyncio
    async def test_tier_five_is_accepted_by_the_check_constraint(
        self, pg_session: AsyncSession, seeded: dict[str, uuid.UUID]
    ) -> None:
        """🔴 Finding #36 — this INSERT is what the old `1..4` bound rejected."""
        repo = SqlAlchemyOcrResultRepository(pg_session, NullCryptoService())
        snapshot = _snapshot(seeded["session"])
        await repo.add(snapshot)
        await pg_session.commit()

        tier = await pg_session.execute(
            text(
                "SELECT normalization_tier FROM ocr_field "
                "WHERE ocr_result_id = :rid AND field_key = 'issue_place'"
            ),
            {"rid": snapshot.id},
        )
        assert tier.scalar_one() == 5

    @pytest.mark.asyncio
    async def test_values_are_stored_encrypted_not_as_text(
        self, pg_session: AsyncSession, seeded: dict[str, uuid.UUID]
    ) -> None:
        """DB-06 — reading the raw column must not reveal the citizen number."""
        crypto = NullCryptoService()
        repo = SqlAlchemyOcrResultRepository(pg_session, crypto)
        snapshot = _snapshot(seeded["session"])
        await repo.add(snapshot)
        await pg_session.commit()

        field_id = snapshot.fields[0].id
        row = await pg_session.execute(
            text("SELECT final_value_enc FROM ocr_field WHERE id = :fid"), {"fid": field_id}
        )
        stored = row.scalar_one()
        assert isinstance(stored, bytes | memoryview)
        assert b"001199012345" not in bytes(stored)
        # …and it is the *right* ciphertext for this exact cell.
        plain = crypto.decrypt(
            bytes(stored),
            AadContext(
                entity_id=str(field_id),
                table_name="ocr_field",
                column_name="final_value_enc",
            ),
        )
        assert plain.decode() == "001199012345"

    @pytest.mark.asyncio
    async def test_a_field_nobody_read_is_stored_as_null(
        self, pg_session: AsyncSession, seeded: dict[str, uuid.UUID]
    ) -> None:
        repo = SqlAlchemyOcrResultRepository(pg_session, NullCryptoService())
        snapshot = _snapshot(seeded["session"])
        await repo.add(snapshot)
        await pg_session.commit()

        row = await pg_session.execute(
            text(
                "SELECT final_value_enc, needs_review FROM ocr_field "
                "WHERE ocr_result_id = :rid AND field_key = 'full_name'"
            ),
            {"rid": snapshot.id},
        )
        value, needs_review = row.one()
        assert value is None
        assert needs_review is True

    @pytest.mark.asyncio
    async def test_second_result_for_the_same_session_is_rejected(
        self, pg_session: AsyncSession, seeded: dict[str, uuid.UUID]
    ) -> None:
        """`ocr_result.ocr_session_id` is UNIQUE — a re-run must not double-write."""
        from cocas.domain.exceptions import DuplicateEntityError

        repo = SqlAlchemyOcrResultRepository(pg_session, NullCryptoService())
        await repo.add(_snapshot(seeded["session"]))
        await pg_session.commit()

        with pytest.raises(DuplicateEntityError):
            await repo.add(_snapshot(seeded["session"]))
