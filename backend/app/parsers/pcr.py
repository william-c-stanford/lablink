"""PCR parser for Bio-Rad CFX / Thermo QuantStudio CSV exports."""

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


class PCRParser(BaseParser):
    """Parses qPCR/RT-PCR CSV data (Bio-Rad CFX, Thermo QuantStudio)."""

    name: ClassVar[str] = "pcr"
    version: ClassVar[str] = "1.0.0"
    instrument_type: ClassVar[str] = "pcr"
    supported_extensions: ClassVar[tuple[str, ...]] = (".csv", ".txt")

    _UNDETERMINED: ClassVar[frozenset[str]] = frozenset(
        {"undetermined", "n/a", "na", "nan", "", "no ct", "no cq"}
    )

    def can_handle(self, ctx: FileContext) -> bool:
        """Detect PCR files by extension + header keywords."""
        if ctx.instrument_type_hint == "pcr":
            return True
        if ctx.extension not in self.supported_extensions:
            return False
        text = ctx.text[:2000].lower()
        # Look for Ct/Cq as column headers or standalone terms (not substrings)
        has_ct = bool(re.search(r"(?:^|[,\t\s])c[tq](?:[,\t\s]|$|\s*mean|\s*value)", text, re.MULTILINE))
        has_pcr_context = any(kw in text for kw in (
            "pcr", "quantstudio", "cfx", "target name", "well position",
            "amplification", "threshold cycle",
        ))
        return has_ct or has_pcr_context

    def parse(self, ctx: FileContext) -> ParsedResult:
        """Parse PCR CSV export into canonical ParsedResult."""
        text = self._decode_text(ctx.file_bytes)
        lines = text.strip().splitlines()

        if len(lines) < 2:
            self._raise_parse_error(
                "File has fewer than 2 lines; expected header + data rows",
                ctx,
                suggestion="Ensure the PCR export contains results headers and data.",
            )

        raw_meta: dict[str, Any] = {}
        warnings: list[str] = []

        # Find data header, collecting metadata
        header_idx = self._find_data_header(lines, raw_meta)
        delimiter = "\t" if "\t" in lines[header_idx] else ","

        try:
            reader = csv.reader(lines[header_idx:], delimiter=delimiter)
            headers = [h.strip() for h in next(reader)]
        except StopIteration:
            self._raise_parse_error(
                "Could not parse CSV headers",
                ctx,
                suggestion="Verify the PCR file has a valid results table.",
            )

        col_map = self._map_columns(headers)

        if "ct" not in col_map:
            self._raise_parse_error(
                "No Ct/Cq column found in PCR data",
                ctx,
                suggestion="Expected a column named 'Ct', 'Cq', 'CT', or 'Ct Mean'.",
            )

        measurements: list[MeasurementValue] = []

        for row_num, row in enumerate(reader, start=header_idx + 2):
            try:
                if not any(cell.strip() for cell in row):
                    continue
            except csv.Error as exc:
                warnings.append(f"Row {row_num}: CSV parse error - {exc}")
                continue
            record = dict(zip(headers, row))

            well = record.get(col_map.get("well", ""), "").strip() or None
            sample_id = record.get(col_map.get("sample", ""), "").strip() or None
            target = record.get(col_map.get("target", ""), "").strip() or None
            reporter = record.get(col_map.get("reporter", ""), "").strip() or None
            task = record.get(col_map.get("task", ""), "").strip() or None

            ct_col = col_map["ct"]
            ct_str = record.get(ct_col, "").strip()

            meta: dict[str, Any] = {}
            if target:
                meta["target_name"] = target
            if reporter:
                meta["reporter_dye"] = reporter
            if task:
                meta["task"] = task

            # Build measurement name
            name_parts = ["ct"]
            if target:
                name_parts.append(target.lower().replace(" ", "_"))
            if well:
                name_parts.append(well)
            meas_name = "_".join(name_parts)

            if not ct_str or ct_str.lower() in self._UNDETERMINED:
                measurements.append(MeasurementValue(
                    name=meas_name,
                    value=None,
                    unit="Ct",
                    sample_id=sample_id,
                    well_position=well,
                    quality=QualityFlag.MISSING,
                    metadata=meta,
                ))
                continue

            try:
                ct = float(ct_str)
            except ValueError:
                warnings.append(f"Row {row_num}: invalid Ct value '{ct_str}'")
                continue

            quality = QualityFlag.GOOD
            if ct <= 0:
                quality = QualityFlag.BAD
                warnings.append(f"Row {row_num}: Ct value {ct} <= 0")
            elif ct > 40:
                quality = QualityFlag.SUSPECT
                warnings.append(f"Row {row_num}: Ct value {ct} > 40 (likely non-specific)")

            measurements.append(MeasurementValue(
                name=meas_name,
                value=ct,
                unit="Ct",
                sample_id=sample_id,
                well_position=well,
                quality=quality,
                metadata=meta,
            ))

        if not measurements:
            self._raise_parse_error(
                "No valid PCR measurements found",
                ctx,
                suggestion="Check that the file contains Ct/Cq values.",
            )

        # Summary statistics
        ct_values = [m.value for m in measurements if m.value is not None]
        if ct_values:
            raw_meta["summary"] = {
                "mean_ct": round(sum(ct_values) / len(ct_values), 2),
                "min_ct": round(min(ct_values), 2),
                "max_ct": round(max(ct_values), 2),
                "total_wells": len(measurements),
                "determined_wells": len(ct_values),
                "undetermined_wells": len(measurements) - len(ct_values),
            }

        settings = InstrumentSettings(
            instrument_model=(
                ctx.extra.get("instrument_model")
                or raw_meta.get("Instrument Name")
                or raw_meta.get("Instrument Type")
            ),
            serial_number=raw_meta.get("Serial Number"),
            software_version=raw_meta.get("Software Version"),
            method_name=(
                raw_meta.get("Experiment Name")
                or raw_meta.get("Protocol")
            ),
            parameters={
                "chemistry": raw_meta.get("Chemistry", ""),
                "passive_reference": raw_meta.get("Passive Reference", ""),
                "block_type": raw_meta.get("Block Type", ""),
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
        """Find results header row, collecting metadata from preceding lines."""
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # [Results] or [Data] section marker
            if re.match(r"^\[(?:results|data)\]", stripped, re.IGNORECASE):
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j].strip():
                        return j
                continue

            lower = stripped.lower()

            # Header row: has "well" and "ct"/"cq"
            if any(kw in lower for kw in ("well",)) and any(
                kw in lower for kw in ("ct", "cq", "cp")
            ):
                return i

            # Metadata: lines with key: value or key = value
            for sep in (":", "="):
                if sep in line:
                    key, _, val = line.partition(sep)
                    key_clean = key.strip().lstrip("* ")
                    if key_clean and not any(c.isdigit() for c in key_clean):
                        raw_meta[key_clean] = val.strip()
                    break

        return 0

    @staticmethod
    def _map_columns(headers: list[str]) -> dict[str, str]:
        """Map canonical column names to actual header strings."""
        col_map: dict[str, str] = {}
        for h in headers:
            lower = h.lower().strip()
            if lower in ("ct", "cq", "cp", "ct value", "cq value"):
                col_map["ct"] = h
            elif lower in ("ct mean", "cq mean"):
                col_map.setdefault("ct", h)  # Use mean as fallback
                col_map["ct_mean"] = h
            elif lower in ("well", "well position", "well_position"):
                col_map["well"] = h
            elif lower in ("sample", "sample name", "sample_name", "sample id"):
                col_map["sample"] = h
            elif lower in ("target", "target name", "target_name", "detector"):
                col_map["target"] = h
            elif lower in ("reporter", "dye", "fluor"):
                col_map["reporter"] = h
            elif lower in ("task", "sample type", "content"):
                col_map["task"] = h
            elif lower in ("quantity", "qty", "starting quantity"):
                col_map["quantity"] = h
        return col_map
