"""Tests for Experiment Pydantic schemas.

Covers ExperimentCreate, ExperimentUpdate, ExperimentRead, and
ExperimentStateTransition with validation rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.experiment import ExperimentStatus
from app.schemas.experiment import (
    ExperimentCreate,
    ExperimentRead,
    ExperimentStateTransition,
    ExperimentUpdate,
)


# ---------------------------------------------------------------------------
# ExperimentCreate
# ---------------------------------------------------------------------------


class TestExperimentCreate:
    """Tests for ExperimentCreate schema."""

    def test_minimal_create(self):
        schema = ExperimentCreate(name="My Experiment")
        assert schema.name == "My Experiment"
        assert schema.description is None
        assert schema.hypothesis is None
        assert schema.parameters is None

    def test_full_create(self):
        schema = ExperimentCreate(
            name="HPLC Run 42",
            description="Testing compound X separation",
            hypothesis="Compound X elutes at 5.2 min",
            intent="Characterize purity",
            project_id="proj-123",
            campaign_id="camp-456",
            parameters={"flow_rate": 1.0, "column": "C18"},
            protocol="Standard HPLC protocol v3",
        )
        assert schema.name == "HPLC Run 42"
        assert schema.parameters == {"flow_rate": 1.0, "column": "C18"}

    def test_name_stripped(self):
        schema = ExperimentCreate(name="  padded name  ")
        assert schema.name == "padded name"

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            ExperimentCreate(name="   ")

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ExperimentCreate(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            ExperimentCreate(name="x" * 256)

    def test_intent_max_length(self):
        with pytest.raises(ValidationError):
            ExperimentCreate(name="Test", intent="x" * 501)

    def test_to_orm_dict_without_parameters(self):
        schema = ExperimentCreate(name="Test", description="desc")
        d = schema.to_orm_dict()
        assert d["name"] == "Test"
        assert d["description"] == "desc"
        assert "parameters" not in d
        assert "parameters_json" not in d

    def test_to_orm_dict_with_parameters(self):
        schema = ExperimentCreate(
            name="Test",
            parameters={"temp": 37.0},
        )
        d = schema.to_orm_dict()
        assert "parameters" not in d
        assert d["parameters_json"] == json.dumps({"temp": 37.0})


# ---------------------------------------------------------------------------
# ExperimentUpdate
# ---------------------------------------------------------------------------


class TestExperimentUpdate:
    """Tests for ExperimentUpdate schema."""

    def test_single_field_update(self):
        schema = ExperimentUpdate(name="New Name")
        assert schema.name == "New Name"

    def test_multiple_fields_update(self):
        schema = ExperimentUpdate(
            name="Updated",
            description="New desc",
            success=True,
        )
        assert schema.name == "Updated"
        assert schema.success is True

    def test_name_stripped(self):
        schema = ExperimentUpdate(name="  spaces  ")
        assert schema.name == "spaces"

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            ExperimentUpdate(name="   ")

    def test_no_fields_rejected(self):
        with pytest.raises(ValidationError, match="At least one field"):
            ExperimentUpdate()

    def test_to_orm_dict_maps_parameters(self):
        schema = ExperimentUpdate(parameters={"ph": 7.4})
        d = schema.to_orm_dict()
        assert "parameters" not in d
        assert d["parameters_json"] == json.dumps({"ph": 7.4})

    def test_to_orm_dict_maps_outcome(self):
        schema = ExperimentUpdate(outcome={"yield": 95.0})
        d = schema.to_orm_dict()
        assert "outcome" not in d
        assert d["outcome_json"] == json.dumps({"yield": 95.0})

    def test_to_orm_dict_excludes_unset(self):
        schema = ExperimentUpdate(name="Only Name")
        d = schema.to_orm_dict()
        assert "name" in d
        assert "description" not in d
        assert "hypothesis" not in d


# ---------------------------------------------------------------------------
# ExperimentRead
# ---------------------------------------------------------------------------


class TestExperimentRead:
    """Tests for ExperimentRead schema."""

    def _base_data(self, **overrides) -> dict:
        """Helper to build a minimal valid ExperimentRead dict."""
        now = datetime.now(timezone.utc)
        base = {
            "id": "exp-1",
            "org_id": "org-1",
            "name": "Test",
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        base.update(overrides)
        return base

    def test_planned_transitions(self):
        schema = ExperimentRead.model_validate(self._base_data(status="draft"))
        assert ExperimentStatus.RUNNING in schema.valid_transitions
        assert ExperimentStatus.CANCELLED in schema.valid_transitions
        assert schema.is_terminal is False

    def test_running_transitions(self):
        schema = ExperimentRead.model_validate(self._base_data(status="running"))
        assert ExperimentStatus.COMPLETED in schema.valid_transitions
        assert ExperimentStatus.FAILED in schema.valid_transitions
        assert schema.is_terminal is False

    def test_completed_is_terminal(self):
        schema = ExperimentRead.model_validate(self._base_data(status="completed"))
        assert schema.valid_transitions == []
        assert schema.is_terminal is True

    def test_failed_is_terminal(self):
        schema = ExperimentRead.model_validate(self._base_data(status="failed"))
        assert schema.valid_transitions == []
        assert schema.is_terminal is True

    def test_cancelled_is_terminal(self):
        schema = ExperimentRead.model_validate(self._base_data(status="cancelled"))
        assert schema.valid_transitions == []
        assert schema.is_terminal is True

    def test_parameters_json_deserialized(self):
        schema = ExperimentRead.model_validate(
            self._base_data(parameters_json='{"flow_rate": 1.0}')
        )
        assert schema.parameters == {"flow_rate": 1.0}

    def test_outcome_json_deserialized(self):
        schema = ExperimentRead.model_validate(
            self._base_data(outcome_json='{"yield": 92.5}')
        )
        assert schema.outcome == {"yield": 92.5}

    def test_parameters_dict_passthrough(self):
        """When parameters is already a dict (not JSON string)."""
        schema = ExperimentRead.model_validate(
            self._base_data(parameters_json={"temp": 25})
        )
        assert schema.parameters == {"temp": 25}

    def test_invalid_json_returns_none(self):
        schema = ExperimentRead.model_validate(
            self._base_data(parameters_json="not-json{{{")
        )
        assert schema.parameters is None

    def test_from_attributes_config(self):
        assert ExperimentRead.model_config["from_attributes"] is True


# ---------------------------------------------------------------------------
# ExperimentStateTransition
# ---------------------------------------------------------------------------


class TestExperimentStateTransition:
    """Tests for ExperimentStateTransition schema."""

    def test_valid_transition_to_running(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="Starting experiment",
        )
        assert schema.target_status == ExperimentStatus.RUNNING
        assert schema.reason == "Starting experiment"

    def test_reason_required(self):
        with pytest.raises(ValidationError):
            ExperimentStateTransition(
                target_status=ExperimentStatus.RUNNING,
            )

    def test_blank_reason_rejected(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            ExperimentStateTransition(
                target_status=ExperimentStatus.RUNNING,
                reason="   ",
            )

    def test_reason_stripped(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="  starting now  ",
        )
        assert schema.reason == "starting now"

    def test_outcome_allowed_on_completed(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.COMPLETED,
            reason="Experiment finished",
            outcome={"yield": 95.0},
            success=True,
            outcome_summary="High yield achieved",
        )
        assert schema.outcome == {"yield": 95.0}
        assert schema.success is True

    def test_outcome_allowed_on_failed(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.FAILED,
            reason="Equipment malfunction",
            success=False,
        )
        assert schema.success is False

    def test_outcome_rejected_on_running(self):
        with pytest.raises(ValidationError, match="terminal state"):
            ExperimentStateTransition(
                target_status=ExperimentStatus.RUNNING,
                reason="Starting",
                outcome={"data": 1},
            )

    def test_success_rejected_on_running(self):
        with pytest.raises(ValidationError, match="terminal state"):
            ExperimentStateTransition(
                target_status=ExperimentStatus.RUNNING,
                reason="Starting",
                success=True,
            )

    def test_validate_transition_valid(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="Go",
        )
        errors = schema.validate_transition(ExperimentStatus.DRAFT)
        assert errors == []

    def test_validate_transition_invalid(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.COMPLETED,
            reason="Done",
            success=True,
        )
        errors = schema.validate_transition(ExperimentStatus.DRAFT)
        assert len(errors) == 1
        assert "Cannot transition" in errors[0]
        assert "draft" in errors[0]
        assert "completed" in errors[0]

    def test_validate_transition_from_terminal(self):
        schema = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="Retry",
        )
        errors = schema.validate_transition(ExperimentStatus.COMPLETED)
        assert len(errors) == 1
        assert "none" in errors[0]

    def test_invalid_target_status(self):
        with pytest.raises(ValidationError):
            ExperimentStateTransition(
                target_status="invalid_status",
                reason="Bad status",
            )
