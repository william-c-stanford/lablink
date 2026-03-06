"""ParsedData model — canonical parsed output from an instrument file."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lablink.database import Base


class ParsedData(Base):
    """Canonical parsed output from an instrument file (ASM-compatible).

    Stores the structured measurement data produced by a parser,
    linked to the originating Upload.  The ``measurements`` JSON column
    holds an array of measurement objects matching the canonical schema.
    """

    __tablename__ = "parsed_data"
    __table_args__ = (
        Index("idx_parsed_data_upload", "upload_id"),
        Index("idx_parsed_data_org_type", "organization_id", "instrument_type"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Foreign keys
    upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Parser info
    instrument_type: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # ASM-compatible fields
    measurement_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sample_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # JSON columns for structured data
    data_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    measurements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    units: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    instrument_settings: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    upload: Mapped["Upload"] = relationship(  # noqa: F821
        "Upload",
        back_populates="parsed_data",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<ParsedData id={self.id!s:.8} upload_id={self.upload_id!s:.8} "
            f"instrument_type={self.instrument_type!r}>"
        )
