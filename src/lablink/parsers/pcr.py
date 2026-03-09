"""PCR/qPCR parser for QuantStudio and Bio-Rad CFX CSV exports.

Handles common PCR data formats:
1. QuantStudio (Applied Biosystems): header metadata + [Results] section with Ct values
2. Bio-Rad CFX: tabular CSV with Cq values
3. Simple Ct table: minimal CSV with Well, Sample, Target, Ct columns

All produce canonical MeasurementValue output with Ct/Cq values, well positions,
target names, and quality flags for undetermined/high-Ct wells.
"""

from __future__ import annotations

import csv
import io
import re
from typing import ClassVar

from lablink.parsers.base import BaseParser, ParseError
from lablink.parsers.registry import ParserRegistry
from lablink.schemas.canonical import (
    InstrumentSettings,
    MeasurementValue,
    ParsedResult,
)

# Allotropy integration (optional — graceful fallback on failure)
try:
    from allotropy.parser_factory import Vendor as _Vendor
    from allotropy.to_allotrope import allotrope_from_io as _allotrope_from_io
    from lablink.parsers.asm_mapper import asm_to_parsed_result as _asm_to_parsed_result
    _ALLOTROPY_AVAILABLE = True
except ImportError:
    _ALLOTROPY_AVAILABLE = False

# Values treated as undetermined / no amplification
_UNDETERMINED = {"undetermined", "n/a", "na", "nan", "", "-", "---", "no ct", "no cq"}

# Ct threshold above which a measurement is flagged suspect
_HIGH_CT_THRESHOLD = 40.0


