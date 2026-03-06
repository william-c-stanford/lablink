"""Canonical parsed result schema for instrument data.

All 5 instrument parsers output a ParsedResult. This schema provides
a standardized, ASM-compatible representation of instrument measurements
with metadata, units, and quality information.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityFlag(str, Enum):
    """Quality assessment for a measurement value."""

    GOOD = "good"
    SUSPECT = "suspect"
    BAD = "bad"
    MISSING = "missing"


class MeasurementValue(BaseModel):
    """A single measurement -- value, unit, sample info, quality flag.

    Follows ASM (Allotrope Simple Model) conventions for measurement
    representation with QUDT unit URIs where available.
    """

    name: str = Field(..., description="Measurement name, e.g. 'absorbance', 'mass', 'ct_value'")
    value: float | None = Field(None, description="Numeric value; None if missing/below LOD")
    unit: str = Field(..., description="Unit string, e.g. 'AU', 'mg', 'seconds'")
    qudt_uri: str | None = Field(
        None,
        description="QUDT unit URI, e.g. 'http://qudt.org/vocab/unit/MilliGM'",
    )
    sample_id: str | None = Field(None, description="Sample identifier from instrument")
    well_position: str | None = Field(None, description="Well position for plate-based instruments, e.g. 'A1'")
    wavelength_nm: float | None = Field(None, description="Wavelength in nm for spectral measurements")
    retention_time_min: float | None = Field(None, description="Retention time in minutes for chromatography")
    cycle_number: int | None = Field(None, description="Cycle number for PCR amplification data")
    quality: QualityFlag = Field(QualityFlag.GOOD, description="Quality assessment flag")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional measurement-specific metadata")


class InstrumentSettings(BaseModel):
    """Instrument configuration at time of measurement."""

    instrument_model: str | None = Field(None, description="Instrument model name")
    serial_number: str | None = Field(None, description="Instrument serial number")
    software_version: str | None = Field(None, description="Software version that generated the file")
    method_name: str | None = Field(None, description="Method/protocol name used")
    operator: str | None = Field(None, description="Operator who ran the measurement")
    temperature_celsius: float | None = Field(None, description="Temperature during measurement")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Instrument-specific parameters (e.g. pathlength, injection volume)",
    )


class ParsedResult(BaseModel):
    """Canonical output from all instrument parsers.

    This is the standardized representation that all 5 parsers
    (spectrophotometer, plate_reader, hplc, pcr, balance) produce.
    Stored as JSON in the parsed_data table.
    """

    parser_name: str = Field(..., description="Name of parser that produced this result")
    parser_version: str = Field(..., description="Parser version string")
    instrument_type: str = Field(
        ...,
        description="Instrument type: spectrophotometer, plate_reader, hplc, pcr, balance",
    )
    file_name: str = Field(..., description="Original file name")
    file_hash: str | None = Field(None, description="SHA-256 hash of source file")
    parsed_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of parsing")

    # Core data
    measurements: list[MeasurementValue] = Field(
        default_factory=list,
        description="List of parsed measurement values",
    )
    sample_count: int = Field(0, description="Number of distinct samples")
    measurement_count: int = Field(0, description="Total number of measurements")

    # Instrument info
    instrument_settings: InstrumentSettings = Field(
        default_factory=InstrumentSettings,
        description="Instrument configuration captured from file",
    )

    # Quality & warnings
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings encountered during parsing",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Errors that did not prevent parsing but indicate data quality issues",
    )

    # Raw metadata from file header
    raw_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw metadata extracted from file headers before canonicalization",
    )

    @property
    def has_warnings(self) -> bool:
        """True if any warnings were generated during parsing."""
        return len(self.warnings) > 0

    @property
    def sample_ids(self) -> list[str]:
        """Unique sample IDs found in measurements."""
        return list({m.sample_id for m in self.measurements if m.sample_id})

    def summary(self) -> dict[str, Any]:
        """Return a compact summary suitable for API responses."""
        return {
            "parser_name": self.parser_name,
            "instrument_type": self.instrument_type,
            "sample_count": self.sample_count,
            "measurement_count": self.measurement_count,
            "warning_count": len(self.warnings),
            "error_count": len(self.errors),
            "parsed_at": self.parsed_at.isoformat(),
        }
