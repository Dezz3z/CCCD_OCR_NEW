"""One error envelope for the whole API (§5.1.4) and the §5.1.5 code table.

Two rules this module exists to enforce, both from §5.5 #5:

  * **Nothing technical reaches the user.** Absolute paths, table names and
    stack traces stay in the log; the response carries a `correlation_id` that
    finds them. `_unhandled()` is where that is decided, and it deliberately
    ignores `str(exc)`.
  * ⭐ **Every error answers "what do I do now?"** — `hint` is not optional
    padding. An error that only says what went wrong leaves the user staring
    at a screen with a customer in front of them (P-08).

`retryable` is machine-readable on purpose: the SPA retries with backoff
without asking, and `False` means "retrying will produce this same answer".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from cocas.domain.exceptions import (
    BusinessRuleViolation,
    CryptoError,
    DomainException,
    DuplicateEntityError,
    EntityNotFound,
    InsufficientStorageError,
    OcrEngineUnavailableError,
    OcrProcessingError,
    PathTraversalError,
    PersistenceError,
    StorageError,
    ValidationError,
)
from cocas.presentation.middlewares.correlation_id import current_correlation_id


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """One row of §5.1.5: the code, the HTTP status, and what to tell the user."""

    code: str
    http_status: int
    type: str
    message: str
    hint: str
    retryable: bool = False


#: ⭐ Keyed by `DomainException.code` — the Domain's own vocabulary — so a Use
#: Case never has to know an HTTP status or a `COCAS-` number. That mapping is
#: a Presentation concern and lives here alone.
_BY_DOMAIN_CODE: dict[str, ErrorSpec] = {
    "VALIDATION_ERROR": ErrorSpec(
        "COCAS-2002", 422, "VALIDATION_ERROR",
        "Dữ liệu không hợp lệ.",
        "Kiểm tra lại các trường được đánh dấu và thử lại.",
    ),
    "ENTITY_NOT_FOUND": ErrorSpec(
        "COCAS-5001", 404, "NOT_FOUND",
        "Không tìm thấy dữ liệu yêu cầu.",
        "Tải lại danh sách — mục này có thể đã bị xoá.",
    ),
    "BUSINESS_RULE_VIOLATION": ErrorSpec(
        "COCAS-7002", 422, "BUSINESS_RULE_VIOLATION",
        "Thao tác không thực hiện được với dữ liệu hiện tại.",
        "Xem chi tiết bên dưới để biết cần sửa gì.",
    ),
    "DUPLICATE_ENTITY": ErrorSpec(
        "COCAS-5002", 409, "CONFLICT",
        "Dữ liệu đã tồn tại trong hệ thống.",
        "Mở bản ghi đã có thay vì tạo mới.",
    ),
    "DUPLICATE_ID_NUMBER": ErrorSpec(
        "COCAS-5002", 409, "CONFLICT",
        "Số CCCD này đã có trong hệ thống.",
        "Mở hồ sơ khách hàng đã có thay vì tạo mới.",
    ),
    "DUPLICATE_CARD_IMAGE": ErrorSpec(
        "COCAS-3007", 409, "IMAGE_ERROR",
        "Ảnh này đã được tải lên trước đó.",
        "Dùng lại ảnh đã có, hoặc chọn ảnh khác.",
    ),
    "TEMPLATE_NOT_FOUND": ErrorSpec(
        "COCAS-6007", 422, "TEMPLATE_ERROR",
        "File mẫu hợp đồng không còn trên đĩa.",
        "Vào Cài đặt → Mẫu hợp đồng và tải lại file mẫu.",
    ),
    "TEMPLATE_CHECKSUM_MISMATCH": ErrorSpec(
        "COCAS-6006", 422, "TEMPLATE_ERROR",
        "File mẫu đã bị thay đổi so với lúc đăng ký.",
        "Tải lại mẫu như một phiên bản mới để hệ thống ghi nhận thay đổi.",
    ),
    "NOT_A_DOCX_FILE": ErrorSpec(
        "COCAS-6002", 400, "TEMPLATE_ERROR",
        "File tải lên không phải tài liệu Word (.docx) hợp lệ.",
        "Mở file bằng Word rồi 'Save As' lại dưới định dạng .docx.",
    ),
    "TEMPLATE_SYNTAX_ERROR": ErrorSpec(
        "COCAS-6003", 422, "TEMPLATE_ERROR",
        "Cú pháp trong file mẫu không hợp lệ.",
        "Kiểm tra các cặp {{ }} và {% %} tại đoạn văn được chỉ ra.",
    ),
    "RENDER_ERROR": ErrorSpec(
        "COCAS-7003", 500, "DOCUMENT_ERROR",
        "Không tạo được file hợp đồng.",
        "Thử lại; nếu vẫn lỗi, kiểm tra lại file mẫu trong Cài đặt.",
        retryable=True,
    ),
    "DOCUMENT_INTEGRITY_MISMATCH": ErrorSpec(
        "COCAS-7009", 500, "DOCUMENT_ERROR",
        "File hợp đồng trên đĩa không khớp với bản đã ghi nhận.",
        "Sinh lại hợp đồng này; bản cũ không còn tin cậy được.",
    ),
    "OCR_ENGINE_UNAVAILABLE": ErrorSpec(
        "COCAS-4007", 503, "OCR_ERROR",
        "Bộ nhận dạng chưa sẵn sàng.",
        "Đợi vài giây rồi thử lại — hệ thống đang nạp mô hình nhận dạng.",
        retryable=True,
    ),
    "OCR_TIMEOUT": ErrorSpec(
        "COCAS-4006", 422, "OCR_ERROR",
        "Quá thời gian xử lý ảnh.",
        "Chụp lại ảnh rõ hơn, hoặc nhập tay các trường cần thiết.",
        retryable=True,
    ),
    "OCR_PROCESSING_ERROR": ErrorSpec(
        "COCAS-4006", 422, "OCR_ERROR",
        "Không đọc được thông tin từ ảnh.",
        "Chụp lại với đủ ánh sáng, giữ thẻ phẳng và nằm trọn trong khung.",
    ),
    "IMAGE_DECODE_ERROR": ErrorSpec(
        "COCAS-3004", 400, "IMAGE_ERROR",
        "File ảnh bị hỏng hoặc không đọc được.",
        "Chọn ảnh khác, hoặc chụp lại.",
    ),
    "IMAGE_TOO_SMALL": ErrorSpec(
        "COCAS-3005", 422, "IMAGE_ERROR",
        "Ảnh có kích thước ngoài phạm vi cho phép.",
        "Chụp lại gần hơn để thẻ chiếm phần lớn khung hình.",
    ),
    "INSUFFICIENT_STORAGE": ErrorSpec(
        "COCAS-8003", 507, "SYSTEM_ERROR",
        "Ổ đĩa không còn đủ dung lượng trống.",
        "Giải phóng ít nhất 500 MB rồi thử lại.",
    ),
    "PATH_TRAVERSAL": ErrorSpec(
        "COCAS-8002", 400, "SYSTEM_ERROR",
        "Yêu cầu không hợp lệ.",
        "Tải lại trang và thử lại.",
    ),
    "STORAGE_ERROR": ErrorSpec(
        "COCAS-8002", 500, "SYSTEM_ERROR",
        "Lỗi truy cập tệp trên đĩa.",
        "Kiểm tra ổ đĩa còn dung lượng và thư mục dữ liệu không bị khoá bởi ứng dụng khác.",
        retryable=True,
    ),
    "VAULT_FILE_NOT_FOUND": ErrorSpec(
        "COCAS-7008", 404, "DOCUMENT_ERROR",
        "Tài liệu chưa sẵn sàng hoặc không còn tồn tại.",
        "Mở lại hợp đồng để kiểm tra trạng thái.",
    ),
    "DECRYPTION_ERROR": ErrorSpec(
        "COCAS-8004", 500, "SYSTEM_ERROR",
        "Không giải mã được dữ liệu.",
        "Khởi động lại ứng dụng; nếu vẫn lỗi, khôi phục từ bản sao lưu gần nhất.",
    ),
    "KEY_UNAVAILABLE": ErrorSpec(
        "COCAS-8004", 500, "SYSTEM_ERROR",
        "Không truy cập được khoá mã hoá.",
        "Đăng nhập lại Windows bằng đúng tài khoản đã cài đặt ứng dụng.",
    ),
    "PERSISTENCE_ERROR": ErrorSpec(
        "COCAS-8001", 500, "SYSTEM_ERROR",
        "Lỗi cơ sở dữ liệu.",
        "Thử lại sau giây lát; nếu vẫn lỗi, khởi động lại ứng dụng.",
        retryable=True,
    ),
}

_UNHANDLED = ErrorSpec(
    "COCAS-8005", 500, "INTERNAL_ERROR",
    "Đã xảy ra lỗi không mong muốn.",
    "Thử lại; nếu lặp lại, gửi mã tham chiếu bên dưới cho bộ phận hỗ trợ.",
)

_REQUEST_VALIDATION = ErrorSpec(
    "COCAS-2001", 422, "VALIDATION_ERROR",
    "Dữ liệu gửi lên không hợp lệ.",
    "Kiểm tra lại các trường được liệt kê bên dưới.",
)

#: Domain exception classes whose `code` is not in the table above fall back to
#: the nearest ancestor listed here — so a new subclass gets a sane envelope
#: instead of a 500 the day it is added.
_FALLBACK_BY_TYPE: tuple[tuple[type[DomainException], str], ...] = (
    (PathTraversalError, "PATH_TRAVERSAL"),
    (InsufficientStorageError, "INSUFFICIENT_STORAGE"),
    (DuplicateEntityError, "DUPLICATE_ENTITY"),
    (EntityNotFound, "ENTITY_NOT_FOUND"),
    (ValidationError, "VALIDATION_ERROR"),
    (BusinessRuleViolation, "BUSINESS_RULE_VIOLATION"),
    (OcrEngineUnavailableError, "OCR_ENGINE_UNAVAILABLE"),
    (OcrProcessingError, "OCR_PROCESSING_ERROR"),
    (StorageError, "STORAGE_ERROR"),
    (CryptoError, "DECRYPTION_ERROR"),
    (PersistenceError, "PERSISTENCE_ERROR"),
)


def spec_for(exc: DomainException) -> ErrorSpec:
    """The §5.1.5 row for one domain exception."""
    found = _BY_DOMAIN_CODE.get(exc.code)
    if found is not None:
        return found
    for exception_type, code in _FALLBACK_BY_TYPE:
        if isinstance(exc, exception_type):
            fallback = _BY_DOMAIN_CODE.get(code)
            if fallback is not None:
                return fallback
    return _UNHANDLED


def envelope(
    spec: ErrorSpec,
    *,
    message: str | None = None,
    hint: str | None = None,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the §5.1.4 body."""
    return {
        "error": {
            "code": spec.code,
            "type": spec.type,
            "message": message or spec.message,
            # ⭐ The exception's own hint wins. Many `DomainException`s already
            # carry a `hint=` written next to the rule that raised them, and
            # that one knows the specific situation; the table's line is the
            # generic fallback for the ones that do not.
            "hint": hint or spec.hint,
            "details": details or [],
            "correlation_id": current_correlation_id(),
            "timestamp": datetime.now(UTC).isoformat(),
            "retryable": spec.retryable,
        }
    }


