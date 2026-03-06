"""End-to-end auth tests: registration, login, token validation,
protected route access, and invalid credential rejection.

Tests run against in-memory SQLite with real bcrypt hashing and JWT signing.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Environment, Settings
from app.core.database import create_engine, create_session_factory, init_db
from app.models.base import Base
from app.services.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_settings() -> Settings:
    """Test settings with a known secret key for deterministic JWT tests."""
    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        debug=False,
        secret_key="test-secret-key-for-auth",
        jwt_expire_minutes=30,
        use_celery=False,
        use_elasticsearch=False,
        use_redis=False,
    )


@pytest.fixture()
async def auth_engine(auth_settings):
    """Create engine and initialize tables for auth tests."""
    eng = create_engine(auth_settings)
    # Create all tables
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture()
async def auth_session(auth_engine, auth_settings):
    """Provide a session for direct service-layer tests."""
    factory = create_session_factory(auth_engine)
    async with factory() as session:
        yield session


@pytest.fixture()
def auth_app(auth_settings, auth_engine):
    """Create a FastAPI app wired to the test database."""
    from app.config import get_settings
    from app.core.database import get_session
    from app.main import create_app

    app = create_app(settings=auth_settings)

    # Override the session dependency to use our test engine
    factory = create_session_factory(auth_engine)

    async def _override_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def _override_settings():
        return auth_settings

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = _override_settings
    return app


@pytest.fixture()
async def auth_client(auth_app):
    """Async HTTP client bound to the auth test app."""
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# Helpers

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"

VALID_REGISTER = {
    "email": "alice@example.com",
    "password": "securepass123",
    "display_name": "Alice",
    "org_name": "Alice's Lab",
    "org_slug": "alices-lab",
}


async def _register_user(client: AsyncClient, **overrides) -> dict:
    """Helper to register a user and return the response JSON."""
    payload = {**VALID_REGISTER, **overrides}
    resp = await client.post(REGISTER_URL, json=payload)
    return resp


async def _login_user(client: AsyncClient, email: str, password: str) -> dict:
    """Helper to login and return the response."""
    resp = await client.post(LOGIN_URL, json={"email": email, "password": password})
    return resp


# ═══════════════════════════════════════════════════════════════════════
# Password Hashing (unit)
# ═══════════════════════════════════════════════════════════════════════


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert verify_password("mypassword", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt produces different salts each time."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1) is True
        assert verify_password("same", h2) is True


# ═══════════════════════════════════════════════════════════════════════
# JWT Token (unit)
# ═══════════════════════════════════════════════════════════════════════


class TestJWTToken:
    def test_create_and_decode(self, auth_settings):
        token, expires_in = create_access_token(
            user_id="user-123",
            email="test@example.com",
            org_id="org-456",
            settings=auth_settings,
        )
        assert isinstance(token, str)
        assert expires_in == 30 * 60  # 30 minutes in seconds

        payload = decode_access_token(token, settings=auth_settings)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["org_id"] == "org-456"

    def test_expired_token_raises(self, auth_settings):
        from app.exceptions import AuthenticationError

        token, _ = create_access_token(
            user_id="user-123",
            email="test@example.com",
            org_id="org-456",
            settings=auth_settings,
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(AuthenticationError, match="expired"):
            decode_access_token(token, settings=auth_settings)

    def test_invalid_token_raises(self, auth_settings):
        from app.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            decode_access_token("not.a.valid.token", settings=auth_settings)

    def test_wrong_secret_raises(self, auth_settings):
        from app.exceptions import AuthenticationError

        token, _ = create_access_token(
            user_id="user-123",
            email="test@example.com",
            org_id="org-456",
            settings=auth_settings,
        )
        # Decode with different secret
        wrong_settings = Settings(
            environment=Environment.test,
            database_url="sqlite+aiosqlite://",
            secret_key="wrong-secret",
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(token, settings=wrong_settings)


# ═══════════════════════════════════════════════════════════════════════
# Registration (e2e)
# ═══════════════════════════════════════════════════════════════════════


class TestRegistration:
    async def test_register_success(self, auth_client):
        resp = await _register_user(auth_client)
        assert resp.status_code == 201
        body = resp.json()

        # Envelope structure
        assert body["data"] is not None
        assert body["errors"] == []
        assert "meta" in body

        # Token response
        token_data = body["data"]
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"
        assert token_data["expires_in"] > 0

    async def test_register_returns_valid_jwt(self, auth_client, auth_settings):
        resp = await _register_user(auth_client)
        token = resp.json()["data"]["access_token"]

        # Decode and verify
        payload = decode_access_token(token, settings=auth_settings)
        assert payload["email"] == "alice@example.com"
        assert "sub" in payload
        assert "org_id" in payload

    async def test_register_duplicate_email_rejected(self, auth_client):
        # First registration succeeds
        resp1 = await _register_user(auth_client)
        assert resp1.status_code == 201

        # Second registration with same email fails
        resp2 = await _register_user(auth_client)
        assert resp2.status_code == 409
        body = resp2.json()
        assert body["data"] is None
        assert len(body["errors"]) > 0
        assert body["errors"][0]["code"] == "conflict"
        assert "suggestion" in body["errors"][0]
        assert body["errors"][0]["suggestion"] is not None

    async def test_register_short_password_rejected(self, auth_client):
        resp = await _register_user(auth_client, password="short")
        assert resp.status_code == 422
        body = resp.json()
        assert body["data"] is None
        assert len(body["errors"]) > 0
        # Should have suggestion for the password field
        has_password_error = any("password" in (e.get("field") or "") for e in body["errors"])
        assert has_password_error

    async def test_register_invalid_email_rejected(self, auth_client):
        resp = await _register_user(auth_client, email="not-an-email")
        assert resp.status_code == 422

    async def test_register_missing_fields_rejected(self, auth_client):
        resp = await auth_client.post(REGISTER_URL, json={})
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0
        # Every error should have a suggestion (agent-native)
        for err in body["errors"]:
            assert err.get("suggestion") is not None


# ═══════════════════════════════════════════════════════════════════════
# Login (e2e)
# ═══════════════════════════════════════════════════════════════════════


class TestLogin:
    async def test_login_success(self, auth_client):
        # Register first
        await _register_user(auth_client)

        # Login
        resp = await _login_user(auth_client, "alice@example.com", "securepass123")
        assert resp.status_code == 200
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []
        assert body["data"]["access_token"]
        assert body["data"]["token_type"] == "bearer"

    async def test_login_returns_valid_jwt(self, auth_client, auth_settings):
        await _register_user(auth_client)
        resp = await _login_user(auth_client, "alice@example.com", "securepass123")
        token = resp.json()["data"]["access_token"]

        payload = decode_access_token(token, settings=auth_settings)
        assert payload["email"] == "alice@example.com"

    async def test_login_wrong_password_rejected(self, auth_client):
        await _register_user(auth_client)
        resp = await _login_user(auth_client, "alice@example.com", "wrongpassword")
        assert resp.status_code == 401
        body = resp.json()
        assert body["data"] is None
        assert body["errors"][0]["code"] == "authentication_error"
        assert body["errors"][0]["suggestion"] is not None

    async def test_login_nonexistent_user_rejected(self, auth_client):
        resp = await _login_user(auth_client, "nobody@example.com", "anypassword")
        assert resp.status_code == 401
        body = resp.json()
        assert body["errors"][0]["code"] == "authentication_error"
        # Should NOT reveal whether the email exists (security)
        assert "Invalid email or password" in body["errors"][0]["message"]

    async def test_login_invalid_email_format_rejected(self, auth_client):
        resp = await _login_user(auth_client, "not-valid-email", "password123")
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# Protected Route Access (e2e)
# ═══════════════════════════════════════════════════════════════════════


class TestProtectedRoute:
    async def test_me_with_valid_token(self, auth_client):
        # Register and get token
        reg_resp = await _register_user(auth_client)
        token = reg_resp.json()["data"]["access_token"]

        # Access protected route
        resp = await auth_client.get(
            ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()

        user_data = body["data"]
        assert user_data["email"] == "alice@example.com"
        assert user_data["display_name"] == "Alice"
        assert user_data["is_active"] is True
        assert user_data["org_id"]  # should have an org_id

    async def test_me_without_token_rejected(self, auth_client):
        resp = await auth_client.get(ME_URL)
        assert resp.status_code in (401, 403)

    async def test_me_with_invalid_token_rejected(self, auth_client):
        resp = await auth_client.get(
            ME_URL,
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["errors"][0]["code"] == "authentication_error"

    async def test_me_with_expired_token_rejected(self, auth_client, auth_settings):
        # Register to get a real user ID
        reg_resp = await _register_user(auth_client)
        valid_token = reg_resp.json()["data"]["access_token"]
        payload = decode_access_token(valid_token, settings=auth_settings)

        # Create an expired token for the same user
        expired_token, _ = create_access_token(
            user_id=payload["sub"],
            email=payload["email"],
            org_id=payload["org_id"],
            settings=auth_settings,
            expires_delta=timedelta(seconds=-1),
        )

        resp = await auth_client.get(
            ME_URL,
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    async def test_me_with_login_token(self, auth_client):
        """Login token should also work for protected routes."""
        await _register_user(auth_client)
        login_resp = await _login_user(auth_client, "alice@example.com", "securepass123")
        token = login_resp.json()["data"]["access_token"]

        resp = await auth_client.get(
            ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "alice@example.com"


# ═══════════════════════════════════════════════════════════════════════
# Envelope Compliance
# ═══════════════════════════════════════════════════════════════════════


class TestEnvelopeCompliance:
    """Verify ALL auth responses follow the Envelope[T] pattern."""

    async def test_register_success_envelope(self, auth_client):
        resp = await _register_user(auth_client)
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}
        assert body["meta"]["timestamp"] is not None

    async def test_register_error_envelope(self, auth_client):
        resp = await auth_client.post(REGISTER_URL, json={})
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}
        assert body["data"] is None

    async def test_login_success_envelope(self, auth_client):
        await _register_user(auth_client)
        resp = await _login_user(auth_client, "alice@example.com", "securepass123")
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}

    async def test_login_error_envelope(self, auth_client):
        resp = await _login_user(auth_client, "nobody@example.com", "password")
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}
        assert body["data"] is None

    async def test_me_success_envelope(self, auth_client):
        reg_resp = await _register_user(auth_client)
        token = reg_resp.json()["data"]["access_token"]
        resp = await auth_client.get(
            ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}

    async def test_all_errors_have_suggestions(self, auth_client):
        """Agent-native: every error response must include suggestion field."""
        # Validation error
        resp1 = await auth_client.post(REGISTER_URL, json={})
        for err in resp1.json()["errors"]:
            assert err.get("suggestion") is not None, f"Missing suggestion in: {err}"

        # Auth error
        resp2 = await _login_user(auth_client, "bad@example.com", "bad")
        for err in resp2.json()["errors"]:
            assert err.get("suggestion") is not None, f"Missing suggestion in: {err}"


# ═══════════════════════════════════════════════════════════════════════
# Full Flow (integration)
# ═══════════════════════════════════════════════════════════════════════


class TestFullAuthFlow:
    async def test_register_login_access_flow(self, auth_client):
        """Complete happy path: register → login → access protected route."""
        # 1. Register
        reg_resp = await _register_user(auth_client)
        assert reg_resp.status_code == 201
        reg_token = reg_resp.json()["data"]["access_token"]

        # 2. Login with same credentials
        login_resp = await _login_user(auth_client, "alice@example.com", "securepass123")
        assert login_resp.status_code == 200
        login_token = login_resp.json()["data"]["access_token"]

        # 3. Both tokens should work on /me
        for token in [reg_token, login_token]:
            me_resp = await auth_client.get(
                ME_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert me_resp.status_code == 200
            assert me_resp.json()["data"]["email"] == "alice@example.com"

    async def test_multiple_users_isolated(self, auth_client):
        """Two users register separately; each can only see their own profile."""
        # Register Alice
        alice_resp = await _register_user(auth_client)
        alice_token = alice_resp.json()["data"]["access_token"]

        # Register Bob
        bob_resp = await _register_user(
            auth_client,
            email="bob@example.com",
            display_name="Bob",
            org_name="Bob's Lab",
            org_slug="bobs-lab",
        )
        bob_token = bob_resp.json()["data"]["access_token"]

        # Alice sees Alice
        alice_me = await auth_client.get(
            ME_URL, headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert alice_me.json()["data"]["email"] == "alice@example.com"

        # Bob sees Bob
        bob_me = await auth_client.get(
            ME_URL, headers={"Authorization": f"Bearer {bob_token}"}
        )
        assert bob_me.json()["data"]["email"] == "bob@example.com"
