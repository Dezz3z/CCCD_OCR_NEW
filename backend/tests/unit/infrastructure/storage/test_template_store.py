"""`TemplateStore` — the plaintext half of the storage layout."""
from __future__ import annotations

import hashlib
from pathlib import Path, PureWindowsPath

import pytest

from cocas.domain.exceptions import PathTraversalError, TemplateNotFoundError
from cocas.infrastructure.storage.template_store import (
    TemplateStore,
    build_relative_path,
)

_DOCX = b"PK\x03\x04" + b"fake docx payload" * 64


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path: Path) -> None:
        store = TemplateStore(tmp_path)
        stored = store.save(_DOCX, "01A_HD_GDN", 1)
        assert store.load(stored.relative_path) == _DOCX

    def test_reports_the_digest_and_size_of_what_it_wrote(self, tmp_path: Path) -> None:
        store = TemplateStore(tmp_path)
        stored = store.save(_DOCX, "01A_HD_GDN", 1)
        assert stored.sha256 == hashlib.sha256(_DOCX).digest()
        assert stored.size_bytes == len(_DOCX)

    def test_path_shape_mirrors_the_resources_tree(self, tmp_path: Path) -> None:
        store = TemplateStore(tmp_path)
        stored = store.save(_DOCX, "01A_GDKQ", 3)
        assert stored.relative_path == "01A_GDKQ/v3/template.docx"

    def test_versions_do_not_overwrite_each_other(self, tmp_path: Path) -> None:
        store = TemplateStore(tmp_path)
        first = store.save(b"PK\x03\x04first", "01A_GDKQ", 1)
        second = store.save(b"PK\x03\x04second", "01A_GDKQ", 2)
        assert store.load(first.relative_path) == b"PK\x03\x04first"
        assert store.load(second.relative_path) == b"PK\x03\x04second"

    def test_no_temp_file_survives(self, tmp_path: Path) -> None:
        """write-temp → verify → rename leaves nothing behind."""
        store = TemplateStore(tmp_path)
        store.save(_DOCX, "01A_HD_GDN", 1)
        assert list(tmp_path.rglob("*.tmp")) == []

    def test_missing_file_is_named_as_such(self, tmp_path: Path) -> None:
        store = TemplateStore(tmp_path)
        with pytest.raises(TemplateNotFoundError):
            store.load("01A_HD_GDN/v1/template.docx")

    def test_exists_is_false_before_save(self, tmp_path: Path) -> None:
        assert TemplateStore(tmp_path).exists("01A_HD_GDN/v1/template.docx") is False


class TestPathGuard:
    @pytest.mark.parametrize(
        "bad",
        [
            "../../Windows/System32/evil.docx",
            "C:/Windows/System32/evil.docx",
            "/Windows/evil.docx",
            "01A_HD_GDN\\v1\\template.docx",
            "01A_HD_GDN/v1/template.docx:stream",
            "01A_HD_GDN/v1/other.docx",
            "01a_hd_gdn/v1/template.docx",
            "01A_HD_GDN/vX/template.docx",
        ],
    )
    def test_rejects_anything_it_did_not_produce(self, tmp_path: Path, bad: str) -> None:
        with pytest.raises(PathTraversalError):
            TemplateStore(tmp_path).resolve(bad)

    def test_pathlib_join_alone_would_not_have_protected_us(self) -> None:
        """⚠️ The same Windows hazard `path_guard` documents, asserted again here.

        On Windows an absolute right-hand side **replaces** the left, so
        "we joined it onto the root, therefore it is under the root" is false.
        The shape check is what makes it true; this test fails the day pathlib
        changes and the reasoning needs revisiting.
        """
        assert PureWindowsPath("C:/templates") / "C:/Windows/x" == PureWindowsPath(
            "C:/Windows/x"
        )
        assert PureWindowsPath("C:/templates") / "/Windows/x" == PureWindowsPath(
            "C:/Windows/x"
        )


class TestBuildRelativePath:
    def test_matches_what_save_produces(self, tmp_path: Path) -> None:
        store = TemplateStore(tmp_path)
        assert (
            store.save(_DOCX, "01A_HD_GDN", 7).relative_path
            == build_relative_path("01A_HD_GDN", 7)
        )
