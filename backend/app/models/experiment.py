"""Experiment models: Experiment, ExperimentFile.

Experiments track scientific work with a state machine lifecycle
(draft -> running -> completed/failed, draft -> cancelled).
ExperimentFile provides many-to-many linking between experiments and uploads.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.state_machine import StateMachine
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExperimentStatus(str, Enum):
    """Valid experiment lifecycle states.

    State transitions:
        draft -> running
        draft -> cancelled
        running -> completed
        running -> failed
    """

    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Reusable state machine instance for experiment lifecycle
EXPERIMENT_STATE_MACHINE = StateMachine(
    transitions={
        ExperimentStatus.DRAFT: {ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED},
        ExperimentStatus.RUNNING: {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED},
        ExperimentStatus.COMPLETED: set(),
        ExperimentStatus.FAILED: set(),
        ExperimentStatus.CANCELLED: set(),
    },
    initial_state=ExperimentStatus.DRAFT,
)

# Backward-compatible alias for code that references EXPERIMENT_TRANSITIONS directly
EXPERIMENT_TRANSITIONS: dict[ExperimentStatus, set[ExperimentStatus]] = {
    state: EXPERIMENT_STATE_MACHINE.valid_transitions(state)
    for state in ExperimentStatus
}


class Experiment(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A scientific experiment with intent, hypothesis, parameters, and outcomes.

    Follows a strict state machine lifecycle:
        draft -> running -> completed | failed
        draft -> cancelled

    Experiments belong to an organization and optionally a project/campaign.
    They can be linked to multiple uploads via ExperimentFile.
    """

    __tablename__ = "experiments"

    # Foreign keys
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="Project ID (FK added when projects table is created)",
    )
    campaign_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="Campaign ID (FK added when campaigns table is created)",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Core fields
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Experiment display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed experiment description",
    )
    hypothesis: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Scientific hypothesis being tested",
    )
    intent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Brief statement of experimental intent/goal",
    )

    # State machine
    status: Mapped[str] = mapped_column(
        String(20),
        default=ExperimentStatus.DRAFT.value,
        nullable=False,
        index=True,
        comment="Lifecycle state: draft, running, completed, failed, cancelled",
    )

    # Parameters and configuration
    parameters_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Experiment parameters/conditions as JSON",
    )
    protocol: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Protocol or method description",
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the experiment was started (transitioned to running)",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the experiment ended (completed, failed, or cancelled)",
    )

    # Outcomes
    outcome_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Measured results/outcome data as JSON",
    )
    outcome_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable summary of the outcome",
    )
    success: Mapped[bool | None] = mapped_column(
        nullable=True,
        comment="Whether the experiment achieved its objective (NULL if no outcome yet)",
    )

    # Relationships
    experiment_files: Mapped[list[ExperimentFile]] = relationship(
        "ExperimentFile",
        back_populates="experiment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_experiments_org_status", "org_id", "status"),
        Index("ix_experiments_org_campaign", "org_id", "campaign_id"),
    )

    def can_transition_to(self, new_status: ExperimentStatus) -> bool:
        """Check if the experiment can transition to the given status."""
        current = ExperimentStatus(self.status)
        return EXPERIMENT_STATE_MACHINE.can_transition(current, new_status)

    def transition_to(self, new_status: ExperimentStatus) -> None:
        """Transition to a new status, raising InvalidTransitionError if not allowed.

        This validates the transition and updates self.status in place.
        The caller is responsible for committing the session.

        Args:
            new_status: The target ExperimentStatus.

        Raises:
            InvalidTransitionError: If the transition is not allowed.
        """
        current = ExperimentStatus(self.status)
        EXPERIMENT_STATE_MACHINE.validate_transition(current, new_status)
        self.status = new_status.value

    @property
    def valid_transitions(self) -> set[ExperimentStatus]:
        """Return the set of valid next states from the current state."""
        current = ExperimentStatus(self.status)
        return EXPERIMENT_STATE_MACHINE.valid_transitions(current)

    @property
    def is_terminal(self) -> bool:
        """True if the experiment is in a terminal state (completed, failed, cancelled)."""
        current = ExperimentStatus(self.status)
        return EXPERIMENT_STATE_MACHINE.is_terminal(current)

    def __repr__(self) -> str:
        return f"<Experiment(id={self.id!r}, name={self.name!r}, status={self.status!r})>"


class ExperimentFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Many-to-many link between experiments and uploads.

    Tracks which instrument files (uploads) are associated with
    which experiments, with optional role/description for the link.
    """

    __tablename__ = "experiment_files"

    # Foreign keys
    experiment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("file_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Link metadata
    role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Role of this file in the experiment: input, output, reference, calibration",
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional description of why this file is linked",
    )
    added_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    experiment: Mapped[Experiment] = relationship(
        "Experiment",
        back_populates="experiment_files",
    )

    __table_args__ = (
        Index(
            "ix_experiment_files_unique",
            "experiment_id",
            "upload_id",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExperimentFile(experiment_id={self.experiment_id!r}, "
            f"upload_id={self.upload_id!r}, role={self.role!r})>"
        )
