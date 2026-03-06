"""Canonical parsed data models (ASM-compatible).

These Pydantic models define the standard output format for all instrument
parsers. Every parser must produce a ParsedResult containing MeasurementValue
instances, regardless of the source instrument or file format.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MeasurementValue(BaseModel):
    """Single measurement from an instrument."""

    sample_id: Optional[str] = None
    sample_name: Optional[str] = None
    well_position: Optional[str] = None  # For plate-based instruments (e.g., "A1")
    value: float
    unit: str  # SI or domain-standard unit
    qudt_uri: Optional[str] = None  # QUDT ontology reference
    measurement_type: str  # absorbance, fluorescence, concentration, mass, area, retention_time, ct_value
    channel: Optional[str] = None  # For multi-channel instruments
    wavelength_nm: Optional[float] = None
    timestamp: Optional[datetime] = None
    quality_flag: Optional[str] = None  # pass, fail, suspect, out_of_range


class InstrumentSettings(BaseModel):
    """Instrument method/settings used for the measurement."""

    method_name: Optional[str] = None
    temperature_c: Optional[float] = None
    wavelength_nm: Optional[float] = None
    excitation_nm: Optional[float] = None
    emission_nm: Optional[float] = None
    flow_rate_ml_min: Optional[float] = None
    injection_volume_ul: Optional[float] = None
    column_type: Optional[str] = None
    run_time_min: Optional[float] = None
    cycle_count: Optional[int] = None  # For PCR
    extra: dict = Field(default_factory=dict)  # Instrument-specific settings


class ParsedResult(BaseModel):
    """Canonical output from any instrument parser."""

    parser_name: str
    parser_version: str
    instrument_type: str  # hplc, pcr, plate_reader, spectrophotometer, balance
    measurement_type: str  # The primary measurement type
    measurements: list[MeasurementValue]
    instrument_settings: Optional[InstrumentSettings] = None
    sample_count: int
    plate_layout: Optional[dict] = None  # For plate readers: { "rows": 8, "cols": 12, "format": "96-well" }
    run_metadata: dict = Field(default_factory=dict)  # Operator, date, software version, etc.
    raw_headers: Optional[list[str]] = None  # Original column headers for reference
    warnings: list[str] = Field(default_factory=list)  # Non-fatal parser warnings
