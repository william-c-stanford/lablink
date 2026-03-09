"""Membership model — links Users to Organizations with a role."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lablink.database import Base


class MemberRole(str, PyEnum):
    """Membership roles within an organization."""

    admin = "admin"
    scientist = "scientist"
    viewer = "viewer"


class Membership(Base):
    """Links a :class:`User` to an :class:`Organization` with a role.

    The ``(user_id, organization_id)`` pair is unique — a user can hold
    exactly one role per organization.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organization_id",
            name="uq_membership_user_org",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=MemberRole.scientist.value,
        nullable=False,
        doc="Role within the organization",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="memberships")  # noqa: F821
    organization: Mapped["Organization"] = relationship(  # noqa: F821
        "Organization",
        back_populates="memberships",
    )

    def __repr__(self) -> str:
        return (
            f"<Membership user_id={self.user_id!r} "
            f"org_id={self.organization_id!r} role={self.role!r}>"
        )
