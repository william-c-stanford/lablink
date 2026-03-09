"""AuditEvent model — immutable, hash-chained audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from lablink.database import Base


class AuditEvent(Base):
    """Immutable, hash-chained audit trail entry.

    Every significant action in the system generates an AuditEvent.
    The ``hash`` field contains SHA-256(previous_hash + event_data)
    to ensure chain integrity — any tampering is detectable.

    ``actor_type`` identifies who performed the action:
    - ``user``: a human user (actor_id = user UUID)
    - ``agent``: a desktop agent (actor_id = agent UUID)
    - ``system``: an automated system process (actor_id may be NULL)
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "idx_audit_events_org_resource",
            "organization_id",
            "resource_type",
            "resource_id",
        ),
        Index("idx_audit_events_created", "organization_id", "created_at"),
        Index("idx_audit_events_actor", "organization_id", "actor_type", "actor_id"),
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
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # user, agent, system
    actor_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # e.g. upload.created, experiment.status_changed
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # upload, experiment, project, etc.
    resource_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )  # IPv4/IPv6 as string
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="SHA-256 chain integrity hash",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    VALID_ACTOR_TYPES = {"user", "agent", "system"}

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id!s:.8} action={self.action!r} "
            f"resource={self.resource_type}:{self.resource_id!s:.8}>"
        )
