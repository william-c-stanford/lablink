"""Pydantic schemas for Experiment CRUD and state transitions.

Provides ExperimentCreate, ExperimentUpdate, ExperimentRead, and
ExperimentStateTransition with validation rules aligned to the
Experiment ORM model and its state machine lifecycle.
"""

from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.experiment import EXPERIMENT_TRANSITIONS, ExperimentStatus


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class ExperimentCreate(BaseModel):
    """Request body to create a new experiment.

    The experiment always starts in DRAFT status (enforced by the service).
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Experiment display name",
    )
    description: str | None = Field(
        None,
        max_length=5000,
        description="Detailed experiment description",
    )
    hypothesis: str | None = Field(
        None,
        max_length=5000,
        description="Scientific hypothesis being tested",
    )
    intent: str | None = Field(
        None,
        max_length=500,
        description="Brief statement of experimental intent/goal",
    )
    project_id: str | None = Field(
        None,
        max_length=36,
        description="Optional project ID to associate with",
    )
    campaign_id: str | None = Field(
        None,
        max_length=36,
        description="Optional campaign ID to associate with",
    )
    parameters: dict[str, Any] | None = Field(
        None,
        description="Experiment parameters/conditions (stored as JSON)",
    )
    protocol: str | None = Field(
        None,
        max_length=10000,
        description="Protocol or method description",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Experiment name must not be blank")
        return v.strip()

    def to_orm_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for ORM model construction.

        Serialises the ``parameters`` dict to a JSON string for the
        ``parameters_json`` column.
        """
        d = self.model_dump(exclude_none=True)
        params = d.pop("parameters", None)
        if params is not None:
            d["parameters_json"] = _json.dumps(params)
        return d


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class ExperimentUpdate(BaseModel):
    """Request body to update experiment fields (PATCH semantics).

    All fields are optional — only provided fields are updated.
    Status changes must go through ExperimentStateTransition.
    """

    name: str | None = Field(None, min_length=1, max_length=255, description="Experiment display name")
    description: str | None = Field(None, max_length=5000, description="Detailed description")
    hypothesis: str | None = Field(None, max_length=5000, description="Scientific hypothesis")
    intent: str | None = Field(None, max_length=500, description="Brief goal statement")
    project_id: str | None = Field(None, max_length=36, description="Optional project ID")
    campaign_id: str | None = Field(None, max_length=36, description="Optional campaign ID")
    parameters: dict[str, Any] | None = Field(None, description="Experiment parameters (stored as JSON)")
    protocol: str | None = Field(None, max_length=10000, description="Protocol or method description")
    outcome_summary: str | None = Field(None, max_length=5000, description="Human-readable outcome summary")
    outcome: dict[str, Any] | None = Field(None, description="Measured results/outcome data (stored as JSON)")
    success: bool | None = Field(None, description="Whether the experiment achieved its objective")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        """Ensure name is not just whitespace when provided."""
        if v is not None:
            if not v.strip():
                raise ValueError("Experiment name must not be blank")
            return v.strip()
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> ExperimentUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self

    def to_orm_dict(self) -> dict[str, Any]:
        """Convert to a dict of only the explicitly set fields for ORM update.

        Maps ``parameters`` -> ``parameters_json`` and
        ``outcome`` -> ``outcome_json`` for column compatibility.
        """
        d = self.model_dump(exclude_unset=True)
        params = d.pop("parameters", None)
        if params is not None:
            d["parameters_json"] = _json.dumps(params)
        outcome = d.pop("outcome", None)
        if outcome is not None:
            d["outcome_json"] = _json.dumps(outcome)
        return d


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class ExperimentFileLink(BaseModel):
    """Represents an experiment-file association in read responses."""

    upload_id: str
    role: str | None = None
    description: str | None = None
    added_by: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExperimentRead(BaseModel):
    """Full experiment representation returned by API endpoints.

    Includes agent-native computed fields (valid_transitions, is_terminal)
    so that consuming agents know what actions are possible.
    """

    id: str
    org_id: str
    project_id: str | None = None
    campaign_id: str | None = None
    created_by: str | None = None

    name: str
    description: str | None = None
    hypothesis: str | None = None
    intent: str | None = None

    status: ExperimentStatus
    parameters: dict[str, Any] | None = None
    protocol: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None

    outcome: dict[str, Any] | None = None
    outcome_summary: str | None = None
    success: bool | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    # Agent-native: expose valid transitions so agents know what's possible
    valid_transitions: list[ExperimentStatus] = Field(
        default_factory=list,
        description="Valid next states from current status",
    )
    is_terminal: bool = Field(
        default=False,
        description="Whether the experiment is in a terminal state",
    )

    experiment_files: list[ExperimentFileLink] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, data: Any) -> Any:
        """Deserialise JSON columns and compute agent-native fields.

        Handles both ORM model instances (with ``parameters_json`` /
        ``outcome_json`` string columns) and plain dicts.
        """
        if hasattr(data, "__dict__"):
            # ORM object — convert to mutable dict
            d: dict[str, Any] = {}
            for key in (
                "id", "org_id", "project_id", "campaign_id", "created_by",
                "name", "description", "hypothesis", "intent", "status",
                "parameters_json", "protocol", "started_at", "completed_at",
                "outcome_json", "outcome_summary", "success",
                "created_at", "updated_at", "deleted_at",
            ):
                val = getattr(data, key, None)
                d[key] = val
            # experiment_files is a lazy-loaded relationship that may trigger
            # a greenlet error in async contexts — guard the access
            try:
                d["experiment_files"] = getattr(data, "experiment_files", None)
            except Exception:
                d["experiment_files"] = []
            data = d

        # Map JSON string columns -> parsed dicts
        params_raw = data.pop("parameters_json", None) if isinstance(data, dict) else None
        if params_raw and isinstance(params_raw, str):
            try:
                data["parameters"] = _json.loads(params_raw)
            except (ValueError, TypeError):
                data["parameters"] = None
        elif params_raw and isinstance(params_raw, dict):
            data["parameters"] = params_raw

        outcome_raw = data.pop("outcome_json", None) if isinstance(data, dict) else None
        if outcome_raw and isinstance(outcome_raw, str):
            try:
                data["outcome"] = _json.loads(outcome_raw)
            except (ValueError, TypeError):
                data["outcome"] = None
        elif outcome_raw and isinstance(outcome_raw, dict):
            data["outcome"] = outcome_raw

        # Compute agent-native fields
        status_val = data.get("status") if isinstance(data, dict) else None
        if status_val:
            try:
                status_enum = (
                    ExperimentStatus(status_val)
                    if not isinstance(status_val, ExperimentStatus)
                    else status_val
                )
                allowed = EXPERIMENT_TRANSITIONS.get(status_enum, set())
                data["valid_transitions"] = sorted(t.value for t in allowed)
                data["is_terminal"] = status_enum in {
                    ExperimentStatus.COMPLETED,
                    ExperimentStatus.FAILED,
                    ExperimentStatus.CANCELLED,
                }
            except ValueError:
                pass

        return data


