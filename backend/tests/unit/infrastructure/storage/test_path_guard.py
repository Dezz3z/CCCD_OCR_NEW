"""§10.4.2 / §12.13.2 — nothing that is not our own path shape gets through."""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path, PureWindowsPath

import pytest

from cocas.domain.exceptions import PathTraversalError
from cocas.domain.ports.storage import VaultCategory, VaultRef
from cocas.infrastructure.storage.path_guard import (
    assert_valid_shape,
    build_relative_path,
    resolve_within,
)

FILE_ID = uuid.UUID("0192f4e2-3333-7000-a777-888899990000")
ON = date(2026, 8, 11)


def test_build_relative_path_matches_the_documented_shape() -> None:
    path = build_relative_path(VaultCategory.CONTRACT_DOCUMENT, ON, FILE_ID)

    assert path == f"contract_document/2026/08/11/{FILE_ID}.enc"
    assert_valid_shape(path)


def test_every_category_produces_a_valid_shape() -> None:
    """⭐ The shape regex is built from the enum — a new category must not
    quietly become un-storable."""
    for category in VaultCategory:
        assert_valid_shape(build_relative_path(category, ON, FILE_ID))


@pytest.mark.parametrize(
    "bad",
    [
        "contract_document/2026/08/11/../../../../Windows/System32/drivers/etc/hosts",
        "../secrets.enc",
        "contract_document/2026/08/11/not-a-uuid.enc",
        f"contract_document/2026/08/11/{FILE_ID}.docx",
        f"unknown_category/2026/08/11/{FILE_ID}.enc",
        f"contract_document\\2026\\08\\11\\{FILE_ID}.enc",
        f"contract_document/2026/08/11/{FILE_ID}.enc:hidden",
        f"/contract_document/2026/08/11/{FILE_ID}.enc",
        f"C:/contract_document/2026/08/11/{FILE_ID}.enc",
        "",
    ],
)
def test_shapes_we_never_produce_are_refused(bad: str) -> None:
    with pytest.raises(PathTraversalError):
        assert_valid_shape(bad)


def test_pathlib_join_alone_would_not_have_protected_us() -> None:
    """⚠️ §12.13.2 — the finding that put the shape check *before* the join.

    This asserts the surprising Windows behaviour itself, so the day pathlib
    changes it, this test says so rather than the guard silently becoming
    belt-without-braces.
    """
    root = PureWindowsPath("C:/COCAS/data/vault")

    assert root / "C:/Windows/System32" == PureWindowsPath("C:/Windows/System32")
    assert root / "/Windows/System32" == PureWindowsPath("C:/Windows/System32")


def test_resolve_within_returns_an_absolute_path_inside_the_root(tmp_path: Path) -> None:
    ref = VaultRef(
        category=VaultCategory.CARD_IMAGE,
        relative_path=build_relative_path(VaultCategory.CARD_IMAGE, ON, FILE_ID),
    )

    resolved = resolve_within(tmp_path, ref)

    assert resolved.is_absolute()
    assert resolved.is_relative_to(tmp_path.resolve())
    assert resolved.name == f"{FILE_ID}.enc"


def test_category_disagreeing_with_the_path_is_refused(tmp_path: Path) -> None:
    """A caller-built ref would otherwise fail later as `DecryptionError`,
    which reads as "the file is corrupt" for what is a wiring bug."""
    ref = VaultRef(
        category=VaultCategory.CARD_IMAGE,
        relative_path=build_relative_path(VaultCategory.CONTRACT_DOCUMENT, ON, FILE_ID),
    )

    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, ref)
