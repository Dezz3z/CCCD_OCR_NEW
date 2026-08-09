"""Outcome of a logged action (§4.3.3 `Outcome`, `activity_log.outcome`)."""
from enum import Enum


class ActivityOutcome(str, Enum):
    """Whether a logged activity succeeded or failed."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
