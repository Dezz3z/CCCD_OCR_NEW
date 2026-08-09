"""Unit tests for `Uuid7Generator` (Port 17 production implementation, DB-01)."""
from __future__ import annotations

import uuid

from cocas.infrastructure.system.id_generator import Uuid7Generator


class TestUuid7Generator:
    def test_returns_stdlib_uuid(self) -> None:
        generated = Uuid7Generator().new_id()
        assert type(generated) is uuid.UUID

    def test_version_is_7(self) -> None:
        assert Uuid7Generator().new_id().version == 7

    def test_ids_are_unique(self) -> None:
        gen = Uuid7Generator()
        ids = {gen.new_id() for _ in range(1000)}
        assert len(ids) == 1000

    def test_ids_are_time_ordered(self) -> None:
        """UUIDv7's leading bits are a millisecond timestamp — successive ids sort ascending."""
        gen = Uuid7Generator()
        ids = [gen.new_id() for _ in range(50)]
        assert ids == sorted(ids)
