"""Tests for FastAPI app factory, CORS, and exception handlers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings, Environment
from app.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    LabLinkError,
    NotFoundError,
    ParseError,
    StateTransitionError,
    ValidationError,
)
from app.main import create_app
from app.schemas.envelope import Envelope, ErrorDetail, ResponseMeta


# ── App Factory ──────────────────────────────────────────────


class TestAppFactory:
    def test_create_app_returns_fastapi(self, app):
        assert isinstance(app, FastAPI)

    def test_app_title(self, app):
        assert app.title == "LabLink"

    def test_app_version(self, app):
        assert app.version == "0.1.0"

    def test_docs_enabled_in_dev(self, test_settings):
        test_settings.environment = Environment.dev
        app = create_app(settings=test_settings)
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"

    def test_docs_disabled_in_production(self, test_settings):
        test_settings.environment = Environment.production
        app = create_app(settings=test_settings)
        assert app.docs_url is None
        assert app.redoc_url is None


# ── Health Endpoint ──────────────────────────────────────────


class TestHealthEndpoint:
    async def test_health_returns_envelope(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert body["data"]["status"] == "healthy"
        assert body["errors"] == []

    async def test_root_returns_envelope(self, client):
        resp = await client.get("/api/v1/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["name"] == "LabLink"
        assert "docs" in body["data"]


# ── CORS ─────────────────────────────────────────────────────


class TestCORS:
    async def test_cors_allows_configured_origin(self, client):
        resp = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    async def test_cors_rejects_unconfigured_origin(self, client):
        resp = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware won't add the header for non-allowed origins
        assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"


# ── Request ID Middleware ────────────────────────────────────


class TestRequestID:
    async def test_response_has_request_id(self, client):
        resp = await client.get("/api/v1/health")
        assert "x-request-id" in resp.headers

    async def test_custom_request_id_echoed(self, client):
        resp = await client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "custom-123"},
        )
        assert resp.headers["x-request-id"] == "custom-123"


# ── Exception Handlers ──────────────────────────────────────


class TestExceptionHandlers:
    async def test_404_returns_envelope(self, client):
        resp = await client.get("/api/v1/nonexistent")
        assert resp.status_code in (404, 405)
        body = resp.json()
        assert "data" in body
        assert "errors" in body
        assert len(body["errors"]) > 0
        assert "suggestion" in body["errors"][0]

    async def test_lablink_error_returns_envelope(self, app, test_settings):
        """Register a test route that raises LabLinkError and verify envelope response."""

        @app.get("/api/v1/test-not-found")
        async def raise_not_found():
            raise NotFoundError(message="Experiment not found")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/test-not-found")

        assert resp.status_code == 404
        body = resp.json()
        assert body["data"] is None
        assert body["errors"][0]["code"] == "not_found"
        assert body["errors"][0]["message"] == "Experiment not found"
        assert body["errors"][0]["suggestion"] is not None

    async def test_conflict_error_returns_envelope(self, app):
        @app.get("/api/v1/test-conflict")
        async def raise_conflict():
            raise ConflictError(message="Duplicate upload")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/test-conflict")

        assert resp.status_code == 409
        body = resp.json()
        assert body["errors"][0]["code"] == "conflict"

    async def test_auth_error_returns_envelope(self, app):
        @app.get("/api/v1/test-auth")
        async def raise_auth():
            raise AuthenticationError()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/test-auth")

        assert resp.status_code == 401
        body = resp.json()
        assert body["errors"][0]["code"] == "authentication_error"
        assert "Bearer" in body["errors"][0]["suggestion"]

    async def test_validation_error_has_field_suggestions(self, app):
        """FastAPI validation errors return envelope with per-field suggestions."""
        from pydantic import BaseModel

        class TestBody(BaseModel):
            name: str
            count: int

        @app.post("/api/v1/test-validation")
        async def validate_body(body: TestBody):
            return body

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/test-validation",
                json={"name": 123},  # missing count, wrong type
            )

        assert resp.status_code == 422
        body = resp.json()
        assert body["data"] is None
        assert len(body["errors"]) >= 1
        for err in body["errors"]:
            assert "suggestion" in err
            assert err["suggestion"] is not None

    async def test_unhandled_exception_returns_500_envelope(self, app):
        @app.get("/api/v1/test-crash")
        async def crash():
            raise RuntimeError("Unexpected boom")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/test-crash")

        assert resp.status_code == 500
        body = resp.json()
        assert body["errors"][0]["code"] == "internal_error"
        assert body["errors"][0]["suggestion"] is not None

    async def test_parse_error_returns_envelope(self, app):
        @app.get("/api/v1/test-parse-error")
        async def raise_parse():
            raise ParseError(message="Invalid CSV header")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/test-parse-error")

        assert resp.status_code == 422
        body = resp.json()
        assert body["errors"][0]["code"] == "parse_error"

    async def test_state_transition_error(self, app):
        @app.get("/api/v1/test-state-error")
        async def raise_state():
            raise StateTransitionError(
                message="Cannot go from completed to running",
                suggestion="Valid transitions from 'completed': none.",
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/test-state-error")

        assert resp.status_code == 409
        body = resp.json()
        assert body["errors"][0]["code"] == "invalid_state_transition"
        assert "completed" in body["errors"][0]["suggestion"]


# ── Envelope Schema ──────────────────────────────────────────


class TestEnvelopeSchema:
    def test_ok_envelope(self):
        env = Envelope.ok({"key": "value"}, request_id="req-1")
        assert env.data == {"key": "value"}
        assert env.meta.request_id == "req-1"
        assert env.errors == []

    def test_error_envelope(self):
        env = Envelope.single_error(
            code="test_error",
            message="Something failed",
            suggestion="Try again",
        )
        assert env.data is None
        assert len(env.errors) == 1
        assert env.errors[0].suggestion == "Try again"

    def test_envelope_serialization(self):
        env = Envelope.ok({"x": 1})
        data = env.model_dump(mode="json")
        assert "data" in data
        assert "meta" in data
        assert "errors" in data
        assert data["meta"]["timestamp"] is not None

    def test_paginated_envelope(self):
        env = Envelope.ok([1, 2, 3], page=1, page_size=10, total=100)
        assert env.meta.page == 1
        assert env.meta.page_size == 10
        assert env.meta.total == 100


# ── Exception Hierarchy ──────────────────────────────────────


class TestExceptionHierarchy:
    def test_all_errors_inherit_from_lablink_error(self):
        errors = [
            NotFoundError(),
            ConflictError(),
            ValidationError(),
            AuthenticationError(),
            AuthorizationError(),
            ParseError(),
            StateTransitionError(),
        ]
        for err in errors:
            assert isinstance(err, LabLinkError)
            assert err.message
            assert err.code
            assert err.status_code > 0

    def test_errors_have_default_suggestions(self):
        errors = [
            NotFoundError(),
            ConflictError(),
            AuthenticationError(),
            AuthorizationError(),
            ParseError(),
        ]
        for err in errors:
            assert err.suggestion is not None, f"{type(err).__name__} missing default suggestion"
