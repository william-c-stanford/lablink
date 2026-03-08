# feat: Replace Custom Parsers with Allotropy

## Overview

Replace LabLink's 5 custom instrument parsers with the [allotropy](https://github.com/Benchling-Open-Source/allotropy) library (by Benchling) where coverage exists, and keep custom implementations as fallbacks where it does not. The existing `BaseParser` ABC interface, file paths, and `ParsedResult` canonical schema are preserved — Month 1 requirements are not deviated from.

**Allotropy coverage vs. LabLink's 5 parsers:**

| Parser | Allotropy Support | Notes |
|--------|-------------------|-------|
| Spectrophotometer (NanoDrop) | `Vendor.THERMO_FISHER_NANODROP_ONE` et al. | Cary UV-Vis — NO support, keep custom |
| Plate Reader (SoftMax Pro) | `Vendor.MOLDEV_SOFTMAX_PRO` | Supported |
| Plate Reader (Gen5/BioTek) | `Vendor.AGILENT_GEN5` | Supported |
| HPLC (Agilent) | `Vendor.AGILENT_OPENLAB_CDS` | Shimadzu — NO support, keep custom |
| PCR (QuantStudio) | `Vendor.APPBIO_QUANTSTUDIO` | Supported |
| PCR (Bio-Rad CFX) | `Vendor.BIORAD_CFX_MAESTRO` | Supported |
| Balance (Mettler/Sartorius) | **NONE** | Keep custom entirely |

---

## Problem Statement

The roadmap architecture diagram (line ~33 of `plans/lablink-product-roadmap.md`) always referenced `allotropy` as the parser backend. The actual build used custom CSV parsers instead. This plan aligns implementation with the original architectural intent, gaining:

- **Broader instrument coverage**: allotropy has 40+ vendor parsers vs. our 5
- **ASM schema compliance**: allotropy outputs Allotrope Simple Model JSON, the emerging lab data standard
- **Reduced maintenance burden**: NanoDrop, Gen5, SoftMax Pro, QuantStudio, and Bio-Rad CFX parsers maintained by Benchling
- **Standards traceability**: QUDT URIs, measurement semantics, and ontology alignment handled by allotropy

---

## Technical Approach

### Adapter Pattern

All parser files keep their existing paths and implement the existing `BaseParser` ABC unchanged:

```
parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult
detect(self, file_bytes: bytes, filename: str | None = None) -> float
```

Inside `parse()`, allotropy-backed parsers:
1. Write `file_bytes` to a `tempfile.NamedTemporaryFile`
2. Call `allotrope_from_file(tmp_path, Vendor.X)`
3. Map the returned ASM dict → `ParsedResult` via a new `asm_mapper.py` module
4. Return `ParsedResult`

Custom implementations are kept for instruments allotropy does not support:
- Cary UV-Vis (within `spectrophotometer.py`)
- Shimadzu HPLC (within `hplc.py`)
- All balance formats (within `balance.py`)

### New Module: `asm_mapper.py`

A single translation layer between allotropy's ASM output and LabLink's canonical schema. This is the only net-new file.

### Month 1 Compliance

All required file paths from the Month 1 spec are preserved:

| Month 1 Required File | Status |
|-----------------------|--------|
| `src/lablink/parsers/base.py` | Unchanged |
| `src/lablink/parsers/registry.py` | Unchanged |
| `src/lablink/parsers/detector.py` | Unchanged |
| `src/lablink/parsers/spectrophotometer.py` | Modified internally |
| `src/lablink/parsers/plate_reader.py` | Modified internally |
| `src/lablink/parsers/hplc.py` | Modified internally |
| `src/lablink/parsers/pcr.py` | Modified internally |
| `src/lablink/parsers/balance.py` | Unchanged (no allotropy support) |
| `src/lablink/schemas/canonical.py` | Unchanged |

---

## Implementation Phases

### Phase 1: Dependency + Mapper (Day 1)

**Goal:** Install allotropy and build the ASM → ParsedResult mapper.

#### `pyproject.toml`

Add to `[project] dependencies`:
```toml
"allotropy>=0.1.112",
```

Allotropy requires Python ≥ 3.10; LabLink requires 3.12+. No conflict.

#### `src/lablink/parsers/asm_mapper.py` (new file)

