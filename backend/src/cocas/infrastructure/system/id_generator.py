"""`IIdGenerator` (Port 17) production implementation — UUIDv7 (DB-01)."""
from __future__ import annotations

import uuid

import uuid_utils


class Uuid7Generator:
    """Client-generated, time-ordered ids — `uuid_utils` implements RFC 9562 UUIDv7.

    Returns a stdlib `uuid.UUID` (not `uuid_utils.UUID`) so every downstream caller
    — SQLAlchemy's `PG_UUID(as_uuid=True)` columns included — sees the type the rest
    of the codebase already expects.
    """

    def new_id(self) -> uuid.UUID:
        return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
