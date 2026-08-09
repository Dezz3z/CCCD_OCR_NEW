"""Structural tests for the 19 ORM models, via `Base.metadata` introspection only.

⚠️ No live database connection is used or needed here — see
`cocas/infrastructure/persistence/models/base.py`'s docstring for why:
this environment has neither PostgreSQL nor Docker, so the mandatory
`upgrade head → downgrade base → upgrade head` roundtrip (§4.9) against
real PostgreSQL 16 is still unverified and must be run before release.
These tests instead lock in everything that *can* be checked without a
database: every table/column/constraint/FK the models claim to define
actually exists in the metadata graph exactly as declared.
"""
from __future__ import annotations

from cocas.infrastructure.persistence.models import Base

EXPECTED_TABLES = {
    "activity_log",
    "backup_record",
    "bank_account",
    "bank_directory",
    "card_image",
    "contract",
    "contract_document",
    "contract_party",
    "contract_template",
    "customer",
    "document_type",
    "job",
    "normalization_alias",
    "ocr_field",
    "ocr_result",
    "ocr_session",
    "province_code",
    "system_setting",
    "template_version",
}


def _fk_targets(table_name: str, column_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    column = table.c[column_name]
    return {fk.target_fullname for fk in column.foreign_keys}


def _constraint_names(table_name: str, constraint_type: type) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {c.name for c in table.constraints if isinstance(c, constraint_type)}


def _index_names(table_name: str) -> set[str]:
    return {ix.name for ix in Base.metadata.tables[table_name].indexes}


class TestTableCount:
    def test_exactly_19_tables(self) -> None:
        """§4.4 §4.4.15 bundles 2 tables under 1 heading — 18 subsections, 19 tables."""
        assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES
        assert len(Base.metadata.tables) == 19


class TestPrimaryKeys:
    def test_most_tables_use_uuid_id(self) -> None:
        uuid_pk_tables = EXPECTED_TABLES - {"activity_log", "province_code", "bank_directory", "system_setting"}
        for table_name in uuid_pk_tables:
            table = Base.metadata.tables[table_name]
            pk_columns = [c.name for c in table.primary_key.columns]
            assert pk_columns == ["id"], f"{table_name} should have a single 'id' PK"

    def test_activity_log_uses_seq_bigserial(self) -> None:
        table = Base.metadata.tables["activity_log"]
        assert [c.name for c in table.primary_key.columns] == ["seq"]
        assert table.c["seq"].autoincrement in (True, "auto")

    def test_reference_tables_use_code_as_pk(self) -> None:
        for table_name in ("province_code", "bank_directory"):
            table = Base.metadata.tables[table_name]
            assert [c.name for c in table.primary_key.columns] == ["code"]

    def test_system_setting_uses_key_as_pk(self) -> None:
        table = Base.metadata.tables["system_setting"]
        assert [c.name for c in table.primary_key.columns] == ["key"]


class TestForeignKeys:
    """Spot-check FK targets across the dependency graph (§4.6)."""

    def test_card_image_references_document_type(self) -> None:
        assert _fk_targets("card_image", "document_type_id") == {"document_type.id"}

    def test_ocr_session_references_both_images(self) -> None:
        assert _fk_targets("ocr_session", "front_image_id") == {"card_image.id"}
        assert _fk_targets("ocr_session", "back_image_id") == {"card_image.id"}

    def test_ocr_result_references_session(self) -> None:
        assert _fk_targets("ocr_result", "ocr_session_id") == {"ocr_session.id"}

    def test_ocr_field_references_result(self) -> None:
        assert _fk_targets("ocr_field", "ocr_result_id") == {"ocr_result.id"}

    def test_bank_account_references_customer(self) -> None:
        assert _fk_targets("bank_account", "customer_id") == {"customer.id"}

    def test_template_version_references_template(self) -> None:
        assert _fk_targets("template_version", "template_id") == {"contract_template.id"}

    def test_contract_template_references_template_version_circularly(self) -> None:
        """⭐ §4.6 #8 — the deliberate reference cycle, broken via `use_alter`."""
        assert _fk_targets("contract_template", "active_version_id") == {"template_version.id"}
        table = Base.metadata.tables["contract_template"]
        fk = next(iter(table.c["active_version_id"].foreign_keys))
        assert fk.constraint is not None
        assert fk.constraint.use_alter is True

    def test_contract_references_customer_and_template_version(self) -> None:
        assert _fk_targets("contract", "primary_customer_id") == {"customer.id"}
        assert _fk_targets("contract", "template_version_id") == {"template_version.id"}

    def test_contract_self_references_for_supersede(self) -> None:
        assert _fk_targets("contract", "supersedes_id") == {"contract.id"}

    def test_ocr_session_front_and_back_fk_names_are_distinct(self) -> None:
        """⭐ Regression (found running a real `CREATE TABLE` against PostgreSQL,
        not metadata introspection alone): two FKs from one table to the same
        target table collapse to an identical name under the default
        `fk_<table>__<referred_table>` naming_convention — Postgres rejects
        the second as `DuplicateObjectError`. front_image_id/back_image_id
        both target card_image, so they need explicit distinct names.
        """
        table = Base.metadata.tables["ocr_session"]
        front_fk = next(iter(table.c["front_image_id"].foreign_keys))
        back_fk = next(iter(table.c["back_image_id"].foreign_keys))
        assert front_fk.constraint is not None
        assert back_fk.constraint is not None
        assert front_fk.constraint.name != back_fk.constraint.name

    def test_no_table_has_duplicate_foreign_key_constraint_names(self) -> None:
        """General-purpose guard against the same class of bug on any other table."""
        from sqlalchemy import ForeignKeyConstraint

        for table_name, table in Base.metadata.tables.items():
            fk_names = [
                c.name for c in table.constraints if isinstance(c, ForeignKeyConstraint)
            ]
            assert len(fk_names) == len(set(fk_names)), (
                f"{table_name} has duplicate FK constraint names: {fk_names}"
            )

    def test_contract_party_references_contract_customer_bank_ocr(self) -> None:
        assert _fk_targets("contract_party", "contract_id") == {"contract.id"}
        assert _fk_targets("contract_party", "customer_id") == {"customer.id"}
        assert _fk_targets("contract_party", "bank_account_id") == {"bank_account.id"}
        assert _fk_targets("contract_party", "ocr_session_id") == {"ocr_session.id"}

    def test_contract_document_references_contract(self) -> None:
        assert _fk_targets("contract_document", "contract_id") == {"contract.id"}

    def test_normalization_alias_references_document_type(self) -> None:
        assert _fk_targets("normalization_alias", "document_type_id") == {"document_type.id"}

    def test_job_has_no_hard_foreign_key(self) -> None:
        """⭐ §4.6 (c) — polymorphic target, deliberately not a FK."""
        table = Base.metadata.tables["job"]
        assert len(table.c["target_id"].foreign_keys) == 0


class TestCascadeBehavior:
    def test_ocr_result_cascades_from_session(self) -> None:
        fk = next(iter(Base.metadata.tables["ocr_result"].c["ocr_session_id"].foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_ocr_field_cascades_from_result(self) -> None:
        fk = next(iter(Base.metadata.tables["ocr_field"].c["ocr_result_id"].foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_customer_to_contract_is_restrict(self) -> None:
        """⭐ §4.6 #5 — never hard-delete a customer with contracts."""
        fk = next(iter(Base.metadata.tables["contract"].c["primary_customer_id"].foreign_keys))
        assert fk.ondelete == "RESTRICT"

    def test_template_version_to_contract_is_restrict(self) -> None:
        """⭐ §4.6 #9 — a contract always points at a specific, immutable version."""
        fk = next(iter(Base.metadata.tables["contract"].c["template_version_id"].foreign_keys))
        assert fk.ondelete == "RESTRICT"

    def test_contract_party_cascades_from_contract(self) -> None:
        fk = next(iter(Base.metadata.tables["contract_party"].c["contract_id"].foreign_keys))
        assert fk.ondelete == "CASCADE"


class TestUniqueConstraints:
    def test_ocr_field_unique_per_result_and_key(self) -> None:
        from sqlalchemy import UniqueConstraint

        assert "uq_ocr_field__result_key" in _constraint_names("ocr_field", UniqueConstraint)

    def test_template_version_unique_per_template_and_no(self) -> None:
        from sqlalchemy import UniqueConstraint

        assert "uq_template_version__no" in _constraint_names("template_version", UniqueConstraint)

    def test_contract_party_unique_slot(self) -> None:
        from sqlalchemy import UniqueConstraint

        assert "uq_contract_party__slot" in _constraint_names("contract_party", UniqueConstraint)

    def test_contract_document_unique_per_type(self) -> None:
        from sqlalchemy import UniqueConstraint

        assert "uq_contract_document__type" in _constraint_names("contract_document", UniqueConstraint)


class TestPartialIndexes:
    """Spot-check the §4.7 index strategy — these all rely on `postgresql_where`."""

    def test_customer_id_number_partial_unique(self) -> None:
        assert "uq_customer__id_number" in _index_names("customer")

    def test_customer_securities_account_partial_unique(self) -> None:
        assert "uq_customer__securities_account" in _index_names("customer")

    def test_job_dispatch_index(self) -> None:
        assert "ix_job__dispatch" in _index_names("job")

    def test_job_stale_index(self) -> None:
        assert "ix_job__stale" in _index_names("job")

    def test_card_image_uploader_sha_dedup_index(self) -> None:
        assert "uq_card_image__uploader_sha" in _index_names("card_image")

    def test_bank_account_one_primary_index(self) -> None:
        assert "uq_bank_account__one_primary" in _index_names("bank_account")

    def test_contract_party_one_primary_index(self) -> None:
        assert "uq_contract_party__one_primary" in _index_names("contract_party")


class TestCheckConstraints:
    def test_customer_issue_place_check_exists(self) -> None:
        from sqlalchemy import CheckConstraint

        names = _constraint_names("customer", CheckConstraint)
        assert any("issue_place" in n for n in names)

    def test_contract_no_self_supersede_check_exists(self) -> None:
        from sqlalchemy import CheckConstraint

        names = _constraint_names("contract", CheckConstraint)
        assert any("no_self_supersede" in n for n in names)

    def test_contract_party_entity_type_check_exists(self) -> None:
        """⭐ v1.0 restricts entity_type to INDIVIDUAL only (ADR-16 hinge)."""
        from sqlalchemy import CheckConstraint

        names = _constraint_names("contract_party", CheckConstraint)
        assert any("entity_type" in n for n in names)


class TestEncryptedColumns:
    """Every `_enc` column must be a binary type, never text — see §4.8.2."""

    def test_customer_encrypted_columns_are_binary(self) -> None:
        from sqlalchemy import LargeBinary

        table = Base.metadata.tables["customer"]
        for column_name in ("id_number_enc", "date_of_birth_enc", "address_enc"):
            assert isinstance(table.c[column_name].type, LargeBinary)

    def test_customer_plaintext_search_columns_are_string(self) -> None:
        from sqlalchemy import String

        table = Base.metadata.tables["customer"]
        for column_name in ("full_name", "phone", "email"):
            assert isinstance(table.c[column_name].type, String)


class TestOptimisticLock:
    def test_only_contract_has_version_column(self) -> None:
        """⭐ DB-09 — the only table with an optimistic-lock `version` column."""
        tables_with_version = {
            name for name, table in Base.metadata.tables.items() if "version" in table.c
        }
        # `template_version` has a `version_no` column, not `version` — excluded correctly.
        assert tables_with_version == {"contract"}
