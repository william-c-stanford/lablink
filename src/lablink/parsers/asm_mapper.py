"""Maps allotropy ASM JSON dicts to LabLink's ParsedResult canonical schema.

Allotropy outputs Allotrope Simple Model (ASM) JSON that varies by instrument
class. This module provides:
  - asm_to_parsed_result(): top-level entry point, dispatches by manifest type
  - _map_qpcr(): handles qPCR documents (Bio-Rad CFX, QuantStudio)
  - _map_generic(): generic walker for other instrument types

ASM structure reference (Bio-Rad CFX / qPCR):
  {
    "$asm.manifest": "http://purl.allotrope.org/manifests/pcr/.../qpcr.manifest",
    "qpcr aggregate document": {
      "qpcr document": [
        {
          "measurement aggregate document": {
            "measurement document": [{
              "sample document": {
                "sample identifier": "Patient_001",
                "location identifier": "A01",
              },
              "target DNA description": "IL6",
              "processed data aggregate document": {
                "processed data document": [{
                  "cycle threshold result (qPCR)": {"value": 24.56, "unit": "(unitless)"},
                }]
              }
            }]
          }
        }
      ]
    }
  }
"""

from __future__ import annotations

from typing import Any

from lablink.schemas.canonical import InstrumentSettings, MeasurementValue, ParsedResult

# QUDT URIs for common units
_QUDT: dict[str, str] = {
    "ng/uL": "http://qudt.org/vocab/unit/NanoGM-PER-MicroL",
    "g": "http://qudt.org/vocab/unit/GM",
    "mg": "http://qudt.org/vocab/unit/MilliGM",
    "kg": "http://qudt.org/vocab/unit/KiloGM",
    "min": "http://qudt.org/vocab/unit/MIN",
    "AU": "http://qudt.org/vocab/unit/ABSORBANCE",
}

# ASM manifest URL substrings that identify instrument classes
_QPCR_MANIFEST = "qpcr"
_SPECTROPHOTOMETRY_MANIFEST = "spectrophotometry"
_PLATE_READER_MANIFEST = "plate-reader"
_LIQUID_CHROMATOGRAPHY_MANIFEST = "liquid-chromatography"


def asm_to_parsed_result(
    asm: dict[str, Any],
    parser_name: str,
    parser_version: str,
    instrument_type: str,
    warnings: list[str] | None = None,
) -> ParsedResult:
    """Translate an allotropy ASM dict to LabLink's ParsedResult.

    Dispatches to a manifest-specific mapper for best fidelity, falling back
    to a generic recursive walker for unknown manifest types.

    Args:
        asm: Allotropy output dict (from allotrope_from_file / allotrope_from_io).
        parser_name: Value for ParsedResult.parser_name.
        parser_version: Value for ParsedResult.parser_version.
        instrument_type: Value for ParsedResult.instrument_type.
        warnings: Pre-existing warning strings to include in the result.

    Returns:
        ParsedResult with measurements extracted from the ASM document.
    """
    manifest: str = asm.get("$asm.manifest", "")
    warn_list = list(warnings or [])

    if _QPCR_MANIFEST in manifest:
        measurements, settings, run_meta, mapper_warnings = _map_qpcr(asm)
        warn_list.extend(mapper_warnings)
    else:
        measurements, settings, run_meta = _map_generic(asm)

    run_meta["asm_manifest"] = manifest

    return ParsedResult(
        parser_name=parser_name,
        parser_version=parser_version,
        instrument_type=instrument_type,
        measurement_type=_infer_primary_type(measurements),
        measurements=measurements,
        instrument_settings=settings if _has_settings(settings) else None,
        sample_count=len({m.sample_id for m in measurements if m.sample_id}),
        run_metadata=run_meta,
        warnings=warn_list,
    )


# ---------------------------------------------------------------------------
# qPCR mapper (Bio-Rad CFX Maestro, AppBio QuantStudio)
# ---------------------------------------------------------------------------

