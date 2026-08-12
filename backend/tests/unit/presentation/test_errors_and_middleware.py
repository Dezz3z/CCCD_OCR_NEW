"""The error envelope (§5.1.4), the code table (§5.1.5) and the two middlewares.

⚠️ Built on a bare `FastAPI()` rather than `create_app()`. `create_app`'s
lifespan constructs the real `Container` — DPAPI key, database engine, job
runner — which would make these unit tests need a machine, and would test the
wiring rather than the envelope.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cocas.domain.exceptions import (
    BusinessRuleViolation,
    DecryptionError,
    DuplicateEntityError,
    EntityNotFound,
    InsufficientStorageError,
    NotADocxFileError,
    OcrEngineUnavailableError,
    PathTraversalError,
    ValidationError,
)
from cocas.presentation.errors import register_exception_handlers, spec_for
from cocas.presentation.middlewares.correlation_id import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
)
from cocas.presentation.middlewares.local_token import (
    LOCAL_TOKEN_HEADER,
    LocalTokenMiddleware,
)

_TOKEN = "s3cret-handshake-token"


def _app(*, token: str = "") -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/boom/{code}")
    async def boom(code: str) -> dict[str, str]:
        raise {
            "not_found": EntityNotFound("Không tìm thấy.", details={"id": "x"}),
            "validation": ValidationError("Sai định dạng.", field="id_number"),
            "rule": BusinessRuleViolation("Không làm được.", code="RULE"),
            "duplicate": DuplicateEntityError("Đã có.", code="DUPLICATE_ENTITY"),
            "docx": NotADocxFileError("Không phải .docx."),
            "engine": OcrEngineUnavailableError("Chưa sẵn sàng."),
            "disk": InsufficientStorageError("Hết đĩa."),
            "traversal": PathTraversalError("Đường dẫn lạ."),
            "crypto": DecryptionError("Không giải mã được."),
            "hinted": BusinessRuleViolation(
                "Có gợi ý riêng.", code="RULE", hint="Làm thế này."
            ),
        }[code]

    @app.get("/api/v1/explode")
    async def explode() -> dict[str, str]:
        raise RuntimeError(r"SELECT * FROM customer WHERE C:\secret\path")

    if token:
        app.add_middleware(LocalTokenMiddleware, token=token)
    app.add_middleware(CorrelationIdMiddleware)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


class TestEnvelopeShape:
    def test_every_required_field_is_present(self, client: TestClient) -> None:
        body = client.get("/api/v1/boom/not_found").json()["error"]
        for key in ("code", "type", "message", "hint", "correlation_id", "timestamp"):
            assert body[key], f"missing {key}"
        assert body["retryable"] is False

    def test_hint_always_answers_what_to_do_now(self, client: TestClient) -> None:
        """⭐ §5.1.4 — an error with no next step is half an error."""
        for code in ("not_found", "validation", "rule", "docx", "engine", "disk"):
            hint = client.get(f"/api/v1/boom/{code}").json()["error"]["hint"]
            assert hint and len(hint) > 10, code

    def test_the_exceptions_own_hint_wins(self, client: TestClient) -> None:
        body = client.get("/api/v1/boom/hinted").json()["error"]
        assert body["hint"] == "Làm thế này."

    def test_context_becomes_details(self, client: TestClient) -> None:
        details = client.get("/api/v1/boom/not_found").json()["error"]["details"]
        assert {"field": "id", "message": "x"} in details

    def test_a_field_scoped_error_names_the_field(self, client: TestClient) -> None:
        details = client.get("/api/v1/boom/validation").json()["error"]["details"]
        assert any(item["field"] == "id_number" for item in details)


class TestStatusMapping:
    @pytest.mark.parametrize(
        ("path", "status", "code"),
        [
            ("not_found", 404, "COCAS-5001"),
            ("validation", 422, "COCAS-2002"),
            ("rule", 422, "COCAS-7002"),
            ("duplicate", 409, "COCAS-5002"),
            ("docx", 400, "COCAS-6002"),
            ("engine", 503, "COCAS-4007"),
            ("disk", 507, "COCAS-8003"),
            ("traversal", 400, "COCAS-8002"),
            ("crypto", 500, "COCAS-8004"),
        ],
    )
    def test_maps_to_the_documented_status_and_code(
        self, client: TestClient, path: str, status: int, code: str
    ) -> None:
        response = client.get(f"/api/v1/boom/{path}")
        assert response.status_code == status
        assert response.json()["error"]["code"] == code

    def test_a_retryable_error_says_so(self, client: TestClient) -> None:
        assert client.get("/api/v1/boom/engine").json()["error"]["retryable"] is True

    def test_an_unknown_domain_code_still_gets_a_sane_envelope(self) -> None:
        """A new `DomainException` subclass falls back to its nearest ancestor."""

        class NewlyInvented(BusinessRuleViolation):
            code = "SOMETHING_NOBODY_MAPPED"

        assert spec_for(NewlyInvented("x")).http_status == 422


class TestUnhandledLeaksNothing:
    def test_the_message_carries_no_sql_and_no_paths(self, client: TestClient) -> None:
        """⭐ §5.5 #5 — the traceback goes to the log, the id goes to the user."""
        body = client.get("/api/v1/explode").json()["error"]
        assert "SELECT" not in body["message"]
        assert "C:\\" not in body["message"]
        assert body["code"] == "COCAS-8005"
        assert uuid.UUID(body["correlation_id"])


