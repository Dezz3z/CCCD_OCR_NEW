"""Domain layer business exceptions hierarchy.

Every leaf exception here is named to match a "Ném ra" (throws) entry in
docs/design/12-dac-ta-module.md so a Port's docstring and its actual raise
statements stay traceable to the spec table. Infrastructure adapters are
responsible for translating library-specific exceptions (`IntegrityError`,
`OperationalError`, OS `PermissionError`, ...) into one of these — Domain
and Application code must never see a raw infrastructure exception (§12.14).
"""


class DomainException(Exception):
    """Base exception for all domain business errors."""

    code: str = "UNKNOWN_ERROR"
    message: str = "An unknown domain error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        field: str | None = None,
        hint: str | None = None,
        **context: object,
    ) -> None:
        """Initialize domain exception.

        `code` overrides the class-level machine-readable error code so a
        single exception class (e.g. ValidationError) can carry many
        distinct codes (INVALID_LENGTH, INVALID_CHARACTER, ...) as spelled
        out per-field in docs/design/08-validation.md.
        """
        self.context = context
        if code:
            self.code = code
        if message:
            self.message = message
        self.field = field
        self.hint = hint
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


# ============================================================================
# OCR (§12.2 IOcrEngine/IRegionRecognizer, §12.4 IImagePreprocessor)
# ============================================================================


class OcrProcessingError(DomainException):
    """Base for every OCR-pipeline failure."""

    code = "OCR_PROCESSING_ERROR"


class OcrEngineUnavailableError(OcrProcessingError):
    """The OCR engine could not be reached or has not finished warming up."""

    code = "OCR_ENGINE_UNAVAILABLE"


class OcrTimeoutError(OcrProcessingError):
    """Recognition did not complete within the allotted time."""

    code = "OCR_TIMEOUT"


class ImageDecodeError(OcrProcessingError):
    """The supplied bytes could not be decoded as an image."""

    code = "IMAGE_DECODE_ERROR"


class ImageTooSmallError(OcrProcessingError):
    """The image's short edge is below the minimum usable resolution."""

    code = "IMAGE_TOO_SMALL"


# ============================================================================
# Document generation (§12.8 TemplateInspector, §12.11 DocxRenderer)
#
# ⭐ D2.1 — `LibreOfficeUnavailableError`, `PdfConversionTimeoutError` and
# `InvalidPdfOutputError` were removed here together with PDF export
# (§9.13). Rendering the `.docx` is now the last step that can fail.
# ============================================================================


class DocumentGenerationError(DomainException):
    """Base for every template-inspection or DOCX-render failure."""

    code = "DOCUMENT_GENERATION_ERROR"


class NotADocxFileError(DocumentGenerationError):
    """The uploaded file is not a valid `.docx` (bad magic bytes / missing part)."""

    code = "NOT_A_DOCX_FILE"


class TemplateSyntaxError(DocumentGenerationError):
    """Invalid Jinja2 syntax found while scanning a template's AST."""

    code = "TEMPLATE_SYNTAX_ERROR"

    def __init__(self, line: int, detail: str) -> None:
        super().__init__(f"Lỗi cú pháp mẫu ở dòng {line}: {detail}", line=line, detail=detail)
        self.line = line
        self.detail = detail


class TemplateNotFoundError(DocumentGenerationError):
    """The template file referenced by a `TemplateVersion` is missing on disk."""

    code = "TEMPLATE_NOT_FOUND"


class TemplateChecksumMismatchError(DocumentGenerationError):
    """The on-disk template file's SHA-256 no longer matches the CSDL record."""

    code = "TEMPLATE_CHECKSUM_MISMATCH"


class RenderError(DocumentGenerationError):
    """`docxtpl` rendering failed."""

    code = "RENDER_ERROR"


# ============================================================================
# Storage (§12.13 EncryptedFileVault)
# ============================================================================


class StorageError(DomainException):
    """Base for every file-vault failure."""

    code = "STORAGE_ERROR"


class PathTraversalError(StorageError):
    """A resolved path escaped the Vault root — never trust caller-supplied paths."""

    code = "PATH_TRAVERSAL"


class VaultFileNotFoundError(StorageError):
    """The referenced Vault file does not exist."""

    code = "VAULT_FILE_NOT_FOUND"


class InsufficientStorageError(StorageError):
    """Not enough free disk space to safely complete a write."""

    code = "INSUFFICIENT_STORAGE"


# ============================================================================
# Cryptography (§12.17 ICryptoService)
# ============================================================================


class CryptoError(DomainException):
    """Base for every encryption/decryption failure."""

    code = "CRYPTO_ERROR"


class DecryptionError(CryptoError):
    """Decryption failed — the GCM authentication tag did not match."""

    code = "DECRYPTION_ERROR"


class KeyUnavailableError(CryptoError):
    """The KEK has not been loaded (DPAPI unwrap failed or not yet run)."""

    code = "KEY_UNAVAILABLE"


# ============================================================================
# Persistence (§12.14 IReadRepository/IWriteRepository/IUnitOfWork)
# ============================================================================


class PersistenceError(DomainException):
    """Base for every repository/unit-of-work failure.

    Infrastructure repositories MUST translate driver-level exceptions into
    one of these before they reach the Application layer — see §12.14:
    `IntegrityError` → `DuplicateEntityError`, `OperationalError` →
    `DatabaseUnavailableError`.
    """

    code = "PERSISTENCE_ERROR"


class DuplicateEntityError(PersistenceError):
    """A UNIQUE constraint was violated (e.g. duplicate CCCD blind index)."""

    code = "DUPLICATE_ENTITY"


class DatabaseUnavailableError(PersistenceError):
    """The database could not be reached."""

    code = "DATABASE_UNAVAILABLE"


class OptimisticLockError(PersistenceError):
    """`expected_version` did not match the row's current `version` (Contract only)."""

    code = "OPTIMISTIC_LOCK_ERROR"


# ============================================================================
# Backup & restore (§12.16 BackupService)
# ============================================================================


class BackupError(DomainException):
    """Base for every backup/restore failure."""

    code = "BACKUP_ERROR"


class WrongPassphraseError(BackupError):
    """The supplied backup passphrase failed to unwrap the archive's KEK."""

    code = "WRONG_PASSPHRASE"


class CorruptedBackupError(BackupError):
    """The backup archive failed integrity verification."""

    code = "CORRUPTED_BACKUP"


class SchemaVersionMismatchError(BackupError):
    """The backup's `schema_version` is newer than the running application's."""

    code = "SCHEMA_VERSION_MISMATCH"
