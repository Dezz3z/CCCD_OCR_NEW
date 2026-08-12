"""`UploadCardImageUseCase` — §5.3.2, and the first path that fills the Vault."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import pytest

from cocas.application.use_cases.ingestion.upload_card_image import (
    UploadCardImageCommand,
    UploadCardImageUseCase,
)
from cocas.domain.entities.card_image import CardImage
from cocas.domain.enums.card_side import CardSide
from cocas.domain.exceptions import DuplicateEntityError, EntityNotFound, StorageError
from cocas.domain.ports.storage import VaultCategory, VaultRef

from .conftest import NOW, FakeClock, FakeUnitOfWork, SequentialIds

_DOC_TYPE_ID = uuid.UUID(int=0xC0CA)
_DATA = b"\xff\xd8\xff" + b"pretend jpeg" * 100


@dataclass(frozen=True, slots=True)
class _Probed:
    size_bytes: int
    mime_type: str = "image/jpeg"
    width_px: int = 1280
    height_px: int = 800


class _DocumentTypes:
    def __init__(self, ids: dict[str, uuid.UUID] | None = None) -> None:
        self._ids = {"CCCD_CHIP": _DOC_TYPE_ID} if ids is None else ids

    async def ids_by_code(self) -> dict[str, uuid.UUID]:
        return dict(self._ids)


class _Vault:
    """Records what was saved and what was deleted."""

    def __init__(self, *, fail_on_save: bool = False) -> None:
        self.saved: list[bytes] = []
        self.deleted: list[VaultRef] = []
        self._fail = fail_on_save

    def save(self, data: bytes, category: VaultCategory) -> VaultRef:
        if self._fail:
            raise StorageError("đĩa hỏng")
        self.saved.append(data)
        return VaultRef(
            category=category,
            relative_path=f"{category.value}/2026/08/12/{uuid.uuid4()}.enc",
        )

    def delete(self, ref: VaultRef) -> None:
        self.deleted.append(ref)

    def load(self, ref: VaultRef) -> bytes:  # pragma: no cover - unused here
        return b""

    def exists(self, ref: VaultRef) -> bool:  # pragma: no cover - unused here
        return True


def _use_case(
    uow: FakeUnitOfWork,
    clock: FakeClock,
    ids: SequentialIds,
    vault: _Vault | None = None,
    doc_types: _DocumentTypes | None = None,
) -> tuple[UploadCardImageUseCase, _Vault]:
    storage = vault or _Vault()
    return (
        UploadCardImageUseCase(
            uow_factory=uow,
            file_storage=storage,  # type: ignore[arg-type]
            document_types=doc_types or _DocumentTypes(),
            probe=lambda data: _Probed(size_bytes=len(data)),  # type: ignore[arg-type,return-value]
            clock=clock,
            id_generator=ids,
        ),
        storage,
    )


def _command(**overrides: object) -> UploadCardImageCommand:
    defaults: dict[str, object] = {
        "data": _DATA,
        "side_hint": CardSide.FRONT,
        "uploaded_by": "tester",
    }
    defaults.update(overrides)
    return UploadCardImageCommand(**defaults)  # type: ignore[arg-type]


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_writes_the_bytes_to_the_vault_and_a_row_to_the_database(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        use_case, vault = _use_case(uow, clock, ids)
        result = await use_case.execute(_command())

        assert vault.saved == [_DATA]
        assert uow.commits == 1
        stored = uow.card_images.added[0]
        assert stored.id == result.image_id
        assert stored.vault_path.startswith("card_image/")

    @pytest.mark.asyncio
    async def test_the_digest_is_of_the_upload(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        use_case, _ = _use_case(uow, clock, ids)
        result = await use_case.execute(_command())
        assert result.sha256 == hashlib.sha256(_DATA).hexdigest()

    @pytest.mark.asyncio
    async def test_side_hint_is_recorded_as_a_hint_not_a_verdict(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """⚠️ `side_resolved` stays empty — S4 decides that, not the button."""
        use_case, _ = _use_case(uow, clock, ids)
        await use_case.execute(_command(side_hint=CardSide.BACK))
        stored = uow.card_images.added[0]
        assert stored.side_hint is CardSide.BACK
        assert stored.side_resolved is None


class TestDuplicates:
    @pytest.mark.asyncio
    async def test_a_repeat_upload_is_refused_before_the_vault_write(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """⭐ `COCAS-3007` costs nothing: no encrypt, no write, no delete."""
        use_case, vault = _use_case(uow, clock, ids)
        await use_case.execute(_command())
        vault.saved.clear()

        with pytest.raises(DuplicateEntityError) as exc_info:
            await use_case.execute(_command())

        assert vault.saved == []
        assert vault.deleted == []
        assert exc_info.value.code == "DUPLICATE_CARD_IMAGE"

    @pytest.mark.asyncio
    async def test_the_existing_image_id_travels_with_the_error(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """So the caller can offer 'dùng lại' instead of only saying no."""
        use_case, _ = _use_case(uow, clock, ids)
        first = await use_case.execute(_command())

        with pytest.raises(DuplicateEntityError) as exc_info:
            await use_case.execute(_command())

        details = exc_info.value.context["details"]
        assert details == {"image_id": str(first.image_id)}

    @pytest.mark.asyncio
    async def test_a_purged_image_does_not_block_a_re_upload(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """P-05 deleted the bytes; the user is entitled to supply them again."""
        use_case, _ = _use_case(uow, clock, ids)
        await use_case.execute(_command())
        stored: CardImage = uow.card_images.added[0]
        stored.purge("retention", NOW)

        again = await use_case.execute(_command())
        assert again.image_id != stored.id


class TestCompensation:
    @pytest.mark.asyncio
    async def test_a_failed_transaction_removes_the_orphan_from_the_vault(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        """An unreferenced `.enc` is customer data nobody can reach or purge."""
        use_case, vault = _use_case(uow, clock, ids)

        async def explode(entity: object) -> None:
            raise RuntimeError("database went away")

        uow.card_images.add = explode  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            await use_case.execute(_command())

        assert len(vault.deleted) == 1


class TestDocumentType:
    @pytest.mark.asyncio
    async def test_an_unknown_code_is_rejected(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        use_case, _ = _use_case(uow, clock, ids)
        with pytest.raises(EntityNotFound):
            await use_case.execute(_command(document_type_code="GPLX"))

    @pytest.mark.asyncio
    async def test_an_empty_catalogue_is_a_deployment_error_not_a_silent_null(
        self, uow: FakeUnitOfWork, clock: FakeClock, ids: SequentialIds
    ) -> None:
        use_case, _ = _use_case(uow, clock, ids, doc_types=_DocumentTypes({}))
        with pytest.raises(EntityNotFound):
            await use_case.execute(_command())
