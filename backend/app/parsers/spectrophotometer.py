"""Spectrophotometer parser for NanoDrop/Cary UV-Vis CSV exports."""

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


class SpectrophotometerParser(BaseParser):
    """Parses NanoDrop and Cary UV-Vis spectrophotometer CSV data."""

    name: ClassVar[str] = "spectrophotometer"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "spectrophotometer"
    supported_extensions: ClassVar[tuple[str, ...]] = (".csv", ".tsv", ".txt")

    def can_handle(self, ctx: FileContext) -> bool:
        if ctx.instrument_type_hint == "spectrophotometer":
            return True
        if ctx.extension not in self.supported_extensions:
            return False
        text = ctx.text[:500].lower()
        return any(kw in text for kw in ("a260", "a280", "absorbance", "nanodrop", "wavelength"))

    def parse(self, ctx: FileContext) -> ParsedResult:
        text = self._decode_text(ctx.file_bytes)
        lines = text.strip().splitlines()

        if len(lines) < 2:
            self._raise_parse_error(
                "File has fewer than 2 lines; expected header + data rows", ctx,
                suggestion="Ensure the CSV has a header row and at least one data row.",
            )

        delimiter = self._detect_delimiter(lines[0])
        raw_meta: dict[str, Any] = {}
        header_idx = self._find_header(lines, delimiter, raw_meta)

        try:
            reader = csv.reader(lines[header_idx:], delimiter=delimiter)
            headers = [h.strip() for h in next(reader)]
        except StopIteration:
            self._raise_parse_error("Could not parse CSV headers", ctx,
                                    suggestion="Verify the file is a valid CSV with headers.")

        measurements: list[MeasurementValue] = []
        warnings: list[str] = []

        for row_num, row in enumerate(reader, start=header_idx + 2):
            try:
                if not any(cell.strip() for cell in row):
                    continue
                record = dict(zip(headers, row))
                measurements.extend(self._extract_measurements(record, headers, warnings, row_num))
            except csv.Error as exc:
                warnings.append(f"Row {row_num}: CSV parse error - {exc}")
            except (ValueError, KeyError) as exc:
                warnings.append(f"Row {row_num}: skipped - {exc}")

        if not measurements:
            self._raise_parse_error(
                "No valid measurements found in file", ctx,
                suggestion="Check that the CSV contains numeric absorbance or concentration values.",
            )

        settings = InstrumentSettings(
            instrument_model=ctx.extra.get("instrument_model") or raw_meta.get("Instrument"),
            serial_number=raw_meta.get("Serial Number"),
            software_version=raw_meta.get("Software Version"),
            method_name=raw_meta.get("Method"),
            parameters=raw_meta,
        )

        return self._make_result(ctx, measurements=measurements,
                                 instrument_settings=settings, warnings=warnings,
                                 raw_metadata=raw_meta)

    def _detect_delimiter(self, line: str) -> str:
        if "\t" in line:
            return "\t"
        if ";" in line:
            return ";"
        return ","

    def _find_header(self, lines: list[str], delimiter: str, raw_meta: dict[str, Any]) -> int:
        for i, line in enumerate(lines):
            parts = line.split(delimiter)
            text_parts = sum(1 for p in parts if re.search(r"[a-zA-Z]", p.strip()))
            if text_parts >= 2 and len(parts) >= 2:
                # Check if this looks like a data header (has common column names)
                lower = line.lower()
                if any(kw in lower for kw in ("sample", "a260", "a280", "absorbance", "wavelength", "conc", "ng")):
                    return i
            if ":" in line and not any(c.isdigit() for c in line.split(":")[0]):
                key, _, val = line.partition(":")
                raw_meta[key.strip()] = val.strip()
        return 0

    def _extract_measurements(self, record: dict[str, str], headers: list[str],
                              warnings: list[str], row_num: int) -> list[MeasurementValue]:
        measurements: list[MeasurementValue] = []
        sample_id = None
        for key in ("Sample ID", "Sample", "sample_id", "Name", "Sample Name"):
            if key in record:
                sample_id = record[key].strip()
                break

        skip = {"sample id", "sample", "sample_id", "name", "sample name", "date", "time", "user"}
        for header in headers:
            hl = header.lower().strip()
            value_str = record.get(header, "").strip()
            if not value_str or hl in skip:
                continue
            try:
                value = float(value_str)
            except ValueError:
                continue

            unit, qudt_uri = self._infer_unit(hl)
            quality = QualityFlag.GOOD

            if "abs" in hl or "a260" in hl or "a280" in hl:
                if value < -0.1 or value > 5.0:
                    quality = QualityFlag.SUSPECT
                    warnings.append(f"Row {row_num}: {header} value {value} outside typical range [-0.1, 5.0]")

            if ("conc" in hl or "ng" in hl) and value < 0:
                quality = QualityFlag.SUSPECT
                warnings.append(f"Row {row_num}: {header} value {value} is negative")

            name = re.sub(r"[^a-zA-Z0-9_]", "_", header.strip()).lower()
            measurements.append(MeasurementValue(
                name=name, value=value, unit=unit, qudt_uri=qudt_uri,
                sample_id=sample_id, quality=quality,
            ))
        return measurements

    def _infer_unit(self, header: str) -> tuple[str, str | None]:
        if "abs" in header or "a260" in header or "a280" in header:
            return "AU", "http://qudt.org/vocab/unit/ABSORBANCE"
        if "ng/ul" in header or "ng/µl" in header:
            return "ng/uL", "http://qudt.org/vocab/unit/NanoGM-PER-MicroL"
        if "260/280" in header or "260_280" in header:
            return "ratio", None
        if "260/230" in header or "260_230" in header:
            return "ratio", None
        if "nm" in header or "wavelength" in header:
            return "nm", "http://qudt.org/vocab/unit/NanoM"
        return "AU", None
