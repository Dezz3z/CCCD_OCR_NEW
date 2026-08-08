"""Domain layer business exceptions hierarchy."""


class DomainException(Exception):
    """Base exception for all domain business errors."""

    code: str = "UNKNOWN_ERROR"
    message: str = "An unknown domain error occurred"

    def __init__(self, message: str | None = None, **context) -> None:
        """Initialize domain exception."""
        self.context = context
        if message:
            self.message = message
        super().__init__(self.message)


class ValidationError(DomainException):
    """Value validation failed."""

    code = "VALIDATION_ERROR"


class BusinessRuleViolation(DomainException):
    """Business rule was violated."""

    code = "BUSINESS_RULE_VIOLATION"


class EntityNotFound(DomainException):
    """Required entity not found."""

    code = "ENTITY_NOT_FOUND"


class OcrProcessingError(DomainException):
    """OCR processing failed."""

    code = "OCR_PROCESSING_ERROR"


class DocumentGenerationError(DomainException):
    """Document generation failed."""

    code = "DOCUMENT_GENERATION_ERROR"
