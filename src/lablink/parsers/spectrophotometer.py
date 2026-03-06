"""Spectrophotometer parser for NanoDrop and Cary UV-Vis CSV files.

Handles two common formats:
1. NanoDrop: tabular CSV with sample names, concentrations, A260/A280 ratios
2. Cary UV-Vis: wavelength scan CSV with wavelength vs absorbance columns

Both produce canonical MeasurementValue output with absorbance/concentration data.
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


@ParserRegistry.register
class SpectrophotometerParser(BaseParser):
    """Parser for UV-Vis spectrophotometer CSV exports."""

    name: ClassVar[str] = "spectrophotometer"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "spectrophotometer"
    supported_extensions: ClassVar[list[str]] = [".csv", ".tsv", ".txt"]

    # Known header patterns for format detection
    _NANODROP_MARKERS = {"a260", "a280", "260/280", "ng/ul", "concentration"}
    _CARY_MARKERS = {"wavelength", "abs", "absorbance"}

    def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
        """Detect spectrophotometer files by header keywords."""
        score = super().detect(file_bytes, filename)
        try:
            header = file_bytes[:2048].decode("utf-8", errors="ignore").lower()
            header_words = set(re.split(r"[\s,;\t]+", header))
            if self._NANODROP_MARKERS & header_words:
                return max(score, 0.85)
            if self._CARY_MARKERS & header_words:
                return max(score, 0.80)
        except Exception:
            pass
        return score

    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        """Parse spectrophotometer CSV into canonical ParsedResult."""
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
                suggestion="Upload a non-empty spectrophotometer CSV file.",
            )

        # Detect delimiter
        delimiter = self._detect_delimiter(text)

        # Detect format
        header_lower = text[:2048].lower()
        if any(m in header_lower for m in ("260/280", "a260", "ng/ul", "nanodrop")):
            return self._parse_nanodrop(text, delimiter, metadata)
        elif any(m in header_lower for m in ("wavelength",)):
            return self._parse_cary(text, delimiter, metadata)
        else:
            # Try generic CSV with numeric columns
            return self._parse_generic(text, delimiter, metadata)

    def _detect_delimiter(self, text: str) -> str:
        """Detect CSV delimiter from first few lines."""
        first_line = text.split("\n", 1)[0]
        tab_count = first_line.count("\t")
        comma_count = first_line.count(",")
        semicolon_count = first_line.count(";")
        if tab_count > comma_count and tab_count > semicolon_count:
            return "\t"
        if semicolon_count > comma_count:
            return ";"
        return ","

    def _parse_nanodrop(
        self, text: str, delimiter: str, metadata: dict
    ) -> ParsedResult:
        """Parse NanoDrop-style tabular CSV."""
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = reader.fieldnames
        if not headers:
            raise ParseError(
                "No headers found in NanoDrop CSV.",
                parser_name=self.name,
                suggestion="Ensure the CSV has a header row with column names.",
            )

        # Normalize header names for matching
        header_map = {h.strip().lower(): h.strip() for h in headers}

        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        sample_names: set[str] = set()
        settings_extra: dict = {}

        # Find key columns
        sample_col = self._find_column(header_map, ["sample", "sample id", "sample name", "name"])
        conc_col = self._find_column(header_map, ["concentration", "ng/ul", "conc.", "ng/µl"])
        a260_col = self._find_column(header_map, ["a260", "260nm", "abs 260"])
        a280_col = self._find_column(header_map, ["a280", "280nm", "abs 280"])
        ratio_col = self._find_column(header_map, ["260/280", "a260/a280"])

        row_count = 0
        for row_idx, row in enumerate(reader):
            try:
                sample_name = row.get(sample_col, f"Sample_{row_idx + 1}") if sample_col else f"Sample_{row_idx + 1}"
                sample_name = sample_name.strip() if sample_name else f"Sample_{row_idx + 1}"
                sample_names.add(sample_name)

                # Concentration measurement
                if conc_col and row.get(conc_col):
                    val = self._parse_float(row[conc_col])
                    if val is not None:
                        measurements.append(
                            MeasurementValue(
                                sample_name=sample_name,
                                value=val,
                                unit="ng/uL",
                                qudt_uri="http://qudt.org/vocab/unit/NanoGM-PER-MicroL",
                                measurement_type="concentration",
                                wavelength_nm=260.0,
                            )
                        )

                # A260 measurement
                if a260_col and row.get(a260_col):
                    val = self._parse_float(row[a260_col])
                    if val is not None:
                        measurements.append(
                            MeasurementValue(
                                sample_name=sample_name,
                                value=val,
                                unit="AU",
                                qudt_uri="http://qudt.org/vocab/unit/ABSORBANCE",
                                measurement_type="absorbance",
                                wavelength_nm=260.0,
                            )
                        )

                # A280 measurement
                if a280_col and row.get(a280_col):
                    val = self._parse_float(row[a280_col])
                    if val is not None:
                        measurements.append(
                            MeasurementValue(
                                sample_name=sample_name,
                                value=val,
                                unit="AU",
                                qudt_uri="http://qudt.org/vocab/unit/ABSORBANCE",
                                measurement_type="absorbance",
                                wavelength_nm=280.0,
                            )
                        )

                # 260/280 ratio
                if ratio_col and row.get(ratio_col):
                    val = self._parse_float(row[ratio_col])
                    if val is not None:
                        measurements.append(
                            MeasurementValue(
                                sample_name=sample_name,
                                value=val,
                                unit="ratio",
                                measurement_type="purity_ratio",
                                channel="260/280",
                            )
                        )
                        # Flag suspect purity
                        if val < 1.7 or val > 2.2:
                            warnings.append(
                                f"Sample '{sample_name}' has 260/280 ratio {val:.2f} "
                                f"(expected 1.7-2.2 for pure nucleic acid)."
                            )

                row_count += 1
            except Exception as e:
                warnings.append(f"Row {row_idx + 1}: skipped due to error: {e}")

        if not measurements:
            raise ParseError(
                "No valid measurements found in NanoDrop CSV.",
                parser_name=self.name,
                suggestion="Check that the CSV contains numeric data columns (concentration, A260, A280).",
            )

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="absorbance",
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="NanoDrop UV-Vis",
                wavelength_nm=260.0,
                extra=settings_extra,
            ),
            sample_count=len(sample_names),
            run_metadata={
                "format": "nanodrop",
                "row_count": row_count,
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=list(headers),
            warnings=warnings,
        )

    def _parse_cary(
        self, text: str, delimiter: str, metadata: dict
    ) -> ParsedResult:
        """Parse Cary UV-Vis wavelength scan CSV."""
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            raise ParseError(
                "Cary UV-Vis CSV must have at least a header row and one data row.",
                parser_name=self.name,
                suggestion="Ensure the file contains wavelength scan data.",
            )

        headers = [h.strip() for h in rows[0]]
        header_lower = [h.lower() for h in headers]

        # Find wavelength column
        wl_idx = None
        for i, h in enumerate(header_lower):
            if "wavelength" in h or h in ("nm", "wl"):
                wl_idx = i
                break
        if wl_idx is None:
            wl_idx = 0  # Assume first column is wavelength

        # Data columns are all other numeric columns
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        sample_names: set[str] = set()

        data_col_indices = [i for i in range(len(headers)) if i != wl_idx]

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or all(c.strip() == "" for c in row):
                continue
            try:
                wavelength = self._parse_float(row[wl_idx])
                if wavelength is None:
                    continue

                for col_idx in data_col_indices:
                    if col_idx >= len(row):
                        continue
                    val = self._parse_float(row[col_idx])
                    if val is None:
                        continue

                    col_name = headers[col_idx] if col_idx < len(headers) else f"Channel_{col_idx}"
                    sample_names.add(col_name)

                    quality = None
                    if val < 0:
                        quality = "suspect"
                        warnings.append(
                            f"Negative absorbance {val:.4f} at {wavelength:.1f} nm "
                            f"for '{col_name}'."
                        )
                    elif val > 4.0:
                        quality = "out_of_range"
                        warnings.append(
                            f"Absorbance {val:.4f} at {wavelength:.1f} nm exceeds "
                            f"detector range for '{col_name}'."
                        )

                    measurements.append(
                        MeasurementValue(
                            sample_name=col_name,
                            value=val,
                            unit="AU",
                            qudt_uri="http://qudt.org/vocab/unit/ABSORBANCE",
                            measurement_type="absorbance",
                            wavelength_nm=wavelength,
                            quality_flag=quality,
                        )
                    )
            except Exception as e:
                warnings.append(f"Row {row_idx}: skipped due to error: {e}")

        if not measurements:
            raise ParseError(
                "No valid absorbance measurements found in Cary UV-Vis CSV.",
                parser_name=self.name,
                suggestion="Ensure the file has wavelength and absorbance columns.",
            )

        # Determine wavelength range
        wavelengths = [m.wavelength_nm for m in measurements if m.wavelength_nm is not None]
        wl_min = min(wavelengths) if wavelengths else None
        wl_max = max(wavelengths) if wavelengths else None

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="absorbance",
            measurements=measurements,
            instrument_settings=InstrumentSettings(
                method_name="UV-Vis Wavelength Scan",
                wavelength_nm=wl_min,
                extra={
                    "wavelength_range_nm": [wl_min, wl_max],
                    "scan_points": len(wavelengths),
                },
            ),
            sample_count=len(sample_names),
            run_metadata={
                "format": "cary_uv_vis",
                "wavelength_min_nm": wl_min,
                "wavelength_max_nm": wl_max,
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=headers,
            warnings=warnings,
        )

    def _parse_generic(
        self, text: str, delimiter: str, metadata: dict
    ) -> ParsedResult:
        """Parse generic spectrophotometer CSV with best-effort column detection."""
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            rows = list(reader)
        except csv.Error:
            raise ParseError(
                "Failed to parse file as CSV.",
                parser_name=self.name,
                suggestion="Ensure the file is a valid CSV/TSV text file.",
            )

        if len(rows) < 2:
            raise ParseError(
                "CSV must have at least a header row and one data row.",
                parser_name=self.name,
                suggestion="Ensure the file is a valid spectrophotometer CSV export.",
            )

        headers = [h.strip() for h in rows[0]]
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        warnings.append("Using generic CSV parser; column mapping may be approximate.")

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or all(c.strip() == "" for c in row):
                continue
            for col_idx, cell in enumerate(row):
                val = self._parse_float(cell)
                if val is not None:
                    col_name = headers[col_idx] if col_idx < len(headers) else f"Col_{col_idx}"
                    measurements.append(
                        MeasurementValue(
                            sample_name=col_name,
                            value=val,
                            unit="AU",
                            measurement_type="absorbance",
                        )
                    )

        if not measurements:
            raise ParseError(
                "No numeric values found in CSV.",
                parser_name=self.name,
                suggestion="Ensure the file contains numeric measurement data.",
            )

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="absorbance",
            measurements=measurements,
            sample_count=len({m.sample_name for m in measurements}),
            raw_headers=headers,
            warnings=warnings,
            run_metadata={"format": "generic_csv"},
        )

    @staticmethod
    def _find_column(header_map: dict[str, str], candidates: list[str]) -> str | None:
        """Find the original column name matching any candidate."""
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
