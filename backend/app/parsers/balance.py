"""Balance parser for Mettler Toledo CSV exports with mass readings."""

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


class BalanceParser(BaseParser):
    """Parses analytical/precision balance CSV data (Mettler Toledo, Sartorius)."""

    name: ClassVar[str] = "balance"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "balance"
    supported_extensions: ClassVar[tuple[str, ...]] = (".csv", ".txt")

    def can_handle(self, ctx: FileContext) -> bool:
        if ctx.instrument_type_hint == "balance":
            return True
        if ctx.extension not in self.supported_extensions:
            return False
        text = ctx.text[:500].lower()
        return any(kw in text for kw in ("mass", "weight", "balance", "tare", "net", "gross"))

    def parse(self, ctx: FileContext) -> ParsedResult:
        text = self._decode_text(ctx.file_bytes)
        lines = text.strip().splitlines()

        if len(lines) < 2:
            self._raise_parse_error(
                "File has fewer than 2 lines; expected header + data rows", ctx,
                suggestion="Ensure the balance export has a header and measurement rows.",
            )

        raw_meta: dict[str, Any] = {}
        measurements: list[MeasurementValue] = []
        warnings: list[str] = []

        header_idx = self._find_data_header(lines, raw_meta)
        delimiter = "\t" if "\t" in lines[header_idx] else (";" if ";" in lines[header_idx] else ",")

        try:
            reader = csv.reader(lines[header_idx:], delimiter=delimiter)
            headers = [h.strip() for h in next(reader)]
        except StopIteration:
            self._raise_parse_error("Could not parse CSV headers", ctx,
                                    suggestion="Verify the balance file is a valid CSV.")

        col_map = self._map_columns(headers)

        if "mass" not in col_map and "net" not in col_map and "value" not in col_map:
            self._raise_parse_error(
                "No mass/weight/value column found in balance data", ctx,
                suggestion="Expected a column named 'Mass', 'Weight', 'Net', 'Value', or 'Gross'.",
            )

        for row_num, row in enumerate(reader, start=header_idx + 2):
            try:
                if not any(cell.strip() for cell in row):
                    continue
            except csv.Error as exc:
                warnings.append(f"Row {row_num}: CSV parse error - {exc}")
                continue
            record = dict(zip(headers, row))

            sample_id = None
            if "sample" in col_map:
                sample_id = record.get(col_map["sample"], "").strip() or None

            mass_col = col_map.get("net") or col_map.get("mass") or col_map.get("value")
            mass_str = record.get(mass_col, "").strip() if mass_col else ""
            mass_str, detected_unit = self._parse_value_with_unit(mass_str)

            if not mass_str:
                continue
            try:
                mass = float(mass_str)
            except ValueError:
                warnings.append(f"Row {row_num}: invalid mass value '{mass_str}'")
                continue

            unit = detected_unit or self._get_unit(record, col_map, raw_meta, ctx.extra)
            qudt_uri = self._unit_to_qudt(unit)
            quality = QualityFlag.GOOD

            if "stability" in col_map:
                stab = record.get(col_map["stability"], "").strip().lower()
                if stab in ("unstable", "u", "d", "dynamic"):
                    quality = QualityFlag.SUSPECT
                    warnings.append(f"Row {row_num}: unstable reading")

            if mass < 0:
                quality = QualityFlag.SUSPECT
                warnings.append(f"Row {row_num}: negative mass {mass} {unit}")

            measurements.append(MeasurementValue(
                name="mass", value=mass, unit=unit, qudt_uri=qudt_uri,
                sample_id=sample_id, quality=quality,
            ))

            if "tare" in col_map:
                tare_str = record.get(col_map["tare"], "").strip()
                tare_str, _ = self._parse_value_with_unit(tare_str)
                if tare_str:
                    try:
                        measurements.append(MeasurementValue(
                            name="tare", value=float(tare_str), unit=unit,
                            qudt_uri=qudt_uri, sample_id=sample_id,
                            quality=QualityFlag.GOOD,
                        ))
                    except ValueError:
                        pass

        if not measurements:
            self._raise_parse_error("No valid mass measurements found", ctx,
                                    suggestion="Check that the file contains numeric mass/weight values.")

        settings = InstrumentSettings(
            instrument_model=ctx.extra.get("instrument_model") or raw_meta.get("Model") or raw_meta.get("Balance"),
            serial_number=raw_meta.get("Serial Number") or raw_meta.get("S/N"),
            software_version=raw_meta.get("Software Version"),
            method_name=raw_meta.get("Method"),
            parameters={"unit": unit if measurements else "g",
                        "readability": raw_meta.get("Readability", "")},
        )

        return self._make_result(ctx, measurements=measurements,
                                 instrument_settings=settings, warnings=warnings,
                                 raw_metadata=raw_meta)

    def _find_data_header(self, lines: list[str], raw_meta: dict[str, Any]) -> int:
        for i, line in enumerate(lines):
            lower = line.lower()
            if any(kw in lower for kw in ("mass", "weight", "net", "gross", "value", "sample")):
                return i
            if ":" in line:
                key, _, val = line.partition(":")
                if not any(c.isdigit() for c in key):
                    raw_meta[key.strip()] = val.strip()
        return 0

    def _map_columns(self, headers: list[str]) -> dict[str, str]:
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
            elif lower in ("sample", "sample id", "sample_id", "id", "sample name"):
                col_map["sample"] = h
            elif lower in ("stability", "stable", "status"):
                col_map["stability"] = h
        return col_map

    def _parse_value_with_unit(self, value_str: str) -> tuple[str, str | None]:
        match = re.match(r"^\s*([-+]?\d*\.?\d+)\s*(mg|g|kg|lb|oz|ct|gr)?\s*$", value_str, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
        return value_str, None

    def _get_unit(self, record: dict, col_map: dict, raw_meta: dict, extra: dict) -> str:
        if "unit_col" in col_map:
            unit = record.get(col_map["unit_col"], "").strip()
            if unit:
                return unit
        if "unit" in extra:
            return extra["unit"]
        if "Unit" in raw_meta:
            return raw_meta["Unit"]
        return "g"

    def _unit_to_qudt(self, unit: str) -> str | None:
        return {
            "g": "http://qudt.org/vocab/unit/GM",
            "mg": "http://qudt.org/vocab/unit/MilliGM",
            "kg": "http://qudt.org/vocab/unit/KiloGM",
            "lb": "http://qudt.org/vocab/unit/LB",
            "oz": "http://qudt.org/vocab/unit/OZ",
        }.get(unit.lower())
