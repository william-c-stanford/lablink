"""Pydantic schemas for Experiment CRUD, outcome recording, and upload linking.

Aligned to the Experiment ORM model in lablink.models.experiment.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lablink.models.experiment import ExperimentStatus


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class ExperimentCreate(BaseModel):
    """Request body to create a new experiment."""

    intent: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="What the experiment aims to achieve",
    )
    hypothesis: str | None = Field(
        default=None,
        max_length=2000,
        description="Scientific hypothesis being tested",
    )
    parameters: dict[str, Any] | None = Field(
        default=None,
        description="Experimental conditions as key-value pairs (e.g. temperature, concentration)",
    )
    campaign_id: uuid.UUID | None = Field(
        default=None,
        description="Optional campaign to associate this experiment with",
    )
    predecessor_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="IDs of predecessor experiments that informed this one (DAG edges)",
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class ExperimentUpdate(BaseModel):
    """Request body to update experiment status (PATCH semantics).

    Status transitions follow the experiment state machine:
    planned -> running -> completed | failed; planned -> cancelled.
    """

    status: ExperimentStatus | None = Field(
        default=None,
        description="New experiment status (must be a valid transition)",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> ExperimentUpdate:
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class ExperimentResponse(BaseModel):
    """Full experiment representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique experiment identifier")
    intent: str = Field(..., description="What the experiment aims to achieve")
    hypothesis: str | None = Field(None, description="Scientific hypothesis being tested")
    status: str = Field(
        ..., description="Lifecycle status: planned, running, completed, failed, cancelled"
    )
    parameters: dict[str, Any] | None = Field(None, description="Experimental conditions")
    constraints: dict[str, Any] | None = Field(None, description="Bounds on parameters")
    outcome: dict[str, Any] | None = Field(None, description="Recorded results after completion")
    design_method: str | None = Field(
        None, description="How parameters were chosen: manual, bayesian_optimization, etc."
    )
    campaign_id: uuid.UUID | None = Field(None, description="Associated campaign, if any")
    created_by: uuid.UUID | None = Field(None, description="User who created the experiment")
    created_at: datetime = Field(..., description="Experiment creation timestamp")
    started_at: datetime | None = Field(
        None, description="Timestamp when experiment moved to running"
    )
    completed_at: datetime | None = Field(
        None, description="Timestamp when experiment completed or failed"
    )


# ---------------------------------------------------------------------------
# Outcome & Upload linking
# ---------------------------------------------------------------------------


class OutcomeRequest(BaseModel):
    """Request body to record the outcome of a completed experiment."""

    results: dict[str, Any] = Field(
        ...,
        description="Structured results data (metrics, measurements, observations)",
    )
    success: bool = Field(
        ...,
        description="Whether the experiment achieved its objective",
    )


class LinkUploadRequest(BaseModel):
    """Request body to link an upload (instrument data file) to an experiment."""

    upload_id: uuid.UUID = Field(
        ...,
        description="ID of the upload to associate with this experiment",
    )
