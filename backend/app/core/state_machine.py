"""Reusable finite state machine helper for domain models.

Provides a generic StateMachine class that validates transitions between
enum-based states. Used by Experiment and potentially other models with
lifecycle state management (e.g., ingestion pipelines, campaigns).

Usage:
    >>> from enum import Enum
    >>> class Status(str, Enum):
    ...     DRAFT = "draft"
    ...     RUNNING = "running"
    ...     DONE = "done"
    >>> sm = StateMachine(transitions={
    ...     Status.DRAFT: {Status.RUNNING},
    ...     Status.RUNNING: {Status.DONE},
    ...     Status.DONE: set(),
    ... })
    >>> sm.can_transition(Status.DRAFT, Status.RUNNING)
    True
    >>> sm.validate_transition(Status.DONE, Status.DRAFT)
    Traceback (most recent call last):
        ...
    app.core.state_machine.InvalidTransitionError: ...
"""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

E = TypeVar("E", bound=Enum)


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed.

    Attributes:
        current_state: The current state value.
        target_state: The attempted target state.
        valid_targets: Set of valid target states from current.
        suggestion: Agent-friendly suggestion for recovery.
    """

    def __init__(
        self,
        current_state: Enum,
        target_state: Enum,
        valid_targets: set[Enum],
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        self.valid_targets = valid_targets
        valid_names = sorted(s.value for s in valid_targets) if valid_targets else ["(none — terminal state)"]
        self.suggestion = (
            f"Cannot transition from '{current_state.value}' to '{target_state.value}'. "
            f"Valid transitions from '{current_state.value}': {valid_names}"
        )
        super().__init__(self.suggestion)


class StateMachine(Generic[E]):
    """Generic finite state machine that validates enum-based state transitions.

    Args:
        transitions: Mapping of each state to its set of valid target states.
        initial_state: The default starting state for new entities.

    The machine is stateless — it doesn't track any entity's current state,
    it only validates whether a given transition is allowed. This makes it
    safe to use as a module-level singleton shared across requests.
    """

    def __init__(
        self,
        transitions: dict[E, set[E]],
        initial_state: E,
    ) -> None:
        self._transitions = transitions
        self._initial_state = initial_state
        # Validate that all target states appear as keys
        all_states = set(transitions.keys())
        for source, targets in transitions.items():
            unknown = targets - all_states
            if unknown:
                raise ValueError(
                    f"Transition targets {unknown} from {source} are not declared states"
                )

    @property
    def initial_state(self) -> E:
        """The default starting state."""
        return self._initial_state

    @property
    def states(self) -> set[E]:
        """All known states."""
        return set(self._transitions.keys())

    @property
    def terminal_states(self) -> set[E]:
        """States with no outgoing transitions."""
        return {s for s, targets in self._transitions.items() if not targets}

    def valid_transitions(self, current: E) -> set[E]:
        """Return valid target states from the given state."""
        return self._transitions.get(current, set())

    def can_transition(self, current: E, target: E) -> bool:
        """Check whether transitioning from current to target is allowed."""
        return target in self._transitions.get(current, set())

    def validate_transition(self, current: E, target: E) -> None:
        """Validate a transition, raising InvalidTransitionError if not allowed.

        Args:
            current: The current state.
            target: The desired target state.

        Raises:
            InvalidTransitionError: If the transition is not in the allowed set.
        """
        if not self.can_transition(current, target):
            raise InvalidTransitionError(
                current_state=current,
                target_state=target,
                valid_targets=self.valid_transitions(current),
            )

    def is_terminal(self, state: E) -> bool:
        """True if the state has no outgoing transitions."""
        return not self._transitions.get(state, set())

    def __repr__(self) -> str:
        states = sorted(s.value for s in self._transitions.keys())
        return f"<StateMachine states={states} initial={self._initial_state.value!r}>"
