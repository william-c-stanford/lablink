"""Authentication service: JWT tokens, password hashing, user registration/login.

This module contains all auth business logic with zero HTTP awareness.
Routers delegate to these functions and wrap results in Envelope responses.

Public API:
    - hash_password / verify_password  -- bcrypt wrappers
    - create_access_token / decode_access_token -- JWT creation & validation
    - register_user    -- creates org + user + membership, returns (User, Org, token, expires)
    - authenticate_user -- credential check, returns (User, token, expires)
    - login_user       -- high-level login returning Pydantic schemas
    - get_user_by_id   -- simple lookup
    - get_current_user_from_token -- resolves JWT -> User
    - validate_api_token -- API-key authentication
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.config import Settings, get_settings
from lablink.exceptions import AuthenticationError, ConflictError
from lablink.models import (
    ApiToken,
    MemberRole,
    Membership,
    Organization,
    Tier,
    User,
)
from lablink.schemas.auth import TokenResponse, UserResponse


# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))


# ---------------------------------------------------------------------------
# JWT token creation & decoding
# ---------------------------------------------------------------------------


def create_access_token(
    user_id: str,
    email: str,
    org_id: str,
    *,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Create a signed JWT access token with user context.

    Returns:
        Tuple of (encoded JWT string, expires_in seconds).
    """
    cfg = settings or get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=cfg.jwt_expire_minutes)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "org_id": org_id,
        "iat": now,
        "exp": expire,
    }
    token = jwt.encode(payload, cfg.secret_key, algorithm=cfg.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(
    token: str, *, settings: Settings | None = None
) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Returns:
        Dict with keys: sub, email, org_id, iat, exp.

    Raises:
        AuthenticationError: If the token is invalid or expired.
    """
    cfg = settings or get_settings()
    try:
        raw = jwt.decode(token, cfg.secret_key, algorithms=[cfg.jwt_algorithm])
    except ExpiredSignatureError:
        raise AuthenticationError(
            message="Token has expired",
            suggestion="Re-authenticate via POST /api/v1/auth/login to get a fresh token.",
        )
    except JWTError as exc:
        raise AuthenticationError(
            message=f"Invalid token: {exc}",
            suggestion="Ensure the token is correctly formatted and has not been tampered with.",
        )

    return {
        "sub": raw.get("sub"),
        "email": raw.get("email", ""),
        "org_id": raw.get("org_id", ""),
        "iat": raw.get("iat"),
        "exp": raw.get("exp"),
    }


# ---------------------------------------------------------------------------
# User registration
# ---------------------------------------------------------------------------


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    org_name: str,
    org_slug: str | None = None,
    settings: Settings | None = None,
) -> tuple[User, Organization, str, int]:
    """Register a new user, creating an organization and admin membership.

    Returns:
        Tuple of (User, Organization, access_token, expires_in).

    Raises:
        ConflictError: If email already exists.
    """
    cfg = settings or get_settings()

    # Check for existing user
    result = await session.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is not None:
        raise ConflictError(
            message=f"User with email '{email}' already exists",
            suggestion="Use a different email address or log in with the existing account.",
            field="email",
        )

    # Create organization
    slug = org_slug or f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(
        name=org_name,
        slug=slug,
        tier=Tier.free.value,
    )
    session.add(org)
    await session.flush()

    # Create user
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # Create admin membership
    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=MemberRole.admin.value,
    )
    session.add(membership)
    await session.flush()

    # Generate token
    token, expires_in = create_access_token(
        user_id=str(user.id),
        email=user.email,
        org_id=str(org.id),
        settings=cfg,
    )

    return user, org, token, expires_in


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> tuple[User, str, int]:
    """Authenticate a user by email and password.

    Returns:
        Tuple of (User, access_token, expires_in).

    Raises:
        AuthenticationError: If credentials are invalid or account is disabled.
    """
    cfg = settings or get_settings()

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError(
            message="Invalid email or password",
            suggestion="Check the email and password, then try again.",
        )

    if user.password_hash is None:
        raise AuthenticationError(
            message="This account uses SSO. Password login is not available.",
            suggestion="Use your SSO provider to authenticate.",
        )

    if not verify_password(password, user.password_hash):
        raise AuthenticationError(
            message="Invalid email or password",
            suggestion="Check the email and password, then try again.",
        )

    if not user.is_active:
        raise AuthenticationError(
            message="Account is disabled",
            suggestion="Contact your organization administrator to reactivate your account.",
        )

    # Get the user's first org for the token
    membership_result = await session.execute(
        select(Membership).where(Membership.user_id == user.id).limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    org_id = str(membership.organization_id) if membership else ""

    # Generate token
    token, expires_in = create_access_token(
        user_id=str(user.id),
        email=user.email,
        org_id=org_id,
        settings=cfg,
    )

    return user, token, expires_in


async def login_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> tuple[UserResponse, TokenResponse]:
    """High-level login returning Pydantic response schemas.

    Returns:
        Tuple of (UserResponse, TokenResponse).
    """
    user, token, expires_in = await authenticate_user(
        session, email=email, password=password, settings=settings
    )
    return (
        UserResponse.model_validate(user),
        TokenResponse(access_token=token, token_type="bearer", expires_in=expires_in),
    )


# ---------------------------------------------------------------------------
# User lookup
# ---------------------------------------------------------------------------


async def get_user_by_id(
    session: AsyncSession, user_id: str | uuid.UUID
) -> User | None:
    """Fetch a user by ID, returning None if not found."""
    if isinstance(user_id, str):
        try:
            user_id = uuid.UUID(user_id)
        except ValueError:
            return None
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user_from_token(
    session: AsyncSession,
    token: str,
    *,
    settings: Settings | None = None,
) -> UserResponse:
    """Resolve a JWT token to the current user.

    Decodes the token, fetches the user from the database, and validates
    that the account is still active and not soft-deleted.

    Raises:
        AuthenticationError: If token is invalid, user not found, or account disabled.
    """
    payload = decode_access_token(token, settings=settings)
    user_id = payload["sub"]

    user = await get_user_by_id(session, user_id)

    if user is None:
        raise AuthenticationError(
            message="User not found for the provided token.",
            suggestion="The user may have been deleted. Register a new account.",
        )

    if user.deleted_at is not None:
        raise AuthenticationError(
            message="User account has been deleted.",
            suggestion="Register a new account.",
        )

    if not user.is_active:
        raise AuthenticationError(
            message="Account is disabled.",
            suggestion="Contact your organization administrator to reactivate your account.",
        )

    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# API-key authentication
# ---------------------------------------------------------------------------


async def validate_api_token(
    session: AsyncSession, raw_token: str
) -> tuple[ApiToken, User]:
    """Validate an API token and return the token record and owner user.

    Looks up the token by its SHA-256 hash, checks it is active and
    not expired, and resolves the creating user.

    Returns:
        Tuple of (ApiToken, User).

    Raises:
        AuthenticationError: If the token is invalid, expired, or owner is inactive.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    result = await session.execute(
        select(ApiToken).where(
            ApiToken.token_hash == token_hash,
            ApiToken.is_active.is_(True),
        )
    )
    api_token = result.scalar_one_or_none()

    if api_token is None:
        raise AuthenticationError(
            message="Invalid API token",
            suggestion="Verify the token value and ensure it has not been revoked.",
        )

    if not api_token.is_valid:
        raise AuthenticationError(
            message="API token has expired",
            suggestion="Generate a new API token via the admin interface.",
        )

    # Update last used
    api_token.last_used_at = datetime.now(timezone.utc)

    # Resolve owner
    user_result = await session.execute(
        select(User).where(User.id == api_token.created_by)
    )
    user = user_result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise AuthenticationError(
            message="Token owner account is inactive or not found",
            suggestion="Contact an administrator to resolve the token ownership.",
        )

    return api_token, user


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------

# Role hierarchy: higher value = more privilege
_ROLE_HIERARCHY: dict[str, int] = {
    MemberRole.viewer.value: 0,
    MemberRole.scientist.value: 1,
    MemberRole.admin.value: 2,
}


async def check_permission(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    required_role: str = MemberRole.viewer.value,
) -> Membership:
    """Check that a user has at least the required role in an organization.

    Returns:
        The Membership record.

    Raises:
        AuthenticationError: If the user is not a member.
        ForbiddenError: If the user's role is insufficient.
    """
    from lablink.exceptions import ForbiddenError

    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise AuthenticationError(
            message="User is not a member of this organization",
            suggestion="Request membership from an organization administrator.",
        )

    user_level = _ROLE_HIERARCHY.get(membership.role, -1)
    required_level = _ROLE_HIERARCHY.get(required_role, 0)

    if user_level < required_level:
        raise ForbiddenError(
            message=f"Role '{membership.role}' insufficient; requires '{required_role}' or higher",
            suggestion=f"Ask an organization admin to upgrade your role to '{required_role}'.",
        )

    return membership
