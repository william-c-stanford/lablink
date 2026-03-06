"""Core identity models: Organization, User, Role, ApiKey.

These form the multi-tenant identity layer. Every resource in LabLink
belongs to an Organization. Users belong to Organizations via Roles.
ApiKeys provide programmatic access for agents and integrations.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    AuditMixin,
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlanTier(str, PyEnum):
    """Pricing tiers for organizations."""

    free = "free"
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class RoleName(str, PyEnum):
    """Built-in role names."""

    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"
    agent = "agent"


class ApiKeyStatus(str, PyEnum):
    """API key lifecycle states."""

    active = "active"
    revoked = "revoked"
    expired = "expired"


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A lab or research organization — the top-level tenant."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Display name of the organization"
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        doc="URL-safe unique identifier",
    )
    plan: Mapped[str] = mapped_column(
        String(20),
        default=PlanTier.free.value,
        nullable=False,
        doc="Current pricing tier",
    )
    description: Mapped[str | None] = mapped_column(
        Text, default=None, nullable=True, doc="Optional description"
    )

    # Relationships
    users: Mapped[list[User]] = relationship(
        "User", back_populates="organization", lazy="selectin"
    )
    roles: Mapped[list[Role]] = relationship(
        "Role", back_populates="organization", lazy="selectin"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="organization", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id!r} slug={self.slug!r}>"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """A human or service-account user within an organization."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_org_id", "org_id"),
    )

    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Parent organization",
    )
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, doc="Unique email address"
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Human-readable display name"
    )
    hashed_password: Mapped[str | None] = mapped_column(
        String(255),
        default=None,
        nullable=True,
        doc="Argon2/bcrypt hash (null for SSO-only users)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, doc="Account enabled flag"
    )
    is_service_account: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="True for agent/bot accounts",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
        doc="Timestamp of last successful login",
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="users"
    )
    roles: Mapped[list[Role]] = relationship(
        "Role", back_populates="user", lazy="selectin"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r}>"


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Maps a user to an organization with a named role.

    This is a join-table-style model that also carries metadata.
    A user can have exactly one role per organization.
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_roles_user_org"),
        Index("ix_roles_org_id", "org_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_name: Mapped[str] = mapped_column(
        String(20),
        default=RoleName.member.value,
        nullable=False,
        doc="Role within the organization",
    )
    granted_by: Mapped[str | None] = mapped_column(
        String(36),
        default=None,
        nullable=True,
        doc="UUID of user who granted this role",
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="roles")
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="roles"
    )

    def __repr__(self) -> str:
        return f"<Role user_id={self.user_id!r} role={self.role_name!r}>"


# ---------------------------------------------------------------------------
# ApiKey
# ---------------------------------------------------------------------------


def _generate_api_key_prefix() -> str:
    """Generate a short prefix for API key identification (e.g. 'll_abc123')."""
    return f"ll_{secrets.token_hex(4)}"


def _generate_api_key_hash() -> str:
    """Generate a secure random API key value."""
    return secrets.token_urlsafe(48)


class ApiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """API key for programmatic/agent access.

    The raw key is only shown once at creation time. We store a
    SHA-256 hash of the key for lookup/validation.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash"),
        Index("ix_api_keys_org_id", "org_id"),
        Index("ix_api_keys_user_id", "user_id"),
    )

    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="User who owns this key",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Human label for the key"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(20),
        default=_generate_api_key_prefix,
        nullable=False,
        doc="Short visible prefix for identification (e.g. ll_abc123)",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        doc="SHA-256 hash of the full API key",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=ApiKeyStatus.active.value,
        nullable=False,
        doc="Current key status",
    )
    scopes: Mapped[str | None] = mapped_column(
        Text,
        default=None,
        nullable=True,
        doc="Comma-separated list of permitted scopes",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
        doc="Optional expiration timestamp",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
        doc="Timestamp of last API call with this key",
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="api_keys"
    )
    user: Mapped[User] = relationship("User", back_populates="api_keys")

    @property
    def is_active(self) -> bool:
        """Check if key is active and not expired."""
        if self.status != ApiKeyStatus.active.value:
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False
        return True

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id!r} prefix={self.key_prefix!r}>"
