"""Pydantic schemas for Campaign CRUD operations.

Campaigns represent a series of related experiments pursuing a shared
objective (e.g. Bayesian optimisation, grid search, manual iteration).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class CampaignStatus(str, Enum):
    """Valid campaign lifecycle states."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class CampaignCreate(BaseModel):
    """Request body to create a new campaign.

    A campaign always starts in ACTIVE status (enforced by the service).
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Campaign display name",
    )
    objective: str | None = Field(
        None,
        max_length=5000,
        description="Scientific or optimisation objective",
    )
    project_id: str | None = Field(
        None,
        max_length=36,
        description="Optional project ID to associate with",
    )
    optimization_method: str | None = Field(
        None,
        max_length=100,
        description="Optimisation strategy: bayesian, grid_search, manual, etc.",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Campaign name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class CampaignUpdate(BaseModel):
    """Request body to update campaign fields (PATCH semantics).

    All fields are optional — only provided fields are updated.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Campaign display name",
    )
    objective: str | None = Field(
        None,
        max_length=5000,
        description="Scientific or optimisation objective",
    )
    status: CampaignStatus | None = Field(
        None,
        description="Campaign status: active, paused, completed",
    )
    optimization_method: str | None = Field(
        None,
        max_length=100,
        description="Optimisation strategy",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        """Ensure name is not just whitespace when provided."""
        if v is not None:
            if not v.strip():
                raise ValueError("Campaign name must not be blank")
            return v.strip()
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> CampaignUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class CampaignRead(BaseModel):
    """Full campaign representation returned by API endpoints."""

    model_config = {"from_attributes": True}

    id: str
    org_id: str
    project_id: str | None = None
    created_by: str | None = None

    name: str
    objective: str | None = None
    status: CampaignStatus = CampaignStatus.ACTIVE
    optimization_method: str | None = None

    created_at: datetime
    updated_at: datetime

    # Agent-native: expose experiment count and progress summary
    experiment_count: int = Field(
        default=0,
        description="Number of experiments linked to this campaign",
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class CampaignListResponse(BaseModel):
    """Paginated list of campaigns."""

    items: list[CampaignRead]
    total: int
    page: int
    page_size: int
