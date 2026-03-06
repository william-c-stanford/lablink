"""Pydantic schemas for Organization CRUD operations.

Provides OrganizationCreate, OrganizationUpdate, OrganizationRead, and
OrganizationList with validation rules aligned to the Organization ORM
model in app.models.identity.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.identity import PlanTier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class OrganizationCreate(BaseModel):
    """Request body to create a new organization.

    The organization starts on the free plan by default.
    """

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
        description="URL-safe unique identifier (lowercase, hyphens allowed)",
    )
    plan: PlanTier = Field(
        default=PlanTier.free,
        description="Pricing tier for the organization",
    )
    description: str | None = Field(
        None,
        max_length=5000,
        description="Optional organization description",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Organization name must not be blank")
        return v.strip()

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        return _validate_slug(v)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class OrganizationUpdate(BaseModel):
    """Request body to update organization fields (PATCH semantics).

    All fields are optional -- only provided fields are updated.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Display name of the organization",
    )
    slug: str | None = Field(
        None,
        min_length=2,
        max_length=100,
        description="URL-safe unique identifier",
    )
    plan: PlanTier | None = Field(
        None,
        description="Pricing tier for the organization",
    )
    description: str | None = Field(
        None,
        max_length=5000,
        description="Optional organization description",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Organization name must not be blank")
            return v.strip()
        return v

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_slug(v)
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> OrganizationUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class OrganizationRead(BaseModel):
    """Full organization representation returned by API endpoints."""

    id: str
    name: str
    slug: str
    plan: PlanTier
    description: str | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class OrganizationList(BaseModel):
    """Paginated list of organizations."""

    items: list[OrganizationRead]
    total: int
    page: int
    page_size: int
