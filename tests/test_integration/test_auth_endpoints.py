"""Integration tests for authentication endpoints.

Tests the full auth flow: register, login, protected endpoints (GET /me),
and JWT token handling through real FastAPI endpoints.
"""

from __future__ import annotations

import uuid

import pytest


class TestRegisterEndpoint:
    """POST /api/v1/auth/register integration tests."""

    @pytest.mark.asyncio
    async def test_register_returns_201_with_envelope(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"new-{uuid.uuid4().hex[:6]}@lablink.io",
                "password": "SecurePass123!",
                "display_name": "New User",
                "org_name": "New Lab",
                "org_slug": f"new-lab-{uuid.uuid4().hex[:6]}",
            },
        )
        assert resp.status_code == 201
        body = resp.json()

        # Envelope shape
        assert body["data"] is not None
        assert body["errors"] == []
        assert "meta" in body

        # Token response data
        data = body["data"]
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert len(data["access_token"]) > 20

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client, registered_user):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": registered_user["email"],
                "password": "AnotherPass123!",
                "display_name": "Duplicate",
                "org_name": "Dup Org",
                "org_slug": f"dup-{uuid.uuid4().hex[:6]}",
            },
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["data"] is None
        assert body["errors"][0]["code"] == "conflict"
        assert body["errors"][0]["suggestion"] is not None


class TestLoginEndpoint:
    """POST /api/v1/auth/login integration tests."""

    @pytest.mark.asyncio
    async def test_login_success_returns_200_with_token(self, client, registered_user):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []
        assert "access_token" in body["data"]
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client, registered_user):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": registered_user["email"],
                "password": "TotallyWrongPassword!",
            },
        )
        assert resp.status_code == 401
        body = resp.json()

        assert body["data"] is None
        error = body["errors"][0]
        assert error["code"] == "authentication_error"
        assert "suggestion" in error
        assert error["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_login_nonexistent_email_returns_401(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@nowhere.com",
                "password": "Whatever123!",
            },
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["errors"][0]["code"] == "authentication_error"

    @pytest.mark.asyncio
    async def test_login_missing_fields_returns_422(self, client):
        resp = await client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0
        for error in body["errors"]:
            assert error["suggestion"] is not None


class TestMeEndpoint:
    """GET /api/v1/auth/me — protected endpoint tests."""

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, client, registered_user):
        headers = {"Authorization": f"Bearer {registered_user['access_token']}"}
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []

        user = body["data"]
        assert user["email"] == registered_user["email"]
        assert user["display_name"] == registered_user["display_name"]
        assert user["is_active"] is True
        assert "id" in user
        assert "org_id" in user
        assert "created_at" in user

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, client):
        resp = await client.get("/api/v1/auth/me")
        # FastAPI's OAuth2 scheme returns 401 for missing token
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_invalid_token_returns_401(self, client):
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401
        body = resp.json()
        assert body["data"] is None
        assert len(body["errors"]) > 0
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_me_with_expired_token_returns_401(self, client, test_settings):
        """Create a token with 0 expiry, verify it's rejected."""
        from datetime import timedelta
        from app.services.auth import create_access_token

        token, _ = create_access_token(
            user_id="fake-user-id",
            email="fake@test.com",
            org_id="fake-org-id",
            settings=test_settings,
            expires_delta=timedelta(seconds=-1),
        )
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401


class TestFullAuthFlow:
    """End-to-end auth flow: register -> login -> access protected resource."""

    @pytest.mark.asyncio
    async def test_register_then_login_then_me(self, client):
        email = f"flow-{uuid.uuid4().hex[:6]}@lablink.io"
        password = "FlowTest123!"

        # 1. Register
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": "Flow User",
                "org_name": "Flow Lab",
                "org_slug": f"flow-lab-{uuid.uuid4().hex[:6]}",
            },
        )
        assert reg_resp.status_code == 201
        reg_token = reg_resp.json()["data"]["access_token"]

        # 2. Login with the same credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )
        assert login_resp.status_code == 200
        login_token = login_resp.json()["data"]["access_token"]

        # Both tokens should work
        for token in [reg_token, login_token]:
            me_resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert me_resp.status_code == 200
            assert me_resp.json()["data"]["email"] == email
