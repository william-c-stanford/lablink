"""Pydantic schemas for Instrument CRUD operations.

Provides InstrumentCreate, InstrumentUpdate, InstrumentRead, and
InstrumentList with validation rules aligned to the Instrument ORM model
and the roadmap SQL schema.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

INSTRUMENT_TYPES = frozenset({
    "spectrophotometer",
    "plate_reader",
    "hplc",
    "pcr",
    "balance",
})


class InstrumentType(str, PyEnum):
    """Supported instrument types for MVP."""

    SPECTROPHOTOMETER = "spectrophotometer"
    PLATE_READER = "plate_reader"
    HPLC = "hplc"
    PCR = "pcr"
    BALANCE = "balance"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class InstrumentCreate(BaseModel):
    """Request body to register a new instrument.

    The instrument is always created with ``is_active=True`` (enforced by
    the service).  ``instrument_type`` must be one of the supported types.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-assigned instrument name, e.g. 'UV-Vis Lab 3'",
    )
    instrument_type: InstrumentType = Field(
        ...,
        description="Instrument type: spectrophotometer, plate_reader, hplc, pcr, balance",
    )
    manufacturer: str | None = Field(
        None,
        max_length=255,
        description="Instrument manufacturer, e.g. 'Agilent'",
    )
    model_name: str | None = Field(
        None,
        max_length=255,
        description="Instrument model name, e.g. 'Cary 60'",
    )
    serial_number: str | None = Field(
        None,
        max_length=255,
        description="Instrument serial number",
    )
    location: str | None = Field(
        None,
        max_length=255,
        description="Physical location, e.g. 'Building A, Room 302'",
    )
    agent_id: str | None = Field(
        None,
        max_length=36,
        description="Optional ID of the desktop agent linked to this instrument",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Additional instrument metadata (stored as JSON)",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Instrument name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class InstrumentUpdate(BaseModel):
    """Request body to update instrument fields (PATCH semantics).

    All fields are optional -- only provided fields are updated.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Instrument display name",
    )
    instrument_type: InstrumentType | None = Field(
        None,
        description="Instrument type",
    )
    manufacturer: str | None = Field(
        None,
        max_length=255,
        description="Instrument manufacturer",
    )
    model_name: str | None = Field(
        None,
        max_length=255,
        description="Instrument model name",
    )
    serial_number: str | None = Field(
        None,
        max_length=255,
        description="Instrument serial number",
    )
    location: str | None = Field(
        None,
        max_length=255,
        description="Physical location",
    )
    agent_id: str | None = Field(
        None,
        max_length=36,
        description="ID of the desktop agent linked to this instrument",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Additional instrument metadata (stored as JSON)",
    )
    is_active: bool | None = Field(
        None,
        description="Whether the instrument is currently in service",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        """Ensure name is not just whitespace when provided."""
        if v is not None:
            if not v.strip():
                raise ValueError("Instrument name must not be blank")
            return v.strip()
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> InstrumentUpdate:
        """Ensure at least one field is provided for update."""
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class InstrumentRead(BaseModel):
    """Full instrument representation returned by API endpoints.

    Includes the linked agent_id and active status so consuming agents
    know the current state.
    """

    id: str
    org_id: str | None = Field(None, description="Organization ID")
    name: str
    instrument_type: str
    manufacturer: str | None = None
    model_name: str | None = None
    serial_number: str | None = None
    location: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool = True

    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, data: Any) -> Any:
        """Handle ORM objects with metadata_json column."""
        if hasattr(data, "__dict__"):
            d: dict[str, Any] = {}
            for key in (
                "id", "org_id", "organization_id", "name", "instrument_type",
                "manufacturer", "model_name", "serial_number", "location",
                "agent_id", "metadata_json", "metadata", "is_active",
                "created_at", "updated_at", "deleted_at",
                # backend/app model uses lab_id instead of org_id
                "lab_id",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    d[key] = val
            # Normalize org_id from different field names
            if "org_id" not in d or d.get("org_id") is None:
                d["org_id"] = d.pop("organization_id", None) or d.pop("lab_id", None)
            data = d

        # Map metadata_json -> metadata
        if isinstance(data, dict):
            import json

            meta_raw = data.pop("metadata_json", None)
            if meta_raw and isinstance(meta_raw, str):
                try:
                    data["metadata"] = json.loads(meta_raw)
                except (ValueError, TypeError):
                    data["metadata"] = None
            elif meta_raw and isinstance(meta_raw, dict):
                data["metadata"] = meta_raw

        return data


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class InstrumentList(BaseModel):
    """Paginated list of instruments."""

    items: list[InstrumentRead]
    total: int
    page: int
    page_size: int
