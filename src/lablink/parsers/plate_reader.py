"""Plate reader parser for SoftMax Pro and Gen5 template-based CSV exports.

Handles two common formats:
1. SoftMax Pro (Molecular Devices): section-based CSV with plate layout blocks
2. Gen5 (BioTek): tabular CSV with well positions or plate grid layout

Both produce canonical MeasurementValue output with well positions and absorbance/
fluorescence data for 96-well (8x12), 384-well (16x24), or other plate formats.
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

# Well row labels
PLATE_ROWS_96 = list("ABCDEFGH")
PLATE_ROWS_384 = list("ABCDEFGHIJKLMNOP")


def _is_plate_row_label(value: str) -> bool:
    """Check if a value looks like a plate row label (A-P)."""
    return bool(re.match(r"^[A-P]$", value.strip().upper()))


def _well_position(row_label: str, col_num: int) -> str:
    """Format a well position like 'A1', 'B12'."""
    return f"{row_label.upper()}{col_num}"


@ParserRegistry.register
class PlateReaderParser(BaseParser):
    """Parser for plate reader CSV exports (SoftMax Pro, Gen5, generic grid)."""

    name: ClassVar[str] = "plate_reader"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "plate_reader"
    supported_extensions: ClassVar[list[str]] = [".csv", ".tsv", ".txt", ".xlsx"]

    _SOFTMAX_MARKERS = {"softmax", "molecular devices", "spectramax", "plate:", "endpoint"}
    _GEN5_MARKERS = {"gen5", "biotek", "synergy", "epoch", "cytation"}

    def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
        """Detect plate reader files by header keywords and grid patterns."""
        score = super().detect(file_bytes, filename)
        try:
            header = file_bytes[:4096].decode("utf-8", errors="ignore").lower()
            header_words = set(re.split(r"[\s,;\t]+", header))

            if self._SOFTMAX_MARKERS & header_words:
                return max(score, 0.90)
            if self._GEN5_MARKERS & header_words:
                return max(score, 0.88)

            # Check for well position pattern (A1, B2, etc.)
            if re.search(r"\b[A-H][1-9]\b", header) or re.search(r"\b[A-H]1[0-2]\b", header):
                return max(score, 0.70)

            # Check for plate grid layout (row of numbers 1-12 as headers)
            if re.search(r"(?:^|\n)\s*,?\s*1\s*,\s*2\s*,\s*3\s*,", header):
                return max(score, 0.65)
        except Exception:
            pass
        return score

    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        """Parse plate reader CSV into canonical ParsedResult."""
        metadata = metadata or {}

        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception:
                raise ParseError(
                    "Cannot decode file as text. Expected UTF-8 or Latin-1 encoded CSV.",
                    parser_name=self.name,
                    suggestion="Ensure the file is a text CSV export from your plate reader software.",
                )

        text = text.strip()
        if not text:
            raise ParseError(
                "File is empty.",
                parser_name=self.name,
                suggestion="Upload a non-empty plate reader CSV file.",
            )

        text_lower = text[:4096].lower()

        # Detect format — check Gen5/BioTek first (more specific markers)
        if any(m in text_lower for m in ("gen5", "biotek", "synergy", "cytation", "epoch")):
            allotropy_result = self._try_allotropy(file_bytes, "AGILENT_GEN5", "file.txt")
            if allotropy_result is not None:
                allotropy_result.run_metadata["allotropy_attempted"] = True
                allotropy_result.run_metadata["allotropy_used"] = True
                return allotropy_result
            result = self._parse_gen5(text, metadata)
            result.run_metadata["allotropy_attempted"] = True
            result.run_metadata["allotropy_used"] = False
            return result
        elif any(m in text_lower for m in ("softmax", "spectramax", "plate#", "##blocks")):
            allotropy_result = self._try_allotropy(file_bytes, "MOLDEV_SOFTMAX_PRO", "file.txt")
            if allotropy_result is not None:
                allotropy_result.run_metadata["allotropy_attempted"] = True
                allotropy_result.run_metadata["allotropy_used"] = True
                return allotropy_result
            result = self._parse_softmax(text, metadata)
            result.run_metadata["allotropy_attempted"] = True
            result.run_metadata["allotropy_used"] = False
            return result
        else:
            return self._parse_grid(text, metadata)

    def _try_allotropy(
        self, file_bytes: bytes, vendor_name: str, filepath: str
    ) -> ParsedResult | None:
        """Attempt to parse via allotropy, returning None on any failure."""
        if not _ALLOTROPY_AVAILABLE:
            return None
        try:
            import io as _io
            vendor = getattr(_Vendor, vendor_name)
            asm = _allotrope_from_io(_io.BytesIO(file_bytes), filepath, vendor)
            return _asm_to_parsed_result(
                asm,
                parser_name=self.name,
                parser_version=self.version,
                instrument_type=self.instrument_type,
            )
        except Exception:
            return None

    def _parse_softmax(self, text: str, metadata: dict) -> ParsedResult:
        """Parse SoftMax Pro section-based CSV format.

        SoftMax Pro exports contain sections like:
        - Header section with plate info
        - Data blocks in grid format (rows A-H, cols 1-12)
        - May have multiple read modes (endpoint, kinetic)
        """
        lines = text.split("\n")
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        plate_info: dict = {}
        wavelength: float | None = None
        measurement_type = "absorbance"
        in_data_block = False
        col_headers: list[int] = []
        raw_headers: list[str] = []

        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                in_data_block = False
                continue

            # Extract metadata from header lines
            lower = stripped.lower()
            if "wavelength" in lower or "lambda" in lower:
                wl_match = re.search(r"(\d{3,4})\s*(?:nm)?", stripped)
                if wl_match:
                    wavelength = float(wl_match.group(1))

            if "fluorescence" in lower or "rfu" in lower:
                measurement_type = "fluorescence"
            elif "luminescence" in lower or "rlu" in lower:
                measurement_type = "luminescence"

            if "plate" in lower and ":" in stripped:
                plate_info["plate_name"] = stripped.split(":", 1)[1].strip()

            if "temperature" in lower:
                temp_match = re.search(r"([\d.]+)\s*(?:°?C|celsius)?", stripped)
                if temp_match:
                    plate_info["temperature_c"] = float(temp_match.group(1))

            # Detect column header row (numbers 1-12 or 1-24)
            cells = self._split_row(stripped)
            if not in_data_block and self._is_column_header_row(cells):
                in_data_block = True
                col_headers = [int(c) for c in cells if c.strip().isdigit()]
                raw_headers = cells
                continue

            # Parse data row in grid block
            if in_data_block and cells:
                first = cells[0].strip().upper()
                if _is_plate_row_label(first):
                    row_label = first
                    for i, cell in enumerate(cells[1:], start=0):
                        if i < len(col_headers):
                            val = self._parse_float(cell)
                            if val is not None:
                                well = _well_position(row_label, col_headers[i])
                                unit = self._get_unit(measurement_type)
                                measurements.append(
                                    MeasurementValue(
                                        well_position=well,
                                        value=val,
                                        unit=unit,
                                        measurement_type=measurement_type,
                                        wavelength_nm=wavelength,
                                    )
                                )
                else:
                    # Not a row label, end of data block
                    in_data_block = False

        if not measurements:
            raise ParseError(
                "No valid plate data found in SoftMax Pro CSV.",
                parser_name=self.name,
                suggestion="Ensure the file contains plate grid data blocks with row labels (A-H) and column numbers.",
            )

        plate_layout = self._detect_plate_layout(measurements)

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type=measurement_type,
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="SoftMax Pro Endpoint",
                wavelength_nm=wavelength,
                temperature_c=plate_info.get("temperature_c"),
                extra={k: v for k, v in plate_info.items() if k != "temperature_c"},
            ),
            sample_count=len(measurements),
            plate_layout=plate_layout,
            run_metadata={
                "format": "softmax_pro",
                "software": "SoftMax Pro",
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=raw_headers or None,
            warnings=warnings,
        )

    def _parse_gen5(self, text: str, metadata: dict) -> ParsedResult:
        """Parse BioTek Gen5 CSV format.

        Gen5 can export in tabular format with well positions or grid format.
        """
        lines = text.split("\n")
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        wavelength: float | None = None
        measurement_type = "absorbance"
        raw_headers: list[str] = []

        # Extract wavelength from header area
        for line in lines[:20]:
            lower = line.lower()
            wl_match = re.search(r"(\d{3,4})\s*(?:nm)", line)
            if wl_match:
                wavelength = float(wl_match.group(1))
            if "fluorescence" in lower:
                measurement_type = "fluorescence"
            elif "luminescence" in lower:
                measurement_type = "luminescence"

        # Try tabular format first (Well, Value columns)
        tabular = self._try_tabular_parse(text, wavelength, measurement_type)
        if tabular:
            measurements, raw_headers = tabular
        else:
            # Fall back to grid format
            measurements, raw_headers, warnings = self._parse_grid_block(
                lines, wavelength, measurement_type
            )

        if not measurements:
            raise ParseError(
                "No valid plate data found in Gen5 CSV.",
                parser_name=self.name,
                suggestion="Ensure the file contains well position data or a plate grid layout.",
            )

        plate_layout = self._detect_plate_layout(measurements)

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type=measurement_type,
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="Gen5 Read",
                wavelength_nm=wavelength,
                extra={"software": "Gen5"},
            ),
            sample_count=len(measurements),
            plate_layout=plate_layout,
            run_metadata={
                "format": "gen5",
                "software": "Gen5",
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=raw_headers or None,
            warnings=warnings,
        )

    def _parse_grid(self, text: str, metadata: dict) -> ParsedResult:
        """Parse a generic plate grid CSV (row labels + numeric columns)."""
        lines = text.split("\n")
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        raw_headers: list[str] = []

        wavelength: float | None = None
        measurement_type = metadata.get("measurement_type", "absorbance")

        # Check for wavelength in header
        for line in lines[:10]:
            wl_match = re.search(r"(\d{3,4})\s*nm", line, re.IGNORECASE)
            if wl_match:
                wavelength = float(wl_match.group(1))
                break

        measurements, raw_headers, grid_warnings = self._parse_grid_block(
            lines, wavelength, measurement_type
        )
        warnings.extend(grid_warnings)

        if not measurements:
            raise ParseError(
                "No valid plate grid data found in CSV. Expected row labels (A-H/A-P) "
                "with numeric values in a grid layout.",
                parser_name=self.name,
                suggestion="Ensure the file has a plate grid with row labels (A, B, ...) and column numbers (1, 2, ...).",
            )

        plate_layout = self._detect_plate_layout(measurements)

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type=measurement_type,
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="Plate Reader",
                wavelength_nm=wavelength,
            ),
            sample_count=len(measurements),
            plate_layout=plate_layout,
            run_metadata={
                "format": "generic_grid",
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=raw_headers or None,
            warnings=warnings,
        )

    def _parse_grid_block(
        self,
        lines: list[str],
        wavelength: float | None,
        measurement_type: str,
    ) -> tuple[list[MeasurementValue], list[str], list[str]]:
        """Parse a plate grid block from lines. Returns (measurements, headers, warnings)."""
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        raw_headers: list[str] = []
        col_headers: list[int] = []
        in_grid = False

        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                if in_grid:
                    in_grid = False
                continue

            cells = self._split_row(stripped)

            if not in_grid and self._is_column_header_row(cells):
                in_grid = True
                col_headers = [int(c) for c in cells if c.strip().isdigit()]
                raw_headers = cells
                continue

            if in_grid and cells:
                first = cells[0].strip().upper()
                if _is_plate_row_label(first):
                    row_label = first
                    for i, cell in enumerate(cells[1:]):
                        if i < len(col_headers):
                            val = self._parse_float(cell)
                            if val is not None:
                                well = _well_position(row_label, col_headers[i])
                                unit = self._get_unit(measurement_type)
                                measurements.append(
                                    MeasurementValue(
                                        well_position=well,
                                        value=val,
                                        unit=unit,
                                        measurement_type=measurement_type,
                                        wavelength_nm=wavelength,
                                    )
                                )
                else:
                    in_grid = False

        return measurements, raw_headers, warnings

    def _try_tabular_parse(
        self,
        text: str,
        wavelength: float | None,
        measurement_type: str,
    ) -> tuple[list[MeasurementValue], list[str]] | None:
        """Try to parse as tabular format with Well/Value columns.

        Scans for the header row containing 'Well' to handle files with
        metadata lines before the actual CSV data.
        """
        delimiter = self._detect_delimiter(text)

        # Find the actual CSV header row (line containing "Well")
        lines = text.split("\n")
        csv_start = 0
        for i, line in enumerate(lines):
            if "well" in line.lower() and delimiter in line:
                csv_start = i
                break
        else:
            return None  # No "Well" column found

        csv_text = "\n".join(lines[csv_start:])
        reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers:
            return None

        header_map = {h.strip().lower(): h.strip() for h in headers}

        # Need a well column and a value column
        well_col = None
        value_col = None
        for key, orig in header_map.items():
            if "well" in key:
                well_col = orig
            elif any(k in key for k in ("value", "od", "abs", "rfu", "rlu", "result", "reading")):
                value_col = orig

        if not well_col or not value_col:
            return None

        measurements: list[MeasurementValue] = []
        well_pattern = re.compile(r"^([A-P])(\d{1,2})$", re.IGNORECASE)
        unit = self._get_unit(measurement_type)

        for row in reader:
            well = row.get(well_col, "").strip()
            if not well_pattern.match(well):
                continue
            val = self._parse_float(row.get(value_col))
            if val is not None:
                measurements.append(
                    MeasurementValue(
                        well_position=well.upper(),
                        value=val,
                        unit=unit,
                        measurement_type=measurement_type,
                        wavelength_nm=wavelength,
                    )
                )

        if measurements:
            return measurements, list(headers)
        return None

    def _is_column_header_row(self, cells: list[str]) -> bool:
        """Check if cells look like column number headers (1, 2, 3, ...)."""
        # Filter to non-empty cells
        non_empty = [c.strip() for c in cells if c.strip()]
        if len(non_empty) < 3:
            return False

        # At least first cell may be empty (row label position), rest should be numbers
        numeric_count = sum(1 for c in non_empty if c.isdigit())
        return numeric_count >= 3 and numeric_count >= len(non_empty) * 0.5

    def _split_row(self, line: str) -> list[str]:
        """Split a CSV line handling both comma and tab delimiters."""
        if "\t" in line:
            return line.split("\t")
        # Use csv reader for proper comma handling
        try:
            return next(csv.reader(io.StringIO(line)))
        except StopIteration:
            return []

    def _detect_delimiter(self, text: str) -> str:
        """Detect CSV delimiter."""
        first_line = text.split("\n", 1)[0]
        if first_line.count("\t") > first_line.count(","):
            return "\t"
        return ","

    def _detect_plate_layout(self, measurements: list[MeasurementValue]) -> dict:
        """Determine plate format from well positions."""
        wells = {m.well_position for m in measurements if m.well_position}
        if not wells:
            return {"format": "unknown"}

        max_row = "A"
        max_col = 1
        for well in wells:
            match = re.match(r"([A-P])(\d+)", well)
            if match:
                row, col = match.group(1), int(match.group(2))
                if row > max_row:
                    max_row = row
                if col > max_col:
                    max_col = col

        row_count = ord(max_row) - ord("A") + 1
        col_count = max_col

        if row_count <= 8 and col_count <= 12:
            return {"rows": 8, "cols": 12, "format": "96-well", "wells_with_data": len(wells)}
        elif row_count <= 16 and col_count <= 24:
            return {"rows": 16, "cols": 24, "format": "384-well", "wells_with_data": len(wells)}
        else:
            return {"rows": row_count, "cols": col_count, "format": f"custom", "wells_with_data": len(wells)}

    @staticmethod
    def _get_unit(measurement_type: str) -> str:
        """Get the appropriate unit for a measurement type."""
        return {
            "absorbance": "OD",
            "fluorescence": "RFU",
            "luminescence": "RLU",
        }.get(measurement_type, "AU")

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        """Safely parse a string to float."""
        if value is None:
            return None
        value = value.strip().replace(",", "")
        if not value or value in ("-", "N/A", "n/a", "NA", "", "---", "OVRFLW", "****"):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
