"""Tests for the Experiment model and its state machine integration."""

from __future__ import annotations

import pytest

from app.core.state_machine import InvalidTransitionError
from app.models.experiment import (
    EXPERIMENT_STATE_MACHINE,
    EXPERIMENT_TRANSITIONS,
    Experiment,
    ExperimentStatus,
)


# --- ExperimentStatus enum ---


class TestExperimentStatus:
    def test_all_states_present(self) -> None:
        expected = {"DRAFT", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
        assert {s.name for s in ExperimentStatus} == expected

    def test_values_are_lowercase(self) -> None:
        for s in ExperimentStatus:
            assert s.value == s.name.lower()

    def test_is_str_enum(self) -> None:
        assert isinstance(ExperimentStatus.DRAFT, str)
        assert ExperimentStatus.DRAFT == "draft"


# --- EXPERIMENT_STATE_MACHINE singleton ---


class TestExperimentStateMachine:
    def test_initial_state_is_draft(self) -> None:
        assert EXPERIMENT_STATE_MACHINE.initial_state == ExperimentStatus.DRAFT

    def test_terminal_states(self) -> None:
        assert EXPERIMENT_STATE_MACHINE.terminal_states == {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
        }

    def test_all_states_covered(self) -> None:
        assert EXPERIMENT_STATE_MACHINE.states == set(ExperimentStatus)

    def test_draft_transitions(self) -> None:
        valid = EXPERIMENT_STATE_MACHINE.valid_transitions(ExperimentStatus.DRAFT)
        assert valid == {ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED}

    def test_running_transitions(self) -> None:
        valid = EXPERIMENT_STATE_MACHINE.valid_transitions(ExperimentStatus.RUNNING)
        assert valid == {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}

    def test_backward_compat_transitions_dict(self) -> None:
        """EXPERIMENT_TRANSITIONS dict is backward-compatible with the state machine."""
        assert EXPERIMENT_TRANSITIONS[ExperimentStatus.DRAFT] == {
            ExperimentStatus.RUNNING,
            ExperimentStatus.CANCELLED,
        }
        assert EXPERIMENT_TRANSITIONS[ExperimentStatus.COMPLETED] == set()


# --- Experiment model (in-memory, no DB) ---


def _make_experiment(status: str = "draft", **kwargs) -> Experiment:
    """Create an Experiment instance without persisting to DB.

    Uses the normal constructor which SQLAlchemy instruments correctly.
    """
    defaults = {
        "id": "exp-001",
        "org_id": "org-001",
        "name": "Test Experiment",
        "status": status,
    }
    defaults.update(kwargs)
    return Experiment(**defaults)


class TestExperimentCanTransitionTo:
    def test_draft_to_running(self) -> None:
        exp = _make_experiment("draft")
        assert exp.can_transition_to(ExperimentStatus.RUNNING) is True

    def test_draft_to_cancelled(self) -> None:
        exp = _make_experiment("draft")
        assert exp.can_transition_to(ExperimentStatus.CANCELLED) is True

    def test_draft_to_completed_blocked(self) -> None:
        exp = _make_experiment("draft")
        assert exp.can_transition_to(ExperimentStatus.COMPLETED) is False

    def test_running_to_completed(self) -> None:
        exp = _make_experiment("running")
        assert exp.can_transition_to(ExperimentStatus.COMPLETED) is True

    def test_running_to_failed(self) -> None:
        exp = _make_experiment("running")
        assert exp.can_transition_to(ExperimentStatus.FAILED) is True

    def test_completed_is_terminal(self) -> None:
        exp = _make_experiment("completed")
        for s in ExperimentStatus:
            assert exp.can_transition_to(s) is False


class TestExperimentTransitionTo:
    def test_valid_transition_updates_status(self) -> None:
        exp = _make_experiment("draft")
        exp.transition_to(ExperimentStatus.RUNNING)
        assert exp.status == "running"

    def test_chain_transitions(self) -> None:
        exp = _make_experiment("draft")
        exp.transition_to(ExperimentStatus.RUNNING)
        exp.transition_to(ExperimentStatus.COMPLETED)
        assert exp.status == "completed"

    def test_invalid_transition_raises(self) -> None:
        exp = _make_experiment("draft")
        with pytest.raises(InvalidTransitionError) as exc_info:
            exp.transition_to(ExperimentStatus.COMPLETED)
        err = exc_info.value
        assert err.current_state == ExperimentStatus.DRAFT
        assert err.target_state == ExperimentStatus.COMPLETED

    def test_terminal_state_blocks_transition(self) -> None:
        exp = _make_experiment("failed")
        with pytest.raises(InvalidTransitionError):
            exp.transition_to(ExperimentStatus.RUNNING)


class TestExperimentValidTransitions:
    def test_draft_valid_transitions(self) -> None:
        exp = _make_experiment("draft")
        assert exp.valid_transitions == {ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED}

    def test_terminal_no_transitions(self) -> None:
        exp = _make_experiment("cancelled")
        assert exp.valid_transitions == set()


class TestExperimentIsTerminal:
    def test_draft_not_terminal(self) -> None:
        exp = _make_experiment("draft")
        assert exp.is_terminal is False

    def test_running_not_terminal(self) -> None:
        exp = _make_experiment("running")
        assert exp.is_terminal is False

    def test_completed_is_terminal(self) -> None:
        exp = _make_experiment("completed")
        assert exp.is_terminal is True

    def test_failed_is_terminal(self) -> None:
        exp = _make_experiment("failed")
        assert exp.is_terminal is True

    def test_cancelled_is_terminal(self) -> None:
        exp = _make_experiment("cancelled")
        assert exp.is_terminal is True


class TestExperimentRepr:
    def test_repr_includes_key_fields(self) -> None:
        exp = _make_experiment("draft", name="My Experiment")
        r = repr(exp)
        assert "Experiment" in r
        assert "My Experiment" in r
        assert "draft" in r


class TestExperimentDefaults:
    def test_default_status_is_draft(self) -> None:
        """The column default should be 'draft'."""
        col = Experiment.__table__.columns["status"]
        assert col.default.arg == "draft"
