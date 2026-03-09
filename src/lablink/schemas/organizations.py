"""Pydantic schemas for Organization and Membership operations.

Provides request/response schemas for organization CRUD, member management,
and invitations. Aligned to the ORM models in lablink.models.identity.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from lablink.models import MemberRole


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


class OrganizationCreate(BaseModel):
    """Request body to create a new organization."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name of the organization",
    )
    slug: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="URL-safe unique identifier (lowercase, hyphens allowed, e.g. 'acme-labs')",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Organization name must not be blank")
        return v.strip()

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens only (e.g. 'acme-labs')"
            )
        return v


class OrganizationUpdate(BaseModel):
    """Request body to partially update an organization (PATCH semantics)."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New display name for the organization",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Organization name must not be blank")
        return v.strip() if v else v

    @model_validator(mode="after")
    def at_least_one_field(self) -> OrganizationUpdate:
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


class OrganizationResponse(BaseModel):
    """Full organization representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique organization identifier")
    name: str = Field(..., description="Display name")
    slug: str = Field(..., description="URL-safe unique identifier")
    tier: str = Field(..., description="Pricing tier: free, starter, professional, enterprise")
    storage_limit_bytes: int = Field(..., description="Maximum storage allowance in bytes")
    instrument_limit: int = Field(..., description="Maximum number of registered instruments")
    user_limit: int = Field(..., description="Maximum number of users")
    created_at: datetime = Field(..., description="Organization creation timestamp")


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


class MemberResponse(BaseModel):
    """Member record within an organization."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID = Field(..., description="User identifier")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="User display name")
    role: str = Field(..., description="Role within the organization: admin, scientist, viewer")
    created_at: datetime = Field(..., description="When the membership was created")


class InviteMemberRequest(BaseModel):
    """Request body to invite a new member to the organization."""

    email: EmailStr = Field(..., description="Email address of the user to invite")
    role: MemberRole = Field(
        default=MemberRole.scientist,
        description="Role to assign: admin, scientist, or viewer",
    )


class UpdateMemberRoleRequest(BaseModel):
    """Request body to change a member's role."""

    role: MemberRole = Field(
        ...,
        description="New role to assign: admin, scientist, or viewer",
    )
