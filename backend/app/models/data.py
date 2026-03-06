"""Data models: Dataset, DataPoint, Tag, TagAssociation.

Datasets represent parsed instrument data stored in canonical form.
DataPoints are individual measurements within a dataset.
Tags provide flexible categorization with polymorphic associations.
"""

from __future__ import annotations

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Dataset(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A parsed instrument dataset — the canonical representation of an upload.

    Each dataset corresponds to one parsed upload file and contains
    the structured measurements, instrument settings, and metadata
    extracted by the appropriate parser.
    """

    __tablename__ = "datasets"

    # Foreign keys
    upload_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("file_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="Project ID (FK added when projects table is created)",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instrument_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Parser instrument type: spectrophotometer, plate_reader, hplc, pcr, balance",
    )
    parser_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of parser that produced this dataset",
    )
    parser_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version of the parser used",
    )

    # Counts (denormalized for query performance)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    measurement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Parsed result JSON — the full ParsedResult stored as JSON text
    parsed_result_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full ParsedResult JSON for re-hydration",
    )

    # Instrument settings JSON
    instrument_settings_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="InstrumentSettings JSON extracted from ParsedResult",
    )

    # Quality
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Content hash for integrity
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of the parsed result for integrity verification",
    )

    # Relationships
    data_points: Mapped[list[DataPoint]] = relationship(
        "DataPoint",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_datasets_org_instrument", "org_id", "instrument_type"),
        Index("ix_datasets_org_project", "org_id", "project_id"),
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id!r}, name={self.name!r}, type={self.instrument_type!r})>"


class DataPoint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single measurement data point within a dataset.

    Represents one MeasurementValue from a ParsedResult, stored
    relationally for efficient querying, filtering, and aggregation.
    """

    __tablename__ = "data_points"

    # Foreign keys
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core measurement fields
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Measurement name, e.g. 'absorbance', 'mass', 'ct_value'",
    )
    value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Numeric value; NULL if missing or below LOD",
    )
    unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Unit string, e.g. 'AU', 'mg', 'seconds'",
    )
    qudt_uri: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="QUDT unit URI for semantic interoperability",
    )

    # Sample identification
    sample_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Sample identifier from instrument",
    )
    well_position: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="Well position for plate-based instruments, e.g. 'A1'",
    )

    # Instrument-specific dimensions
    wavelength_nm: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Wavelength in nm for spectral measurements",
    )
    retention_time_min: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Retention time in minutes for chromatography",
    )
    cycle_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Cycle number for PCR amplification data",
    )

    # Quality
    quality: Mapped[str] = mapped_column(
        String(20),
        default="good",
        nullable=False,
        comment="Quality flag: good, suspect, bad, missing",
    )

    # Extra metadata JSON
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional measurement-specific metadata as JSON",
    )

    # Relationships
    dataset: Mapped[Dataset] = relationship(
        "Dataset",
        back_populates="data_points",
    )

    __table_args__ = (
        Index("ix_data_points_dataset_name", "dataset_id", "name"),
        Index("ix_data_points_dataset_sample", "dataset_id", "sample_id"),
    )

    def __repr__(self) -> str:
        return f"<DataPoint(id={self.id!r}, name={self.name!r}, value={self.value})>"


class Tag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A reusable label for categorizing resources.

    Tags are org-scoped and can be associated with datasets,
    experiments, uploads, and other resources via TagAssociation.
    """

    __tablename__ = "tags"

    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tag display name",
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="URL-friendly slug, unique within org",
    )
    color: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
        comment="Hex color code, e.g. '#FF5733'",
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    associations: Mapped[list[TagAssociation]] = relationship(
        "TagAssociation",
        back_populates="tag",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_tags_org_slug", "org_id", "slug", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id!r}, name={self.name!r}, org_id={self.org_id!r})>"


class TagAssociation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Polymorphic many-to-many relationship between tags and resources.

    Allows tags to be associated with any resource type (dataset,
    experiment, upload, etc.) using a resource_type + resource_id pattern.
    """

    __tablename__ = "tag_associations"

    tag_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of associated resource: dataset, experiment, upload, etc.",
    )
    resource_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="ID of the associated resource",
    )

    # Relationships
    tag: Mapped[Tag] = relationship(
        "Tag",
        back_populates="associations",
    )

    __table_args__ = (
        Index("ix_tag_assoc_resource", "resource_type", "resource_id"),
        Index("ix_tag_assoc_tag_resource", "tag_id", "resource_type", "resource_id", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<TagAssociation(tag_id={self.tag_id!r}, "
            f"resource_type={self.resource_type!r}, resource_id={self.resource_id!r})>"
        )
