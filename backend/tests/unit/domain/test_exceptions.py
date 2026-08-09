"""Tests for the domain exception hierarchy (§12 'Ném ra' entries)."""
import pytest

from cocas.domain.exceptions import (
    BackupError,
    BusinessRuleViolation,
    CorruptedBackupError,
    CryptoError,
    DatabaseUnavailableError,
    DecryptionError,
    DocumentGenerationError,
    DomainException,
    DuplicateEntityError,
    EntityNotFound,
    ImageDecodeError,
    ImageTooSmallError,
    InsufficientStorageError,
    InvalidPdfOutputError,
    KeyUnavailableError,
    LibreOfficeUnavailableError,
    NotADocxFileError,
    OcrEngineUnavailableError,
    OcrProcessingError,
    OcrTimeoutError,
    OptimisticLockError,
    PathTraversalError,
    PdfConversionTimeoutError,
    PersistenceError,
    RenderError,
    SchemaVersionMismatchError,
    StorageError,
    TemplateChecksumMismatchError,
    TemplateNotFoundError,
    TemplateSyntaxError,
    ValidationError,
    VaultFileNotFoundError,
    WrongPassphraseError,
)


class TestBaseBehavior:
    def test_default_message_and_code(self) -> None:
        exc = DomainException()
        assert exc.code == "UNKNOWN_ERROR"
        assert str(exc) == "An unknown domain error occurred"

    def test_message_override(self) -> None:
        exc = ValidationError("custom message")
        assert str(exc) == "custom message"

    def test_code_override(self) -> None:
        exc = ValidationError("x", code="MY_CODE")
        assert exc.code == "MY_CODE"

    def test_field_and_hint_stored(self) -> None:
        exc = ValidationError("x", field="full_name", hint="check the value")
        assert exc.field == "full_name"
        assert exc.hint == "check the value"

    def test_field_and_hint_default_none(self) -> None:
        exc = ValidationError("x")
        assert exc.field is None
        assert exc.hint is None

    def test_extra_context_captured(self) -> None:
        exc = ValidationError("x", entity_id="abc-123")
        assert exc.context == {"entity_id": "abc-123"}

    def test_all_domain_exceptions_are_exception_subclasses(self) -> None:
        assert issubclass(DomainException, Exception)


class TestHierarchy:
    """Each leaf must chain up to its documented base (§12.x)."""

    @pytest.mark.parametrize(
        ("leaf", "base"),
        [
            (OcrEngineUnavailableError, OcrProcessingError),
            (OcrTimeoutError, OcrProcessingError),
            (ImageDecodeError, OcrProcessingError),
            (ImageTooSmallError, OcrProcessingError),
            (NotADocxFileError, DocumentGenerationError),
            (TemplateSyntaxError, DocumentGenerationError),
            (TemplateNotFoundError, DocumentGenerationError),
            (TemplateChecksumMismatchError, DocumentGenerationError),
            (RenderError, DocumentGenerationError),
            (LibreOfficeUnavailableError, DocumentGenerationError),
            (PdfConversionTimeoutError, DocumentGenerationError),
            (InvalidPdfOutputError, DocumentGenerationError),
            (PathTraversalError, StorageError),
            (VaultFileNotFoundError, StorageError),
            (InsufficientStorageError, StorageError),
            (DecryptionError, CryptoError),
            (KeyUnavailableError, CryptoError),
            (DuplicateEntityError, PersistenceError),
            (DatabaseUnavailableError, PersistenceError),
            (OptimisticLockError, PersistenceError),
            (WrongPassphraseError, BackupError),
            (CorruptedBackupError, BackupError),
            (SchemaVersionMismatchError, BackupError),
            (OcrProcessingError, DomainException),
            (DocumentGenerationError, DomainException),
            (StorageError, DomainException),
            (CryptoError, DomainException),
            (PersistenceError, DomainException),
            (BackupError, DomainException),
            (ValidationError, DomainException),
            (BusinessRuleViolation, DomainException),
            (EntityNotFound, DomainException),
        ],
    )
    def test_is_subclass(self, leaf: type[DomainException], base: type[DomainException]) -> None:
        assert issubclass(leaf, base)

    def test_catching_base_catches_leaf(self) -> None:
        with pytest.raises(OcrProcessingError):
            raise OcrTimeoutError("timed out")

    def test_catching_domain_exception_catches_everything(self) -> None:
        with pytest.raises(DomainException):
            raise DuplicateEntityError("dup")


class TestUniqueCodes:
    def test_every_leaf_has_distinct_code(self) -> None:
        leaves = [
            OcrEngineUnavailableError, OcrTimeoutError, ImageDecodeError, ImageTooSmallError,
            NotADocxFileError, TemplateSyntaxError, TemplateNotFoundError,
            TemplateChecksumMismatchError, RenderError, LibreOfficeUnavailableError,
            PdfConversionTimeoutError, InvalidPdfOutputError, PathTraversalError,
            VaultFileNotFoundError, InsufficientStorageError, DecryptionError,
            KeyUnavailableError, DuplicateEntityError, DatabaseUnavailableError,
            OptimisticLockError, WrongPassphraseError, CorruptedBackupError,
            SchemaVersionMismatchError,
        ]
        codes = [cls.code for cls in leaves]
        assert len(codes) == len(set(codes))


class TestTemplateSyntaxError:
    def test_carries_line_and_detail(self) -> None:
        exc = TemplateSyntaxError(line=42, detail="unexpected '}'")
        assert exc.line == 42
        assert exc.detail == "unexpected '}'"
        assert "42" in str(exc)

    def test_is_document_generation_error(self) -> None:
        assert isinstance(TemplateSyntaxError(line=1, detail="x"), DocumentGenerationError)
