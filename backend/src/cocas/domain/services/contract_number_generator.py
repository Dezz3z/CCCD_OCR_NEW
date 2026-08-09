"""ContractNumberGenerator — formats `contract_no_pattern` templates (§4.4.8/§4.4.10).

Pure formatting: this service does NOT own or increment the sequence
counter — that is `Template.next_contract_sequence()`, called by the
Application layer inside a `SELECT ... FOR UPDATE` (DB-09). This service
only knows how to turn `(pattern, date, sequence)` into a string.

Only 3 tokens appear anywhere in the docs/design examples:
`{yyyy}`, `{MM}`, `{seq:0Nd}` (e.g. `01A-GDN-{yyyy}{MM}-{seq:05d}` →
`01A-GDN-202608-00042`). The literal prefix (`01A-GDN`, `01A-KQ`) is part of
the pattern string itself, not a token.
"""
from __future__ import annotations

import re
from datetime import date

from cocas.domain.exceptions import BusinessRuleViolation

_TOKEN_YEAR = "{yyyy}"
_TOKEN_MONTH = "{MM}"
_SEQ_TOKEN_PATTERN = re.compile(r"\{seq:0(\d+)d\}")
_ANY_BRACE_PATTERN = re.compile(r"\{[^}]*\}")


class ContractNumberGenerator:
    """Domain Service — format a contract number from its template pattern."""

    def generate(self, pattern: str, on: date, sequence: int) -> str:
        if not pattern:
            raise BusinessRuleViolation(
                "Mẫu số hợp đồng không được để trống.", code="EMPTY_CONTRACT_NO_PATTERN"
            )
        if sequence < 0:
            raise BusinessRuleViolation(
                "Số thứ tự hợp đồng không được âm.", code="NEGATIVE_CONTRACT_SEQUENCE"
            )

        result = pattern.replace(_TOKEN_YEAR, f"{on.year:04d}")
        result = result.replace(_TOKEN_MONTH, f"{on.month:02d}")
        result = _SEQ_TOKEN_PATTERN.sub(lambda m: str(sequence).zfill(int(m.group(1))), result)

        leftover = _ANY_BRACE_PATTERN.search(result)
        if leftover is not None:
            raise BusinessRuleViolation(
                f"Mẫu số hợp đồng chứa token không hỗ trợ: '{leftover.group(0)}'.",
                code="UNSUPPORTED_CONTRACT_NO_TOKEN",
            )
        return result
