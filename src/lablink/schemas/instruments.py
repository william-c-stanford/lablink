"""Pydantic schemas for Instrument CRUD operations (router-facing).

Provides InstrumentCreate, InstrumentUpdate, and InstrumentResponse aligned
to the Instrument ORM model in lablink.models.lab.

Note: The more detailed InstrumentCreate/InstrumentUpdate/InstrumentRead
schemas live in lablink.schemas.instrument (singular). This module provides
the simplified router-facing versions specified in the API design.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lablink.schemas.instrument import InstrumentType


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class InstrumentCreate(BaseModel):
    """Request body to register a new instrument."""

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
        default=None,
        max_length=255,
        description="Instrument manufacturer, e.g. 'Agilent'",
    )
    model: str | None = Field(
        default=None,
        max_length=255,
        description="Instrument model name, e.g. 'Cary 60'",
    )
    serial_number: str | None = Field(
        default=None,
        max_length=255,
        description="Instrument serial number for asset tracking",
    )
    location: str | None = Field(
        default=None,
        max_length=255,
        description="Physical location, e.g. 'Building A, Room 302'",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Instrument name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class InstrumentUpdate(BaseModel):
    """Request body to partially update an instrument (PATCH semantics)."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Instrument display name",
    )
    location: str | None = Field(
        default=None,
        max_length=255,
        description="Physical location",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional instrument metadata (replaces existing metadata entirely)",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Instrument name must not be blank")
        return v.strip() if v else v

    @model_validator(mode="after")
    def at_least_one_field(self) -> InstrumentUpdate:
        provided = self.model_dump(exclude_unset=True)
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class InstrumentResponse(BaseModel):
    """Full instrument representation returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique instrument identifier")
    name: str = Field(..., description="User-assigned instrument name")
    instrument_type: str = Field(..., description="Instrument type (e.g. hplc, pcr, plate_reader)")
    manufacturer: str | None = Field(None, description="Instrument manufacturer")
    model: str | None = Field(None, description="Instrument model name")
    serial_number: str | None = Field(None, description="Instrument serial number")
    location: str | None = Field(None, description="Physical location")
    agent_id: uuid.UUID | None = Field(None, description="ID of the linked desktop agent")
    created_at: datetime = Field(..., description="Registration timestamp")
    metadata: dict[str, Any] | None = Field(None, description="Additional instrument metadata")
