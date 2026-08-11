"""Dependency injection container — Composition Root.

⭐ CRITICAL: This is the ONLY file allowed to import from all 4 layers (the
import-linter "Container exception" contract exists specifically for this file).
Every other module must respect the Dependency Rule: Presentation → Application
→ Domain, with Infrastructure wired in here and nowhere else.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from cocas.application.pipelines.extraction_pipeline import ExtractionPipeline
from cocas.application.use_cases.ocr.process_ocr_session import ProcessOcrSessionUseCase
from cocas.config.settings import Settings
from cocas.domain.ports.crypto import ICryptoService
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.domain.services.field_normalizer import FieldNormalizer
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.infrastructure.logging.loguru_config import configure_logging
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.classification.document_type_selector import (
    MarkerDocumentTypeSelector,
)
from cocas.infrastructure.ocr.classification.side_classifier import HeuristicSideClassifier
from cocas.infrastructure.ocr.engines.paddle_ocr_adapter import PaddleOcrAdapter
from cocas.infrastructure.ocr.extraction.zone_anchor_extractor import ZoneAndAnchorExtractor
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import OpenCvPreprocessor
from cocas.infrastructure.persistence.repositories.alias_repository import (
    SqlAlchemyAliasRepository,
)
from cocas.infrastructure.persistence.repositories.document_type_repository import (
    SqlAlchemyDocumentTypeRepository,
)
from cocas.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from cocas.infrastructure.security.crypto import DpapiCryptoService
from cocas.infrastructure.security.dpapi import DpapiKeyManager
from cocas.infrastructure.system.clock import SystemClock
from cocas.infrastructure.system.id_generator import Uuid7Generator


class Container:
    """Wires every Port to its production Infrastructure implementation once at
    startup — nothing built here is optional or swapped conditionally at
    runtime (P-11: the app has exactly one deployment target, Windows).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # Logging first — every line below this point is worth capturing.
        configure_logging(log_dir=settings.log_dir, log_level=settings.log_level)

        kek = DpapiKeyManager(Path(settings.dpapi_key_path)).load_or_create_kek()
        self.crypto: ICryptoService = DpapiCryptoService(kek)

        self.clock: IClock = SystemClock()
        self.id_generator: IIdGenerator = Uuid7Generator()

        self.engine: AsyncEngine = create_async_engine(
            settings.database_url, echo=settings.database_echo
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

        # ---- OCR stack (P2's 8 adapters + P3's pipeline) -----------------
        #
        # ⭐ These two repositories take the session **factory**, not a session:
        # they are read-mostly reference data consumed by a process-lifetime
        # pipeline, not by one Use Case's transaction. See
        # `SqlAlchemyAliasRepository`'s docstring for what binding them to a
        # session would break.
        self.aliases = SqlAlchemyAliasRepository(self.session_factory)
        self.document_types = SqlAlchemyDocumentTypeRepository(self.session_factory)

        # ⚠️ The engine is a singleton holding ~150 MB of model weights, and
        # `PaddleOcrAdapter.warm_up()` is **not** called here: it loads from
        # disk and must fail loudly at a moment someone is watching, not during
        # `Container.__init__` while the splash screen is up. §7.9's offline
        # rule means it never downloads, so a missing model is a hard error.
        self.ocr_engine = PaddleOcrAdapter(settings.ocr_models_dir)
        self.preprocessor = OpenCvPreprocessor()
        self.qr_decoder = ZxingQrDecoder()
        self.mrz_reader = Td1MrzReader(self.ocr_engine)
        self.side_classifier = HeuristicSideClassifier(self.qr_decoder, self.ocr_engine)
        self.field_extractor = ZoneAndAnchorExtractor()
        self.document_type_selector = MarkerDocumentTypeSelector()
        self.field_normalizer = FieldNormalizer(IssuePlaceNormalizer(self.aliases))

        self.extraction_pipeline = ExtractionPipeline(
            preprocessor=self.preprocessor,
            side_classifier=self.side_classifier,
            qr_decoder=self.qr_decoder,
            mrz_reader=self.mrz_reader,
            engine=self.ocr_engine,
            extractor=self.field_extractor,
            doc_type_selector=self.document_type_selector,
            normalizer=self.field_normalizer,
            clock=self.clock,
        )

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """A fresh `IUnitOfWork` per call — one transaction, one `async with` block (§12.14)."""
        return SqlAlchemyUnitOfWork(self.session_factory, self.crypto)

    def process_ocr_session_use_case(self) -> ProcessOcrSessionUseCase:
        """⭐ The whole OCR chain as one callable (§12.3 + §4.4.3).

        Built per call rather than once: the Use Case is stateless and holds
        only references, while making it an attribute would invite someone to
        cache a `IUnitOfWork` inside it — the one thing §12.14 forbids.
        """
        return ProcessOcrSessionUseCase(
            pipeline=self.extraction_pipeline,
            document_types=self.document_types,
            uow_factory=self.unit_of_work,
            id_generator=self.id_generator,
            clock=self.clock,
        )

    async def close(self) -> None:
        """Release the DB connection pool on shutdown."""
        await self.engine.dispose()


# Global container instance
_container: Container | None = None


def get_container() -> Container:
    """Get the global container instance."""
    if _container is None:
        raise RuntimeError("Container not initialized. Call init_container() first.")
    return _container


def init_container(settings: Settings) -> Container:
    """Initialize the global container."""
    global _container
    _container = Container(settings)
    return _container
