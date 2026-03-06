"""Auth router — thin layer delegating to auth service.

Endpoints:
  POST /auth/register  — Create user + org, return JWT
  POST /auth/login     — Authenticate, return JWT
  GET  /auth/me        — Return current user (protected)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.database import get_session
from app.dependencies import get_current_user
from app.models.identity import User
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.envelope import Envelope
from app.services.auth import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Envelope[TokenResponse], status_code=201)
async def register(
    body: UserRegisterRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Envelope[TokenResponse]:
    """Register a new user and organization."""
    user, org, token, expires_in = await register_user(
        session=session,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        org_name=body.org_name,
        org_slug=body.org_slug,
        settings=settings,
    )
    return Envelope.ok(
        TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
        )
    )


@router.post("/login", response_model=Envelope[TokenResponse])
async def login(
    body: UserLoginRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Envelope[TokenResponse]:
    """Authenticate and return a JWT token."""
    user, token, expires_in = await authenticate_user(
        session=session,
        email=body.email,
        password=body.password,
        settings=settings,
    )
    return Envelope.ok(
        TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
        )
    )


@router.get("/me", response_model=Envelope[UserResponse])
async def me(
    current_user: User = Depends(get_current_user),
) -> Envelope[UserResponse]:
    """Return the currently authenticated user."""
    return Envelope.ok(
        UserResponse(
            id=current_user.id,
            email=current_user.email,
            display_name=current_user.display_name,
            org_id=current_user.org_id,
            is_active=current_user.is_active,
            is_service_account=current_user.is_service_account,
            created_at=current_user.created_at,
            last_login_at=current_user.last_login_at,
        )
    )
