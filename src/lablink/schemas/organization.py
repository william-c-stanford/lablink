"""Pydantic schemas for Organization and Membership CRUD operations.

Provides OrganizationCreate, OrganizationUpdate, OrganizationRead,
MembershipRead, and related schemas aligned to the ORM models in
lablink.models.identity.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from lablink.models import MemberRole, Tier


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_slug(v: str) -> str:
    """Ensure slug is lowercase alphanumeric with hyphens only."""
    v = v.strip().lower()
    if not _SLUG_RE.match(v):
        raise ValueError(
            "Slug must be lowercase alphanumeric with hyphens only "
            "(e.g. 'acme-labs')"
        )
    return v


class OrganizationCreate(BaseModel):
    """Request body to create a new organization."""

    name: str = Field(
        ..., min_length=1, max_length=255,
        description="Display name of the organization",
    )
    slug: str = Field(
        ..., min_length=2, max_length=100,
        description="URL-safe unique identifier",
    )
    tier: Tier = Field(default=Tier.free, description="Pricing tier")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Organization name must not be blank")
        return v.strip()

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        return _validate_slug(v)


class OrganizationUpdate(BaseModel):
    """Request body to partially update an organization (PATCH semantics)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=2, max_length=100)
    tier: Optional[Tier] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Organization name must not be blank")
        return v.strip() if v else v

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_slug(v)
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> OrganizationUpdate:
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


class OrganizationRead(BaseModel):
    """Full organization representation returned by API."""

    id: uuid.UUID
    name: str
    slug: str
    tier: str
    storage_limit_bytes: int
    instrument_limit: int
    user_limit: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MembershipRead(BaseModel):
    """Membership record linking user to org."""

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    """Request body to add a member to an organization."""

    user_id: uuid.UUID = Field(..., description="UUID of the user to add")
    role: MemberRole = Field(
        default=MemberRole.scientist,
        description="Role to assign to the member",
    )
