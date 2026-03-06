"""Instrument and instrument driver models.

Represents the physical instruments in a lab and their associated
parser/driver configurations. Each instrument has a type, model info,
and links to one or more watched folders for file ingestion.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InstrumentDriver(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Parser/driver configuration for a class of instruments.

    Maps instrument types to their parser implementation. For example,
    'spectrophotometer' -> 'spectrophotometer' parser module.
    """

    __tablename__ = "instrument_drivers"

    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="Human-readable driver name, e.g. 'Spectrophotometer CSV'",
    )
    instrument_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Instrument type: spectrophotometer, plate_reader, hplc, pcr, balance",
    )
    parser_module: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Python module path for the parser, e.g. 'app.parsers.spectrophotometer'",
    )
    file_patterns: Mapped[str] = mapped_column(
        String(500), nullable=False, default="*.csv",
        comment="Comma-separated glob patterns for matching files, e.g. '*.csv,*.txt'",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Description of what this driver handles",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Whether this driver is available for use",
    )

    # Relationships
    instruments: Mapped[list[Instrument]] = relationship(
        "Instrument", back_populates="driver", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<InstrumentDriver {self.name!r} type={self.instrument_type!r}>"


class Instrument(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A physical instrument in a lab.

    Each instrument belongs to a lab (identified by lab_id) and is
    associated with a driver that determines how its output files
    are parsed.
    """

    __tablename__ = "instruments"

    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="User-assigned instrument name, e.g. 'UV-Vis Lab 3'",
    )
    lab_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
        comment="ID of the lab this instrument belongs to",
    )
    driver_id: Mapped[str] = mapped_column(
        ForeignKey("instrument_drivers.id"), nullable=False, index=True,
        comment="Foreign key to the instrument driver/parser",
    )
    serial_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Instrument serial number",
    )
    model_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="Instrument model name, e.g. 'Cary 60'",
    )
    manufacturer: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="Instrument manufacturer, e.g. 'Agilent'",
    )
    location: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="Physical location, e.g. 'Building A, Room 302'",
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Free-text notes about this instrument",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Whether the instrument is currently in service",
    )

    # Relationships
    driver: Mapped[InstrumentDriver] = relationship(
        "InstrumentDriver", back_populates="instruments", lazy="selectin",
    )
    watched_folders: Mapped[list[WatchedFolder]] = relationship(
        "WatchedFolder", back_populates="instrument", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Instrument {self.name!r} lab={self.lab_id!r}>"


class WatchedFolder(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A filesystem path watched by the desktop agent for new data files.

    Each watched folder is linked to an instrument. When the Go agent
    detects a new file matching the driver's file_patterns, it uploads
    the file and triggers ingestion.
    """

    __tablename__ = "watched_folders"

    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True,
        comment="Instrument this folder is associated with",
    )
    folder_path: Mapped[str] = mapped_column(
        String(1000), nullable=False,
        comment="Absolute path on the lab workstation being watched",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Whether the agent is actively watching this folder",
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="ID of the desktop agent watching this folder",
    )

    # Relationships
    instrument: Mapped[Instrument] = relationship(
        "Instrument", back_populates="watched_folders", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<WatchedFolder {self.folder_path!r} instrument={self.instrument_id!r}>"
