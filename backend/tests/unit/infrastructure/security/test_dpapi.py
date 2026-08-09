"""Tests for DpapiKeyManager (§4.8.1, §4.8.5) — REAL Windows DPAPI, no mocking.

This environment is Windows with a working DPAPI user profile store, so
these exercise the actual `win32crypt.CryptProtectData`/`CryptUnprotectData`
round trip rather than faking it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cocas.domain.exceptions import KeyUnavailableError
from cocas.infrastructure.security.dpapi import KEK_LENGTH_BYTES, DpapiKeyManager


class TestFirstRun:
    def test_creates_key_file(self, tmp_path: Path) -> None:
        manager = DpapiKeyManager(tmp_path / "keys" / "master.key.dpapi")
        manager.load_or_create_kek()
        assert (tmp_path / "keys" / "master.key.dpapi").exists()

    def test_generated_kek_is_32_bytes(self, tmp_path: Path) -> None:
        manager = DpapiKeyManager(tmp_path / "master.key.dpapi")
        kek = manager.load_or_create_kek()
        assert len(kek) == KEK_LENGTH_BYTES

    def test_no_leftover_tmp_file(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key.dpapi"
        manager = DpapiKeyManager(key_path)
        manager.load_or_create_kek()
        assert not key_path.with_suffix(".tmp").exists()

    def test_wrapped_file_does_not_contain_kek_in_the_clear(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key.dpapi"
        manager = DpapiKeyManager(key_path)
        kek = manager.load_or_create_kek()
        assert kek not in key_path.read_bytes()


class TestSubsequentRuns:
    def test_reloading_returns_same_kek(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key.dpapi"
        first_kek = DpapiKeyManager(key_path).load_or_create_kek()
        second_kek = DpapiKeyManager(key_path).load_or_create_kek()
        assert first_kek == second_kek

    def test_does_not_overwrite_existing_key(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key.dpapi"
        DpapiKeyManager(key_path).load_or_create_kek()
        wrapped_after_first_run = key_path.read_bytes()
        DpapiKeyManager(key_path).load_or_create_kek()
        assert key_path.read_bytes() == wrapped_after_first_run


class TestCorruptedOrForeignData:
    def test_garbage_file_raises_key_unavailable(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key.dpapi"
        key_path.write_bytes(b"not a real dpapi blob at all")
        manager = DpapiKeyManager(key_path)
        with pytest.raises(KeyUnavailableError):
            manager.load_or_create_kek()


class TestRewrapForRestore:
    def test_rewrap_then_reload_round_trips(self, tmp_path: Path) -> None:
        """§4.8.6 step 5: restoring a backup re-wraps an externally-supplied KEK."""
        key_path = tmp_path / "master.key.dpapi"
        manager = DpapiKeyManager(key_path)
        external_kek = bytes(range(32))
        manager.rewrap_for_this_machine(external_kek)
        assert manager.load_or_create_kek() == external_kek

    def test_rewrap_overwrites_existing_key(self, tmp_path: Path) -> None:
        key_path = tmp_path / "master.key.dpapi"
        manager = DpapiKeyManager(key_path)
        manager.load_or_create_kek()
        new_kek = bytes(range(32))
        manager.rewrap_for_this_machine(new_kek)
        assert manager.load_or_create_kek() == new_kek
