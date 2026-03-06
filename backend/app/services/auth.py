"""Authentication service: password hashing, JWT tokens, user management.

Thin routers, fat services — all auth logic lives here.

Public API:
    - hash_password / verify_password  — bcrypt wrappers
    - create_access_token / decode_access_token — JWT helpers
    - register_user  — creates org + user + owner role, returns (User, Org, token, expires)
    - login_user     — credential verification + token issuance (returns schemas)
    - get_current_user_from_token — resolves JWT → UserResponse
    - authenticate_user — low-level credential check (returns ORM model + token)
    - get_user_by_id — simple lookup
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import (
    TokenError,
    create_access_token as _core_create_token,
    decode_access_token as _core_decode_token,
    hash_password,
    verify_password,
)
from app.exceptions import AuthenticationError, ConflictError
from app.models.identity import Organization, Role, RoleName, User
from app.schemas.auth import TokenResponse, UserResponse


def create_access_token(
    user_id: str,
    email: str,
    org_id: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Create a signed JWT access token with user context.

    Delegates to ``core.security.create_access_token`` for signing.

    Returns:
        Tuple of (encoded JWT string, expires_in seconds).
    """
    cfg = settings or get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=cfg.jwt_expire_minutes)

    token = _core_create_token(
        subject=user_id,
        expires_delta=expires_delta,
        extra_claims={"email": email, "org_id": org_id},
        settings=cfg,
    )
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str, settings: Settings | None = None) -> dict:
    """Decode and validate a JWT access token.

    Delegates to ``core.security.decode_access_token`` and converts
    the result to a plain dict for backward compatibility.

    Raises:
        AuthenticationError: If the token is invalid or expired.
    """
    try:
        payload = _core_decode_token(token, settings=settings)
    except TokenError as e:
        raise AuthenticationError(
            message=str(e),
            suggestion="Obtain a new token via POST /api/v1/auth/login.",
        )
    # Return a flat dict matching the previous interface
    return {"sub": payload.sub, "email": payload.extra.get("email", ""), "org_id": payload.extra.get("org_id", ""), "iat": payload.iat, "exp": payload.exp}


async def register_user(
    session: AsyncSession,
    email: str,
    password: str,
    display_name: str,
    org_name: str,
    org_slug: str | None = None,
    settings: Settings | None = None,
) -> tuple[User, Organization, str, int]:
    """Register a new user, creating an org.

    Returns:
        Tuple of (User, Organization, access_token, expires_in).

    Raises:
        ConflictError: If email already exists.
    """
    if settings is None:
        settings = get_settings()

    # Check for existing user
    result = await session.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message=f"User with email '{email}' already exists",
            suggestion="Use a different email address or log in with the existing account.",
            field="email",
        )

    # Create organization
    slug = org_slug or f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=str(uuid.uuid4()),
        name=org_name,
        slug=slug,
    )
    session.add(org)
    await session.flush()

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        org_id=org.id,
        email=email,
        display_name=display_name,
        hashed_password=hash_password(password),
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # Assign owner role
    role = Role(
        id=str(uuid.uuid4()),
        user_id=user.id,
        org_id=org.id,
        role_name=RoleName.owner.value,
    )
    session.add(role)
    await session.flush()

    # Generate token
    token, expires_in = create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=org.id,
        settings=settings,
    )

    return user, org, token, expires_in


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> tuple[User, str, int]:
    """Authenticate a user by email and password.

    Returns:
        Tuple of (User, access_token, expires_in).

    Raises:
        AuthenticationError: If credentials are invalid.
    """
    if settings is None:
        settings = get_settings()

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError(
            message="Invalid email or password",
            suggestion="Check the email and password, then try again.",
        )

    if user.hashed_password is None:
        raise AuthenticationError(
            message="This account uses SSO. Password login is not available.",
            suggestion="Use your SSO provider to authenticate.",
        )

    if not verify_password(password, user.hashed_password):
        raise AuthenticationError(
            message="Invalid email or password",
            suggestion="Check the email and password, then try again.",
        )

    if not user.is_active:
        raise AuthenticationError(
            message="Account is disabled",
            suggestion="Contact your organization administrator to reactivate your account.",
        )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    # Generate token
    token, expires_in = create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=user.org_id,
        settings=settings,
    )

    return user, token, expires_in


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    """Fetch a user by ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# High-level service functions (return Pydantic schemas)
# ---------------------------------------------------------------------------


async def login_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> tuple[UserResponse, TokenResponse]:
    """Authenticate a user by email/password and issue a JWT token.

    This is the high-level login function that combines credential verification
    with token issuance — the primary entry point for the login endpoint.

    Args:
        session: Database session.
        email: User's email.
        password: Plain-text password.
        settings: Optional settings override for token creation.

    Returns:
        Tuple of (UserResponse, TokenResponse).

    Raises:
        AuthenticationError: If credentials are invalid or account is disabled.
    """
    user, token, expires_in = await authenticate_user(
        session, email=email, password=password, settings=settings
    )

    return (
        UserResponse.model_validate(user),
        TokenResponse(access_token=token, token_type="bearer", expires_in=expires_in),
    )


async def get_current_user_from_token(
    session: AsyncSession,
    token: str,
    *,
    settings: Settings | None = None,
) -> UserResponse:
    """Resolve a JWT token to the current user.

    Decodes the token, fetches the user from the database, and validates
    that the account is still active and not soft-deleted.

    Args:
        session: Database session.
        token: Encoded JWT string (without 'Bearer ' prefix).
        settings: Optional settings override for token decoding.

    Returns:
        UserResponse for the authenticated user.

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
