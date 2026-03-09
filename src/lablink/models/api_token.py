"""ApiToken model — programmatic access for agents and integrations."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lablink.database import Base
from lablink.models.base import SoftDeleteMixin


class TokenScope(str, PyEnum):
    """API token permission scopes."""

    read = "read"
    write = "write"
    admin = "admin"


class IdentityType(str, PyEnum):
    """Identity type for API tokens."""

    user = "user"
    agent = "agent"
    integration = "integration"


def _token_prefix() -> str:
    """Generate a short prefix for token identification (e.g. ``ll_a1b2c3``)."""
    return f"ll_{secrets.token_hex(4)}"


class ApiToken(Base, SoftDeleteMixin):
    """API token for programmatic / agent access.

    The raw token value is shown only at creation time.  We store a
    SHA-256 hash (``token_hash``) for lookup and validation.
    """

    __tablename__ = "api_tokens"

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
    created_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="User who created this token",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human label for the token",
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        doc="SHA-256 hash of the full token value",
    )
    scope: Mapped[str] = mapped_column(
        String(20),
        default=TokenScope.read.value,
        nullable=False,
        doc="Permission scope: read, write, admin",
    )
    identity_type: Mapped[str] = mapped_column(
        String(20),
        default=IdentityType.user.value,
        nullable=False,
        doc="Token identity: user, agent, integration",
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Token enabled flag",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    organization: Mapped["Organization"] = relationship(  # noqa: F821
        "Organization",
        back_populates="api_tokens",
    )
    creator: Mapped["User"] = relationship("User")  # noqa: F821

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Return the SHA-256 hex digest of *raw_token*."""
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @property
    def is_valid(self) -> bool:
        """Return *True* when the token is active and not expired."""
        if not self.is_active:
            return False
        if self.expires_at is not None and self.expires_at < datetime.now(timezone.utc):
            return False
        return True

    def __repr__(self) -> str:
        return f"<ApiToken id={self.id!r} name={self.name!r}>"
