"""Auth router — registration, login, token refresh, and API token management.

Endpoints:
    POST /auth/register       — Register a new user + organization
    POST /auth/login          — Authenticate and receive JWT tokens
    POST /auth/refresh        — Refresh an expired access token
    POST /auth/api-tokens     — Create a new API token
    GET  /auth/api-tokens     — List current user's API tokens
    DELETE /auth/api-tokens/{id} — Revoke an API token
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError
from lablink.models import ApiToken, Organization, User
from lablink.schemas.auth import (
    ApiTokenCreate,
    ApiTokenResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.services.auth_service import (
    authenticate_user,
    create_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=Envelope[dict],
    status_code=201,
    operation_id="register_user",
    response_model_exclude_none=True,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> Envelope:
    """Register a new user, creating an organization and admin membership."""
    user, org, token, expires_in = await register_user(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        org_name=body.org_name,
    )
    return success_response(
        data={
            "user": UserResponse.model_validate(user).model_dump(mode="json"),
            "token": TokenResponse(
                access_token=token,
                refresh_token=token,
                token_type="bearer",
                expires_in=expires_in,
            ).model_dump(mode="json"),
        }
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=Envelope[dict],
    operation_id="login_user",
    response_model_exclude_none=True,
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Envelope:
    """Authenticate a user and return JWT tokens."""
    user, token, expires_in = await authenticate_user(
        db, email=body.email, password=body.password
    )
    return success_response(
        data={
            "user": UserResponse.model_validate(user).model_dump(mode="json"),
            "token": TokenResponse(
                access_token=token,
                refresh_token=token,
                token_type="bearer",
                expires_in=expires_in,
            ).model_dump(mode="json"),
        }
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=Envelope[TokenResponse],
    operation_id="refresh_token",
    response_model_exclude_none=True,
)
async def refresh(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Envelope:
    """Refresh an access token using the current valid token."""
    from lablink.models import Membership

    membership_result = await db.execute(
        select(Membership).where(Membership.user_id == user.id).limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    org_id = str(membership.organization_id) if membership else ""

    token, expires_in = create_access_token(
        user_id=str(user.id),
        email=user.email,
        org_id=org_id,
    )
    return success_response(
        data=TokenResponse(
            access_token=token,
            refresh_token=token,
            token_type="bearer",
            expires_in=expires_in,
        )
    )


# ---------------------------------------------------------------------------
# POST /auth/api-tokens
# ---------------------------------------------------------------------------


@router.post(
    "/api-tokens",
    response_model=Envelope[ApiTokenResponse],
    status_code=201,
    operation_id="create_api_token",
    response_model_exclude_none=True,
)
async def create_api_token(
    body: ApiTokenCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Create a new API token for programmatic access."""
    raw_token = f"ll_{secrets.token_hex(24)}"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    api_token = ApiToken(
        organization_id=org.id,
        created_by=user.id,
        name=body.name,
        token_hash=token_hash,
        scope=body.scope.value,
        identity_type=body.identity_type.value,
        expires_at=body.expires_at,
    )
    db.add(api_token)
    await db.flush()

    response = ApiTokenResponse.model_validate(api_token)
    response.token = raw_token
    return success_response(data=response)


# ---------------------------------------------------------------------------
# GET /auth/api-tokens
# ---------------------------------------------------------------------------


@router.get(
    "/api-tokens",
    response_model=Envelope[list[ApiTokenResponse]],
    operation_id="list_api_tokens",
    response_model_exclude_none=True,
)
async def list_api_tokens(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List API tokens for the current user in the current organization."""
    from sqlalchemy import func

    count_stmt = select(func.count(ApiToken.id)).where(
        ApiToken.organization_id == org.id,
        ApiToken.created_by == user.id,
        ApiToken.is_active.is_(True),
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ApiToken)
        .where(
            ApiToken.organization_id == org.id,
            ApiToken.created_by == user.id,
            ApiToken.is_active.is_(True),
        )
        .order_by(ApiToken.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    tokens = [ApiTokenResponse.model_validate(t) for t in result.scalars().all()]

    return success_response(
        data=tokens,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# DELETE /auth/api-tokens/{id}
# ---------------------------------------------------------------------------


@router.delete(
    "/api-tokens/{token_id}",
    response_model=Envelope[dict],
    operation_id="revoke_api_token",
    response_model_exclude_none=True,
)
async def revoke_api_token(
    token_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Revoke (soft-delete) an API token."""
    stmt = select(ApiToken).where(
        ApiToken.id == token_id,
        ApiToken.organization_id == org.id,
        ApiToken.created_by == user.id,
    )
    result = await db.execute(stmt)
    api_token = result.scalar_one_or_none()

    if api_token is None:
        raise NotFoundError(
            message=f"API token '{token_id}' not found",
            suggestion="Use list_api_tokens to find valid token IDs.",
        )

    api_token.is_active = False
    api_token.deleted_at = datetime.now(timezone.utc)
    await db.flush()

    return success_response(data={"id": str(token_id), "revoked": True})
