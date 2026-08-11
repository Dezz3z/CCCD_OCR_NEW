"""⭐ The 18 Ports — every point at which infrastructure can be replaced (P-03).

Numbered per the lookup table in docs/design/12-dac-ta-module.md §12.19:

| #  | Port                  | Module        |
|----|-----------------------|---------------|
| 1  | IOcrEngine            | `ocr`         |
| 2  | IRegionRecognizer     | `ocr`         |
| 3  | IImagePreprocessor    | `ocr`         |
| 4  | ICardSideClassifier   | `ocr`         |
| 5  | IQrDecoder            | `ocr`         |
| 6  | IMrzReader            | `ocr`         |
| 7  | IFieldExtractor       | `ocr`         |
| 8  | IReadRepository       | `persistence` |
| 9  | IWriteRepository      | `persistence` |
| 10 | IAliasRepository      | `persistence` |
| 11 | IFileStorage          | `storage`     |
| 12 | IDocumentRenderer     | `documents`   |
| ~~13~~ | ~~IPdfConverter~~ | 🗑️ removed in D2.1 (§9.13) — number left vacant on purpose |
| 14 | IUnitOfWork           | `persistence` |
| 15 | IJobQueue             | `queue`       |
| 16 | IClock                | `system`      |
| 17 | IIdGenerator          | `system`      |
| 18 | ICryptoService        | `crypto`      |
| 19 | IDocumentTypeSelector | `ocr`         |

⭐ Acceptance criterion (§12.19): every port must have at least one
fake/null implementation used in tests.

`IReadWriteRepository` is a convenience composition of #8 and #9, not a
port of its own.

⭐ **Port 19 was added in P3**, when `ExtractionPipeline` needed to answer a
question no earlier module had to: *which* of the two circulating card
generations is this? See `IDocumentTypeSelector` for why it cannot be the
caller's answer.

⭐ **Port 13 was removed in D2.1** together with PDF export (§9.13). The
numbering keeps the gap rather than shifting 14–19 down, so every existing
`§12.1x` citation in code, docs and commit history still points at the same
thing. That is why 18 ports are numbered 1–19.
"""
from cocas.domain.ports.crypto import AadContext, BidxField, ICryptoService
from cocas.domain.ports.documents import IDocumentRenderer, RenderResult
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    EngineInfo,
    ExtractionStrategy,
    ICardSideClassifier,
    IDocumentTypeSelector,
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
    OcrFieldSnapshot,
    OcrResultSnapshot,
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
    "IDocumentTypeSelector",
    "IFieldExtractor",
    "IFileStorage",
    "IIdGenerator",
    "IImagePreprocessor",
    "IJobQueue",
    "IMrzReader",
    "IOcrEngine",
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
    "OcrFieldSnapshot",
    "OcrOptions",
    "OcrResultSnapshot",
    "Page",
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