def _map_qpcr(asm: dict[str, Any]) -> tuple[list[MeasurementValue], InstrumentSettings, dict, list[str]]:
    """Extract measurements from a qPCR ASM document."""
    measurements: list[MeasurementValue] = []
    settings = InstrumentSettings()
    run_meta: dict[str, Any] = {}
    warnings: list[str] = []

    agg_doc = asm.get("qpcr aggregate document", {})

    # Device / instrument info
    device_sys = agg_doc.get("device system document", {})
    if isinstance(device_sys, dict):
        settings.extra["instrument_model"] = device_sys.get("model number", "")
        settings.extra["serial_number"] = device_sys.get("equipment serial number", "")
        manufacturer = device_sys.get("product manufacturer", "")
        if manufacturer:
            run_meta["manufacturer"] = manufacturer

    # Data system info (software version, file name)
    data_sys = agg_doc.get("data system document", {})
    if isinstance(data_sys, dict):
        run_meta["software_version"] = data_sys.get("ASM converter name", "")
        run_meta["file_name"] = data_sys.get("file name", "")

    qpcr_docs = agg_doc.get("qpcr document", [])
    if not isinstance(qpcr_docs, list):
        qpcr_docs = [qpcr_docs]

    for qpcr_doc in qpcr_docs:
        if not isinstance(qpcr_doc, dict):
            continue
        meas_agg = qpcr_doc.get("measurement aggregate document", {})
        meas_docs = meas_agg.get("measurement document", [])
        if not isinstance(meas_docs, list):
            meas_docs = [meas_docs]

        for meas_doc in meas_docs:
            mv = _qpcr_meas_doc_to_mv(meas_doc)
            if mv is not None:
                measurements.append(mv)

    ct_vals = [m.value for m in measurements if m.measurement_type == "ct_value" and m.quality_flag != "missing"]
    if ct_vals:
        run_meta["summary"] = {
            "total_wells": len(measurements),
            "determined_wells": len(ct_vals),
            "undetermined_wells": len(measurements) - len(ct_vals),
            "mean_ct": round(sum(ct_vals) / len(ct_vals), 3),
            "min_ct": min(ct_vals),
            "max_ct": max(ct_vals),
        }

    # Generate warnings for high-Ct suspect wells
    for m in measurements:
        if m.quality_flag == "suspect" and m.value > 40.0:
            well_label = m.well_position or "unknown"
            warnings.append(
                f"Well {well_label}: Ct {m.value:.2f} > 40 suggests non-specific amplification."
            )

    return measurements, settings, run_meta, warnings


def _qpcr_meas_doc_to_mv(meas_doc: dict[str, Any]) -> MeasurementValue | None:
    """Convert one qPCR measurement document to a MeasurementValue."""
    sample_doc = meas_doc.get("sample document", {})
    sample_id = sample_doc.get("sample identifier")
    well_pos = sample_doc.get("location identifier") or sample_doc.get("well location identifier")
    channel = meas_doc.get("target DNA description")

    # Ct/Cq value lives in processed data aggregate document
    proc_agg = meas_doc.get("processed data aggregate document", {})
    proc_docs = proc_agg.get("processed data document", [])
    if not isinstance(proc_docs, list):
        proc_docs = [proc_docs]

    ct_value: float | None = None
    quality_flag: str | None = None

    for proc_doc in proc_docs:
        ct_qty = proc_doc.get("cycle threshold result (qPCR)") or proc_doc.get("Cq result")
        if isinstance(ct_qty, dict):
            raw_val = ct_qty.get("value")
            if raw_val is None:
                ct_value = 0.0
                quality_flag = "missing"
            else:
                try:
                    ct_value = float(raw_val)
                    if ct_value > 40.0:
                        quality_flag = "suspect"
                except (TypeError, ValueError):
                    ct_value = 0.0
                    quality_flag = "missing"
            break

    # Treat wells with no Ct data as undetermined (value=0.0, quality_flag="missing")
    # rather than skipping them, to preserve row count parity with the raw file.
    if ct_value is None:
        ct_value = 0.0
        quality_flag = "missing"

    return MeasurementValue(
        sample_id=str(sample_id) if sample_id is not None else None,
        well_position=_normalize_well(str(well_pos)) if well_pos else None,
        value=ct_value,
        unit="Ct",
        measurement_type="ct_value",
        channel=str(channel) if channel else None,
        quality_flag=quality_flag,
    )


def _normalize_well(well: str) -> str:
    """Normalize well identifier: 'A01' → 'A1', uppercased."""
    well = well.strip().upper()
    if len(well) >= 2 and well[0].isalpha() and well[1:].isdigit():
        return well[0] + str(int(well[1:]))
    return well


# ---------------------------------------------------------------------------
# Generic recursive mapper (spectrophotometry, plate reader, HPLC)
# ---------------------------------------------------------------------------

