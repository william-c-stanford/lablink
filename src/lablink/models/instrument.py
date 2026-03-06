"""Instrument model — a registered lab instrument within an organization."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lablink.database import Base

from datetime import datetime, timezone


class Instrument(Base):
    """A registered lab instrument within an organization.

    Instruments may optionally be linked to an Agent.
    The ``instrument_type`` field matches parser instrument types
    (hplc, pcr, plate_reader, spectrophotometer, balance).
    """

    __tablename__ = "instruments"
    __table_args__ = (
        Index("ix_instruments_org_type", "organization_id", "instrument_type"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(100), nullable=False)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, default=dict, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    agent: Mapped[Optional["Agent"]] = relationship(  # noqa: F821
        "Agent",
        back_populates="instruments",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Instrument {self.name!r} type={self.instrument_type!r}>"
