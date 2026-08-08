"""Contract status enumeration."""
from enum import Enum


class ContractStatus(str, Enum):
    """Contract lifecycle status."""

    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    SIGNED = "SIGNED"
    ARCHIVED = "ARCHIVED"
