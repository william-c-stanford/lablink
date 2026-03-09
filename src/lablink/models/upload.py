"""Upload model — raw instrument file uploaded by a user or agent."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lablink.database import Base


if TYPE_CHECKING:
    from lablink.models.parsed_data import ParsedData

class UploadStatus(str, enum.Enum):
    """Upload lifecycle states."""

    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    parse_failed = "parse_failed"
    indexed = "indexed"


class Upload(Base):
    """Raw instrument file uploaded by a user or agent.

    Tracks the file through the ingestion pipeline:
    uploaded -> parsing -> parsed -> indexed (or parse_failed).

    The content_hash (SHA-256) is used for deduplication within an org.
    """

    __tablename__ = "uploads"
    __table_args__ = (
        UniqueConstraint("organization_id", "content_hash", name="uq_uploads_org_hash"),
        Index("idx_uploads_org_status", "organization_id", "status"),
        Index("idx_uploads_content_hash", "organization_id", "content_hash"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Foreign keys
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    instrument_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # File metadata
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="SHA-256 hash for deduplication",
    )
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Pipeline state
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UploadStatus.uploaded.value,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instrument_type_detected: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    parser_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    parsed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -- relationships -------------------------------------------------------
    parsed_data: Mapped[list["ParsedData"]] = relationship(  # noqa: F821
        "ParsedData",
        back_populates="upload",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Upload id={self.id!s:.8} filename={self.filename!r} status={self.status!r}>"
