"""`UploadCardImageUseCase` — §5.3.2 `POST /upload/front` and `/upload/back`.

⭐ This is where card images finally reach the Vault. Port 11 and
`VaultCategory.CARD_IMAGE` shipped in module 6, but nothing called them, so
P-05 (delete the source images once the contract exists) had nothing to
delete. The `RETENTION_PURGE` job now has real rows to work on.

Ordering mirrors `RegisterTemplateVersionUseCase` and for the same reason
(§12.14): probe → encrypt+write → one transaction → delete the file if the
transaction fails. A `.enc` with no `card_image` row is unreferenced
ciphertext, and §9.15's reconciliation would otherwise report it as a
discrepancy forever.

⚠️ `side_hint` is a **hint**. It records which button the user pressed, not
what the photo turned out to be: `HeuristicSideClassifier` decides that at S4
and writes `side_resolved`. Two names, because a session where the user
swapped the images has to stay diagnosable afterwards (`auto_swapped`).
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from loguru import logger

from cocas.domain.entities.card_image import CardImage
from cocas.domain.enums.card_side import CardSide
from cocas.domain.exceptions import DuplicateEntityError, EntityNotFound
from cocas.domain.ports.storage import IFileStorage, VaultCategory
from cocas.domain.ports.system import IClock, IIdGenerator


class IProbedImage(Protocol):
    """What `infrastructure.images.probe()` reports, seen from Application."""

    @property
    def mime_type(self) -> str: ...

    @property
    def width_px(self) -> int: ...

    @property
    def height_px(self) -> int: ...

    @property
    def size_bytes(self) -> int: ...


class IImageProbe(Protocol):
    def __call__(self, data: bytes) -> IProbedImage: ...


class IDocumentTypeIds(Protocol):
    async def ids_by_code(self) -> dict[str, uuid.UUID]: ...


class ICardImageWriter(Protocol):
    async def add(self, entity: CardImage) -> None: ...

    async def find_by_sha256(self, digest: bytes) -> CardImage | None: ...


class IIngestionUnitOfWork(Protocol):
    card_images: ICardImageWriter

    async def __aenter__(self) -> IIngestionUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class UploadCardImageCommand:
    data: bytes
    side_hint: CardSide
    uploaded_by: str
    document_type_code: str | None = None


@dataclass(frozen=True, slots=True)
class UploadedCardImage:
    image_id: uuid.UUID
    side_hint: CardSide
    mime_type: str
    width_px: int
    height_px: int
    size_bytes: int
    sha256: str


class UploadCardImageUseCase:
    """Validate one uploaded photo, encrypt it into the Vault, record the row."""

    def __init__(
        self,
        uow_factory: Callable[[], IIngestionUnitOfWork],
        file_storage: IFileStorage,
        document_types: IDocumentTypeIds,
        probe: IImageProbe,
        clock: IClock,
        id_generator: IIdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._document_types = document_types
        self._probe = probe
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, command: UploadCardImageCommand) -> UploadedCardImage:
        probed = self._probe(command.data)
        document_type_id = await self._document_type_id(command.document_type_code)
        digest = hashlib.sha256(command.data).digest()

        # ⭐ `COCAS-3007` before the Vault write, not after. `card_image.sha256`
        # is UNIQUE, so a repeat upload was already refused — but only once the
        # bytes had been encrypted, written, verified and then deleted again.
        # The id of the existing row travels with the error so the caller can
        # offer "dùng lại ảnh đã tải" instead of just saying no.
        async with self._uow_factory() as uow:
            existing = await uow.card_images.find_by_sha256(digest)
        if existing is not None and not existing.is_purged:
            raise DuplicateEntityError(
                "Ảnh này đã được tải lên trước đó.",
                code="DUPLICATE_CARD_IMAGE",
                hint="Dùng lại ảnh đã có, hoặc chọn ảnh khác.",
                details={"image_id": str(existing.id)},
            )

        ref = self._file_storage.save(command.data, VaultCategory.CARD_IMAGE)
        try:
            image = CardImage(
                id=self._id_generator.new_id(),
                uploaded_by=command.uploaded_by,
                document_type_id=document_type_id,
                side_hint=command.side_hint,
                vault_path=ref.relative_path,
                mime_type=probed.mime_type,
                width_px=probed.width_px,
                height_px=probed.height_px,
                size_bytes=probed.size_bytes,
                sha256=digest,
                created_at=self._clock.now(),
            )
            async with self._uow_factory() as uow:
                await uow.card_images.add(image)
                await uow.commit()
        except Exception:
            self._file_storage.delete(ref)
            raise

        logger.info(
            "card image uploaded",
            image_id=str(image.id),
            side_hint=command.side_hint.value,
            width=probed.width_px,
            height=probed.height_px,
            size_bytes=probed.size_bytes,
        )
        return UploadedCardImage(
            image_id=image.id,
            side_hint=command.side_hint,
            mime_type=probed.mime_type,
            width_px=probed.width_px,
            height_px=probed.height_px,
            size_bytes=probed.size_bytes,
            sha256=image.sha256.hex(),
        )

    async def _document_type_id(self, code: str | None) -> uuid.UUID:
        """The FK to store, from an optional client hint.

        ⚠️ Records what the **uploader assumed**, never a verdict. Which
        generation the card belongs to is settled at S7 from the printed text
        (§7.4.7); a client that guesses wrong here changes nothing downstream,
        because `ExtractionPipeline` is handed every candidate type and picks
        for itself (P3 module 1). The column exists so the row has a valid FK
        and so a support ticket can say what the UI believed at the time.
        """
        ids = await self._document_types.ids_by_code()
        if not ids:
            raise EntityNotFound(
                "Chưa có loại giấy tờ nào được bật để nhận dạng.",
                details={"hint": "Chạy migration seed trước khi tải ảnh."},
            )
        if code is not None:
            found = ids.get(code)
            if found is None:
                raise EntityNotFound(
                    "Loại giấy tờ không tồn tại.", details={"document_type_code": code}
                )
            return found
        return next(iter(ids.values()))
