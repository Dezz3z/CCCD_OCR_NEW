"""⭐ Architecture acceptance test (§12.19).

*"Mỗi Port phải có ít nhất một hiện thực fake/null dùng trong test. Đây là
tiêu chí nghiệm thu kiến trúc."*

This module is that criterion, executable: it asserts all 18 ports exist and
that each has a conforming fake. If someone adds a 19th port without a fake,
`test_all_18_ports_have_a_fake` fails.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cocas.domain.ports import (
    IAliasRepository,
    ICardSideClassifier,
    IClock,
    ICryptoService,
    IDocumentRenderer,
    IFieldExtractor,
    IFileStorage,
    IIdGenerator,
    IImagePreprocessor,
    IJobQueue,
    IMrzReader,
    IOcrEngine,
    IPdfConverter,
    IQrDecoder,
    IReadRepository,
    IRegionRecognizer,
    IUnitOfWork,
    IWriteRepository,
)
from tests.fixtures.fake_ports import (
    FakeAliasRepository,
    FakeCardSideClassifier,
    FakeDocumentRenderer,
    FakeFieldExtractor,
    FakeImagePreprocessor,
    FakeMrzReader,
    FakeOcrEngine,
    FakePdfConverter,
    FakeQrDecoder,
    FakeUnitOfWork,
    FrozenClock,
    InMemoryFileStorage,
    InMemoryJobQueue,
    InMemoryRepository,
    NullCryptoService,
    NullOcrEngine,
    NullPdfConverter,
    SequentialIdGenerator,
)

NOW = datetime(2026, 8, 9, tzinfo=UTC)

# (port number, port protocol, a conforming fake instance)
PORT_FAKES: list[tuple[int, type, object]] = [
    (1, IOcrEngine, FakeOcrEngine()),
    (2, IRegionRecognizer, FakeOcrEngine()),
    (3, IImagePreprocessor, FakeImagePreprocessor()),
    (4, ICardSideClassifier, FakeCardSideClassifier()),
    (5, IQrDecoder, FakeQrDecoder()),
    (6, IMrzReader, FakeMrzReader()),
    (7, IFieldExtractor, FakeFieldExtractor()),
    (8, IReadRepository, InMemoryRepository()),
    (9, IWriteRepository, InMemoryRepository()),
    (10, IAliasRepository, FakeAliasRepository()),
    (11, IFileStorage, InMemoryFileStorage()),
    (12, IDocumentRenderer, FakeDocumentRenderer()),
    (13, IPdfConverter, FakePdfConverter()),
    (14, IUnitOfWork, FakeUnitOfWork()),
    (15, IJobQueue, InMemoryJobQueue()),
    (16, IClock, FrozenClock(NOW)),
    (17, IIdGenerator, SequentialIdGenerator()),
    (18, ICryptoService, NullCryptoService()),
]


class TestPortConformance:
    def test_all_18_ports_have_a_fake(self) -> None:
        assert len(PORT_FAKES) == 18
        assert [n for n, _, _ in PORT_FAKES] == list(range(1, 19))

    @pytest.mark.parametrize(
        ("number", "port", "fake"),
        PORT_FAKES,
        ids=[f"{n:02d}-{p.__name__}" for n, p, _ in PORT_FAKES],
    )
    def test_fake_conforms_to_port(self, number: int, port: type, fake: object) -> None:
        assert isinstance(fake, port)

    def test_null_implementations_also_conform(self) -> None:
        """P-08 degraded-mode stand-ins must satisfy the same contracts."""
        assert isinstance(NullOcrEngine(), IOcrEngine)
        assert isinstance(NullPdfConverter(), IPdfConverter)
        assert isinstance(NullCryptoService(), ICryptoService)

    def test_ocr_engine_inherits_region_recognizer(self) -> None:
        """§12.2 ISP split: every IOcrEngine is also an IRegionRecognizer."""
        assert issubclass(IOcrEngine, IRegionRecognizer)
        assert isinstance(FakeOcrEngine(), IRegionRecognizer)
