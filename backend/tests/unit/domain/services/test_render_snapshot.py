"""`render_snapshot` — the canonical form behind `contract.snapshot_sha256`."""
from __future__ import annotations

import hashlib
import json

from cocas.domain.services import render_snapshot


class TestCanonicalBytes:
    def test_key_order_does_not_change_the_bytes(self) -> None:
        """P-09: the same context must hash the same on any run."""
        a = render_snapshot.canonical_bytes({"b": 2, "a": 1})
        b = render_snapshot.canonical_bytes({"a": 1, "b": 2})
        assert a == b

    def test_vietnamese_survives_unescaped(self) -> None:
        """An audit reads the decrypted blob; `\\u1ec5` soup would defeat that."""
        raw = render_snapshot.canonical_bytes({"full_name": "NGUYỄN VĂN AN"})
        assert "NGUYỄN VĂN AN" in raw.decode("utf-8")

    def test_a_changed_value_changes_the_digest(self) -> None:
        before = render_snapshot.digest({"full_name": "A", "amount": 1})
        after = render_snapshot.digest({"full_name": "A", "amount": 2})
        assert before != after

    def test_digest_is_sha256_of_canonical_bytes(self) -> None:
        context = {"x": 1, "y": "ạ"}
        assert (
            render_snapshot.digest(context)
            == hashlib.sha256(render_snapshot.canonical_bytes(context)).digest()
        )

    def test_the_canonical_form_is_the_one_the_repository_encrypts(self) -> None:
        """⚠️ The whole point of the column.

        `SqlAlchemyContractRepository._encrypt_snapshot` calls this same
        helper. If it ever grows its own `json.dumps`, the stored hash stops
        describing the stored blob and "chứng minh snapshot không bị sửa"
        (§4.4.10) becomes a claim with nothing behind it. Spelling the exact
        serialisation out here makes that divergence a test failure.
        """
        context = {"z": "ạ", "a": [1, 2]}
        assert render_snapshot.canonical_bytes(context) == json.dumps(
            context, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
