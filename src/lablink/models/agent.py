"""Agent model — a desktop agent instance that watches folders and uploads files."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lablink.database import Base


class Agent(Base):
    """A desktop agent instance that watches folders and uploads files.

    Agents are identified by an API key (hashed) and report heartbeats
    to indicate liveness.  The ``status`` field tracks agent health:
    active, inactive, or offline.
    """

    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_org_status", "organization_id", "status"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )  # windows, macos, linux
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active",
    )
    config: Mapped[Optional[dict]] = mapped_column(
        JSON, default=dict, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    instruments: Mapped[list["Instrument"]] = relationship(  # noqa: F821
        "Instrument",
        back_populates="agent",
        lazy="selectin",
    )

    VALID_STATUSES = {"active", "inactive", "offline"}
    VALID_PLATFORMS = {"windows", "macos", "linux"}

    def __repr__(self) -> str:
        return f"<Agent {self.name!r} status={self.status!r}>"

    @property
    def is_online(self) -> bool:
        return self.status == "active"

    def record_heartbeat(self) -> None:
        """Update the last heartbeat timestamp to now."""
        self.last_heartbeat_at = datetime.now(timezone.utc)
        self.status = "active"
