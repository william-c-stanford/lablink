"""Experiment model — a scientific experiment with state-machine lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lablink.database import Base


class ExperimentStatus(str, PyEnum):
    """Valid experiment lifecycle states."""

    planned = "planned"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


EXPERIMENT_TRANSITIONS: dict[ExperimentStatus, set[ExperimentStatus]] = {
    ExperimentStatus.planned: {ExperimentStatus.running, ExperimentStatus.cancelled},
    ExperimentStatus.running: {ExperimentStatus.completed, ExperimentStatus.failed},
    ExperimentStatus.completed: set(),
    ExperimentStatus.failed: set(),
    ExperimentStatus.cancelled: set(),
}


class Experiment(Base):
    """A scientific experiment with intent, hypothesis, parameters, and outcomes.

    Follows a strict state-machine lifecycle:
        planned -> running -> completed | failed
        planned -> cancelled

    Experiments belong to an organization and optionally a project/campaign.
    They can be linked to multiple uploads via ExperimentUpload.
    """

    __tablename__ = "experiments"
    __table_args__ = (
        Index("ix_experiments_org_status", "organization_id", "status"),
        Index("ix_experiments_campaign", "campaign_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    campaign_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Core fields
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=ExperimentStatus.planned.value,
        nullable=False,
        index=True,
    )

    # Parameters and design
    parameters: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, default=dict, nullable=True,
    )
    constraints: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, default=dict, nullable=True,
    )
    outcome: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    design_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    design_agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Provenance
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # -- relationships -------------------------------------------------------
    campaign: Mapped[Optional["Campaign"]] = relationship(  # noqa: F821
        "Campaign",
        back_populates="experiments",
    )
    uploads: Mapped[list["ExperimentUpload"]] = relationship(  # noqa: F821
        "ExperimentUpload",
        back_populates="experiment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # --- State-machine helpers ---

    def can_transition_to(self, new_status: ExperimentStatus) -> bool:
        current = ExperimentStatus(self.status)
        return new_status in EXPERIMENT_TRANSITIONS.get(current, set())

    def transition_to(self, new_status: ExperimentStatus) -> None:
        if not self.can_transition_to(new_status):
            current = ExperimentStatus(self.status)
            valid = sorted(s.value for s in EXPERIMENT_TRANSITIONS.get(current, set()))
            raise ValueError(
                f"Cannot transition from '{self.status}' to '{new_status.value}'. "
                f"Valid transitions from '{self.status}': {valid}"
            )
        self.status = new_status.value

    @property
    def valid_transitions(self) -> set[ExperimentStatus]:
        current = ExperimentStatus(self.status)
        return EXPERIMENT_TRANSITIONS.get(current, set())

    @property
    def is_terminal(self) -> bool:
        current = ExperimentStatus(self.status)
        return not EXPERIMENT_TRANSITIONS.get(current, set())

    def __repr__(self) -> str:
        return f"<Experiment id={self.id!r} intent={self.intent!r} status={self.status!r}>"
