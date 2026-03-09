"""Shared FastAPI dependencies for authentication, authorization, and database access.

Provides:
- ``get_db`` — re-exported from :mod:`lablink.database` for convenience
- ``get_current_user`` — extracts and validates the JWT/API-token bearer
- ``get_current_org`` — resolves the active organization for the authenticated user
- ``require_role`` — factory returning a dependency that enforces minimum role level

All dependencies return structured Envelope errors with agent-actionable
``suggestion`` fields so MCP tool consumers can self-correct.

Usage::

    from lablink.dependencies import get_current_user, get_current_org, require_role

    @router.get("/items")
    async def list_items(
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
        org: Organization = Depends(get_current_org),
    ):
        ...

    @router.post("/admin-only")
    async def admin_action(
        user: User = Depends(require_role("admin")),
    ):
        ...
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from jose import JWTError, jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.config import get_settings
from lablink.database import get_db as _get_db  # noqa: F401 – re-export
from lablink.models import (
    ApiToken,
    MemberRole,
    Membership,
    Organization,
    User,
)

logger = logging.getLogger("lablink.dependencies")

# ---------------------------------------------------------------------------
# Re-export get_db so callers can import everything from one module
# ---------------------------------------------------------------------------

get_db = _get_db

# ---------------------------------------------------------------------------
# Security scheme
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)

# Role hierarchy: higher index = more privilege
_ROLE_HIERARCHY: dict[str, int] = {
    MemberRole.viewer.value: 0,
    MemberRole.scientist.value: 1,
    MemberRole.admin.value: 2,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_jwt(token: str) -> dict:
    """Decode and validate a JWT, returning its payload.

    Raises :class:`HTTPException` (401) on any failure.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def _resolve_api_token(
    raw_token: str, db: AsyncSession
) -> tuple[User, uuid.UUID]:
    """Look up an API token by its SHA-256 hash and return (user, org_id).

    Raises :class:`HTTPException` (401) if the token is missing, inactive,
    or expired.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    stmt = select(ApiToken).where(
        ApiToken.token_hash == token_hash,
        ApiToken.is_active.is_(True),
    )
    result = await db.execute(stmt)
    api_token = result.scalar_one_or_none()

    if api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )

    # Check expiration
    if api_token.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires = api_token.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API token has expired",
            )

    # Update last_used_at
    api_token.last_used_at = datetime.now(timezone.utc)

    # Resolve the creator user
    user_stmt = select(User).where(User.id == api_token.created_by)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token owner account is inactive",
        )

    return user, api_token.organization_id


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> User:
    """FastAPI dependency that extracts and validates the authenticated user.

    Supports two authentication methods:

    1. **JWT Bearer token** — issued by the ``/auth/login`` endpoint.
       The token payload must contain ``sub`` (user ID) and optionally
       ``org_id`` (active organization).
    2. **API token** — prefixed with ``ll_``, looked up by SHA-256 hash.

    The resolved :class:`User` is stored on ``request.state`` for
    downstream dependencies to access without re-querying.

    Raises:
        HTTPException 401: Missing or invalid credentials.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Detect API token vs JWT
    if token.startswith("ll_"):
        user, org_id = await _resolve_api_token(token, db)
        request.state.auth_org_id = org_id
        request.state.auth_method = "api_token"
    else:
        payload = _decode_jwt(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim",
            )

        try:
            # Validate the UUID format but query with the canonical
            # hyphenated string so it matches the String(36) column.
            user_id = str(uuid.UUID(user_id))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 'sub' claim in token",
            )

        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive",
            )

        # Store org_id from JWT payload if present (as hyphenated string)
        org_id_str = payload.get("org_id")
        if org_id_str:
            try:
                request.state.auth_org_id = str(uuid.UUID(org_id_str))
            except (ValueError, TypeError):
                request.state.auth_org_id = None
        else:
            request.state.auth_org_id = None

        request.state.auth_method = "jwt"

    request.state.current_user = user
    return user


# ---------------------------------------------------------------------------
# get_current_org
# ---------------------------------------------------------------------------


async def get_current_org(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    x_org_id: str | None = Header(None, alias="X-Org-ID"),
) -> Organization:
    """FastAPI dependency that resolves the active organization.

    Organization is determined in priority order:

    1. ``X-Org-ID`` header (explicit override)
    2. ``org_id`` from JWT claims or API token
    3. The user's sole organization (if they belong to exactly one)

    The user must be an active member of the resolved organization.

    Raises:
        HTTPException 400: Ambiguous organization (user has multiple, none specified).
        HTTPException 403: User is not a member of the requested organization.
        HTTPException 404: Organization not found.
    """
    org_id: str | None = None

    # Priority 1: X-Org-ID header
    if x_org_id:
        try:
            org_id = str(uuid.UUID(x_org_id))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Org-ID header — must be a valid UUID",
            )

    # Priority 2: From auth context (JWT org_id or API token org)
    if org_id is None:
        raw = getattr(request.state, "auth_org_id", None)
        if raw is not None:
            org_id = str(raw) if isinstance(raw, uuid.UUID) else raw

    # Priority 3: User's sole organization
    if org_id is None:
        membership_stmt = select(Membership).where(
            Membership.user_id == user.id,
        )
        result = await db.execute(membership_stmt)
        memberships = result.scalars().all()

        if len(memberships) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of any organization",
            )
        if len(memberships) == 1:
            org_id = memberships[0].organization_id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User belongs to multiple organizations; set X-Org-ID header or include org_id in JWT",
            )

    # Fetch and validate the organization
    org_stmt = select(Organization).where(Organization.id == org_id)
    result = await db.execute(org_stmt)
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization '{org_id}' not found",
        )

    if org.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization has been deleted",
        )

    # Verify membership
    membership_check = select(Membership).where(
        Membership.user_id == user.id,
        Membership.organization_id == org_id,
    )
    result = await db.execute(membership_check)
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    # Store for downstream use
    request.state.current_org = org
    request.state.current_membership = membership
    return org


# ---------------------------------------------------------------------------
# require_role
# ---------------------------------------------------------------------------


def require_role(
    minimum_role: str,
) -> Callable:
    """Factory that returns a FastAPI dependency enforcing a minimum role.

    The role hierarchy is: ``viewer`` < ``scientist`` < ``admin``.

    Args:
        minimum_role: The minimum role required (e.g. ``"admin"``).

    Returns:
        A FastAPI dependency that resolves to the authenticated :class:`User`
        if they hold at least ``minimum_role`` in the current organization.

    Usage::

        @router.delete("/org/{id}")
        async def delete_org(
            user: User = Depends(require_role("admin")),
        ):
            ...
    """
    min_level = _ROLE_HIERARCHY.get(minimum_role, 0)

    async def _check_role(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
        org: Organization = Depends(get_current_org),
    ) -> User:
        membership = getattr(request.state, "current_membership", None)

        if membership is None:
            # Shouldn't happen since get_current_org already checks, but be safe
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No membership found for current organization",
            )

        user_level = _ROLE_HIERARCHY.get(membership.role, -1)

        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{membership.role}' insufficient; "
                    f"requires '{minimum_role}' or higher"
                ),
            )

        return user

    return _check_role
