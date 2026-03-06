"""Balance parser for analytical/precision balance CSV exports.

Handles common formats:
1. Mettler Toledo: header metadata block + CSV with Sample ID, Net, Tare, Unit, Stability
2. Sartorius: simple CSV with Sample, Mass, Unit columns
3. Generic: any CSV with recognizable mass/weight columns

Produces canonical MeasurementValue output with mass/tare data, QUDT URIs,
stability quality flags, and negative-mass warnings.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, ClassVar

from lablink.parsers.base import BaseParser, ParseError
from lablink.parsers.registry import ParserRegistry
from lablink.schemas.canonical import (
    InstrumentSettings,
    MeasurementValue,
    ParsedResult,
)

# QUDT unit URI mapping for mass units
_QUDT_MASS_URIS: dict[str, str] = {
    "g": "http://qudt.org/vocab/unit/GM",
    "mg": "http://qudt.org/vocab/unit/MilliGM",
    "kg": "http://qudt.org/vocab/unit/KiloGM",
    "lb": "http://qudt.org/vocab/unit/LB",
    "oz": "http://qudt.org/vocab/unit/OZ",
}

# Keywords that indicate a balance/mass data file
_BALANCE_KEYWORDS = frozenset(
    {"mass", "weight", "balance", "tare", "net", "gross", "net weight"}
)


@ParserRegistry.register
class BalanceParser(BaseParser):
    """Parser for analytical balance CSV exports (Mettler Toledo, Sartorius, etc.)."""

    name: ClassVar[str] = "balance"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "balance"
    supported_extensions: ClassVar[list[str]] = [".csv", ".txt", ".tsv"]

    def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
        """Detect balance files by header keywords and extension."""
        score = super().detect(file_bytes, filename)
        try:
            header = file_bytes[:2048].decode("utf-8", errors="ignore").lower()
            words = set(re.split(r"[\s,;\t:]+", header))
            if _BALANCE_KEYWORDS & words:
                return max(score, 0.85)
            # Check for Mettler Toledo or Sartorius brand markers
            if "mettler" in header or "sartorius" in header:
                return max(score, 0.90)
        except Exception:
            pass
        return score

    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        """Parse balance CSV into canonical ParsedResult."""
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
                    suggestion="Ensure the file is a text CSV export, not a binary format.",
                )

        text = text.strip()
        if not text:
            raise ParseError(
                "File is empty.",
                parser_name=self.name,
                suggestion="Upload a non-empty balance CSV file.",
            )

        lines = text.splitlines()
        raw_meta: dict[str, Any] = {}
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []

        # Find the data header row (skip metadata preamble)
        header_idx = self._find_data_header(lines, raw_meta)
        if header_idx >= len(lines):
            raise ParseError(
                "No data header row found in balance file.",
                parser_name=self.name,
                suggestion="Ensure the file has a header row with column names like "
                "'Sample', 'Mass', 'Net', 'Weight'.",
            )

        # Detect delimiter
        delimiter = self._detect_delimiter(lines[header_idx])

        # Parse as CSV starting from header row
        try:
            reader = csv.reader(lines[header_idx:], delimiter=delimiter)
            headers = [h.strip() for h in next(reader)]
        except (StopIteration, csv.Error):
            raise ParseError(
                "Could not parse CSV headers.",
                parser_name=self.name,
                suggestion="Verify the balance file is a valid CSV.",
            )

        col_map = self._map_columns(headers)

        # Must have at least one mass/weight/value column
        mass_key = self._resolve_mass_column(col_map)
        if mass_key is None:
            raise ParseError(
                "No mass/weight/value column found in balance data.",
                parser_name=self.name,
                suggestion="Expected a column named 'Mass', 'Weight', 'Net', 'Value', or 'Gross'.",
            )

        # Default unit from metadata block
        default_unit = raw_meta.get("Unit", "g")

        for row_num, row in enumerate(reader, start=header_idx + 2):
            if not row or all(c.strip() == "" for c in row):
                continue
            record = dict(zip(headers, row))

            # Sample ID
            sample_id = None
            if "sample" in col_map:
                sample_id = record.get(col_map["sample"], "").strip() or None

            # Mass value
            mass_col = col_map[mass_key]
            mass_str = record.get(mass_col, "").strip()
            mass_str, detected_unit = self._parse_value_with_unit(mass_str)
            if not mass_str:
                continue

            try:
                mass_val = float(mass_str)
            except ValueError:
                warnings.append(f"Row {row_num}: invalid mass value '{mass_str}'")
                continue

            # Determine unit
            unit = detected_unit or self._get_unit_from_record(
                record, col_map, default_unit
            )
            qudt_uri = _QUDT_MASS_URIS.get(unit.lower())

            # Quality flag
            quality_flag: str | None = None

            # Check stability column
            if "stability" in col_map:
                stab = record.get(col_map["stability"], "").strip().lower()
                if stab in ("unstable", "u", "d", "dynamic"):
                    quality_flag = "suspect"
                    warnings.append(
                        f"Unstable reading for sample '{sample_id or f'row {row_num}'}'"
                    )

            # Negative mass check
            if mass_val < 0:
                quality_flag = "suspect"
                warnings.append(
                    f"Negative mass {mass_val} {unit} for sample "
                    f"'{sample_id or f'row {row_num}'}'"
                )

            measurements.append(
                MeasurementValue(
                    sample_name=sample_id,
                    sample_id=sample_id,
                    value=mass_val,
                    unit=unit,
                    qudt_uri=qudt_uri,
                    measurement_type="mass",
                    quality_flag=quality_flag,
                )
            )

            # Tare measurement (if present)
            if "tare" in col_map:
                tare_str = record.get(col_map["tare"], "").strip()
                tare_str, _ = self._parse_value_with_unit(tare_str)
                if tare_str:
                    try:
                        tare_val = float(tare_str)
                        measurements.append(
                            MeasurementValue(
                                sample_name=sample_id,
                                sample_id=sample_id,
                                value=tare_val,
                                unit=unit,
                                qudt_uri=qudt_uri,
                                measurement_type="tare",
                            )
                        )
                    except ValueError:
                        pass

        if not measurements:
            raise ParseError(
                "No valid mass measurements found in balance file.",
                parser_name=self.name,
                suggestion="Check that the file contains numeric mass/weight values.",
            )

        # Build instrument settings from extracted metadata
        instrument_model = raw_meta.get("Model") or raw_meta.get("Balance")
        serial_number = raw_meta.get("Serial Number") or raw_meta.get("S/N")
        software_version = raw_meta.get("Software Version")
        readability = raw_meta.get("Readability", "")

        # Extract Sartorius model from "Balance" field
        if not instrument_model:
            balance_field = raw_meta.get("Balance", "")
            if balance_field:
                instrument_model = balance_field

        settings = InstrumentSettings(
            method_name="Balance Weighing",
            extra={
                "instrument_model": instrument_model,
                "serial_number": serial_number,
                "software_version": software_version,
                "readability": readability,
                "unit": unit if measurements else "g",
            },
        )

        unique_samples = {
            m.sample_id or m.sample_name
            for m in measurements
            if m.sample_id or m.sample_name
        }

        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            measurement_type="mass",
            measurements=measurements,
            instrument_settings=settings,
            sample_count=len(unique_samples),
            run_metadata={
                "format": self._detect_format(raw_meta),
                **{k: v for k, v in raw_meta.items()},
                **{k: v for k, v in metadata.items() if k != "instrument_type"},
            },
            raw_headers=headers,
            warnings=warnings,
        )

    # -- Private helpers -------------------------------------------------------

    def _find_data_header(
        self, lines: list[str], raw_meta: dict[str, Any]
    ) -> int:
        """Find the index of the CSV data header row, extracting metadata above it."""
        for i, line in enumerate(lines):
            lower = line.lower().strip()
            # Check if this line looks like a CSV data header
            if any(
                kw in lower
                for kw in ("mass", "weight", "net", "gross", "value", "sample")
            ):
                return i
            # Extract key: value metadata from preamble
            if ":" in line and not any(c.isdigit() for c in line.split(":")[0]):
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key and val:
                    raw_meta[key] = val
        return 0

    @staticmethod
    def _detect_delimiter(line: str) -> str:
        """Detect CSV delimiter from a header line."""
        tab_count = line.count("\t")
        comma_count = line.count(",")
        semicolon_count = line.count(";")
        if tab_count > comma_count and tab_count > semicolon_count:
            return "\t"
        if semicolon_count > comma_count:
            return ";"
        return ","

    @staticmethod
    def _map_columns(headers: list[str]) -> dict[str, str]:
        """Map semantic roles to actual column names."""
        col_map: dict[str, str] = {}
        for h in headers:
            lower = h.lower().strip()
            if lower in ("mass", "weight", "gross", "gross weight"):
                col_map["mass"] = h
            elif lower in ("net", "net weight", "net mass"):
                col_map["net"] = h
            elif lower in ("value", "reading"):
                col_map["value"] = h
            elif lower in ("tare", "tare weight"):
                col_map["tare"] = h
            elif lower in ("unit", "units"):
                col_map["unit_col"] = h
            elif lower in (
                "sample",
                "sample id",
                "sample_id",
                "id",
                "sample name",
            ):
                col_map["sample"] = h
            elif lower in ("stability", "stable", "status"):
                col_map["stability"] = h
        return col_map

    @staticmethod
    def _resolve_mass_column(col_map: dict[str, str]) -> str | None:
        """Return the key in col_map to use for the mass value, preferring net > mass > value."""
        for key in ("net", "mass", "value"):
            if key in col_map:
                return key
        return None

    @staticmethod
    def _parse_value_with_unit(value_str: str) -> tuple[str, str | None]:
        """Extract numeric value and optional unit suffix."""
        match = re.match(
            r"^\s*([-+]?\d*\.?\d+)\s*(mg|g|kg|lb|oz|ct|gr)?\s*$",
            value_str,
            re.IGNORECASE,
        )
        if match:
            return match.group(1), match.group(2)
        return value_str, None

    @staticmethod
    def _get_unit_from_record(
        record: dict[str, str],
        col_map: dict[str, str],
        default_unit: str,
    ) -> str:
        """Get the unit for a record, checking unit column then default."""
        if "unit_col" in col_map:
            unit = record.get(col_map["unit_col"], "").strip()
            if unit:
                return unit
        return default_unit

    @staticmethod
    def _detect_format(raw_meta: dict[str, Any]) -> str:
        """Guess the file format from extracted metadata."""
        meta_str = " ".join(str(v) for v in raw_meta.values()).lower()
        if "mettler" in meta_str or "xpe" in meta_str or "xsr" in meta_str:
            return "mettler_toledo"
        if "sartorius" in meta_str or "quintix" in meta_str or "cubis" in meta_str:
            return "sartorius"
        return "generic_balance"
