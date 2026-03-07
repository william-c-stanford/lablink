"""Tests for allotropy adapter integration in LabLink parsers.

These tests verify:
1. The asm_mapper module correctly translates ASM → ParsedResult
2. Each allotropy-backed parser marks run_metadata with attempt/success flags
3. Bio-Rad CFX uses the allotropy path (fixture is compatible)
4. Other parsers fall back gracefully when allotropy cannot parse the file

Tests are written BEFORE implementation and fail until parsers are updated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# asm_mapper tests — fail until src/lablink/parsers/asm_mapper.py exists
# ---------------------------------------------------------------------------


def test_asm_mapper_importable() -> None:
    """asm_mapper module must exist and be importable."""
    from lablink.parsers import asm_mapper  # noqa: F401


def test_asm_mapper_returns_parsed_result_from_cfx_asm() -> None:
    """asm_to_parsed_result converts a real Bio-Rad CFX ASM dict to ParsedResult."""
    import io
    import warnings

    warnings.filterwarnings("ignore")
    from allotropy.parser_factory import Vendor
    from allotropy.to_allotrope import allotrope_from_io

    from lablink.parsers.asm_mapper import asm_to_parsed_result
    from lablink.schemas.canonical import ParsedResult

    data = (FIXTURES / "pcr" / "biorad_cfx.csv").read_bytes()
    asm = allotrope_from_io(io.BytesIO(data), "biorad_cfx.csv", Vendor.CFXMAESTRO)

    result = asm_to_parsed_result(asm, parser_name="pcr", parser_version="1.0.0", instrument_type="pcr")

    assert isinstance(result, ParsedResult)
    assert result.parser_name == "pcr"
    assert result.instrument_type == "pcr"
    assert result.measurement_type == "ct_value"
    assert len(result.measurements) > 0
    ct_meas = result.measurements[0]
    assert ct_meas.measurement_type == "ct_value"
    assert isinstance(ct_meas.value, float)


def test_asm_mapper_infers_primary_type() -> None:
    """_infer_primary_type returns most-common measurement_type."""
    from lablink.parsers.asm_mapper import _infer_primary_type
    from lablink.schemas.canonical import MeasurementValue

    mvs = [
        MeasurementValue(value=1.0, unit="AU", measurement_type="absorbance"),
        MeasurementValue(value=2.0, unit="AU", measurement_type="absorbance"),
        MeasurementValue(value=3.0, unit="RFU", measurement_type="fluorescence"),
    ]
    assert _infer_primary_type(mvs) == "absorbance"


def test_asm_mapper_empty_measurements_defaults_absorbance() -> None:
    from lablink.parsers.asm_mapper import _infer_primary_type

    assert _infer_primary_type([]) == "absorbance"


# ---------------------------------------------------------------------------
# PCR parser — Bio-Rad CFX should use allotropy (fixture is compatible)
# ---------------------------------------------------------------------------


def test_biorad_cfx_uses_allotropy_path() -> None:
    """Bio-Rad CFX fixture is allotropy-compatible; parser should use allotropy."""
    from lablink.parsers.pcr import PCRParser

    parser = PCRParser()
    data = (FIXTURES / "pcr" / "biorad_cfx.csv").read_bytes()
    result = parser.parse(data, {})

    # Parser must mark that allotropy was attempted and succeeded
    assert result.run_metadata.get("allotropy_attempted") is True, (
        "PCR parser did not attempt allotropy — missing run_metadata['allotropy_attempted']"
    )
    assert result.run_metadata.get("allotropy_used") is True, (
        "Bio-Rad CFX fixture should parse successfully via allotropy"
    )
    assert len(result.measurements) > 0
    assert all(m.measurement_type == "ct_value" for m in result.measurements)


# ---------------------------------------------------------------------------
# PCR parser — QuantStudio falls back gracefully (missing run end time)
# ---------------------------------------------------------------------------


def test_quantstudio_fallback_graceful() -> None:
    """QuantStudio fixture triggers allotropy failure; parser falls back to custom."""
    from lablink.parsers.pcr import PCRParser

    parser = PCRParser()
    data = (FIXTURES / "pcr" / "quantstudio_results.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted") is True
    # allotropy_used may be False (fallback) — but result must still be valid
    assert len(result.measurements) > 0
    assert result.measurement_type == "ct_value"


# ---------------------------------------------------------------------------
# Spectrophotometer — NanoDrop fallback (fixture uses simplified column names)
# ---------------------------------------------------------------------------


def test_nanodrop_allotropy_attempted() -> None:
    """Spectrophotometer parser attempts allotropy for NanoDrop files."""
    from lablink.parsers.spectrophotometer import SpectrophotometerParser

    parser = SpectrophotometerParser()
    data = (FIXTURES / "spectrophotometer" / "nanodrop_sample.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted") is True
    assert len(result.measurements) > 0  # fallback must produce valid output


def test_cary_uvvis_skips_allotropy() -> None:
    """Cary UV-Vis format skips allotropy (no vendor support); uses custom only."""
    from lablink.parsers.spectrophotometer import SpectrophotometerParser

    parser = SpectrophotometerParser()
    data = (FIXTURES / "spectrophotometer" / "cary_uv_vis_scan.csv").read_bytes()
    result = parser.parse(data, {})

    # Cary goes straight to custom — allotropy_attempted should be False or absent
    assert result.run_metadata.get("allotropy_attempted", False) is False
    assert len(result.measurements) > 0


# ---------------------------------------------------------------------------
# Plate reader — SoftMax Pro and Gen5 fall back gracefully
# ---------------------------------------------------------------------------


def test_softmax_allotropy_attempted() -> None:
    from lablink.parsers.plate_reader import PlateReaderParser

    parser = PlateReaderParser()
    data = (FIXTURES / "plate_reader" / "softmax_pro_96well.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted") is True
    assert len(result.measurements) > 0


def test_gen5_allotropy_attempted() -> None:
    from lablink.parsers.plate_reader import PlateReaderParser

    parser = PlateReaderParser()
    data = (FIXTURES / "plate_reader" / "gen5_tabular.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted") is True
    assert len(result.measurements) > 0


# ---------------------------------------------------------------------------
# HPLC — Agilent fallback; measurement_type fix
# ---------------------------------------------------------------------------


def test_agilent_hplc_allotropy_attempted() -> None:
    from lablink.parsers.hplc import HPLCParser

    parser = HPLCParser()
    data = (FIXTURES / "hplc" / "agilent_chemstation.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted") is True
    assert len(result.measurements) > 0


def test_hplc_measurement_type_is_not_chromatography() -> None:
    """ParsedResult.measurement_type must not be the invalid value 'chromatography'."""
    from lablink.parsers.hplc import HPLCParser

    parser = HPLCParser()
    data = (FIXTURES / "hplc" / "agilent_chemstation.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.measurement_type != "chromatography", (
        "measurement_type 'chromatography' is not in the canonical list; "
        "use 'retention_time' instead"
    )
    assert result.measurement_type == "retention_time"


def test_shimadzu_skips_allotropy() -> None:
    """Shimadzu HPLC skips allotropy (no vendor support); uses custom only."""
    from lablink.parsers.hplc import HPLCParser

    parser = HPLCParser()
    data = (FIXTURES / "hplc" / "shimadzu_export.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted", False) is False
    assert len(result.measurements) > 0


# ---------------------------------------------------------------------------
# Balance — no allotropy support; completely custom
# ---------------------------------------------------------------------------


def test_balance_no_allotropy_attempted() -> None:
    """Balance parser never attempts allotropy (no vendor support)."""
    from lablink.parsers.balance import BalanceParser

    parser = BalanceParser()
    data = (FIXTURES / "balance" / "mettler_toledo.csv").read_bytes()
    result = parser.parse(data, {})

    assert result.run_metadata.get("allotropy_attempted", False) is False
    assert len(result.measurements) > 0


# ---------------------------------------------------------------------------
# Fallback safety: allotropy errors never crash the parser
# ---------------------------------------------------------------------------


def test_allotropy_failure_does_not_crash_parser() -> None:
    """Even if allotropy raises an unexpected error, the parser returns a valid result."""
    from unittest.mock import patch

    from lablink.parsers.pcr import PCRParser

    parser = PCRParser()
    data = (FIXTURES / "pcr" / "biorad_cfx.csv").read_bytes()

    with patch("allotropy.to_allotrope.allotrope_from_io", side_effect=RuntimeError("boom")):
        result = parser.parse(data, {})

    assert result is not None
    assert len(result.measurements) > 0
