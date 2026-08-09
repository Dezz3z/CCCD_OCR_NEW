"""BankAccountNumber value object (§8.3.4)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError

_DIGITS_ONLY = re.compile(r"\D")
_PATTERN = re.compile(r"^\d{6,20}$")


@dataclass(frozen=True, slots=True)
class BankAccountNumber:
    """A validated bank account number — digits only, 6 to 20 characters long.

    The exact allowed length range for a *specific* bank comes from
    `bank_directory` (a CSDL table), so it cannot be a static domain
    invariant. `matches_bank_length()` lets a caller check that once it has
    looked up the bank's `account_min_len`/`account_max_len`.
    """

    value: str

    def __post_init__(self) -> None:
        if not _PATTERN.match(self.value):
            raise ValidationError(
                "Số tài khoản chỉ được chứa chữ số.",
                code="INVALID_BANK_ACCOUNT_NUMBER",
                field="bank_account_number",
            )

    @classmethod
    def from_raw(cls, raw: str) -> BankAccountNumber:
        """Strip every non-digit character before validating."""
        return cls(_DIGITS_ONLY.sub("", raw or ""))

    def matches_bank_length(self, min_len: int, max_len: int) -> bool:
        """Whether this account number's length fits the given bank's range."""
        return min_len <= len(self.value) <= max_len

    def __str__(self) -> str:
        return self.value