class TestCorrelationId:
    def test_a_client_supplied_uuid_is_echoed(self, client: TestClient) -> None:
        supplied = str(uuid.uuid4())
        response = client.get(
            "/api/v1/boom/not_found", headers={CORRELATION_ID_HEADER: supplied}
        )
        assert response.headers[CORRELATION_ID_HEADER] == supplied
        assert response.json()["error"]["correlation_id"] == supplied

    def test_a_non_uuid_is_replaced_not_passed_through(
        self, client: TestClient
    ) -> None:
        """⚠️ The value lands in a log file and a response header."""
        response = client.get(
            "/api/v1/boom/not_found",
            headers={CORRELATION_ID_HEADER: "not-a-uuid-with\nnewline"},
        )
        assert uuid.UUID(response.headers[CORRELATION_ID_HEADER])

    def test_one_is_minted_when_absent(self, client: TestClient) -> None:
        response = client.get("/health")
        assert uuid.UUID(response.headers[CORRELATION_ID_HEADER])


class TestLocalToken:
    def test_a_request_without_the_token_is_refused(self) -> None:
        with TestClient(_app(token=_TOKEN)) as client:
            response = client.get("/api/v1/boom/not_found")
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "COCAS-1007"

    def test_a_wrong_token_is_refused(self) -> None:
        with TestClient(_app(token=_TOKEN)) as client:
            response = client.get(
                "/api/v1/boom/not_found", headers={LOCAL_TOKEN_HEADER: "wrong"}
            )
            assert response.status_code == 403

    def test_the_right_token_passes_through(self) -> None:
        with TestClient(_app(token=_TOKEN)) as client:
            response = client.get(
                "/api/v1/boom/not_found", headers={LOCAL_TOKEN_HEADER: _TOKEN}
            )
            assert response.status_code == 404

    def test_the_liveness_probe_is_exempt(self) -> None:
        """⭐ The supervisor polls this to decide whether to restart us."""
        with TestClient(_app(token=_TOKEN)) as client:
            assert client.get("/health").status_code == 200

    def test_the_rejection_still_carries_a_correlation_id(self) -> None:
        with TestClient(_app(token=_TOKEN)) as client:
            body = client.get("/api/v1/boom/not_found").json()["error"]
            assert uuid.UUID(body["correlation_id"])
