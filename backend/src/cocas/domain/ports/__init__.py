"""⭐ The 18 Ports — every point at which infrastructure can be replaced (P-03).

Numbered per the lookup table in docs/design/12-dac-ta-module.md §12.19:

| #  | Port                | Module        |
|----|---------------------|---------------|
| 1  | IOcrEngine          | `ocr`         |
| 2  | IRegionRecognizer   | `ocr`         |
| 3  | IImagePreprocessor  | `ocr`         |
| 4  | ICardSideClassifier | `ocr`         |
| 5  | IQrDecoder          | `ocr`         |
| 6  | IMrzReader          | `ocr`         |
| 7  | IFieldExtractor     | `ocr`         |
| 8  | IReadRepository     | `persistence` |
| 9  | IWriteRepository    | `persistence` |
| 10 | IAliasRepository    | `persistence` |
| 11 | IFileStorage        | `storage`     |
| 12 | IDocumentRenderer   | `documents`   |
| 13 | IPdfConverter       | `documents`   |
| 14 | IUnitOfWork         | `persistence` |
| 15 | IJobQueue           | `queue`       |
| 16 | IClock              | `system`      |
| 17 | IIdGenerator        | `system`      |
| 18 | ICryptoService      | `crypto`      |

⭐ Acceptance criterion (§12.19): every port must have at least one
fake/null implementation used in tests.

`IReadWriteRepository` is a convenience composition of #8 and #9, not a
19th port.
"""
from cocas.domain.ports.crypto import AadContext, BidxField, ICryptoService
from cocas.domain.ports.documents import IDocumentRenderer, IPdfConverter, PdfResult, RenderResult
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    EngineInfo,
    ExtractionStrategy,
    ICardSideClassifier,
    IFieldExtractor,
    IImagePreprocessor,
    ImageData,
    ImageQuality,
    IMrzReader,
    IOcrEngine,
    IQrDecoder,
    IRegionRecognizer,
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
from cocas.domain.ports.persistence import (
    AliasRecord,
    IAliasRepository,
    IReadRepository,
    IReadWriteRepository,
    IUnitOfWork,
    IWriteRepository,
    Page,
    Specification,
)
from cocas.domain.ports.queue import DEFAULT_PRIORITY, IJobQueue, JobSnapshot, JobTarget
from cocas.domain.ports.storage import IFileStorage, VaultCategory, VaultRef
from cocas.domain.ports.system import IClock, IIdGenerator

__all__ = [
    "DEFAULT_PRIORITY",
    "AadContext",
    "AliasRecord",
    "BidxField",
    "DocumentTypeSpec",
    "EngineInfo",
    "ExtractionStrategy",
    "IAliasRepository",
    "ICardSideClassifier",
    "IClock",
    "ICryptoService",
    "IDocumentRenderer",
    "IFieldExtractor",
    "IFileStorage",
    "IIdGenerator",
    "IImagePreprocessor",
    "IJobQueue",
    "IMrzReader",
    "IOcrEngine",
    "IPdfConverter",
    "IQrDecoder",
    "IReadRepository",
    "IReadWriteRepository",
    "IRegionRecognizer",
    "IUnitOfWork",
    "IWriteRepository",
    "ImageData",
    "ImageQuality",
    "JobSnapshot",
    "JobTarget",
    "MrzExtractionResult",
    "OcrOptions",
    "Page",
    "PdfResult",
    "PreprocessProfile",
    "PreprocessedImageSet",
    "QrExtractionResult",
    "RawFieldValue",
    "RelativeBox",
    "RenderResult",
    "SideClassification",
    "SideVerdict",
    "Specification",
    "TextRegion",
    "VaultCategory",
    "VaultRef",
]