```python
"""Maps allotropy ASM JSON dict to LabLink's ParsedResult canonical schema."""
from __future__ import annotations
from typing import Any
from lablink.schemas.canonical import ParsedResult, MeasurementValue, InstrumentSettings

def asm_to_parsed_result(
    asm: dict[str, Any],
    parser_name: str,
    parser_version: str,
    instrument_type: str,
    warnings: list[str] | None = None,
) -> ParsedResult:
    """
    Translate an allotropy ASM dict to LabLink's ParsedResult.

    ASM structure (simplified):
      {
        "$asm.manifest": "...",
        "spectrophotometry aggregate document": {
          "spectrophotometry document": [
            {
              "measurement aggregate document": {
                "measurement document": [
                  {
                    "sample document": {"sample identifier": "S1"},
                    "absorbance": {"value": 1.23, "unit": "AU"},
                    "wavelength setting": {"value": 260, "unit": "nm"},
                  }
                ]
              }
            }
          ]
        }
      }

    The exact key names vary by instrument class. This mapper handles
    the common measurement types relevant to LabLink's 5 parsers.
    """
    measurements: list[MeasurementValue] = []
    run_metadata: dict[str, Any] = {"asm_manifest": asm.get("$asm.manifest", "")}
    settings = InstrumentSettings()

    # Walk all nested "measurement document" arrays regardless of top-level key
    _extract_measurements(asm, measurements, run_metadata, settings)

    return ParsedResult(
        parser_name=parser_name,
        parser_version=parser_version,
        instrument_type=instrument_type,
        measurement_type=_infer_primary_type(measurements),
        measurements=measurements,
        instrument_settings=settings if _has_settings(settings) else None,
        sample_count=len({m.sample_id for m in measurements if m.sample_id}),
        run_metadata=run_metadata,
        warnings=warnings or [],
    )

def _extract_measurements(
    node: Any,
    out: list[MeasurementValue],
    run_metadata: dict,
    settings: InstrumentSettings,
) -> None:
    """Recursively walk ASM dict, extract measurement document arrays."""
    if isinstance(node, dict):
        for key, val in node.items():
            if key == "measurement document" and isinstance(val, list):
                for doc in val:
                    mv = _doc_to_measurement(doc, run_metadata, settings)
                    if mv:
                        out.append(mv)
            elif key in ("device system document", "device document"):
                _extract_device_info(val, settings, run_metadata)
            else:
                _extract_measurements(val, out, run_metadata, settings)
    elif isinstance(node, list):
        for item in node:
            _extract_measurements(item, out, run_metadata, settings)

def _doc_to_measurement(
    doc: dict, run_metadata: dict, settings: InstrumentSettings
) -> MeasurementValue | None:
    """Convert a single ASM measurement document to MeasurementValue."""
    # Sample info
    sample_doc = doc.get("sample document", {})
    sample_id = sample_doc.get("sample identifier") or sample_doc.get("well identifier")
    sample_name = sample_doc.get("sample name")
    well_pos = sample_doc.get("well plate identifier") or sample_doc.get("location identifier")

    # Measurement value — try common ASM quantity keys
    ASM_QUANTITY_KEYS = [
        ("absorbance", "absorbance", "AU"),
        ("fluorescence", "fluorescence", "RFU"),
        ("luminescence", "luminescence", "RLU"),
        ("concentration", "concentration", "ng/uL"),
        ("mass", "mass", "g"),
        ("Ct value", "ct_value", "Ct"),
        ("peak area", "area", "mAU*s"),
        ("retention time", "retention_time", "min"),
        ("Cq", "ct_value", "Cq"),
    ]

    value_raw = None
    measurement_type = "absorbance"
    unit = "AU"
    wavelength_nm = None
    qudt_uri = None

    for asm_key, mtype, default_unit in ASM_QUANTITY_KEYS:
        qty = doc.get(asm_key)
        if isinstance(qty, dict) and "value" in qty:
            value_raw = float(qty["value"])
            measurement_type = mtype
            unit = qty.get("unit", default_unit)
            break

    if value_raw is None:
        return None

    # Wavelength
    wl = doc.get("wavelength setting") or doc.get("detector wavelength setting")
    if isinstance(wl, dict) and "value" in wl:
        wavelength_nm = float(wl["value"])
        if settings.wavelength_nm is None:
            settings.wavelength_nm = wavelength_nm

    # QUDT URI hints
    QUDT_MAP = {
        "ng/uL": "http://qudt.org/vocab/unit/NanoGM-PER-MicroL",
        "g": "http://qudt.org/vocab/unit/GM",
        "mg": "http://qudt.org/vocab/unit/MilliGM",
        "kg": "http://qudt.org/vocab/unit/KiloGM",
        "min": "http://qudt.org/vocab/unit/MIN",
    }
    qudt_uri = QUDT_MAP.get(unit)

    return MeasurementValue(
        sample_id=str(sample_id) if sample_id is not None else None,
        sample_name=str(sample_name) if sample_name else None,
        well_position=str(well_pos) if well_pos else None,
        value=value_raw,
        unit=unit,
        qudt_uri=qudt_uri,
        measurement_type=measurement_type,
        wavelength_nm=wavelength_nm,
    )

def _extract_device_info(
    node: Any, settings: InstrumentSettings, run_metadata: dict
) -> None:
    if isinstance(node, dict):
        model = node.get("device identifier") or node.get("model number")
        if model:
            settings.extra["instrument_model"] = model
        sw = node.get("firmware version") or node.get("software version")
        if sw:
            run_metadata["software_version"] = sw
    elif isinstance(node, list):
        for item in node:
            _extract_device_info(item, settings, run_metadata)

def _infer_primary_type(measurements: list[MeasurementValue]) -> str:
    if not measurements:
        return "absorbance"
    types = [m.measurement_type for m in measurements]
    return max(set(types), key=types.count)

def _has_settings(s: InstrumentSettings) -> bool:
    return any([
        s.method_name, s.temperature_c, s.wavelength_nm,
        s.flow_rate_ml_min, s.injection_volume_ul, s.column_type,
        s.run_time_min, s.cycle_count, s.extra,
    ])
```

