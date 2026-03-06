"""Integration tests for FastAPI endpoint response envelope format.

Every endpoint must return the Envelope[T] shape: {data, meta, errors}.
Success responses have data + meta, error responses have errors + meta.
All errors include a suggestion field for agent recovery.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. Health / Root endpoints return Envelope
# ---------------------------------------------------------------------------

class TestHealthEndpointEnvelope:
    """Verify health/root endpoints return proper envelope."""

    @pytest.mark.asyncio
    async def test_health_returns_envelope_shape(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()

        # Envelope top-level keys
        assert "data" in body
        assert "meta" in body
        assert "errors" in body

        # Success: data is populated, errors is empty
        assert body["data"] is not None
        assert body["errors"] == []
        assert body["data"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_meta_has_timestamp(self, client):
        resp = await client.get("/api/v1/health")
        body = resp.json()
        assert "timestamp" in body["meta"]
        assert body["meta"]["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_root_returns_envelope(self, client):
        resp = await client.get("/api/v1/")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert body["data"]["name"] == "LabLink"

    @pytest.mark.asyncio
    async def test_response_has_request_id_header(self, client):
        resp = await client.get("/api/v1/health")
        assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_custom_request_id_echoed(self, client):
        custom_id = "test-req-12345"
        resp = await client.get(
            "/api/v1/health",
            headers={"X-Request-ID": custom_id},
        )
        assert resp.headers["x-request-id"] == custom_id


# ---------------------------------------------------------------------------
# 2. 404 errors return envelope with suggestion
# ---------------------------------------------------------------------------

class TestNotFoundEnvelope:
    """Verify 404 errors return envelope with suggestion field."""

    @pytest.mark.asyncio
    async def test_nonexistent_route_returns_envelope(self, client):
        resp = await client.get("/api/v1/nonexistent")
        assert resp.status_code in (404, 405)
        body = resp.json()

        assert "data" in body
        assert "meta" in body
        assert "errors" in body

        assert body["data"] is None
        assert len(body["errors"]) > 0

        error = body["errors"][0]
        assert "code" in error
        assert "message" in error
        assert "suggestion" in error
        assert error["suggestion"] is not None
        assert len(error["suggestion"]) > 0

    @pytest.mark.asyncio
    async def test_nonexistent_experiment_returns_404_with_suggestion(self, client):
        resp = await client.get("/api/v1/experiments/nonexistent-id-xyz")
        assert resp.status_code == 404
        body = resp.json()

        assert body["data"] is None
        assert len(body["errors"]) > 0

        error = body["errors"][0]
        assert error["code"] == "not_found"
        assert "suggestion" in error
        assert error["suggestion"] is not None


# ---------------------------------------------------------------------------
# 3. Validation errors return envelope with field-level suggestions
# ---------------------------------------------------------------------------

class TestValidationErrorEnvelope:
    """Verify validation errors return envelope with per-field suggestions."""

    @pytest.mark.asyncio
    async def test_missing_required_fields_returns_422(self, client):
        """POST to auth/register with empty body should return validation errors."""
        resp = await client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422
        body = resp.json()

        assert body["data"] is None
        assert len(body["errors"]) > 0

        # Each validation error should have a suggestion
        for error in body["errors"]:
            assert error["code"] == "validation_error"
            assert error["suggestion"] is not None
            assert len(error["suggestion"]) > 0

    @pytest.mark.asyncio
    async def test_invalid_email_returns_field_error(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "ValidPass123!",
            "display_name": "Test",
            "org_name": "Test Org",
            "org_slug": "test-org",
        })
        assert resp.status_code == 422
        body = resp.json()

        assert len(body["errors"]) > 0
        # At least one error should reference the email field
        email_errors = [e for e in body["errors"] if e.get("field") and "email" in e["field"]]
        assert len(email_errors) > 0

    @pytest.mark.asyncio
    async def test_short_password_returns_field_error(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "valid@test.com",
            "password": "short",
            "display_name": "Test",
            "org_name": "Test Org",
            "org_slug": "test-org",
        })
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0

    @pytest.mark.asyncio
    async def test_invalid_org_slug_returns_field_error(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "valid@test.com",
            "password": "ValidPass123!",
            "display_name": "Test",
            "org_name": "Test Org",
            "org_slug": "INVALID SLUG WITH SPACES",
        })
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0


# ---------------------------------------------------------------------------
# 4. Domain errors (LabLinkError) return envelope with suggestion
# ---------------------------------------------------------------------------

class TestDomainErrorEnvelope:
    """Verify LabLinkError subclasses produce proper envelopes."""

    @pytest.mark.asyncio
    async def test_conflict_error_on_duplicate_registration(self, client, registered_user):
        """Registering the same email twice should return a conflict error."""
        payload = {
            "email": registered_user["email"],
            "password": "AnotherPass123!",
            "display_name": "Another User",
            "org_name": "Another Org",
            "org_slug": "another-org",
        }
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        body = resp.json()

        assert body["data"] is None
        assert len(body["errors"]) > 0

        error = body["errors"][0]
        assert error["code"] == "conflict"
        assert "suggestion" in error
        assert error["suggestion"] is not None
        # Suggestion should guide the agent
        assert "email" in error["suggestion"].lower() or "log in" in error["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_auth_error_on_wrong_credentials(self, client, registered_user):
        """Login with wrong password should return auth error with suggestion."""
        resp = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": "WrongPassword!123",
        })
        assert resp.status_code == 401
        body = resp.json()

        assert body["data"] is None
        error = body["errors"][0]
        assert error["code"] == "authentication_error"
        assert error["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_state_transition_error_has_suggestion(self, client):
        """Invalid state transition should return suggestion with valid transitions."""
        # Create an experiment
        create_resp = await client.post("/api/v1/experiments", json={
            "name": "Transition Test Experiment",
        })
        assert create_resp.status_code == 201
        exp_id = create_resp.json()["data"]["id"]

        # Try invalid transition: draft -> completed (not allowed)
        resp = await client.post(f"/api/v1/experiments/{exp_id}/transition", json={
            "target_status": "completed",
            "reason": "Trying invalid transition",
        })
        assert resp.status_code == 409
        body = resp.json()

        error = body["errors"][0]
        assert error["code"] == "invalid_state_transition"
        assert error["suggestion"] is not None
        # Suggestion should mention valid transitions
        assert "running" in error["suggestion"].lower() or "cancelled" in error["suggestion"].lower()
