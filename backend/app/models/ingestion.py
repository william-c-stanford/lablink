"""Ingestion pipeline models.

Tracks the lifecycle of data files from upload through parsing to
final storage. FileRecord is the immutable audit trail entry for
every file that enters the system. ParseResult stores the parsed
output with hash-chain integrity.

State machine for FileRecord.status:
  uploaded -> queued -> parsing -> parsed -> failed
                                    +-> stored (after S3 upload)
"""

from __future__ import annotations

import hashlib
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FileStatus(str, Enum):
    """Processing status for ingested files."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"
    STORED = "stored"


class FileRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable audit record for every file entering the system.

    Once created, FileRecord rows are never updated except for
    status transitions and the storage_path (set after S3 upload).
    The file_hash provides content-addressable deduplication.
    The prev_hash field creates an append-only hash chain for
    tamper-evident audit trail.

    This model intentionally does NOT use SoftDeleteMixin because
    audit records must never be deleted (even soft-deleted).
    """

    __tablename__ = "file_records"

    # File identity
    file_name: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Original filename as seen on the lab workstation",
    )
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="SHA-256 hash of file content for deduplication",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="File size in bytes",
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="MIME type of the file, e.g. 'text/csv'",
    )

    # Hash chain for immutable audit trail
    prev_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 of the previous FileRecord for hash-chain integrity",
    )

    # Source tracking
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True,
        comment="Instrument that produced this file",
    )
    watched_folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("watched_folders.id"), nullable=True,
        comment="Watched folder the file came from (null if manual upload)",
    )
    lab_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
        comment="Lab that owns this file",
    )
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="User ID who uploaded (null if agent-uploaded)",
    )

    # Processing state
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FileStatus.UPLOADED.value,
        index=True,
        comment="Current processing status",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Error details if status is 'failed'",
    )

    # Storage
    storage_path: Mapped[str | None] = mapped_column(
        String(1000), nullable=True,
        comment="Path in S3 or local storage after upload",
    )
    storage_backend: Mapped[str] = mapped_column(
        String(20), nullable=False, default="local",
        comment="Storage backend: 'local' or 's3'",
    )

    # Relationships
    instrument: Mapped["Instrument"] = relationship(  # noqa: F821
        "Instrument", lazy="selectin",
    )
    watched_folder: Mapped["WatchedFolder | None"] = relationship(  # noqa: F821
        "WatchedFolder", lazy="selectin",
    )
    parse_results: Mapped[list[ParseResult]] = relationship(
        "ParseResult", back_populates="file_record", lazy="selectin",
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_file_records_lab_status", "lab_id", "status"),
        Index("ix_file_records_instrument_created", "instrument_id", "created_at"),
    )

    def compute_chain_hash(self) -> str:
        """Compute the hash-chain value for this record.

        Combines file_hash + prev_hash to create a tamper-evident chain.
        """
        payload = f"{self.file_hash}:{self.prev_hash or 'genesis'}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"<FileRecord {self.file_name!r} status={self.status!r}>"


class ParseResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Stored output from parsing an instrument file.

    Each FileRecord can have multiple ParseResults if re-parsed with
    a different parser version. The parsed_data JSON column holds the
    full ParsedResult Pydantic model serialized to JSON.

    Like FileRecord, ParseResult is append-only (immutable audit trail).
    """

    __tablename__ = "parse_results"

    file_record_id: Mapped[str] = mapped_column(
        ForeignKey("file_records.id"), nullable=False, index=True,
        comment="The file that was parsed",
    )

    # Parser info
    parser_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Parser that produced this result, e.g. 'spectrophotometer'",
    )
    parser_version: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Version of the parser used",
    )

    # Result data (stored as JSON text for SQLite compatibility)
    parsed_data: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Full ParsedResult JSON blob",
    )

    # Summary fields for efficient querying without JSON parsing
    instrument_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Instrument type from the parsed result",
    )
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Number of distinct samples found",
    )
    measurement_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Total number of measurements",
    )
    warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Number of warnings during parsing",
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Number of non-fatal errors during parsing",
    )

    # Duration tracking
    parse_duration_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Time taken to parse the file in seconds",
    )

    # Quality flag
    is_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Whether this parse result passed validation",
    )

    # Relationships
    file_record: Mapped[FileRecord] = relationship(
        "FileRecord", back_populates="parse_results", lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_parse_results_type_created", "instrument_type", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ParseResult parser={self.parser_name!r} "
            f"file={self.file_record_id!r} "
            f"measurements={self.measurement_count}>"
        )