---

### Phase 2: Spectrophotometer + Plate Reader (Day 2)

#### `src/lablink/parsers/spectrophotometer.py`

Strategy:
- **NanoDrop**: delegate to allotropy via `Vendor.THERMO_FISHER_NANODROP_ONE` (or `NANODROP_8000`, `NANODROP_EIGHT`)
- **Cary UV-Vis**: keep custom `_parse_cary()` — no allotropy support
- **Generic fallback**: keep custom `_parse_generic()`

Detection logic and `detect()` method: unchanged.

```python
# Pseudocode showing allotropy delegation for NanoDrop branch
from allotropy.parser_factory import Vendor
from allotropy.to_allotrope import allotrope_from_io
from lablink.parsers.asm_mapper import asm_to_parsed_result
import io

def _parse_nanodrop_allotropy(self, file_bytes: bytes, metadata: dict) -> ParsedResult:
    try:
        buf = io.BytesIO(file_bytes)
        # allotrope_from_io accepts file-like objects
        asm = allotrope_from_io(buf, Vendor.THERMO_FISHER_NANODROP_ONE)
        return asm_to_parsed_result(
            asm,
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
        )
    except Exception as exc:
        # Fall back to custom parser on allotropy failure
        warnings = [f"allotropy parse failed ({exc}), using custom parser"]
        return self._parse_nanodrop_custom(file_bytes, metadata, extra_warnings=warnings)
```

Vendor enum candidates for NanoDrop:
- `Vendor.THERMO_FISHER_NANODROP_ONE`
- `Vendor.THERMO_FISHER_NANODROP_8000`
- `Vendor.THERMO_FISHER_NANODROP_EIGHT`

Auto-detect which Vendor to use based on file content markers (same detection logic as existing `_parse_nanodrop()` sub-parser). If allotropy parse fails, fall back to existing custom logic.

#### `src/lablink/parsers/plate_reader.py`

Strategy:
- **SoftMax Pro**: `Vendor.MOLDEV_SOFTMAX_PRO`
- **Gen5/BioTek**: `Vendor.AGILENT_GEN5`
- **Generic grid fallback**: keep custom

Same pattern: try allotropy, fall back to custom on failure, collect warnings.

---

### Phase 3: HPLC + PCR (Day 3)

#### `src/lablink/parsers/hplc.py`

