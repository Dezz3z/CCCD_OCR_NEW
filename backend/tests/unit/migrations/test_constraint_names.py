"""A migration may only drop a constraint the schema actually calls by that name.

⭐ `op.drop_constraint("ck_ocr_field__tier_range", …)` is a string. Nothing in
Python checks it against the ORM, the name is assembled by
`NAMING_CONVENTION` rather than written out at the declaration site, and the
failure arrives as `constraint … does not exist` **during `upgrade head` on the
customer's machine** — after the installer has already started.

This test resolves the name the same way SQLAlchemy does and compares it to
what the migrations say, with no database connection.

⚠️ Deliberately not a general "every migration is valid" test. It checks the
one thing that is both silent locally and fatal remotely.
"""
from __future__ import annotations

import re
from pathlib import Path

from cocas.infrastructure.persistence.models import Base

_VERSIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "versions"
_DROP_CONSTRAINT = re.compile(
    r'op\.drop_constraint\(\s*"([^"]+)"\s*,\s*"([^"]+)"', re.MULTILINE
)


def _declared_constraint_names(table_name: str) -> set[str]:
    """Every constraint name on a table, as the naming convention renders it."""
    table = Base.metadata.tables[table_name]
    names = {c.name for c in table.constraints if c.name is not None}
    names |= {index.name for index in table.indexes if index.name is not None}
    return {str(name) for name in names}


class TestDroppedConstraintsExist:
    def test_every_dropped_constraint_is_one_the_schema_declares(self) -> None:
        missing: list[str] = []
        for path in sorted(_VERSIONS_DIR.glob("*.py")):
            for name, table in _DROP_CONSTRAINT.findall(path.read_text(encoding="utf-8")):
                if table not in Base.metadata.tables:
                    missing.append(f"{path.name}: unknown table {table!r}")
                elif name not in _declared_constraint_names(table):
                    missing.append(
                        f"{path.name}: {table}.{name!r} — declared names are "
                        f"{sorted(_declared_constraint_names(table))}"
                    )
        assert missing == [], "\n".join(missing)


class TestTierRangeMatchesTheNormalizer:
    """⭐ The CHECK and `IssuePlaceNormalizer` have to agree about how many tiers
    exist. They disagreed once: the fifth tier shipped on 2026-08-11 and the
    constraint still said 1..4, so every `issue_place` the pipeline resolved
    would have been rejected at INSERT time inside a background job.
    """

    def test_the_check_admits_every_tier_the_normalizer_can_return(self) -> None:
        from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer

        # ⚠️ `.name` is the *rendered* name — the naming convention has already
        # turned `name="tier_range"` into `ck_ocr_field__tier_range` by the time
        # the constraint is attached to the table.
        table = Base.metadata.tables["ocr_field"]
        check = next(
            c
            for c in table.constraints
            if str(getattr(c, "name", "")) == "ck_ocr_field__tier_range"
        )
        sql = str(check.sqltext)  # type: ignore[attr-defined]
        highest = max(
            int(n) for n in re.findall(r"BETWEEN\s+\d+\s+AND\s+(\d+)", sql, re.IGNORECASE)
        )
        assert highest >= IssuePlaceNormalizer.MAX_TIER, (
            f"ocr_field.tier_range allows up to {highest} but the normalizer "
            f"can return {IssuePlaceNormalizer.MAX_TIER}"
        )
