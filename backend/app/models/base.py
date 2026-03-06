"""SQLAlchemy declarative base and common model mixins."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


class TimestampMixin:
    """Adds created_at and updated_at columns with automatic timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key column."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class SoftDeleteMixin:
    """Adds soft-delete support with a deleted_at timestamp."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditMixin:
    """Immutable audit trail with hash chain for tamper detection.

    Each record stores:
      - actor_id: who performed the action
      - action: what happened (e.g. 'create', 'update', 'delete')
      - prev_hash: hash of the previous audit entry (chain link)
      - record_hash: SHA-256 hash of this record's auditable content
    """

    actor_id: Mapped[str | None] = mapped_column(
        String(36),
        default=None,
        nullable=True,
        doc="UUID of the user/agent that performed the action",
    )
    action: Mapped[str | None] = mapped_column(
        String(50),
        default=None,
        nullable=True,
        doc="Audit action: create, update, delete, etc.",
    )
    prev_hash: Mapped[str | None] = mapped_column(
        String(64),
        default=None,
        nullable=True,
        doc="SHA-256 hash of previous record in audit chain",
    )
    record_hash: Mapped[str | None] = mapped_column(
        String(64),
        default=None,
        nullable=True,
        doc="SHA-256 hash of this record's auditable content",
    )

    def compute_hash(self, fields: dict[str, Any] | None = None) -> str:
        """Compute SHA-256 hash over the given fields dict.

        Args:
            fields: Dict of field names to values. If None, uses a default
                    set of {id, actor_id, action, prev_hash}.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        if fields is None:
            fields = {
                "id": getattr(self, "id", None),
                "actor_id": self.actor_id,
                "action": self.action,
                "prev_hash": self.prev_hash,
            }
        payload = json.dumps(fields, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()
