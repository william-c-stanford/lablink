"""Webhook model — outbound webhook subscription for an organization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lablink.database import Base


class Webhook(Base):
    """Outbound webhook subscription for an organization.

    Webhooks receive POST requests with JSON payloads signed using
    HMAC-SHA256.  The ``events`` list specifies which event types
    trigger delivery (e.g. ``upload.completed``, ``parsing.completed``).
    """

    __tablename__ = "webhooks"

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
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="HMAC-SHA256 signing secret",
    )
    events: Mapped[list[str]] = mapped_column(
        JSON, nullable=False,
        doc='Event types, e.g. ["upload.completed", "parsing.completed"]',
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(  # noqa: F821
        "WebhookDelivery",
        back_populates="webhook",
        lazy="selectin",
    )

    SUPPORTED_EVENTS = {
        "upload.completed",
        "parsing.completed",
        "parsing.failed",
        "experiment.created",
        "experiment.status_changed",
        "experiment.completed",
        "agent.connected",
        "agent.disconnected",
    }

    def __repr__(self) -> str:
        return f"<Webhook id={self.id!s:.8} url={self.url!r} active={self.is_active}>"

    def subscribes_to(self, event_type: str) -> bool:
        """Check if this webhook is subscribed to the given event type."""
        return self.is_active and event_type in self.events