@ParserRegistry.register
class PCRParser(BaseParser):
    """Parser for PCR/qPCR CSV exports (QuantStudio, Bio-Rad CFX, generic)."""

    name: ClassVar[str] = "pcr"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "pcr"
    supported_extensions: ClassVar[list[str]] = [".csv", ".tsv", ".txt", ".rdml", ".eds"]

    # Header markers for format detection
    _QUANTSTUDIO_MARKERS = {"quantstudio", "applied biosystems", "design & analysis"}
    _BIORAD_MARKERS = {"bio-rad", "cfx", "cq"}
    _CT_COLUMN_NAMES = {"ct", "cq", "ct value", "cq value", "c(t)", "c(q)"}

    def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
        """Detect PCR files by header keywords and Ct/Cq columns."""
        score = super().detect(file_bytes, filename)
        try:
            header = file_bytes[:4096].decode("utf-8", errors="ignore").lower()
            header_words = set(re.split(r"[\s,;\t]+", header))

            if self._QUANTSTUDIO_MARKERS & header_words:
                return max(score, 0.90)
            if self._BIORAD_MARKERS & header_words:
                return max(score, 0.88)

            # Check for Ct/Cq column headers
            if any(marker in header for marker in ("ct,", ",ct", "\tct", "cq,", ",cq", "\tcq")):
                return max(score, 0.80)
            # QuantStudio-style metadata lines
            if "* instrument type" in header or "[results]" in header:
                return max(score, 0.85)
        except Exception:
            pass
        return score

    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        """Parse PCR CSV into canonical ParsedResult."""
        metadata = metadata or {}

        try:
            text = file_bytes.decode("utf-8-sig")  # Handle BOM
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception:
                raise ParseError(
                    "Cannot decode file as text. Expected UTF-8 or Latin-1 encoded CSV.",
                    parser_name=self.name,
                    suggestion="Ensure the file is a text CSV export from your qPCR software.",
                )

        text = text.strip()
        if not text:
            raise ParseError(
                "File is empty.",
                parser_name=self.name,
                suggestion="Upload a non-empty PCR results CSV file.",
            )

        # Detect format, then try allotropy before falling back to custom parsers
        header_area = text[:4096].lower()
        if "* instrument type" in header_area or "[results]" in header_area:
            allotropy_result = self._try_allotropy(file_bytes, "APPBIO_QUANTSTUDIO", "file.txt")
            if allotropy_result is not None:
                allotropy_result.run_metadata["allotropy_attempted"] = True
                allotropy_result.run_metadata["allotropy_used"] = True
                return allotropy_result
            result = self._parse_quantstudio(text, metadata)
            result.run_metadata["allotropy_attempted"] = True
            result.run_metadata["allotropy_used"] = False
            return result
        elif any(m in header_area for m in ("fluor", "content", "cq")):
            first_data_line = text.split("\n", 1)[0].lower()
            if "cq" in first_data_line or "fluor" in first_data_line:
                allotropy_result = self._try_allotropy(file_bytes, "CFXMAESTRO", "file.csv")
                if allotropy_result is not None:
                    allotropy_result.run_metadata["allotropy_attempted"] = True
                    allotropy_result.run_metadata["allotropy_used"] = True
                    return allotropy_result
                result = self._parse_biorad(text, metadata)
                result.run_metadata["allotropy_attempted"] = True
                result.run_metadata["allotropy_used"] = False
                return result
            return self._parse_generic_ct(text, metadata)
        else:
            return self._parse_generic_ct(text, metadata)

    def _parse_quantstudio(self, text: str, metadata: dict) -> ParsedResult:
        """Parse QuantStudio-style CSV with metadata header and [Results] section.

        Format:
            * Key = Value (metadata lines)
            [Results]
            Well,Sample Name,Target Name,Task,Reporter,CT
            A1,Sample_01,GAPDH,UNKNOWN,SYBR,18.45
        """
        instrument_meta: dict = {}
        warnings: list[str] = []

        lines = text.split("\n")
        results_start = None

        # Parse metadata lines (start with *)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("*"):
                # Parse "* Key = Value" or "* Key: Value"
                meta_match = re.match(r"\*\s*(.+?)\s*[=:]\s*(.+)", stripped)
                if meta_match:
                    key = meta_match.group(1).strip()
                    value = meta_match.group(2).strip()
                    instrument_meta[key] = value
            elif stripped.lower() == "[results]":
                results_start = i + 1
                break

        if results_start is None:
            # No [Results] section — try generic parse
            return self._parse_generic_ct(text, metadata)

        # Parse the CSV data after [Results]
        csv_text = "\n".join(lines[results_start:])
        csv_text = csv_text.strip()
        if not csv_text:
            raise ParseError(
                "Empty [Results] section in QuantStudio CSV.",
                parser_name=self.name,
                suggestion="Ensure the QuantStudio export contains result data after [Results].",
            )

        delimiter = self._detect_delimiter(csv_text)
        reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers:
            raise ParseError(
                "No column headers found in QuantStudio results section.",
                parser_name=self.name,
                suggestion="Ensure the CSV has column headers (Well, Sample Name, Target Name, CT).",
            )

        header_map = {h.strip().lower(): h.strip() for h in headers}

        # Find columns
        well_col = self._find_column(header_map, ["well", "well position"])
        sample_col = self._find_column(header_map, ["sample name", "sample", "sample id"])
        ct_col = self._find_column(header_map, ["ct", "cq", "ct value", "cq value"])
        reporter_col = self._find_column(header_map, ["reporter", "reporter dye", "fluor"])
        if ct_col is None:
            raise ParseError(
                "No Ct or Cq column found in QuantStudio CSV.",
                parser_name=self.name,
                suggestion="Ensure the CSV has a CT or Cq column with threshold cycle values.",
            )

        measurements: list[MeasurementValue] = []
        ct_values: list[float] = []

        for row_idx, row in enumerate(reader):
            try:
                # Well position
                well = None
                if well_col and row.get(well_col):
                    well = self._normalize_well(row[well_col].strip())

                # Sample name/ID
                sample_name = None
                if sample_col and row.get(sample_col):
                    sample_name = row[sample_col].strip()

                # Reporter dye
                reporter = None
                if reporter_col and row.get(reporter_col):
                    reporter = row[reporter_col].strip()

                # Ct value
                ct_raw = row.get(ct_col, "").strip()
                ct_value, quality_flag = self._parse_ct_value(ct_raw)

                if ct_value is not None:
                    ct_values.append(ct_value)
                    if ct_value > _HIGH_CT_THRESHOLD:
                        quality_flag = "suspect"
                        warnings.append(
                            f"Well {well or row_idx + 1}: Ct {ct_value:.2f} > 40 "
                            f"suggests non-specific amplification."
                        )

                measurements.append(
                    MeasurementValue(
                        sample_id=sample_name,
                        sample_name=sample_name,
                        well_position=well,
                        value=ct_value if ct_value is not None else 0.0,
                        unit="Ct",
                        measurement_type="ct_value",
                        channel=reporter,
                        quality_flag=quality_flag,
                    )
                )

                # Store extra metadata on the measurement
                # Note: we use the channel field for reporter and store target in run_metadata

            except Exception as e:
                warnings.append(f"Row {row_idx + 1}: skipped due to error: {e}")

        if not measurements:
            raise ParseError(
                "No valid measurements found in QuantStudio CSV.",
                parser_name=self.name,
                suggestion="Check that the CSV contains Ct/Cq data rows.",
            )

        # Compute summary statistics
        summary = self._compute_summary(ct_values, len(measurements))

        # Build instrument settings
        cycle_count_str = instrument_meta.get("Cycle Count", instrument_meta.get("cycle_count"))
        cycle_count = int(cycle_count_str) if cycle_count_str and cycle_count_str.isdigit() else None

        settings = InstrumentSettings(
            method_name=instrument_meta.get("Experiment Name", "QuantStudio qPCR"),
            cycle_count=cycle_count,
            extra={k: v for k, v in instrument_meta.items()},
        )

        # Collect unique targets and samples
        sample_names = {m.sample_name for m in measurements if m.sample_name}

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="ct_value",
            measurements=measurements,
            instrument_settings=settings,
            sample_count=len(sample_names),
            run_metadata={
                "format": "quantstudio",
                "summary": summary,
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
                **instrument_meta,
            },
            raw_headers=list(headers),
            warnings=warnings,
        )

    def _parse_biorad(self, text: str, metadata: dict) -> ParsedResult:
        """Parse Bio-Rad CFX-style CSV with Cq column.

        Format:
            Well,Fluor,Target,Content,Sample,Cq
            A01,SYBR,IL6,Unkn,Patient_001,24.56
        """
        warnings: list[str] = []
        delimiter = self._detect_delimiter(text)

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers:
            raise ParseError(
                "No column headers found in Bio-Rad CSV.",
                parser_name=self.name,
                suggestion="Ensure the CSV has column headers (Well, Fluor, Target, Cq).",
            )

        header_map = {h.strip().lower(): h.strip() for h in headers}

        # Find columns
        well_col = self._find_column(header_map, ["well", "well position"])
        sample_col = self._find_column(header_map, ["sample", "sample name", "sample id"])
        ct_col = self._find_column(header_map, ["cq", "ct", "cq value", "ct value"])
        fluor_col = self._find_column(header_map, ["fluor", "reporter", "reporter dye"])

        if ct_col is None:
            raise ParseError(
                "No Ct or Cq column found in Bio-Rad CSV.",
                parser_name=self.name,
                suggestion="Ensure the CSV has a Cq or CT column with threshold cycle values.",
            )

        measurements: list[MeasurementValue] = []
        ct_values: list[float] = []

        for row_idx, row in enumerate(reader):
            try:
                well = None
                if well_col and row.get(well_col):
                    well = self._normalize_well(row[well_col].strip())

                sample_name = None
                if sample_col and row.get(sample_col):
                    sample_name = row[sample_col].strip()

                reporter = None
                if fluor_col and row.get(fluor_col):
                    reporter = row[fluor_col].strip()

                ct_raw = row.get(ct_col, "").strip()
                ct_value, quality_flag = self._parse_ct_value(ct_raw)

                if ct_value is not None:
                    ct_values.append(ct_value)
                    if ct_value > _HIGH_CT_THRESHOLD:
                        quality_flag = "suspect"
                        warnings.append(
                            f"Well {well or row_idx + 1}: Ct {ct_value:.2f} > 40 "
                            f"suggests non-specific amplification."
                        )

                measurements.append(
                    MeasurementValue(
                        sample_id=sample_name,
                        sample_name=sample_name,
                        well_position=well,
                        value=ct_value if ct_value is not None else 0.0,
                        unit="Ct",
                        measurement_type="ct_value",
                        channel=reporter,
                        quality_flag=quality_flag,
                    )
                )

            except Exception as e:
                warnings.append(f"Row {row_idx + 1}: skipped due to error: {e}")

        if not measurements:
            raise ParseError(
                "No valid measurements found in Bio-Rad CSV.",
                parser_name=self.name,
                suggestion="Check that the CSV contains Cq data rows.",
            )

        summary = self._compute_summary(ct_values, len(measurements))
        sample_names = {m.sample_name for m in measurements if m.sample_name}

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="ct_value",
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="Bio-Rad CFX qPCR",
                extra={"software": "Bio-Rad CFX Manager"},
            ),
            sample_count=len(sample_names),
            run_metadata={
                "format": "biorad_cfx",
                "summary": summary,
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=list(headers),
            warnings=warnings,
        )

    def _parse_generic_ct(self, text: str, metadata: dict) -> ParsedResult:
        """Parse generic PCR CSV with Ct/Cq column."""
        warnings: list[str] = []
        delimiter = self._detect_delimiter(text)

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers:
            raise ParseError(
                "No column headers found in PCR CSV.",
                parser_name=self.name,
                suggestion="Ensure the CSV has column headers including a Ct or Cq column.",
            )

        header_map = {h.strip().lower(): h.strip() for h in headers}

        well_col = self._find_column(header_map, ["well", "well position"])
        sample_col = self._find_column(header_map, ["sample name", "sample", "sample id"])
        ct_col = self._find_column(header_map, ["ct", "cq", "ct value", "cq value"])

        if ct_col is None:
            raise ParseError(
                "No Ct or Cq column found in CSV. Cannot identify PCR data.",
                parser_name=self.name,
                suggestion="Ensure the CSV has a column named CT, Ct, Cq, or similar.",
            )

        measurements: list[MeasurementValue] = []
        ct_values: list[float] = []

        for row_idx, row in enumerate(reader):
            try:
                well = None
                if well_col and row.get(well_col):
                    well = self._normalize_well(row[well_col].strip())

                sample_name = None
                if sample_col and row.get(sample_col):
                    sample_name = row[sample_col].strip()

                ct_raw = row.get(ct_col, "").strip()
                ct_value, quality_flag = self._parse_ct_value(ct_raw)

                if ct_value is not None:
                    ct_values.append(ct_value)
                    if ct_value > _HIGH_CT_THRESHOLD:
                        quality_flag = "suspect"
                        warnings.append(
                            f"Well {well or row_idx + 1}: Ct {ct_value:.2f} > 40 "
                            f"suggests non-specific amplification."
                        )

                measurements.append(
                    MeasurementValue(
                        sample_id=sample_name,
                        sample_name=sample_name,
                        well_position=well,
                        value=ct_value if ct_value is not None else 0.0,
                        unit="Ct",
                        measurement_type="ct_value",
                        channel=None,
                        quality_flag=quality_flag,
                    )
                )

            except Exception as e:
                warnings.append(f"Row {row_idx + 1}: skipped due to error: {e}")

        if not measurements:
            raise ParseError(
                "No valid measurements found in PCR CSV.",
                parser_name=self.name,
                suggestion="Check that the CSV contains Ct/Cq data rows.",
            )

        summary = self._compute_summary(ct_values, len(measurements))
        sample_names = {m.sample_name for m in measurements if m.sample_name}

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="ct_value",
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="qPCR",
            ),
            sample_count=len(sample_names),
            run_metadata={
                "format": "generic_ct",
                "summary": summary,
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=list(headers),
            warnings=warnings,
        )

    # -- Helpers ---------------------------------------------------------------

    def _try_allotropy(
        self, file_bytes: bytes, vendor_name: str, filepath: str
    ) -> ParsedResult | None:
        """Attempt to parse file_bytes via allotropy, returning None on any failure."""
        if not _ALLOTROPY_AVAILABLE:
            return None
        try:
            vendor = getattr(_Vendor, vendor_name)
            asm = _allotrope_from_io(io.BytesIO(file_bytes), filepath, vendor)
            return _asm_to_parsed_result(
                asm,
                parser_name=self.name,
                parser_version=self.version,
                instrument_type=self.instrument_type,
            )
        except Exception:
            return None

    @staticmethod
    def _parse_ct_value(raw: str) -> tuple[float | None, str | None]:
        """Parse a Ct/Cq value string, returning (value, quality_flag).

        Returns:
            (float_value, None) for valid Ct values
            (None, "missing") for undetermined/N/A
        """
        cleaned = raw.strip().lower()
        if cleaned in _UNDETERMINED:
            return None, "missing"
        try:
            val = float(raw.strip().replace(",", ""))
            return val, None
        except (ValueError, TypeError):
            return None, "missing"

    @staticmethod
    def _normalize_well(well: str) -> str:
        """Normalize well position to standard format (A1, B12, etc.).

        Handles formats like: A01 -> A1, a1 -> A1, A 1 -> A1
        """
        well = well.strip().upper().replace(" ", "")
        match = re.match(r"^([A-P])0*(\d{1,2})$", well)
        if match:
            return f"{match.group(1)}{match.group(2)}"
        return well

    @staticmethod
    def _compute_summary(ct_values: list[float], total_wells: int) -> dict:
        """Compute summary statistics for Ct values."""
        determined = len(ct_values)
        undetermined = total_wells - determined

        summary: dict = {
            "total_wells": total_wells,
            "determined_wells": determined,
            "undetermined_wells": undetermined,
        }

        if ct_values:
            summary["mean_ct"] = round(sum(ct_values) / len(ct_values), 2)
            summary["min_ct"] = round(min(ct_values), 2)
            summary["max_ct"] = round(max(ct_values), 2)

        return summary

    @staticmethod
    def _detect_delimiter(text: str) -> str:
        """Detect CSV delimiter from first few lines."""
        first_line = text.split("\n", 1)[0]
        tab_count = first_line.count("\t")
        comma_count = first_line.count(",")
        if tab_count > comma_count:
            return "\t"
        return ","

    @staticmethod
    def _find_column(header_map: dict[str, str], candidates: list[str]) -> str | None:
        """Find the original column name matching any candidate (exact then partial)."""
        for candidate in candidates:
            if candidate in header_map:
                return header_map[candidate]
        for candidate in candidates:
            for key, original in header_map.items():
                if candidate in key:
                    return original
        return None
