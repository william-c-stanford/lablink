"""Tests for the reusable StateMachine helper."""

from __future__ import annotations

from enum import Enum

import pytest

from app.core.state_machine import InvalidTransitionError, StateMachine


# --- Test enum ---


class TrafficLight(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


TRAFFIC_TRANSITIONS = {
    TrafficLight.RED: {TrafficLight.GREEN},
    TrafficLight.GREEN: {TrafficLight.YELLOW},
    TrafficLight.YELLOW: {TrafficLight.RED},
}


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


TASK_TRANSITIONS = {
    TaskStatus.TODO: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


@pytest.fixture
def traffic_sm() -> StateMachine[TrafficLight]:
    return StateMachine(transitions=TRAFFIC_TRANSITIONS, initial_state=TrafficLight.RED)


@pytest.fixture
def task_sm() -> StateMachine[TaskStatus]:
    return StateMachine(transitions=TASK_TRANSITIONS, initial_state=TaskStatus.TODO)


# --- Construction tests ---


class TestStateMachineConstruction:
    def test_initial_state(self, traffic_sm: StateMachine[TrafficLight]) -> None:
        assert traffic_sm.initial_state == TrafficLight.RED

    def test_states(self, traffic_sm: StateMachine[TrafficLight]) -> None:
        assert traffic_sm.states == {TrafficLight.RED, TrafficLight.GREEN, TrafficLight.YELLOW}

    def test_terminal_states_cyclic(self, traffic_sm: StateMachine[TrafficLight]) -> None:
        """A cyclic state machine has no terminal states."""
        assert traffic_sm.terminal_states == set()

    def test_terminal_states_with_sinks(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.terminal_states == {TaskStatus.DONE, TaskStatus.CANCELLED}

    def test_invalid_target_state_raises(self) -> None:
        """Defining a transition to an undeclared state should fail at construction."""

        class Broken(str, Enum):
            A = "a"
            B = "b"

        with pytest.raises(ValueError, match="not declared states"):
            StateMachine(
                transitions={Broken.A: {Broken.B}},  # B is a target but not a key
                initial_state=Broken.A,
            )

    def test_repr(self, traffic_sm: StateMachine[TrafficLight]) -> None:
        r = repr(traffic_sm)
        assert "StateMachine" in r
        assert "red" in r


# --- Transition validation tests ---


class TestCanTransition:
    def test_valid_transition(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.can_transition(TaskStatus.TODO, TaskStatus.IN_PROGRESS) is True

    def test_invalid_transition(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.can_transition(TaskStatus.TODO, TaskStatus.DONE) is False

    def test_self_transition_not_allowed(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.can_transition(TaskStatus.TODO, TaskStatus.TODO) is False

    def test_terminal_state_blocks_all(self, task_sm: StateMachine[TaskStatus]) -> None:
        for target in TaskStatus:
            assert task_sm.can_transition(TaskStatus.DONE, target) is False

    def test_cyclic_transitions(self, traffic_sm: StateMachine[TrafficLight]) -> None:
        assert traffic_sm.can_transition(TrafficLight.RED, TrafficLight.GREEN) is True
        assert traffic_sm.can_transition(TrafficLight.GREEN, TrafficLight.YELLOW) is True
        assert traffic_sm.can_transition(TrafficLight.YELLOW, TrafficLight.RED) is True

    def test_reverse_not_allowed(self, traffic_sm: StateMachine[TrafficLight]) -> None:
        assert traffic_sm.can_transition(TrafficLight.GREEN, TrafficLight.RED) is False


class TestValidateTransition:
    def test_valid_does_not_raise(self, task_sm: StateMachine[TaskStatus]) -> None:
        task_sm.validate_transition(TaskStatus.TODO, TaskStatus.IN_PROGRESS)

    def test_invalid_raises_with_details(self, task_sm: StateMachine[TaskStatus]) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            task_sm.validate_transition(TaskStatus.DONE, TaskStatus.TODO)
        err = exc_info.value
        assert err.current_state == TaskStatus.DONE
        assert err.target_state == TaskStatus.TODO
        assert err.valid_targets == set()
        assert "terminal state" in err.suggestion

    def test_error_suggestion_lists_valid_targets(self, task_sm: StateMachine[TaskStatus]) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            task_sm.validate_transition(TaskStatus.TODO, TaskStatus.DONE)
        err = exc_info.value
        assert "cancelled" in err.suggestion
        assert "in_progress" in err.suggestion

    def test_error_is_exception(self, task_sm: StateMachine[TaskStatus]) -> None:
        """InvalidTransitionError is a standard Exception subclass."""
        with pytest.raises(Exception):
            task_sm.validate_transition(TaskStatus.DONE, TaskStatus.TODO)


class TestValidTransitions:
    def test_returns_set(self, task_sm: StateMachine[TaskStatus]) -> None:
        result = task_sm.valid_transitions(TaskStatus.TODO)
        assert result == {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}

    def test_terminal_returns_empty(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.valid_transitions(TaskStatus.DONE) == set()


class TestIsTerminal:
    def test_terminal(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.is_terminal(TaskStatus.DONE) is True
        assert task_sm.is_terminal(TaskStatus.CANCELLED) is True

    def test_non_terminal(self, task_sm: StateMachine[TaskStatus]) -> None:
        assert task_sm.is_terminal(TaskStatus.TODO) is False
        assert task_sm.is_terminal(TaskStatus.IN_PROGRESS) is False