# Backward-compatible alias used by earlier code
ExperimentResponse = ExperimentRead


# ---------------------------------------------------------------------------
# State transition
# ---------------------------------------------------------------------------


class ExperimentStateTransition(BaseModel):
    """Request body to transition an experiment's lifecycle state.

    Validates the target status and requires a reason for the immutable
    audit trail.
    """

    target_status: ExperimentStatus = Field(
        ...,
        description="The desired new status for the experiment",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Reason for the state transition (required for audit trail)",
    )
    outcome_summary: str | None = Field(
        None,
        max_length=5000,
        description="Outcome summary (typically set when completing/failing)",
    )
    outcome: dict[str, Any] | None = Field(
        None,
        description="Outcome data (typically set when completing/failing)",
    )
    success: bool | None = Field(
        None,
        description="Whether the experiment succeeded (set on completion)",
    )

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        """Ensure reason is not just whitespace."""
        if not v.strip():
            raise ValueError("Transition reason must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def validate_outcome_fields(self) -> ExperimentStateTransition:
        """Outcome/success fields are only valid for terminal transitions."""
        terminal_statuses = {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
        }
        if self.target_status not in terminal_statuses:
            if self.outcome is not None or self.success is not None:
                raise ValueError(
                    "outcome and success can only be set when transitioning "
                    "to a terminal state (completed, failed, cancelled)"
                )
        return self

    def validate_transition(self, current_status: ExperimentStatus) -> list[str]:
        """Check if this transition is allowed from ``current_status``.

        Returns a list of error messages (empty list == valid).
        """
        errors: list[str] = []
        allowed = EXPERIMENT_TRANSITIONS.get(current_status, set())
        if self.target_status not in allowed:
            valid_names = sorted(s.value for s in allowed) if allowed else ["none"]
            errors.append(
                f"Cannot transition from '{current_status.value}' to "
                f"'{self.target_status.value}'. "
                f"Valid transitions: {', '.join(valid_names)}"
            )
        return errors


# Keep old name as alias for backward compatibility
ExperimentTransition = ExperimentStateTransition


# ---------------------------------------------------------------------------
# List response helper
# ---------------------------------------------------------------------------


class ExperimentListResponse(BaseModel):
    """Paginated list of experiments."""

    items: list[ExperimentRead]
    total: int
    page: int
    page_size: int
