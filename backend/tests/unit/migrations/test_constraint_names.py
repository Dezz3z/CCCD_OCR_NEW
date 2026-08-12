"""A migration may only drop a constraint the schema actually calls by that name.

⭐ `op.drop_constraint("tier_range", …)` is a string. Nothing in Python checks
it against the ORM, the name is assembled by `NAMING_CONVENTION` rather than
written out at the declaration site, and the failure arrives as
`constraint … does not exist` **during `upgrade head` on the customer's
machine** — after the installer has already started.

🔴 **This test used to assert the wrong thing, and so did the migrations it
was guarding.** It required the *full* rendered name (`ck_ocr_field__
tier_range`), and the migrations obligingly passed it — but `env.py` gives
Alembic `target_metadata`, so `op` applies the naming convention to whatever
it is handed. The full name came back out as
`ck_ocr_field__ck_ocr_field__tier_range`, and `upgrade head` failed on the
first real run (2026-08-12). A green test and a broken migration, agreeing
with each other.

So the rule is inverted: the migration passes the **short** name, and this
test checks that the convention renders it into something the schema declares.
The `startswith("ck_")` guard is what stops the old mistake coming back.

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


def _dropped_names() -> list[tuple[str, str, str]]:
    """`(migration file, table, name passed to drop_constraint)`."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        for name, table in _DROP_CONSTRAINT.findall(path.read_text(encoding="utf-8")):
            found.append((path.name, table, name))
    return found


class TestDroppedConstraintsExist:
    def test_every_dropped_constraint_is_one_the_schema_declares(self) -> None:
        missing: list[str] = []
        for file_name, table, short in _dropped_names():
            if table not in Base.metadata.tables:
                missing.append(f"{file_name}: unknown table {table!r}")
                continue
            rendered = f"ck_{table}__{short}"
            if rendered not in _declared_constraint_names(table):
                missing.append(
                    f"{file_name}: {table}.{short!r} renders to {rendered!r}, "
                    f"but declared names are {sorted(_declared_constraint_names(table))}"
                )
        assert missing == [], "\n".join(missing)

    def test_no_migration_passes_the_already_rendered_name(self) -> None:
        """⭐ The regression guard for 2026-08-12.

        Alembic applies `NAMING_CONVENTION` to the name it is given, so a name
        that already carries the `ck_<table>__` prefix gets it twice.
        """
        doubled = [
            f"{file_name}: drop_constraint({name!r}) — pass {name.split('__', 1)[-1]!r}"
            for file_name, _table, name in _dropped_names()
            if name.startswith(("ck_", "uq_", "fk_", "ix_"))
        ]
        assert doubled == [], "\n".join(doubled)


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
