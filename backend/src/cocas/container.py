"""Dependency injection container — Composition Root.

⭐ CRITICAL: This is the ONLY file allowed to import from all 4 layers (the
import-linter "Container exception" contract exists specifically for this file).
Every other module must respect the Dependency Rule: Presentation → Application
→ Domain, with Infrastructure wired in here and nowhere else.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from cocas.application.pipelines.extraction_pipeline import ExtractionPipeline
from cocas.application.render_context_builder import RenderContextBuilder
from cocas.application.use_cases.contract.download_contract_document import (
    DownloadContractDocumentUseCase,
)
from cocas.application.use_cases.contract.generate_contract import GenerateContractUseCase
from cocas.application.use_cases.customer.manage_customer import (
    CreateCustomerUseCase,
    FindCustomerByIdNumberUseCase,
)
from cocas.application.use_cases.ingestion.upload_card_image import (
    UploadCardImageUseCase,
)
from cocas.application.use_cases.ocr.manage_ocr_session import (
    OCR_TARGET_TYPE,
    ConfirmOcrSessionUseCase,
    CreateOcrSessionUseCase,
    FailOcrSessionUseCase,
    GetOcrSessionUseCase,
    UpdateOcrFieldsUseCase,
)
from cocas.application.use_cases.ocr.process_ocr_session import ProcessOcrSessionUseCase
from cocas.application.use_cases.ocr.run_ocr_job import RunOcrJobUseCase
from cocas.application.use_cases.template.register_template_version import (
    RegisterTemplateVersionUseCase,
)
from cocas.config.settings import Settings
from cocas.domain.enums.job_type import JobType
from cocas.domain.ports.crypto import ICryptoService
from cocas.domain.ports.storage import IFileStorage
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.domain.services.contract_number_generator import ContractNumberGenerator
from cocas.domain.services.export_name_generator import ExportNameGenerator
from cocas.domain.services.field_normalizer import FieldNormalizer
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.domain.validation.engine import ValidationEngine
from cocas.infrastructure.documents.docx_context_adapter import DocxContextAdapter
from cocas.infrastructure.documents.docx_renderer import DocxRenderer
from cocas.infrastructure.documents.template_inspector import DocxTemplateInspector
from cocas.infrastructure.images.probe import probe as probe_image
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
from cocas.infrastructure.queue.job_runner import JobRunner
from cocas.infrastructure.security.crypto import DpapiCryptoService
from cocas.infrastructure.security.dpapi import DpapiKeyManager
from cocas.infrastructure.storage.encrypted_file_vault import EncryptedFileVault
from cocas.infrastructure.storage.template_store import TemplateStore
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
        crypto = DpapiCryptoService(kek)
        self.crypto: ICryptoService = crypto

        self.clock: IClock = SystemClock()
        self.id_generator: IIdGenerator = Uuid7Generator()

        # ⭐ Port 11. Takes the **derived** VAULT_KEY, not the crypto service:
        # §4.8.1's key tree gives Vault files their own branch, and handing
        # the service over would encrypt every image and contract under the
        # same key as the PII columns (§12.13.1). `crypto` is the concrete
        # type here for exactly this one property.
        self.file_storage: IFileStorage = EncryptedFileVault(
            root=Path(settings.vault_dir),
            vault_key=crypto.vault_key,
            clock=self.clock,
            id_generator=self.id_generator,
        )

        # ⭐ A **sibling** of the Vault and deliberately unencrypted — see
        # `TemplateStore`'s docstring. It is not an `IFileStorage`: the two
        # have different guarantees, and giving them one interface is how a
        # contract ends up written to the plaintext half.
        self.template_store = TemplateStore(Path(settings.templates_dir))

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

        # ---- Documents (P3 module 3+) ------------------------------------
        #
        # ⭐ Port 20. Safe to share for the process lifetime: it holds only a
        # Jinja2 `Environment` used for `parse()`, keeps no per-file state,
        # and — unlike the OCR engine — needs no warm-up, because it never
        # renders and so never loads anything.
        self.template_inspector = DocxTemplateInspector()

        # ⭐ Port 12. A singleton **because** of its cache: preparing a
        # template costs 6–9 s and every render after that costs ~0.4 s
        # (§9.12.1). Rebuilding the renderer per request would pay the 6–9 s
        # on every contract and quietly break NFR-03.
        self.document_renderer = DocxRenderer()

        # ⭐ Pure functions with no state; shared for the same reason
        # `IssuePlaceNormalizer` is (§12.5).
        self.render_context_builder = RenderContextBuilder()
        self.docx_context_adapter = DocxContextAdapter()
        self.contract_number_generator = ContractNumberGenerator()
        self.export_name_generator = ExportNameGenerator()

        # ⭐ Holds the 4 rule sets of §12.7 — `CONTRACT_GENERATION` gained its
        # 10 `V-CTR-*` members in P3 module 6; the other two P3 sets are still
        # registered **empty**, which is a valid report, not a missing key.
        self.validation_engine = ValidationEngine()

        #: Created lazily by `job_runner()` — see there for why it is the one
        #: singleton among the Use Case factories.
        self._job_runner: JobRunner | None = None

        #: Whether `ocr_engine.warm_up()` has run — see `ensure_ocr_ready()`.
        self._ocr_ready = False

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

    def generate_contract_use_case(self) -> GenerateContractUseCase:
        """⭐ The whole of §9.11 as one callable — OCR's counterpart for documents.

        Built per call for the same reason `process_ocr_session_use_case()` is:
        it is stateless, and making it an attribute invites someone to cache a
        `IUnitOfWork` inside it.
        """
        return GenerateContractUseCase(
            uow_factory=self.unit_of_work,
            context_builder=self.render_context_builder,
            context_adapter=self.docx_context_adapter,
            renderer=self.document_renderer,
            file_storage=self.file_storage,
            validator=self.validation_engine,
            contract_numbers=self.contract_number_generator,
            export_names=self.export_name_generator,
            templates_dir=Path(self.settings.templates_dir),
            clock=self.clock,
            id_generator=self.id_generator,
        )

    # ---- P3 module 7: the §5.4 endpoint chain -----------------------------
    #
    # Each is built per call, for the same reason the two above are: they are
    # stateless, and an attribute would invite someone to cache a UoW inside.

    def upload_card_image_use_case(self) -> UploadCardImageUseCase:
        return UploadCardImageUseCase(
            uow_factory=self.unit_of_work,
            file_storage=self.file_storage,
            document_types=self.document_types,
            probe=probe_image,
            clock=self.clock,
            id_generator=self.id_generator,
        )

    def create_ocr_session_use_case(self) -> CreateOcrSessionUseCase:
        return CreateOcrSessionUseCase(
            uow_factory=self.unit_of_work,
            clock=self.clock,
            id_generator=self.id_generator,
        )

    def get_ocr_session_use_case(self) -> GetOcrSessionUseCase:
        return GetOcrSessionUseCase(uow_factory=self.unit_of_work)

    def update_ocr_fields_use_case(self) -> UpdateOcrFieldsUseCase:
        return UpdateOcrFieldsUseCase(uow_factory=self.unit_of_work)

    def confirm_ocr_session_use_case(self) -> ConfirmOcrSessionUseCase:
        return ConfirmOcrSessionUseCase(uow_factory=self.unit_of_work)

    def run_ocr_job_use_case(self) -> RunOcrJobUseCase:
        return RunOcrJobUseCase(
            uow_factory=self.unit_of_work,
            process_session=self.process_ocr_session_use_case(),
            file_storage=self.file_storage,
            clock=self.clock,
        )

    def find_customer_use_case(self) -> FindCustomerByIdNumberUseCase:
        return FindCustomerByIdNumberUseCase(uow_factory=self.unit_of_work)

    def create_customer_use_case(self) -> CreateCustomerUseCase:
        return CreateCustomerUseCase(
            uow_factory=self.unit_of_work,
            clock=self.clock,
            id_generator=self.id_generator,
        )

    def download_contract_document_use_case(self) -> DownloadContractDocumentUseCase:
        return DownloadContractDocumentUseCase(
            uow_factory=self.unit_of_work,
            file_storage=self.file_storage,
            clock=self.clock,
        )

    def job_runner(self) -> JobRunner:
        """⭐ A singleton, unlike every other factory on this class.

        The runner owns a background `asyncio.Task`; a second instance would
        be a second poller against the same table. `SKIP LOCKED` means they
        would not corrupt anything — they would just both be running OCR on a
        4 GB machine, which constraint #9 says produces `Insufficient memory`
        from inside OpenCV.
        """
        if self._job_runner is None:
            self._job_runner = JobRunner(
                uow_factory=self.unit_of_work,
                clock=self.clock,
                handlers={JobType.OCR: self._handle_ocr_job},
                on_terminal_failure=self._release_job_target,
            )
        return self._job_runner

    async def _handle_ocr_job(
        self, job_id: uuid.UUID, payload: dict[str, object]
    ) -> None:
        await self.ensure_ocr_ready()
        await self.run_ocr_job_use_case().execute(job_id, payload)

    async def ensure_ocr_ready(self) -> None:
        """Load the OCR models once, off the event loop.

        ⭐ `__init__` deliberately does not do this (see `self.ocr_engine`), and
        the first end-to-end run showed why the gap needed filling somewhere:
        the first OCR job raised `OcrEngineUnavailableError` three times and the
        session ended `FAILED` with the models still on disk. The queue is the
        right place — it is the only caller that needs the engine, the cost is
        paid once, and a missing model file fails a job the user can see rather
        than a startup nobody is watching (P-08).

        ⚠️ `asyncio.to_thread`, because `warm_up()` blocks for several seconds
        reading weights. On the event loop that would stall every in-flight
        HTTP request — including the `/health` probe the supervisor uses to
        decide whether this process is alive.
        """
        if self._ocr_ready:
            return
        await asyncio.to_thread(self.ocr_engine.warm_up)
        self._ocr_ready = True

    async def _release_job_target(
        self, target_type: str, target_id: uuid.UUID, code: str, detail: str
    ) -> None:
        """Move a job's subject out of its in-progress state after final failure."""
        if target_type == OCR_TARGET_TYPE:
            await FailOcrSessionUseCase(self.unit_of_work, self.clock).execute(
                target_id, code, detail
            )

    def register_template_version_use_case(self) -> RegisterTemplateVersionUseCase:
        """Upload + activate one `.docx` version of a registered template."""
        return RegisterTemplateVersionUseCase(
            uow_factory=self.unit_of_work,
            inspector=self.template_inspector,
            template_store=self.template_store,
            clock=self.clock,
            id_generator=self.id_generator,
        )

    async def close(self) -> None:
        """Stop the runner, then release the DB connection pool."""
        if self._job_runner is not None:
            # ⚠️ Before `engine.dispose()`. A job still in flight needs its
            # connection to write its outcome; disposing first turns a clean
            # shutdown into a job stuck at `RUNNING` until the stale sweep.
            await self._job_runner.stop()
            self._job_runner = None
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
