"""WebhookDelivery model — tracks individual webhook delivery attempts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lablink.database import Base


class DeliveryStatus(str, enum.Enum):
    """Webhook delivery lifecycle states."""

    pending = "pending"
    delivered = "delivered"
    failed = "failed"


class WebhookDelivery(Base):
    """Tracks individual webhook delivery attempts.

    Each delivery starts as ``pending`` and moves to ``delivered``
    or ``failed`` after the HTTP request completes.  The system
    retries failed deliveries up to a configurable limit.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    webhook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DeliveryStatus.pending.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    response_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    webhook: Mapped["Webhook"] = relationship(  # noqa: F821
        "Webhook",
        back_populates="deliveries",
        lazy="joined",
    )

    MAX_ATTEMPTS = 5

    def __repr__(self) -> str:
        return (
            f"<WebhookDelivery id={self.id!s:.8} webhook_id={self.webhook_id!s:.8} "
            f"status={self.status!r} attempts={self.attempts}>"
        )

    @property
    def can_retry(self) -> bool:
        """Whether this delivery can be retried."""
        return self.status == DeliveryStatus.failed.value and self.attempts < self.MAX_ATTEMPTS
