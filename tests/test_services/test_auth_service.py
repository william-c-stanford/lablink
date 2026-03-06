"""Tests for the auth service: registration, login, token management.

Uses in-memory SQLite via the session fixture from conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.security import hash_password, verify_password
from app.exceptions import AuthenticationError, ConflictError
from app.models.identity import Organization, RoleName, User
from app.services.auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_current_user_from_token,
    get_user_by_id,
    login_user,
    register_user,
)


# ===========================================================================
# Password hashing (via core.security, delegated by auth service)
# ===========================================================================


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        hashed = hash_password("my-secret-password")
        assert verify_password("my-secret-password", hashed) is True
        assert verify_password("wrong-password", hashed) is False

    def test_hash_is_not_plaintext(self) -> None:
        hashed = hash_password("password123")
        assert hashed != "password123"
        assert len(hashed) > 20


# ===========================================================================
# JWT token creation/decoding
# ===========================================================================


class TestTokenCreation:
    def test_create_and_decode(self, test_settings: Settings) -> None:
        token, expires_in = create_access_token(
            user_id="user-1", email="a@b.com", org_id="org-1",
            settings=test_settings,
        )
        assert isinstance(token, str)
        assert expires_in > 0

        payload = decode_access_token(token, settings=test_settings)
        assert payload["sub"] == "user-1"
        assert payload["email"] == "a@b.com"
        assert payload["org_id"] == "org-1"

    def test_invalid_token_raises(self, test_settings: Settings) -> None:
        with pytest.raises(AuthenticationError):
            decode_access_token("invalid.jwt.token", settings=test_settings)

    def test_expires_in_matches_settings(self, test_settings: Settings) -> None:
        _, expires_in = create_access_token(
            user_id="u1", email="a@b.com", org_id="o1",
            settings=test_settings,
        )
        assert expires_in == test_settings.jwt_expire_minutes * 60


# ===========================================================================
# register_user
# ===========================================================================


class TestRegisterUser:
    async def test_register_creates_user_org_role(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        user, org, token, expires_in = await register_user(
            session,
            email="scientist@lab.com",
            password="secure-password-123",
            display_name="Dr. Scientist",
            org_name="Research Lab",
            org_slug="research-lab",
            settings=test_settings,
        )

        assert user.email == "scientist@lab.com"
        assert user.display_name == "Dr. Scientist"
        assert user.is_active is True
        assert user.hashed_password is not None

        assert org.name == "Research Lab"
        assert org.slug == "research-lab"

        assert isinstance(token, str)
        assert expires_in > 0

        # Verify role was created
        from sqlalchemy import select
        from app.models.identity import Role
        stmt = select(Role).where(Role.user_id == user.id)
        result = await session.execute(stmt)
        role = result.scalar_one()
        assert role.role_name == RoleName.owner.value

    async def test_register_duplicate_email_raises(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        await register_user(
            session,
            email="dup@lab.com", password="password123",
            display_name="User 1", org_name="Lab 1",
            settings=test_settings,
        )
        await session.flush()

        with pytest.raises(ConflictError) as exc_info:
            await register_user(
                session,
                email="dup@lab.com", password="password456",
                display_name="User 2", org_name="Lab 2",
                settings=test_settings,
            )
        assert "already exists" in exc_info.value.message

    async def test_register_auto_generates_slug(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        user, org, _, _ = await register_user(
            session,
            email="auto@lab.com", password="password123",
            display_name="Auto User", org_name="Auto Lab",
            settings=test_settings,
        )
        assert org.slug.startswith("org-")


# ===========================================================================
# authenticate_user
# ===========================================================================


class TestAuthenticateUser:
    async def test_authenticate_success(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        await register_user(
            session,
            email="auth@lab.com", password="correct-password",
            display_name="Auth User", org_name="Auth Lab",
            settings=test_settings,
        )
        await session.flush()

        user, token, expires_in = await authenticate_user(
            session, email="auth@lab.com", password="correct-password",
            settings=test_settings,
        )
        assert user.email == "auth@lab.com"
        assert user.last_login_at is not None
        assert isinstance(token, str)

    async def test_authenticate_wrong_password(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        await register_user(
            session,
            email="wrong@lab.com", password="correct-password",
            display_name="Wrong User", org_name="Lab",
            settings=test_settings,
        )
        await session.flush()

        with pytest.raises(AuthenticationError) as exc_info:
            await authenticate_user(
                session, email="wrong@lab.com", password="wrong-password",
                settings=test_settings,
            )
        assert exc_info.value.suggestion is not None

    async def test_authenticate_nonexistent_email(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        with pytest.raises(AuthenticationError):
            await authenticate_user(
                session, email="nobody@lab.com", password="anything",
                settings=test_settings,
            )

    async def test_authenticate_inactive_user(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        user, _, _, _ = await register_user(
            session,
            email="inactive@lab.com", password="password123",
            display_name="Inactive", org_name="Lab",
            settings=test_settings,
        )
        user.is_active = False
        await session.flush()

        with pytest.raises(AuthenticationError) as exc_info:
            await authenticate_user(
                session, email="inactive@lab.com", password="password123",
                settings=test_settings,
            )
        assert "disabled" in exc_info.value.message.lower()

    async def test_authenticate_sso_user_no_password(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        """User with hashed_password=None (SSO) cannot use password login."""
        # Create user directly without password
        org = Organization(id="o1", name="SSO Lab", slug="sso-lab")
        session.add(org)
        await session.flush()

        user = User(
            org_id="o1", email="sso@lab.com",
            display_name="SSO User",
            hashed_password=None,
        )
        session.add(user)
        await session.flush()

        with pytest.raises(AuthenticationError) as exc_info:
            await authenticate_user(
                session, email="sso@lab.com", password="any",
                settings=test_settings,
            )
        assert "sso" in exc_info.value.message.lower()


# ===========================================================================
# login_user (high-level)
# ===========================================================================


class TestLoginUser:
    async def test_login_returns_schemas(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        await register_user(
            session,
            email="login@lab.com", password="password123",
            display_name="Login User", org_name="Lab",
            settings=test_settings,
        )
        await session.flush()

        user_resp, token_resp = await login_user(
            session, email="login@lab.com", password="password123",
            settings=test_settings,
        )
        assert user_resp.email == "login@lab.com"
        assert token_resp.token_type == "bearer"
        assert token_resp.expires_in > 0


# ===========================================================================
# get_user_by_id
# ===========================================================================


class TestGetUserById:
    async def test_found(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        user, _, _, _ = await register_user(
            session,
            email="find@lab.com", password="password123",
            display_name="Find Me", org_name="Lab",
            settings=test_settings,
        )
        await session.flush()

        found = await get_user_by_id(session, user.id)
        assert found is not None
        assert found.email == "find@lab.com"

    async def test_not_found(self, session: AsyncSession) -> None:
        result = await get_user_by_id(session, "nonexistent")
        assert result is None


# ===========================================================================
# get_current_user_from_token
# ===========================================================================


class TestGetCurrentUserFromToken:
    async def test_valid_token_returns_user(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        user, _, token, _ = await register_user(
            session,
            email="current@lab.com", password="password123",
            display_name="Current User", org_name="Lab",
            settings=test_settings,
        )
        await session.flush()

        result = await get_current_user_from_token(
            session, token, settings=test_settings,
        )
        assert result.email == "current@lab.com"
        assert result.id == user.id

    async def test_invalid_token_raises(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        with pytest.raises(AuthenticationError):
            await get_current_user_from_token(
                session, "bad.token.here", settings=test_settings,
            )

    async def test_deleted_user_raises(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        from datetime import datetime, timezone
        user, _, token, _ = await register_user(
            session,
            email="deleted@lab.com", password="password123",
            display_name="Deleted", org_name="Lab",
            settings=test_settings,
        )
        user.deleted_at = datetime.now(timezone.utc)
        await session.flush()

        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user_from_token(
                session, token, settings=test_settings,
            )
        assert "deleted" in exc_info.value.message.lower()

    async def test_inactive_user_raises(
        self, session: AsyncSession, test_settings: Settings,
    ) -> None:
        user, _, token, _ = await register_user(
            session,
            email="disabled@lab.com", password="password123",
            display_name="Disabled", org_name="Lab",
            settings=test_settings,
        )
        user.is_active = False
        await session.flush()

        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user_from_token(
                session, token, settings=test_settings,
            )
        assert "disabled" in exc_info.value.message.lower()
