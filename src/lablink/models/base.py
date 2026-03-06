"""Common mixins for LabLink ORM models.

Provides:
- ``TimestampMixin``: ``id`` (UUID PK), ``created_at``, ``updated_at``
- ``SoftDeleteMixin``: ``deleted_at`` for soft-delete support
- ``UpdatedAtMixin``: standalone ``updated_at`` column

Base is imported from :mod:`lablink.database` — it is NOT defined here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from lablink.database import Base  # noqa: F401 — re-export for convenience


class TimestampMixin:
    """Provides ``id`` (UUID PK), ``created_at``, and ``updated_at``.

    Mix into any model that needs all three standard columns.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
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


class UpdatedAtMixin:
    """Adds an ``updated_at`` column that auto-updates on each flush."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds soft-delete support via a ``deleted_at`` timestamp.

    Records are never physically removed; instead ``deleted_at`` is set
    and queries should filter on :pyattr:`is_deleted`.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Return *True* when the record has been soft-deleted."""
        return self.deleted_at is not None
