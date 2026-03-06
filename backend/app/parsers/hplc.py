"""HPLC parser for Agilent/Shimadzu CSV exports with retention time and peak area."""

from __future__ import annotations

import csv
import re
from typing import Any, ClassVar

from app.parsers.base import BaseParser, FileContext, ParseError
from app.schemas.parsed_result import (
    InstrumentSettings,
    MeasurementValue,
    QualityFlag,
)


class HPLCParser(BaseParser):
    """Parses HPLC chromatography CSV data (Agilent ChemStation, Shimadzu LabSolutions)."""

    name: ClassVar[str] = "hplc"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "hplc"
    supported_extensions: ClassVar[tuple[str, ...]] = (".csv", ".txt")

    def can_handle(self, ctx: FileContext) -> bool:
        """Detect HPLC files by extension + header keywords."""
        if ctx.instrument_type_hint == "hplc":
            return True
        if ctx.extension not in self.supported_extensions:
            return False
        text = ctx.text[:2000].lower()
        has_rt = any(kw in text for kw in ("retention time", "ret. time", "ret.time"))
        has_peak = any(kw in text for kw in ("area", "height", "peak"))
        return has_rt and has_peak

    def parse(self, ctx: FileContext) -> ParsedResult:
        """Parse HPLC CSV export into canonical ParsedResult."""
        text = self._decode_text(ctx.file_bytes)
        lines = text.strip().splitlines()

        if len(lines) < 2:
            self._raise_parse_error(
                "File has fewer than 2 lines; expected header + peak data",
                ctx,
                suggestion="Ensure the HPLC export contains peak table headers and data rows.",
            )

        raw_meta: dict[str, Any] = {}
        warnings: list[str] = []

        # Find data header, collecting metadata along the way
        header_idx = self._find_data_header(lines, raw_meta)
        delimiter = self._detect_delimiter(lines[header_idx])

        try:
            reader = csv.reader(lines[header_idx:], delimiter=delimiter)
            headers = [h.strip() for h in next(reader)]
        except StopIteration:
            self._raise_parse_error(
                "Could not parse CSV headers",
                ctx,
                suggestion="Verify the HPLC file is a valid CSV with a peak table.",
            )

        col_map = self._map_columns(headers)
        if "retention_time" not in col_map:
            self._raise_parse_error(
                "No retention time column found in HPLC data",
                ctx,
                suggestion="Expected a column named 'Retention Time', 'RT', or 'Ret. Time'.",
            )

        sample_id = ctx.extra.get("sample_id") or raw_meta.get("Sample Name")
        measurements: list[MeasurementValue] = []

        for row_num, row in enumerate(reader, start=header_idx + 2):
            try:
                if not any(cell.strip() for cell in row):
                    continue
            except csv.Error as exc:
                warnings.append(f"Row {row_num}: CSV parse error - {exc}")
                continue
            record = dict(zip(headers, row))
            rt_str = record.get(col_map["retention_time"], "").strip()
            try:
                rt = float(rt_str)
            except (ValueError, KeyError):
                warnings.append(f"Row {row_num}: invalid retention time")
                continue

            peak_num = row_num - header_idx - 1

            # Retention time
            measurements.append(MeasurementValue(
                name=f"peak_{peak_num}_retention_time",
                value=rt,
                unit="min",
                qudt_uri="http://qudt.org/vocab/unit/MIN",
                sample_id=sample_id,
                retention_time_min=rt,
                quality=QualityFlag.GOOD,
            ))

            # Peak area
            if "area" in col_map:
                area_str = record.get(col_map["area"], "").strip()
                try:
                    area = float(area_str)
                    q = QualityFlag.SUSPECT if area < 0 else QualityFlag.GOOD
                    if area < 0:
                        warnings.append(f"Row {row_num}: negative peak area {area}")
                    measurements.append(MeasurementValue(
                        name=f"peak_{peak_num}_area",
                        value=area,
                        unit="mAU*s",
                        sample_id=sample_id,
                        quality=q,
                    ))
                except ValueError:
                    warnings.append(f"Row {row_num}: invalid area value")

            # Peak height
            if "height" in col_map:
                height_str = record.get(col_map["height"], "").strip()
                try:
                    measurements.append(MeasurementValue(
                        name=f"peak_{peak_num}_height",
                        value=float(height_str),
                        unit="mAU",
                        sample_id=sample_id,
                        quality=QualityFlag.GOOD,
                    ))
                except ValueError:
                    pass

            # Area percent
            if "area_pct" in col_map:
                pct_str = record.get(col_map["area_pct"], "").strip()
                try:
                    pct = float(pct_str)
                    q = QualityFlag.SUSPECT if (pct < 0 or pct > 100) else QualityFlag.GOOD
                    if pct < 0 or pct > 100:
                        warnings.append(f"Row {row_num}: area% {pct} outside [0, 100]")
                    measurements.append(MeasurementValue(
                        name=f"peak_{peak_num}_area_pct",
                        value=pct,
                        unit="%",
                        sample_id=sample_id,
                        quality=q,
                    ))
                except ValueError:
                    pass

        if not measurements:
            self._raise_parse_error(
                "No valid peaks found in HPLC data",
                ctx,
                suggestion="Ensure the peak table has retention time and area columns.",
            )

        settings = InstrumentSettings(
            instrument_model=(
                ctx.extra.get("instrument_model")
                or raw_meta.get("Instrument")
            ),
            serial_number=raw_meta.get("Serial Number"),
            software_version=raw_meta.get("Software Version"),
            method_name=raw_meta.get("Method") or raw_meta.get("Method Name"),
            parameters={
                "column": raw_meta.get("Column", ""),
                "detector": raw_meta.get("Detector", "UV"),
            },
        )

        return self._make_result(
            ctx,
            measurements=measurements,
            instrument_settings=settings,
            warnings=warnings,
            raw_metadata=raw_meta,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_data_header(self, lines: list[str], raw_meta: dict[str, Any]) -> int:
        """Find peak table header row, collecting metadata from preceding lines."""
        for i, line in enumerate(lines):
            lower = line.lower()
            # Header row with RT column
            if any(kw in lower for kw in ("retention time", "ret. time", "ret.time")):
                return i
            # Peak# style header
            if re.match(r"^(peak\s*#?|#|no\.?)\s*,", lower):
                return i
            # Metadata key:value lines
            if ":" in line:
                key, _, val = line.partition(":")
                if not any(c.isdigit() for c in key):
                    raw_meta[key.strip()] = val.strip()
        return 0

    @staticmethod
    def _detect_delimiter(line: str) -> str:
        """Auto-detect CSV delimiter."""
        if "\t" in line:
            return "\t"
        if ";" in line:
            return ";"
        return ","

    @staticmethod
    def _map_columns(headers: list[str]) -> dict[str, str]:
        """Map canonical column names to actual header strings."""
        col_map: dict[str, str] = {}
        for h in headers:
            lower = h.lower().strip()
            if any(kw in lower for kw in (
                "retention time", "ret. time", "ret.time", "rt (min)", "time (min)",
            )):
                col_map["retention_time"] = h
            elif lower in ("rt", "r.t."):
                col_map.setdefault("retention_time", h)
            elif "area" in lower and "%" in lower:
                col_map["area_pct"] = h
            elif "area" in lower:
                col_map["area"] = h
            elif "height" in lower:
                col_map["height"] = h
        return col_map
