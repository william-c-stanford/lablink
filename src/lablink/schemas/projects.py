"""Pydantic schemas for Project CRUD operations.

Provides ProjectCreate, ProjectUpdate, and ProjectResponse aligned to the
Project ORM model in lablink.models.lab.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    """Request body to create a new project."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project name, e.g. 'Q2 Formulation Study'",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional project description",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Project name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class ProjectUpdate(BaseModel):
    """Request body to partially update a project (PATCH semantics)."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New project name",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="New project description",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Project name must not be blank")
        return v.strip() if v else v

    @model_validator(mode="after")
    def at_least_one_field(self) -> ProjectUpdate:
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class ProjectResponse(BaseModel):
    """Full project representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: str | None = Field(None, description="Project description")
    created_by: uuid.UUID = Field(..., description="User who created the project")
    created_at: datetime = Field(..., description="Project creation timestamp")
    archived_at: datetime | None = Field(None, description="Archive timestamp, null if active")
