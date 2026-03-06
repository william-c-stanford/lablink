"""Pydantic schemas for Campaign CRUD and progress tracking.

Aligned to the Campaign ORM model in lablink.models.experiment.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class CampaignCreate(BaseModel):
    """Request body to create a new optimization campaign."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Campaign name, e.g. 'Yield Optimization Q2'",
    )
    objective: str | None = Field(
        default=None,
        max_length=2000,
        description="What this campaign aims to achieve",
    )
    optimization_method: str | None = Field(
        default=None,
        max_length=100,
        description="Optimization strategy: bayesian, grid_search, manual, etc.",
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class CampaignResponse(BaseModel):
    """Full campaign representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique campaign identifier")
    name: str = Field(..., description="Campaign name")
    objective: str | None = Field(None, description="Campaign objective")
    status: str = Field(..., description="Lifecycle status: active, paused, completed")
    optimization_method: str | None = Field(None, description="Optimization strategy")
    created_by: uuid.UUID | None = Field(None, description="User who created the campaign")
    created_at: datetime = Field(..., description="Campaign creation timestamp")


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


class CampaignProgressResponse(BaseModel):
    """Aggregated progress metrics for a campaign."""

    campaign_id: uuid.UUID = Field(..., description="Campaign identifier")
    experiment_count: int = Field(..., description="Total number of experiments in the campaign")
    completed_count: int = Field(..., description="Number of completed experiments")
    failed_count: int = Field(..., description="Number of failed experiments")
    best_result: dict[str, Any] | None = Field(
        default=None,
        description="Best outcome observed so far (from completed experiments)",
    )
    trend: list[dict[str, Any]] | None = Field(
        default=None,
        description="Ordered list of outcomes showing optimization trajectory",
    )
