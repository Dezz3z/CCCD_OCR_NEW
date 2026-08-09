"""Customer gender (§4.3.3 `Gender`, `customer.gender`)."""
from enum import Enum


class Gender(str, Enum):
    """A customer's recorded gender."""

    NAM = "NAM"
    NU = "NỮ"
    KHAC = "KHÁC"
    UNKNOWN = "UNKNOWN"
