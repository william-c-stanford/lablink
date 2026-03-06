"""Auth-related Pydantic schemas for registration, login, and token handling."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=8, max_length=128, description="Password (8-128 characters)"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable display name"
    )
    org_name: str = Field(
        ..., min_length=1, max_length=255, description="Organization name"
    )
    org_slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe org slug (lowercase, hyphens allowed)",
    )


class UserLoginRequest(BaseModel):
    """Request body for login (credential verification)."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    """JWT token response returned after successful authentication."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Token expiry in seconds")


class UserResponse(BaseModel):
    """Public user representation returned by API endpoints."""

    id: str
    email: str
    display_name: str
    org_id: str
    is_active: bool
    is_service_account: bool
    created_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
