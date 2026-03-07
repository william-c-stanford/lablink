"""HPLC parser for Agilent ChemStation and Shimadzu LabSolutions CSV exports.

Handles common HPLC peak table formats:
1. Agilent ChemStation: header metadata + peak table with Retention Time, Area, Height, Area%
2. Shimadzu LabSolutions: header metadata + peak table with Ret. Time, Area, Height, Area%, Compound
3. Simple/generic: CSV with Retention Time column and numeric data

Produces canonical MeasurementValue output with retention_time, area, height, and area_percent data.
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


@ParserRegistry.register
class HPLCParser(BaseParser):
    """Parser for HPLC peak table CSV exports (Agilent, Shimadzu, generic)."""

    name: ClassVar[str] = "hplc"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "hplc"
    supported_extensions: ClassVar[list[str]] = [".csv", ".tsv", ".txt", ".cdf"]

    # Header keywords for format detection
    _HPLC_MARKERS = {
        "retention time", "ret. time", "ret time", "rt (min)", "rt(min)",
        "peak#", "peak #", "area %", "area%", "mau*s", "mau",
    }
    _AGILENT_MARKERS = {"agilent", "chemstation", "openlab"}
    _SHIMADZU_MARKERS = {"shimadzu", "labsolutions", "nexera"}

    def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
        """Detect HPLC files by header keywords and instrument markers."""
        score = super().detect(file_bytes, filename)
        try:
            header = file_bytes[:4096].decode("utf-8", errors="ignore").lower()

            # Check for HPLC-specific keywords
            has_rt = any(marker in header for marker in (
                "retention time", "ret. time", "ret time", "rt (min)", "rt(min)",
            ))
            has_peak = "peak" in header
            has_area = "area" in header

            if has_rt and (has_peak or has_area):
                score = max(score, 0.80)

            # Boost for known instrument brands
            if any(m in header for m in self._AGILENT_MARKERS):
                score = max(score, 0.90)
            elif any(m in header for m in self._SHIMADZU_MARKERS):
                score = max(score, 0.90)
        except Exception:
            pass
        return score

    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        """Parse HPLC peak table CSV into canonical ParsedResult."""
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
                    suggestion="Ensure the file is a text CSV export, not a binary format.",
                )

        text = text.strip()
        if not text:
            raise ParseError(
                "File is empty.",
                parser_name=self.name,
                suggestion="Upload a non-empty HPLC CSV file.",
            )

        # Split into header metadata and data table
        header_meta, data_text, raw_headers = self._split_header_and_data(text)

        if not data_text:
            raise ParseError(
                "No peak table found in file.",
                parser_name=self.name,
                suggestion="Ensure the file contains a peak table with retention time data.",
            )

        # Detect format from header metadata
        header_lower = text[:4096].lower()
        is_agilent = any(m in header_lower for m in self._AGILENT_MARKERS)
        is_shimadzu = any(m in header_lower for m in self._SHIMADZU_MARKERS)

        # Try allotropy for Agilent (OpenLab CDS); Shimadzu has no allotropy support
        if is_agilent:
            allotropy_result = self._try_allotropy(file_bytes, "AGILENT_OPENLAB_CDS", "file.rslt")
            if allotropy_result is not None:
                allotropy_result.run_metadata["allotropy_attempted"] = True
                allotropy_result.run_metadata["allotropy_used"] = True
                return allotropy_result

        # Parse instrument metadata from header lines
        instrument_meta = self._parse_header_metadata(header_meta)

        # Detect delimiter
        delimiter = self._detect_delimiter(data_text)

        # Parse peak table
        measurements, warnings, sample_names = self._parse_peak_table(
            data_text, delimiter, metadata, instrument_meta
        )

        if not measurements:
            raise ParseError(
                "No valid peak measurements found in HPLC CSV.",
                parser_name=self.name,
                suggestion="Check that the CSV contains a peak table with retention time column.",
            )

        # Build instrument settings
        settings = self._build_settings(instrument_meta, is_agilent, is_shimadzu)

        # Determine format label
        if is_agilent:
            fmt = "agilent_chemstation"
        elif is_shimadzu:
            fmt = "shimadzu_labsolutions"
        else:
            fmt = "generic_hplc"

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="retention_time",
            measurements=measurements,
            instrument_settings=settings,
            sample_count=len(sample_names) if sample_names else 1,
            run_metadata={
                "format": fmt,
                "peak_count": len([m for m in measurements if m.measurement_type == "retention_time"]),
                "allotropy_attempted": is_agilent,
                "allotropy_used": False,
                **{k: v for k, v in instrument_meta.items()},
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=raw_headers,
            warnings=warnings,
        )

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

    def _split_header_and_data(self, text: str) -> tuple[list[str], str, list[str] | None]:
        """Split file into header metadata lines and the data table portion.

        HPLC exports often have metadata lines before the CSV table.
        The table starts at the first line that looks like a CSV header with
        known column names (Peak#, Retention Time, Area, etc.).

        Returns:
            (header_lines, data_text, raw_column_headers)
        """
        lines = text.split("\n")
        header_lines: list[str] = []
        data_start = None

        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            # Detect table header row
            if any(kw in line_lower for kw in (
                "retention time", "ret. time", "ret time", "rt (min)", "rt(min)",
            )):
                data_start = i
                break
            header_lines.append(line)

        if data_start is None:
            # No recognized header - maybe the whole file is a table
            # Try if first line has at least some numeric-looking columns
            if lines and "," in lines[0]:
                return [], text, None
            return header_lines, "", None

        data_text = "\n".join(lines[data_start:])
        # Parse column headers
        raw_headers = [h.strip() for h in lines[data_start].split(",")]

        return header_lines, data_text, raw_headers

    def _parse_header_metadata(self, header_lines: list[str]) -> dict:
        """Extract key-value metadata from header lines (e.g., 'Instrument: Agilent 1260')."""
        meta: dict = {}
        for line in header_lines:
            line = line.strip()
            if not line:
                continue
            # Match "Key: Value" pattern
            match = re.match(r"^([^:]+):\s*(.+)$", line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                meta[key] = value
        return meta

    def _detect_delimiter(self, text: str) -> str:
        """Detect CSV delimiter from first line of data."""
        first_line = text.split("\n", 1)[0]
        tab_count = first_line.count("\t")
        comma_count = first_line.count(",")
        semicolon_count = first_line.count(";")
        if tab_count > comma_count and tab_count > semicolon_count:
            return "\t"
        if semicolon_count > comma_count:
            return ";"
        return ","

    def _parse_peak_table(
        self,
        data_text: str,
        delimiter: str,
        metadata: dict,
        instrument_meta: dict,
    ) -> tuple[list[MeasurementValue], list[str], set[str]]:
        """Parse the peak table CSV portion into measurements."""
        reader = csv.DictReader(io.StringIO(data_text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers:
            raise ParseError(
                "No column headers found in peak table.",
                parser_name=self.name,
                suggestion="Ensure the CSV has a header row with column names like 'Retention Time', 'Area'.",
            )

        # Normalize header names for matching
        header_map = {h.strip().lower(): h.strip() for h in headers}

        # Find key columns
        rt_col = self._find_column(header_map, [
            "retention time (min)", "retention time", "ret. time", "ret time",
            "rt (min)", "rt(min)", "rt",
        ])
        area_col = self._find_column(header_map, [
            "area (mau*s)", "area",
        ])
        height_col = self._find_column(header_map, [
            "height (mau)", "height",
        ])
        area_pct_col = self._find_column(header_map, [
            "area %", "area%", "area_pct",
        ])
        compound_col = self._find_column(header_map, [
            "compound", "compound name", "name", "component",
        ])
        width_col = self._find_column(header_map, [
            "width (min)", "width", "peak width",
        ])
        peak_col = self._find_column(header_map, [
            "peak#", "peak #", "peak", "no.", "#",
        ])

        if not rt_col:
            raise ParseError(
                "No retention time column found in peak table.",
                parser_name=self.name,
                suggestion="Ensure the CSV has a 'Retention Time' or 'Ret. Time' column.",
            )

        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        sample_names: set[str] = set()

        sample_name = instrument_meta.get("Sample Name") or metadata.get("sample_name", "Unknown")
        sample_id = metadata.get("sample_id")
        detector_info = instrument_meta.get("Detector", "")

        # Extract wavelength from detector info (e.g., "UV 254nm" or "DAD 254 nm")
        detector_wavelength = self._extract_wavelength(detector_info)

        for row_idx, row in enumerate(reader):
            try:
                # Get retention time
                rt_str = row.get(rt_col)
                rt_val = self._parse_float(rt_str)
                if rt_val is None:
                    warnings.append(f"Row {row_idx + 1}: skipped, no valid retention time.")
                    continue

                # Build peak identifier
                peak_num = row.get(peak_col, str(row_idx + 1)) if peak_col else str(row_idx + 1)
                peak_num = peak_num.strip() if peak_num else str(row_idx + 1)
                compound_name = row.get(compound_col, "").strip() if compound_col else ""

                peak_label = compound_name if compound_name else f"Peak_{peak_num}"
                sample_names.add(sample_name)

                # Retention time measurement
                measurements.append(
                    MeasurementValue(
                        sample_id=sample_id,
                        sample_name=peak_label,
                        value=rt_val,
                        unit="min",
                        qudt_uri="http://qudt.org/vocab/unit/MIN",
                        measurement_type="retention_time",
                        channel=detector_info or None,
                        wavelength_nm=detector_wavelength,
                    )
                )

                # Area measurement
                if area_col and row.get(area_col):
                    area_val = self._parse_float(row[area_col])
                    if area_val is not None:
                        quality = None
                        if area_val < 0:
                            quality = "suspect"
                            warnings.append(
                                f"Peak {peak_num}: negative area {area_val}."
                            )
                        measurements.append(
                            MeasurementValue(
                                sample_id=sample_id,
                                sample_name=peak_label,
                                value=area_val,
                                unit="mAU*s",
                                measurement_type="area",
                                channel=detector_info or None,
                                wavelength_nm=detector_wavelength,
                                quality_flag=quality,
                            )
                        )

                # Height measurement
                if height_col and row.get(height_col):
                    height_val = self._parse_float(row[height_col])
                    if height_val is not None:
                        measurements.append(
                            MeasurementValue(
                                sample_id=sample_id,
                                sample_name=peak_label,
                                value=height_val,
                                unit="mAU",
                                measurement_type="height",
                                channel=detector_info or None,
                                wavelength_nm=detector_wavelength,
                            )
                        )

                # Area percent measurement
                if area_pct_col and row.get(area_pct_col):
                    pct_val = self._parse_float(row[area_pct_col])
                    if pct_val is not None:
                        measurements.append(
                            MeasurementValue(
                                sample_id=sample_id,
                                sample_name=peak_label,
                                value=pct_val,
                                unit="%",
                                measurement_type="area_percent",
                                channel=detector_info or None,
                            )
                        )

            except Exception as e:
                warnings.append(f"Row {row_idx + 1}: skipped due to error: {e}")

        return measurements, warnings, sample_names

    def _build_settings(
        self,
        instrument_meta: dict,
        is_agilent: bool,
        is_shimadzu: bool,
    ) -> InstrumentSettings:
        """Build InstrumentSettings from parsed header metadata."""
        method_name = instrument_meta.get("Method") or instrument_meta.get("Method Name")
        column_type = instrument_meta.get("Column")
        detector = instrument_meta.get("Detector", "")

        # Parse flow rate
        flow_rate = None
        flow_str = instrument_meta.get("Flow Rate", "")
        if flow_str:
            flow_val = self._parse_float(flow_str.split()[0] if flow_str else "")
            if flow_val is not None:
                flow_rate = flow_val

        # Parse injection volume
        injection_vol = None
        inj_str = instrument_meta.get("Injection Volume", "")
        if inj_str:
            inj_val = self._parse_float(inj_str.split()[0] if inj_str else "")
            if inj_val is not None:
                injection_vol = inj_val

        # Extract wavelength from detector info
        wavelength = self._extract_wavelength(detector)

        extra: dict = {}
        if instrument_meta.get("Instrument"):
            extra["instrument_model"] = instrument_meta["Instrument"]
        if instrument_meta.get("Serial Number"):
            extra["serial_number"] = instrument_meta["Serial Number"]
        if instrument_meta.get("Software Version"):
            extra["software_version"] = instrument_meta["Software Version"]
        if instrument_meta.get("Run Date"):
            extra["run_date"] = instrument_meta["Run Date"]
        if detector:
            extra["detector"] = detector

        return InstrumentSettings(
            method_name=method_name,
            wavelength_nm=wavelength,
            flow_rate_ml_min=flow_rate,
            injection_volume_ul=injection_vol,
            column_type=column_type,
            extra=extra,
        )

    @staticmethod
    def _extract_wavelength(detector_str: str) -> float | None:
        """Extract wavelength from detector description (e.g., 'UV 254nm' -> 254.0)."""
        if not detector_str:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)\s*nm", detector_str, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    @staticmethod
    def _find_column(header_map: dict[str, str], candidates: list[str]) -> str | None:
        """Find the original column name matching any candidate (exact then partial)."""
        for candidate in candidates:
            if candidate in header_map:
                return header_map[candidate]
        # Partial match
        for candidate in candidates:
            for key, original in header_map.items():
                if candidate in key:
                    return original
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        """Safely parse a string to float, returning None on failure."""
        if value is None:
            return None
        value = value.strip().replace(",", "")
        if not value or value in ("-", "N/A", "n/a", "NA", "", "---"):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
