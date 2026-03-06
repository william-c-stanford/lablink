"""System and audit models: AuditEvent, AuditLog, Notification, SystemConfig."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AuditAction(str, PyEnum):
    """Actions recorded in the audit log."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    RESTORE = "RESTORE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    UPLOAD = "UPLOAD"
    PARSE = "PARSE"
    EXPORT = "EXPORT"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    STATE_CHANGE = "STATE_CHANGE"


class NotificationLevel(str, PyEnum):
    """Severity levels for notifications."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class NotificationStatus(str, PyEnum):
    """Read/unread status for notifications."""

    UNREAD = "UNREAD"
    READ = "READ"
    DISMISSED = "DISMISSED"


# ---------------------------------------------------------------------------
# AuditLog – Immutable audit trail with hash chain
# ---------------------------------------------------------------------------


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable, append-only audit trail.

    Each entry is hash-chained to the previous entry so that any tampering
    is detectable.  Rows are never updated or deleted.
    """

    __tablename__ = "audit_logs"

    # Sequence for ordering (auto-incrementing, separate from UUID PK)
    sequence: Mapped[int] = mapped_column(
        Integer, autoincrement=True, unique=True, nullable=False
    )

    # What happened
    action: Mapped[str] = mapped_column(
        Enum(AuditAction, native_enum=False, length=32),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Who did it
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(32), default="user", nullable=False
    )  # "user", "system", "agent"

    # Details
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hash chain for immutability verification
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamp (not using mixin — audit logs have their own immutable timestamp)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_actor", "actor_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry's content + previous hash."""
        payload = json.dumps(
            {
                "id": self.id,
                "sequence": self.sequence,
                "action": self.action,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "actor_id": self.actor_id,
                "summary": self.summary,
                "detail": self.detail,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def extra_metadata(self) -> dict | None:
        """Parse metadata_json back to dict."""
        if self.metadata_json is None:
            return None
        return json.loads(self.metadata_json)

    @extra_metadata.setter
    def extra_metadata(self, value: dict | None) -> None:
        self.metadata_json = json.dumps(value) if value is not None else None


# ---------------------------------------------------------------------------
# AuditEvent – Canonical append-only audit trail (spec-aligned)
# ---------------------------------------------------------------------------


class AuditEvent(Base, UUIDPrimaryKeyMixin):
    """Immutable, append-only audit event with hash chain for tamper detection.

    This model enforces an append-only contract: rows are never updated or
    deleted.  Each event is hash-chained to its predecessor so that any
    tampering with historical records is detectable by verifying the chain.

    Field naming follows the AC spec:
      event_hash / previous_hash  (hash chain)
      actor / action / resource_type / resource_id / timestamp / detail
    """

    __tablename__ = "audit_events"

    # ---- ordering ----------------------------------------------------------
    sequence: Mapped[int] = mapped_column(
        Integer, autoincrement=True, unique=True, nullable=False,
        doc="Monotonic sequence number for deterministic ordering",
    )

    # ---- who / what --------------------------------------------------------
    actor: Mapped[str] = mapped_column(
        String(256), nullable=False,
        doc="Identifier of the user, agent, or system that triggered the event",
    )
    actor_type: Mapped[str] = mapped_column(
        String(32), default="user", nullable=False,
        doc="Category of actor: user, agent, system, api_key",
    )
    action: Mapped[str] = mapped_column(
        Enum(AuditAction, native_enum=False, length=32), nullable=False,
        doc="The action that was performed",
    )

    # ---- target resource ---------------------------------------------------
    resource_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
        doc="Type of resource affected (e.g. experiment, file_record, dataset)",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        doc="UUID of the affected resource (null for system-wide events)",
    )

    # ---- detail payload ----------------------------------------------------
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="JSON-serialised detail payload with event-specific data",
    )

    # ---- hash chain --------------------------------------------------------
    previous_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        doc="SHA-256 hash of the preceding event (null for genesis event)",
    )
    event_hash: Mapped[str] = mapped_column(
        String(64), nullable=False,
        doc="SHA-256 hash of this event's content + previous_hash",
    )

    # ---- timestamp (own column, not mixin – immutable) ---------------------
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        doc="Immutable wall-clock time of the event",
    )

    __table_args__ = (
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
        Index("ix_audit_events_actor", "actor"),
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_timestamp", "timestamp"),
    )

    # ---- hash computation --------------------------------------------------

    def compute_hash(self) -> str:
        """Compute SHA-256 hash over canonical fields + previous_hash.

        The hash covers: id, sequence, actor, action, resource_type,
        resource_id, detail, previous_hash.  Timestamp is intentionally
        excluded to allow deterministic hashing before server_default fires.
        """
        payload = json.dumps(
            {
                "id": self.id,
                "sequence": self.sequence,
                "actor": self.actor,
                "action": self.action,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "detail": self.detail,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ---- detail helpers ----------------------------------------------------

    @property
    def detail_dict(self) -> dict | None:
        """Parse detail JSON string back to a dict."""
        if self.detail is None:
            return None
        return json.loads(self.detail)

    @detail_dict.setter
    def detail_dict(self, value: dict | None) -> None:
        self.detail = json.dumps(value) if value is not None else None

    def __repr__(self) -> str:
        return (
            f"<AuditEvent(id={self.id!r}, action={self.action!r}, "
            f"resource_type={self.resource_type!r}, actor={self.actor!r})>"
        )


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User/system notifications (e.g. parse complete, error alerts)."""

    __tablename__ = "notifications"

    # Target
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lab_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Content
    level: Mapped[str] = mapped_column(
        Enum(NotificationLevel, native_enum=False, length=16),
        default=NotificationLevel.INFO.value,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        Enum(NotificationStatus, native_enum=False, length=16),
        default=NotificationStatus.UNREAD.value,
        nullable=False,
    )

    # Optional link to related resource
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Read timestamp
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_notifications_user_status", "user_id", "status"),
        Index("ix_notifications_lab", "lab_id"),
        Index("ix_notifications_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# SystemConfig – Key-value configuration store
# ---------------------------------------------------------------------------


class SystemConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Dynamic key-value system configuration.

    Used for runtime-configurable settings that don't require a restart
    (e.g. feature flags, parser defaults, retention policies).
    """

    __tablename__ = "system_configs"

    # Unique config key, namespaced with dots (e.g. "parsers.balance.tolerance")
    key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(
        String(16), default="string", nullable=False
    )  # string, int, float, bool, json

    # Documentation
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(
        String(64), default="general", nullable=False
    )

    # Change tracking
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_system_configs_category", "category"),
    )

    @property
    def typed_value(self) -> str | int | float | bool | dict | list:
        """Return value cast to its declared type."""
        if self.value_type == "int":
            return int(self.value)
        if self.value_type == "float":
            return float(self.value)
        if self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        if self.value_type == "json":
            return json.loads(self.value)
        return self.value
