"""Tests for auth API endpoints — register, login, me."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

class TestRegisterEndpoint:
    async def test_register_success(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@lab.io",
                "password": "securepass1",
                "display_name": "New User",
                "org_name": "New Lab",
                "org_slug": "new-lab",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["access_token"]
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["expires_in"] > 0
        assert body["errors"] == []

    async def test_register_duplicate_email(self, client):
        payload = {
            "email": "dup@lab.io",
            "password": "securepass1",
            "display_name": "First",
            "org_name": "Lab A",
            "org_slug": "lab-a",
        }
        resp1 = await client.post("/api/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        payload["org_slug"] = "lab-b"
        resp2 = await client.post("/api/v1/auth/register", json=payload)
        assert resp2.status_code == 409
        body = resp2.json()
        assert body["errors"][0]["code"] == "conflict"
        assert body["errors"][0]["suggestion"] is not None

    async def test_register_short_password(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@lab.io",
                "password": "short",
                "display_name": "Short",
                "org_name": "Lab",
                "org_slug": "lab-short",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0
        assert body["errors"][0]["suggestion"] is not None

    async def test_register_invalid_email(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "securepass1",
                "display_name": "Bad Email",
                "org_name": "Lab",
                "org_slug": "lab-bad",
            },
        )
        assert resp.status_code == 422

    async def test_register_missing_fields(self, client):
        resp = await client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0

    async def test_register_envelope_structure(self, client):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "envelope@lab.io",
                "password": "securepass1",
                "display_name": "Envelope",
                "org_name": "Envelope Lab",
                "org_slug": "envelope-lab",
            },
        )
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert "timestamp" in body["meta"]


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

class TestLoginEndpoint:
    async def _register_user(self, client, email="login@lab.io"):
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "securepass1",
                "display_name": "Login User",
                "org_name": "Login Lab",
                "org_slug": f"login-lab-{email.split('@')[0]}",
            },
        )

    async def test_login_success(self, client):
        await self._register_user(client)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@lab.io", "password": "securepass1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["access_token"]
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["expires_in"] > 0
        assert body["errors"] == []

    async def test_login_wrong_password(self, client):
        await self._register_user(client, email="wrongpw@lab.io")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@lab.io", "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["errors"][0]["code"] == "authentication_error"
        assert body["errors"][0]["suggestion"] is not None

    async def test_login_nonexistent_user(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@lab.io", "password": "anypassword"},
        )
        assert resp.status_code == 401

    async def test_login_envelope_structure(self, client):
        await self._register_user(client, email="env-login@lab.io")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "env-login@lab.io", "password": "securepass1"},
        )
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

class TestMeEndpoint:
    async def _get_token(self, client, email="me@lab.io") -> str:
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "securepass1",
                "display_name": "Me User",
                "org_name": "Me Lab",
                "org_slug": f"me-lab-{email.split('@')[0]}",
            },
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "securepass1"},
        )
        return resp.json()["data"]["access_token"]

    async def test_me_returns_user(self, client):
        token = await self._get_token(client)
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["email"] == "me@lab.io"
        assert body["data"]["display_name"] == "Me User"
        assert body["data"]["is_active"] is True
        assert body["data"]["org_id"]
        assert body["errors"] == []

    async def test_me_without_token(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)

    async def test_me_with_invalid_token(self, client):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401

    async def test_me_envelope_structure(self, client):
        token = await self._get_token(client, email="me-env@lab.io")
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert "timestamp" in body["meta"]

    async def test_me_returns_user_fields(self, client):
        token = await self._get_token(client, email="fields@lab.io")
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()["data"]
        assert "id" in data
        assert "email" in data
        assert "display_name" in data
        assert "org_id" in data
        assert "is_active" in data
        assert "is_service_account" in data
        assert "created_at" in data
