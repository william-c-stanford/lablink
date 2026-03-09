"""Campaign model — a series of related experiments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lablink.database import Base


if TYPE_CHECKING:
    from lablink.models.experiment import Experiment


class CampaignStatus(str, PyEnum):
    """Valid campaign lifecycle states."""

    active = "active"
    paused = "paused"
    completed = "completed"


CAMPAIGN_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.active: {CampaignStatus.paused, CampaignStatus.completed},
    CampaignStatus.paused: {CampaignStatus.active, CampaignStatus.completed},
    CampaignStatus.completed: set(),
}


class Campaign(Base):
    """A series of related experiments, e.g. an optimization campaign.

    Campaigns group experiments that share a common objective and
    optimization strategy (bayesian, grid_search, manual, etc.).
    """

    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_org_status", "organization_id", "status"),)

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=CampaignStatus.active.value,
        nullable=False,
        index=True,
    )
    optimization_method: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    experiments: Mapped[list["Experiment"]] = relationship(  # noqa: F821
        "Experiment",
        back_populates="campaign",
        lazy="selectin",
    )

    def can_transition_to(self, new_status: CampaignStatus) -> bool:
        """Check if the campaign can transition to the given status."""
        current = CampaignStatus(self.status)
        return new_status in CAMPAIGN_TRANSITIONS.get(current, set())

    def transition_to(self, new_status: CampaignStatus) -> None:
        """Transition to a new status, raising ValueError if invalid."""
        if not self.can_transition_to(new_status):
            current = CampaignStatus(self.status)
            valid = sorted(s.value for s in CAMPAIGN_TRANSITIONS.get(current, set()))
            raise ValueError(
                f"Cannot transition campaign from '{self.status}' to '{new_status.value}'. "
                f"Valid transitions: {valid}"
            )
        self.status = new_status.value

    @property
    def is_terminal(self) -> bool:
        current = CampaignStatus(self.status)
        return not CAMPAIGN_TRANSITIONS.get(current, set())

    def __repr__(self) -> str:
        return f"<Campaign id={self.id!r} name={self.name!r} status={self.status!r}>"