Strategy:
- **Agilent (OpenLab CDS / ChemStation)**: `Vendor.AGILENT_OPENLAB_CDS`
- **Shimadzu (LabSolutions)**: keep custom `_parse_shimadzu()` — no allotropy support
- **Generic peak table fallback**: keep custom

HPLC ASM → ParsedResult mapping notes:
- Retention time measurements: `measurement_type = "retention_time"`, `unit = "min"`
- Peak area: `measurement_type = "area"`, `unit = "mAU*s"`
- `ParsedResult.measurement_type` should be `"retention_time"` (replaces the invalid `"chromatography"` value)
- `InstrumentSettings`: map `flow_rate`, `injection_volume`, `column_type` from ASM device document

#### `src/lablink/parsers/pcr.py`

Strategy:
- **QuantStudio**: `Vendor.APPBIO_QUANTSTUDIO`
- **Bio-Rad CFX**: `Vendor.BIORAD_CFX_MAESTRO`
- **Generic Ct fallback**: keep custom

PCR ASM → ParsedResult mapping notes:
- Ct/Cq values: `measurement_type = "ct_value"`
- Undetermined wells: allotropy may encode as `None` or special value; map to `value=0.0, quality_flag="missing"`
- `InstrumentSettings.cycle_count`: extract from ASM device document

---

### Phase 4: Balance + Tests (Day 4)

#### `src/lablink/parsers/balance.py`

**No changes.** Allotropy has zero balance parser support. The custom Mettler Toledo / Sartorius / generic implementation remains as the sole path.

#### Test Updates

The existing test files import from `app.parsers` (System B). Two options:

**Option A (Recommended):** Add integration tests in `tests/test_parsers/test_allotropy_adapters.py` that test the allotropy path specifically, using the existing fixture files. The existing System B tests continue to pass unchanged.

**Option B:** Update System B parsers to also use allotropy (requires updating `backend/app/parsers/` files to use `FileContext` adapter).

Option A is recommended because:
- Zero risk of breaking existing 1,296 tests
- Cleaner separation: unit tests (System B) vs. integration tests (allotropy)
- Month 1 spec says tests live in `tests/test_parsers/` — adding a new file there is compliant

New test file: `tests/test_parsers/test_allotropy_adapters.py`

```python
# Pseudocode
import pytest
from pathlib import Path
from lablink.parsers.spectrophotometer import SpectrophotometerParser
from lablink.parsers.plate_reader import PlateReaderParser
from lablink.parsers.hplc import HPLCParser
from lablink.parsers.pcr import PCRParser

FIXTURES = Path("tests/fixtures")

def test_nanodrop_via_allotropy():
    parser = SpectrophotometerParser()
    data = (FIXTURES / "spectrophotometer/nanodrop_sample.csv").read_bytes()
    result = parser.parse(data, {"instrument_type": "spectrophotometer"})
    assert result.parser_name == "spectrophotometer"
    assert len(result.measurements) > 0
    assert any(m.measurement_type == "absorbance" for m in result.measurements)

def test_softmax_via_allotropy():
    parser = PlateReaderParser()
    data = (FIXTURES / "plate_reader/softmax_pro_96well.csv").read_bytes()
    result = parser.parse(data, {})
    assert result.plate_layout is not None
    assert result.plate_layout["format"] in ("96-well", "384-well")

# ... one test per allotropy-backed instrument format
```

---

## Architecture Diagram Fix

Update `plans/lablink-product-roadmap.md` architecture diagram to replace:

```
│  │  - allotropy    │
│  │  - Custom CSV   │
```

With:

```
│  │  - allotropy    │  ← NanoDrop, Gen5, SoftMax Pro,
│  │  - Custom CSV   │    Agilent HPLC, QuantStudio, Bio-Rad
│  │                 │  ← Cary, Shimadzu, Balance (custom)
```

---

## Acceptance Criteria

### Functional Requirements

