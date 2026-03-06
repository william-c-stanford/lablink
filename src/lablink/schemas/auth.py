"""Auth-related Pydantic schemas for registration, login, tokens, and users.

Provides request/response schemas for the auth service layer.
These are HTTP-agnostic and used by both routers and services.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from lablink.models import IdentityType, TokenScope


# ---------------------------------------------------------------------------
# Registration & Login
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Request body for new user registration."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)",
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable display name",
    )


class LoginRequest(BaseModel):
    """Request body for user login (credential verification)."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


# ---------------------------------------------------------------------------
# Token responses
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """JWT token pair returned after successful authentication."""

    access_token: str = Field(..., description="Short-lived JWT access token")
    refresh_token: str = Field(..., description="Long-lived refresh token for obtaining new access tokens")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Access token expiry in seconds")


# ---------------------------------------------------------------------------
# API tokens (programmatic / agent access)
# ---------------------------------------------------------------------------


class ApiTokenCreate(BaseModel):
    """Request body to create a new API token for programmatic access."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable label for the token, e.g. 'CI Pipeline'",
    )
    scope: TokenScope = Field(
        default=TokenScope.read,
        description="Permission scope: read, write, or admin",
    )
    identity_type: IdentityType = Field(
        default=IdentityType.user,
        description="Token identity type: user, agent, or integration",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiration timestamp (UTC). Null means no expiry.",
    )


class ApiTokenResponse(BaseModel):
    """API token representation returned by endpoints.

    The ``token`` field is populated **only** on creation; subsequent reads
    return ``None`` because the server stores only the hash.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique token identifier")
    name: str = Field(..., description="Human-readable token label")
    scope: str = Field(..., description="Permission scope: read, write, or admin")
    identity_type: str = Field(..., description="Token identity type: user, agent, or integration")
    created_at: datetime = Field(..., description="Timestamp when the token was created")
    expires_at: datetime | None = Field(None, description="Expiration timestamp, or null if no expiry")
    last_used_at: datetime | None = Field(None, description="Timestamp of last API call using this token")
    token: str | None = Field(
        default=None,
        description="Plaintext token value, returned only at creation time",
    )


# ---------------------------------------------------------------------------
# User response
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public user representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique user identifier")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="User display name")
    is_active: bool = Field(..., description="Whether the account is enabled")
    created_at: datetime = Field(..., description="Account creation timestamp")
