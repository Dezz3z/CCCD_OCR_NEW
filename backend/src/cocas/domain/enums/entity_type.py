"""Contract party entity type (§4.3.3 `EntityType`, `contract_party.entity_type`).

⭐ v1.0 only supports `INDIVIDUAL` — the `contract_party` table and
`party_schema` plumbing already accommodate a future `ORGANIZATION` member
(ADR-16, roadmap §14.7 B1), but that member is deliberately not added until
the Organization model actually ships, per P-10 (Radical Simplicity).
"""
from enum import Enum


class EntityType(str, Enum):
    """The kind of subject a contract party is."""

    INDIVIDUAL = "INDIVIDUAL"
