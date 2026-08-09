"""Template inspection outcome (§4.3.3 `TemplateValidationStatus`, `template_version.validation_status`)."""
from enum import Enum


class TemplateValidationStatus(str, Enum):
    """Result of `TemplateInspector.inspect()` for a template version."""

    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
