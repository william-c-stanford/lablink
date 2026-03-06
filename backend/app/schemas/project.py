"""Pydantic schemas for Project CRUD operations.

Provides ProjectCreate, ProjectUpdate, ProjectRead, and ProjectList
with validation rules. Projects are org-scoped containers that group
experiments, datasets, and uploads.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectStatus(str, PyEnum):
    """Lifecycle states for a project."""

    active = "active"
    archived = "archived"
    completed = "completed"


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
            "(e.g. 'protein-binding-study')"
        )
    return v


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    """Request body to create a new project.

    Projects always start in ``active`` status (enforced by the service).
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project display name",
    )
    slug: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="URL-safe unique identifier within the org (lowercase, hyphens allowed)",
    )
    description: str | None = Field(
        None,
        max_length=5000,
        description="Detailed project description",
    )
    goal: str | None = Field(
        None,
        max_length=5000,
        description="Scientific or business goal for this project",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Project name must not be blank")
        return v.strip()

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        return _validate_slug(v)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class ProjectUpdate(BaseModel):
    """Request body to update project fields (PATCH semantics).

    All fields are optional -- only provided fields are updated.
    Status changes should use the dedicated status transition endpoint
    when one exists, but can also be set directly via update for simplicity.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Project display name",
    )
    slug: str | None = Field(
        None,
        min_length=2,
        max_length=100,
        description="URL-safe unique identifier",
    )
    description: str | None = Field(
        None,
        max_length=5000,
        description="Detailed project description",
    )
    goal: str | None = Field(
        None,
        max_length=5000,
        description="Scientific or business goal",
    )
    status: ProjectStatus | None = Field(
        None,
        description="Project lifecycle status",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Project name must not be blank")
            return v.strip()
        return v

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_slug(v)
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> ProjectUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class ProjectRead(BaseModel):
    """Full project representation returned by API endpoints.

    Includes computed counts for agent-native discoverability so that
    consuming agents can assess project scope at a glance.
    """

    id: str
    org_id: str
    created_by: str | None = None

    name: str
    slug: str
    description: str | None = None
    goal: str | None = None
    status: ProjectStatus = ProjectStatus.active

    # Denormalized counts for agent-native API
    experiment_count: int = Field(
        default=0,
        description="Number of experiments in this project",
    )
    dataset_count: int = Field(
        default=0,
        description="Number of datasets in this project",
    )

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class ProjectList(BaseModel):
    """Paginated list of projects."""

    items: list[ProjectRead]
    total: int
    page: int
    page_size: int