def _detail_list(exc: DomainException) -> list[dict[str, Any]]:
    """Turn the exception's context into the envelope's `details` array.

    ⚠️ Reads `DomainException.context`, not a `.details` attribute — there is
    no such attribute. `__init__` collects `**context`, so a call written
    `EntityNotFound(..., details={"id": x})` lands as `context["details"]`,
    one level deeper than it looks. That nesting is unwrapped here rather than
    at ~30 call sites.

    Only keys a Use Case chose to pass are exposed. Nothing is scraped off the
    exception object itself (§5.5 #5).
    """
    context = getattr(exc, "context", None)
    if not isinstance(context, dict):
        return []

    raw: dict[str, Any] = {}
    for key, value in context.items():
        if key == "details" and isinstance(value, dict):
            raw.update(value)
        else:
            raw[key] = value

    out: list[dict[str, Any]] = []
    for key, value in raw.items():
        if key == "diagnostics" and isinstance(value, list):
            out.extend(item for item in value if isinstance(item, dict))
        else:
            out.append({"field": key, "message": str(value)})
    if exc.field:
        out.append({"field": exc.field, "message": exc.message})
    return out


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the three handlers every route relies on."""

    @app.exception_handler(DomainException)
    async def _domain(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainException)
        spec = spec_for(exc)
        logger.warning(
            "domain error",
            error_code=spec.code,
            domain_code=exc.code,
            exception=type(exc).__name__,
        )
        # ⭐ `str(exc)` IS shown here, unlike the unhandled path: every
        # `DomainException` message in this codebase is written in Vietnamese
        # for the end user (project convention), and it is more specific than
        # the table's generic line.
        return JSONResponse(
            status_code=spec.http_status,
            content=envelope(
                spec,
                message=str(exc) or None,
                hint=exc.hint,
                details=_detail_list(exc),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
                "code": str(error.get("type", "")),
                "message": str(error.get("msg", "")),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=_REQUEST_VALIDATION.http_status,
            content=envelope(_REQUEST_VALIDATION, details=details),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # ⭐ `str(exc)` is deliberately absent from the response. An unexpected
        # exception's text is written for a developer and routinely contains
        # absolute paths, SQL and table names (§5.5 #5). It goes to the log,
        # findable by the correlation id the user is shown.
        logger.opt(exception=exc).error(
            "unhandled error", exception=type(exc).__name__
        )
        return JSONResponse(
            status_code=_UNHANDLED.http_status, content=envelope(_UNHANDLED)
        )