# Mapping of ASM quantity key → (measurement_type, default_unit)
_ASM_QUANTITY_KEYS: list[tuple[str, str, str]] = [
    ("absorbance", "absorbance", "AU"),
    ("fluorescence emission", "fluorescence", "RFU"),
    ("luminescence", "luminescence", "RLU"),
    ("concentration", "concentration", "ng/uL"),
    ("mass", "mass", "g"),
    ("peak area", "area", "mAU*s"),
    ("retention time", "retention_time", "min"),
    ("cycle threshold result (qPCR)", "ct_value", "Ct"),
    ("Cq result", "ct_value", "Cq"),
]


def _map_generic(asm: dict[str, Any]) -> tuple[list[MeasurementValue], InstrumentSettings, dict]:
    """Generic recursive walker for non-qPCR ASM documents."""
    measurements: list[MeasurementValue] = []
    settings = InstrumentSettings()
    run_meta: dict[str, Any] = {}

    _walk(asm, measurements, settings, run_meta)
    return measurements, settings, run_meta


def _walk(
    node: Any,
    measurements: list[MeasurementValue],
    settings: InstrumentSettings,
    run_meta: dict,
) -> None:
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "measurement document" and isinstance(val, list):
                for doc in val:
                    mv = _generic_doc_to_mv(doc, settings)
                    if mv is not None:
                        measurements.append(mv)
            elif key in ("device system document", "device document") and isinstance(val, dict):
                _extract_device(val, settings, run_meta)
            elif key == "data system document" and isinstance(val, dict):
                sw = val.get("ASM converter name") or val.get("software version")
                if sw:
                    run_meta["software_version"] = sw
            else:
                _walk(val, measurements, settings, run_meta)
    elif isinstance(node, list):
        for item in node:
            _walk(item, measurements, settings, run_meta)


def _generic_doc_to_mv(doc: dict[str, Any], settings: InstrumentSettings) -> MeasurementValue | None:
    sample_doc = doc.get("sample document", {})
    sample_id = sample_doc.get("sample identifier") or sample_doc.get("well identifier")
    sample_name = sample_doc.get("sample name")
    well_pos = sample_doc.get("location identifier") or sample_doc.get("well plate identifier")

    value_raw: float | None = None
    measurement_type = "absorbance"
    unit = "AU"
    wavelength_nm: float | None = None

    for asm_key, mtype, default_unit in _ASM_QUANTITY_KEYS:
        qty = doc.get(asm_key)
        if isinstance(qty, dict) and "value" in qty:
            try:
                value_raw = float(qty["value"])
            except (TypeError, ValueError):
                continue
            measurement_type = mtype
            unit = qty.get("unit", default_unit)
            break

    if value_raw is None:
        return None

    wl = doc.get("wavelength setting") or doc.get("detector wavelength setting")
    if isinstance(wl, dict) and "value" in wl:
        try:
            wavelength_nm = float(wl["value"])
            if settings.wavelength_nm is None:
                settings.wavelength_nm = wavelength_nm
        except (TypeError, ValueError):
            pass

    return MeasurementValue(
        sample_id=str(sample_id) if sample_id is not None else None,
        sample_name=str(sample_name) if sample_name else None,
        well_position=str(well_pos) if well_pos else None,
        value=value_raw,
        unit=unit,
        qudt_uri=_QUDT.get(unit),
        measurement_type=measurement_type,
        wavelength_nm=wavelength_nm,
    )


def _extract_device(node: dict[str, Any], settings: InstrumentSettings, run_meta: dict) -> None:
    model = node.get("device identifier") or node.get("model number")
    if model:
        settings.extra["instrument_model"] = model
    serial = node.get("equipment serial number")
    if serial:
        settings.extra["serial_number"] = serial
    sw = node.get("firmware version") or node.get("software version")
    if sw:
        run_meta["software_version"] = sw


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _infer_primary_type(measurements: list[MeasurementValue]) -> str:
    """Return the most common measurement_type, defaulting to 'absorbance'."""
    if not measurements:
        return "absorbance"
    types = [m.measurement_type for m in measurements]
    return max(set(types), key=types.count)


def _has_settings(s: InstrumentSettings) -> bool:
    return any([
        s.method_name,
        s.temperature_c,
        s.wavelength_nm,
        s.flow_rate_ml_min,
        s.injection_volume_ul,
        s.column_type,
        s.run_time_min,
        s.cycle_count,
        s.extra,
    ])