- [ ] `pyproject.toml` adds `allotropy>=0.1.112` as a production dependency
- [ ] `SpectrophotometerParser.parse()` uses allotropy for NanoDrop files; falls back to custom for Cary UV-Vis and unrecognized formats
- [ ] `PlateReaderParser.parse()` uses allotropy for Gen5 and SoftMax Pro files; falls back to custom grid parser for unrecognized formats
- [ ] `HPLCParser.parse()` uses allotropy for Agilent files; keeps custom parser for Shimadzu and generic peak tables
- [ ] `PCRParser.parse()` uses allotropy for QuantStudio and Bio-Rad CFX files; falls back to custom for generic Ct tables
- [ ] `BalanceParser.parse()` is unchanged (allotropy has no balance support)
- [ ] All parser files remain at their Month 1 spec paths (`src/lablink/parsers/*.py`)
- [ ] `BaseParser` ABC signature `parse(bytes, dict) -> ParsedResult` is unchanged
- [ ] `ParsedResult` and `MeasurementValue` schemas are unchanged
- [ ] `ParsedResult.measurement_type` for HPLC is corrected from `"chromatography"` to `"retention_time"`

### Non-Functional Requirements

- [ ] Allotropy parse failures do not raise unhandled exceptions; parsers fall back to custom with a warning in `ParsedResult.warnings`
- [ ] All existing 1,296 tests continue to pass (`python -m pytest tests/ -x -q`)
- [ ] New allotropy adapter tests cover all 5 allotropy-backed instrument formats
- [ ] `allotropy` temp file usage does not leak file handles (use context managers)

### Month 1 Spec Compliance

- [ ] No new parser file paths introduced that contradict Month 1 spec
- [ ] `asm_mapper.py` is the only net-new file (not required by spec, but not prohibited)
- [ ] Test fixture files in `tests/fixtures/` are unchanged

---

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Allotropy NanoDrop Vendor enum name differs from expected | Medium | Low | Test with `NANODROP_ONE`, `NANODROP_8000`, `NANODROP_EIGHT`; choose by content detection |
| Allotropy ASM output structure changes between versions | Low | Medium | Pin `allotropy>=0.1.112,<0.2.0`; test suite catches regressions |
| allotropy + BytesIO not supported (needs file path) | Medium | Low | Use `tempfile.NamedTemporaryFile` if `allotrope_from_io` fails |
| Fixture files don't match allotropy's expected format | High | Medium | Existing fixtures are synthetic — may need updated NanoDrop fixtures matching allotropy's test data format |
| Two parser systems (A + B) diverge further | Medium | Medium | Only update System A; leave System B tests untouched |

---

## Dependencies & Prerequisites

- `allotropy>=0.1.112` (MIT license, by Benchling)
- Python 3.12+ (already required; allotropy requires 3.10+)
- No new infrastructure: allotropy is pure Python, no Docker deps

---

## Files Changed

| File | Change Type | Notes |
|------|------------|-------|
| `pyproject.toml` | Modified | Add allotropy dependency |
| `src/lablink/parsers/asm_mapper.py` | **New** | ASM → ParsedResult translation layer |
| `src/lablink/parsers/spectrophotometer.py` | Modified | NanoDrop → allotropy; Cary custom kept |
| `src/lablink/parsers/plate_reader.py` | Modified | Gen5 + SoftMax → allotropy; generic kept |
| `src/lablink/parsers/hplc.py` | Modified | Agilent → allotropy; Shimadzu custom kept |
| `src/lablink/parsers/pcr.py` | Modified | QuantStudio + Bio-Rad → allotropy; generic kept |
| `src/lablink/parsers/balance.py` | Unchanged | No allotropy support |
| `tests/test_parsers/test_allotropy_adapters.py` | **New** | Integration tests for allotropy-backed parsers |
| `plans/lablink-product-roadmap.md` | Modified | Fix architecture diagram allotropy annotation |

---

## Internal References

- Current parsers: `src/lablink/parsers/spectrophotometer.py`, `plate_reader.py`, `hplc.py`, `pcr.py`, `balance.py`
- Canonical schema: `src/lablink/schemas/canonical.py`
- Parse task entry point: `src/lablink/tasks/parse_task.py`
- Roadmap architecture diagram: `plans/lablink-product-roadmap.md:33`
- Month 1 parser requirements: `plans/lablink-product-roadmap.md:928-955`

## External References

- allotropy PyPI: https://pypi.org/project/allotropy/
- allotropy GitHub: https://github.com/Benchling-Open-Source/allotropy
- Allotrope Simple Model (ASM) spec: https://www.allotrope.org/asm
- Supported instruments: `SUPPORTED_INSTRUMENT_SOFTWARE.adoc` in allotropy repo
