"""Static checks on Alembic revision files — no database connection needed.

⭐ `test_revision_ids_fit_in_32_chars` guards a real bug found running the
actual `upgrade head` against PostgreSQL: Alembic's own `alembic_version`
table hard-codes `version_num VARCHAR(32)` (`alembic/ddl/impl.py`,
`version_table_impl()`), with no public config knob to widen it. 4 of the
8 original revision ids exceeded 32 characters and broke `upgrade head`
midway with `StringDataRightTruncationError` — see docs/design/04-co-so-du-lieu.md
§4.9's "Sửa tên revision" note.
"""
from __future__ import annotations

import re
from pathlib import Path

MAX_REVISION_LENGTH = 32

_VERSIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "versions"
_REVISION_PATTERN = re.compile(r'^revision\s*=\s*"([^"]+)"', re.MULTILINE)
_DOWN_REVISION_PATTERN = re.compile(r'^down_revision\s*=\s*"([^"]+)"', re.MULTILINE)


def _migration_files() -> list[Path]:
    return sorted(p for p in _VERSIONS_DIR.glob("*.py") if p.name != "__init__.py")


class TestRevisionIdLength:
    def test_versions_directory_is_not_empty(self) -> None:
        assert len(_migration_files()) >= 8

    def test_every_revision_id_fits_in_32_chars(self) -> None:
        offenders = []
        for path in _migration_files():
            match = _REVISION_PATTERN.search(path.read_text(encoding="utf-8"))
            assert match is not None, f"{path.name} has no `revision = \"...\"` line"
            revision_id = match.group(1)
            if len(revision_id) > MAX_REVISION_LENGTH:
                offenders.append((path.name, revision_id, len(revision_id)))
        assert not offenders, f"Revision ids exceeding {MAX_REVISION_LENGTH} chars: {offenders}"


class TestRevisionChain:
    """Every migration must chain to exactly one parent, forming a single line — no branches."""

    def test_single_linear_chain_to_one_head(self) -> None:
        revisions: dict[str, str | None] = {}
        for path in _migration_files():
            text = path.read_text(encoding="utf-8")
            rev_match = _REVISION_PATTERN.search(text)
            down_match = _DOWN_REVISION_PATTERN.search(text)
            assert rev_match is not None
            revision_id = rev_match.group(1)
            down_revision = down_match.group(1) if down_match else None
            revisions[revision_id] = down_revision

        parents = set(revisions.values()) - {None}
        heads = set(revisions) - parents
        assert len(heads) == 1, f"Expected exactly one head, found: {heads}"

        # Walk the chain from the head back to the root — must visit every revision exactly once.
        (head,) = heads
        visited = []
        current: str | None = head
        while current is not None:
            assert current not in visited, f"Cycle detected at {current}"
            visited.append(current)
            current = revisions[current]
        assert set(visited) == set(revisions), "Chain does not cover every migration file"
