"""Tests for the auth service layer — password hashing, JWT, register, login, current-user."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import Settings
from app.exceptions import AuthenticationError, ConflictError
from app.models.identity import Organization, User
from app.schemas.auth import TokenResponse, UserResponse
from app.services.auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_current_user_from_token,
    get_user_by_id,
    hash_password,
    login_user,
    register_user,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        hashed = hash_password("mysecretpassword")
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("correct-password")
        assert verify_password("correct-password", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct-password")
        assert verify_password("wrong-password", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt salts differ


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

class TestJWT:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            environment="test",
            secret_key="jwt-test-key",
            jwt_algorithm="HS256",
            jwt_expire_minutes=15,
        )

    def test_create_access_token_returns_tuple(self, settings):
        token, expires_in = create_access_token(
            user_id="user-123",
            email="test@example.com",
            org_id="org-456",
            settings=settings,
        )
        assert isinstance(token, str)
        assert expires_in == 15 * 60

    def test_decode_access_token_roundtrip(self, settings):
        token, _ = create_access_token(
            user_id="user-123",
            email="test@example.com",
            org_id="org-456",
            settings=settings,
        )
        payload = decode_access_token(token, settings)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["org_id"] == "org-456"

    def test_decode_invalid_token_raises(self, settings):
        with pytest.raises(AuthenticationError):
            decode_access_token("not.a.valid.token", settings)

    def test_decode_wrong_secret_raises(self, settings):
        token, _ = create_access_token(
            user_id="user-123",
            email="test@example.com",
            org_id="org-456",
            settings=settings,
        )
        other_settings = Settings(
            environment="test",
            secret_key="different-secret",
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(token, other_settings)

    def test_token_contains_expected_claims(self, settings):
        token, _ = create_access_token(
            user_id="u1",
            email="e@e.com",
            org_id="o1",
            settings=settings,
        )
        # Decode without verification to inspect claims
        payload = jwt.get_unverified_claims(token)
        assert "sub" in payload
        assert "email" in payload
        assert "org_id" in payload
        assert "iat" in payload
        assert "exp" in payload


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class TestRegisterUser:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            environment="test",
            database_url="sqlite+aiosqlite://",
            secret_key="reg-test-key",
            jwt_expire_minutes=60,
        )

    async def test_register_creates_user_and_org(self, session, settings):
        user, org, token, expires_in = await register_user(
            session=session,
            email="alice@lab.io",
            password="securepass123",
            display_name="Alice",
            org_name="Alice's Lab",
            settings=settings,
        )
        assert user.email == "alice@lab.io"
        assert user.display_name == "Alice"
        assert user.is_active is True
        assert org.name == "Alice's Lab"
        assert isinstance(token, str)
        assert expires_in == 3600

    async def test_register_assigns_owner_role(self, session, settings):
        user, org, _, _ = await register_user(
            session=session,
            email="bob@lab.io",
            password="securepass123",
            display_name="Bob",
            org_name="Bob's Lab",
            settings=settings,
        )
        await session.flush()
        # Refresh to load relationships
        from sqlalchemy import select
        from app.models.identity import Role
        result = await session.execute(
            select(Role).where(Role.user_id == user.id)
        )
        role = result.scalar_one()
        assert role.role_name == "owner"
        assert role.org_id == org.id

    async def test_register_duplicate_email_raises(self, session, settings):
        await register_user(
            session=session,
            email="dupe@lab.io",
            password="securepass123",
            display_name="First",
            org_name="First Lab",
            settings=settings,
        )
        with pytest.raises(ConflictError) as exc_info:
            await register_user(
                session=session,
                email="dupe@lab.io",
                password="securepass123",
                display_name="Second",
                org_name="Second Lab",
                settings=settings,
            )
        assert "already exists" in exc_info.value.message
        assert exc_info.value.field == "email"

    async def test_register_with_custom_slug(self, session, settings):
        user, org, _, _ = await register_user(
            session=session,
            email="slugtest@lab.io",
            password="securepass123",
            display_name="Slug",
            org_name="Slug Lab",
            org_slug="slug-lab",
            settings=settings,
        )
        assert org.slug == "slug-lab"


# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------

class TestAuthenticateUser:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            environment="test",
            database_url="sqlite+aiosqlite://",
            secret_key="auth-test-key",
            jwt_expire_minutes=30,
        )

    async def test_authenticate_valid_credentials(self, session, settings):
        await register_user(
            session=session,
            email="carol@lab.io",
            password="correcthorse",
            display_name="Carol",
            org_name="Carol's Lab",
            settings=settings,
        )
        user, token, expires_in = await authenticate_user(
            session=session,
            email="carol@lab.io",
            password="correcthorse",
            settings=settings,
        )
        assert user.email == "carol@lab.io"
        assert isinstance(token, str)
        assert expires_in == 30 * 60

    async def test_authenticate_wrong_password(self, session, settings):
        await register_user(
            session=session,
            email="dave@lab.io",
            password="rightpass123",
            display_name="Dave",
            org_name="Dave's Lab",
            settings=settings,
        )
        with pytest.raises(AuthenticationError) as exc_info:
            await authenticate_user(
                session=session,
                email="dave@lab.io",
                password="wrongpass123",
                settings=settings,
            )
        assert "Invalid email or password" in exc_info.value.message

    async def test_authenticate_nonexistent_email(self, session, settings):
        with pytest.raises(AuthenticationError):
            await authenticate_user(
                session=session,
                email="nobody@lab.io",
                password="anypassword",
                settings=settings,
            )

    async def test_authenticate_updates_last_login(self, session, settings):
        await register_user(
            session=session,
            email="eve@lab.io",
            password="password123",
            display_name="Eve",
            org_name="Eve's Lab",
            settings=settings,
        )
        user, _, _ = await authenticate_user(
            session=session,
            email="eve@lab.io",
            password="password123",
            settings=settings,
        )
        assert user.last_login_at is not None


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

class TestGetUserById:
    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            environment="test",
            database_url="sqlite+aiosqlite://",
            secret_key="test-key",
        )

    async def test_get_existing_user(self, session, settings):
        user, _, _, _ = await register_user(
            session=session,
            email="frank@lab.io",
            password="password123",
            display_name="Frank",
            org_name="Frank's Lab",
            settings=settings,
        )
        found = await get_user_by_id(session, user.id)
        assert found is not None
        assert found.email == "frank@lab.io"

    async def test_get_nonexistent_user(self, session):
        found = await get_user_by_id(session, "nonexistent-id")
        assert found is None


# ---------------------------------------------------------------------------
# login_user (high-level: credential verification + token issuance)
# ---------------------------------------------------------------------------


class TestLoginUser:
    """Tests for login_user — returns Pydantic schemas (UserResponse, TokenResponse)."""

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            environment="test",
            database_url="sqlite+aiosqlite://",
            secret_key="login-test-key",
            jwt_expire_minutes=45,
        )

    async def test_login_returns_user_and_token_responses(self, session, settings):
        await register_user(
            session=session,
            email="login@lab.io",
            password="my-password-123",
            display_name="Login User",
            org_name="Login Lab",
            settings=settings,
        )

        user_resp, token_resp = await login_user(
            session, email="login@lab.io", password="my-password-123", settings=settings
        )

        # UserResponse is a Pydantic model
        assert isinstance(user_resp, UserResponse)
        assert user_resp.email == "login@lab.io"
        assert user_resp.display_name == "Login User"
        assert user_resp.is_active is True
        assert user_resp.last_login_at is not None

        # TokenResponse is a Pydantic model
        assert isinstance(token_resp, TokenResponse)
        assert token_resp.token_type == "bearer"
        assert token_resp.expires_in == 45 * 60
        assert len(token_resp.access_token) > 10

    async def test_login_token_decodes_to_correct_user(self, session, settings):
        await register_user(
            session=session,
            email="decode@lab.io",
            password="my-password-123",
            display_name="Decode User",
            org_name="Decode Lab",
            settings=settings,
        )

        user_resp, token_resp = await login_user(
            session, email="decode@lab.io", password="my-password-123", settings=settings
        )

        payload = decode_access_token(token_resp.access_token, settings)
        assert payload["sub"] == user_resp.id
        assert payload["email"] == "decode@lab.io"
        assert payload["org_id"] == user_resp.org_id

    async def test_login_wrong_password_raises(self, session, settings):
        await register_user(
            session=session,
            email="fail@lab.io",
            password="correct-password",
            display_name="Fail User",
            org_name="Fail Lab",
            settings=settings,
        )

        with pytest.raises(AuthenticationError, match="Invalid email or password"):
            await login_user(
                session, email="fail@lab.io", password="wrong-password", settings=settings
            )

    async def test_login_nonexistent_email_raises(self, session, settings):
        with pytest.raises(AuthenticationError):
            await login_user(
                session, email="nobody@lab.io", password="any", settings=settings
            )

    async def test_login_error_has_suggestion(self, session, settings):
        with pytest.raises(AuthenticationError) as exc_info:
            await login_user(
                session, email="nobody@lab.io", password="any", settings=settings
            )
        assert exc_info.value.suggestion is not None

    async def test_login_disabled_account_raises(self, session, settings):
        user, _, _, _ = await register_user(
            session=session,
            email="disabled-login@lab.io",
            password="some-password",
            display_name="Disabled",
            org_name="Lab",
            settings=settings,
        )
        user.is_active = False
        await session.flush()

        with pytest.raises(AuthenticationError, match="disabled"):
            await login_user(
                session,
                email="disabled-login@lab.io",
                password="some-password",
                settings=settings,
            )


# ---------------------------------------------------------------------------
# get_current_user_from_token
# ---------------------------------------------------------------------------


class TestGetCurrentUserFromToken:
    """Tests for get_current_user_from_token — resolves JWT to UserResponse."""

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            environment="test",
            database_url="sqlite+aiosqlite://",
            secret_key="current-user-test-key",
            jwt_expire_minutes=30,
        )

    async def test_get_current_user_success(self, session, settings):
        user, org, token, _ = await register_user(
            session=session,
            email="current@lab.io",
            password="my-password-123",
            display_name="Current User",
            org_name="Current Lab",
            settings=settings,
        )
        await session.flush()

        user_resp = await get_current_user_from_token(session, token, settings=settings)

        assert isinstance(user_resp, UserResponse)
        assert user_resp.id == user.id
        assert user_resp.email == "current@lab.io"
        assert user_resp.display_name == "Current User"
        assert user_resp.org_id == org.id
        assert user_resp.is_active is True

    async def test_get_current_user_invalid_token(self, session, settings):
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await get_current_user_from_token(session, "garbage-token", settings=settings)

    async def test_get_current_user_expired_token(self, session, settings):
        user, org, _, _ = await register_user(
            session=session,
            email="expired@lab.io",
            password="my-password-123",
            display_name="Expired User",
            org_name="Expired Lab",
            settings=settings,
        )
        await session.flush()

        # Create an already-expired token
        expired_token, _ = create_access_token(
            user.id, user.email, org.id,
            settings=settings,
            expires_delta=timedelta(seconds=-1),
        )

        with pytest.raises(AuthenticationError):
            await get_current_user_from_token(session, expired_token, settings=settings)

    async def test_get_current_user_deleted_user(self, session, settings):
        user, _, token, _ = await register_user(
            session=session,
            email="deleted@lab.io",
            password="my-password-123",
            display_name="Deleted User",
            org_name="Deleted Lab",
            settings=settings,
        )
        # Soft-delete the user
        user.deleted_at = datetime.now(timezone.utc)
        await session.flush()

        with pytest.raises(AuthenticationError, match="deleted"):
            await get_current_user_from_token(session, token, settings=settings)

    async def test_get_current_user_disabled_account(self, session, settings):
        user, _, token, _ = await register_user(
            session=session,
            email="inactive@lab.io",
            password="my-password-123",
            display_name="Inactive User",
            org_name="Inactive Lab",
            settings=settings,
        )
        user.is_active = False
        await session.flush()

        with pytest.raises(AuthenticationError, match="disabled"):
            await get_current_user_from_token(session, token, settings=settings)

    async def test_get_current_user_nonexistent_user_id_in_token(self, session, settings):
        """Token has valid signature but user doesn't exist in DB."""
        fake_token, _ = create_access_token(
            str(uuid.uuid4()), "ghost@lab.io", str(uuid.uuid4()),
            settings=settings,
        )

        with pytest.raises(AuthenticationError, match="not found"):
            await get_current_user_from_token(session, fake_token, settings=settings)

    async def test_get_current_user_suggestion_on_error(self, session, settings):
        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user_from_token(session, "bad-token", settings=settings)
        assert exc_info.value.suggestion is not None
        assert "/api/v1/auth/login" in exc_info.value.suggestion
