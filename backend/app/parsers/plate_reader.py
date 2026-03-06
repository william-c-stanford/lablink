"""Plate reader parser for SoftMax Pro / Gen5 CSV exports with 96-well layout."""

from __future__ import annotations

import csv
import re
from typing import Any, ClassVar

from app.parsers.base import BaseParser, FileContext, ParseError
from app.schemas.parsed_result import (
    InstrumentSettings,
    MeasurementValue,
    ParsedResult,
    QualityFlag,
)

PLATE_ROWS = "ABCDEFGH"


class PlateReaderParser(BaseParser):
    """Parses plate reader CSV data (SoftMax Pro, Gen5 format)."""

    name: ClassVar[str] = "plate_reader"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "plate_reader"
    supported_extensions: ClassVar[tuple[str, ...]] = (".csv", ".txt")

    def can_handle(self, ctx: FileContext) -> bool:
        if ctx.instrument_type_hint == "plate_reader":
            return True
        if ctx.extension not in self.supported_extensions:
            return False
        text = ctx.text[:1000].lower()
        return any(kw in text for kw in ("plate", "well", "96", "softmax", "gen5"))

    def parse(self, ctx: FileContext) -> ParsedResult:
        text = self._decode_text(ctx.file_bytes)
        lines = text.strip().splitlines()

        if len(lines) < 2:
            self._raise_parse_error(
                "File has fewer than 2 lines", ctx,
                suggestion="Ensure the plate reader export contains header and data rows.",
            )

        raw_meta: dict[str, Any] = {}
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []

        plate_start = self._find_plate_data(lines)

        if plate_start is not None:
            for line in lines[:plate_start]:
                if ":" in line:
                    key, _, val = line.partition(":")
                    raw_meta[key.strip()] = val.strip()
            measurements, warnings = self._parse_plate_layout(lines[plate_start:], ctx.extra)
        else:
            measurements, warnings = self._parse_tabular(lines, raw_meta, ctx.extra)

        if not measurements:
            self._raise_parse_error(
                "No valid measurements found in plate reader file", ctx,
                suggestion="Check that the file contains a 96-well plate layout or tabular data with well positions.",
            )

        settings = InstrumentSettings(
            instrument_model=ctx.extra.get("instrument_model") or raw_meta.get("Instrument"),
            serial_number=raw_meta.get("Serial Number"),
            software_version=raw_meta.get("Software Version"),
            method_name=raw_meta.get("Protocol") or raw_meta.get("Method"),
            parameters={"read_mode": raw_meta.get("Read Mode", "Absorbance"),
                        "wavelength": raw_meta.get("Wavelength", "")},
        )

        return self._make_result(ctx, measurements=measurements,
                                 instrument_settings=settings, warnings=warnings,
                                 raw_metadata=raw_meta)

    def _find_plate_data(self, lines: list[str]) -> int | None:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^[,\t]?\s*1[,\t]\s*2[,\t]\s*3", stripped):
                return i
            if re.match(r"^A[,\t]\s*[\d.]", stripped):
                return i
        return None

    def _parse_plate_layout(self, lines: list[str], extra: dict[str, Any]
                            ) -> tuple[list[MeasurementValue], list[str]]:
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        delimiter = "\t" if "\t" in lines[0] else ","

        start = 0
        first_parts = lines[0].split(delimiter)
        if first_parts[0].strip() == "" or first_parts[0].strip().lower() in ("", "row"):
            start = 1

        for line in lines[start:]:
            try:
                if not line.strip():
                    continue
                parts = line.split(delimiter)
                row_label = parts[0].strip().upper()
                if row_label not in PLATE_ROWS:
                    continue
                for col_idx, value_str in enumerate(parts[1:], start=1):
                    value_str = value_str.strip()
                    if not value_str or value_str.lower() in ("", "nan", "n/a", "-"):
                        continue
                    well = f"{row_label}{col_idx}"
                    quality = QualityFlag.GOOD
                    try:
                        value = float(value_str)
                    except ValueError:
                        warnings.append(f"Well {well}: non-numeric value '{value_str}'")
                        continue
                    if value < 0:
                        quality = QualityFlag.SUSPECT
                        warnings.append(f"Well {well}: negative value {value}")
                    read_mode = extra.get("read_mode", "absorbance")
                    unit = "RFU" if "fluorescence" in str(read_mode).lower() else "AU"
                    measurements.append(MeasurementValue(
                        name=f"{read_mode}_{well}", value=value, unit=unit,
                        well_position=well, quality=quality,
                    ))
            except (IndexError, TypeError) as exc:
                warnings.append(f"Plate row parse error: {exc}")
        return measurements, warnings

    def _parse_tabular(self, lines: list[str], raw_meta: dict[str, Any],
                       extra: dict[str, Any]) -> tuple[list[MeasurementValue], list[str]]:
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []
        delimiter = "\t" if "\t" in lines[0] else ","

        header_idx = 0
        for i, line in enumerate(lines):
            if ":" in line and not any(c.isdigit() for c in line.split(":")[0]):
                key, _, val = line.partition(":")
                raw_meta[key.strip()] = val.strip()
                header_idx = i + 1
            else:
                header_idx = i
                break

        try:
            reader = csv.reader(lines[header_idx:], delimiter=delimiter)
            headers = [h.strip() for h in next(reader)]
        except StopIteration:
            return measurements, warnings

        well_col = None
        for h in headers:
            if h.lower() in ("well", "well position", "well_position", "wells"):
                well_col = h
                break

        for row in reader:
            try:
                if not any(cell.strip() for cell in row):
                    continue
                record = dict(zip(headers, row))
                well = record.get(well_col, "").strip() if well_col else None
                for header in headers:
                    if header == well_col:
                        continue
                    value_str = record.get(header, "").strip()
                    if not value_str:
                        continue
                    try:
                        value = float(value_str)
                    except ValueError:
                        continue
                    measurements.append(MeasurementValue(
                        name=re.sub(r"[^a-zA-Z0-9_]", "_", header).lower(),
                        value=value, unit="AU", well_position=well, quality=QualityFlag.GOOD,
                    ))
            except csv.Error as exc:
                warnings.append(f"CSV parse error: {exc}")
        return measurements, warnings
