"""Integration tests validating all 5 parsers produce ASM-compatible ParsedResult
and handle malformed/edge-case inputs.

Tests cover:
- Happy path: realistic instrument CSV files parse into valid ParsedResult
- ASM compatibility: measurements have name, value, unit; settings captured
- Edge cases: out-of-range values, negative numbers, empty wells
- Malformed input: graceful ParseError with suggestion field
- Cross-parser consistency: all parsers share the same output structure
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.parsers.base import BaseParser, FileContext, ParseError
from app.parsers.spectrophotometer import SpectrophotometerParser
from app.parsers.plate_reader import PlateReaderParser
from app.parsers.hplc import HPLCParser
from app.parsers.pcr import PCRParser
from app.parsers.balance import BalanceParser
from app.schemas.parsed_result import (
    InstrumentSettings,
    MeasurementValue,
    ParsedResult,
    QualityFlag,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _ctx(fixture_name: str, **extra: object) -> FileContext:
    """Create a FileContext from a fixture file."""
    data = (FIXTURES / fixture_name).read_bytes()
    return FileContext(file_name=fixture_name, file_bytes=data, extra=extra)


def _ctx_raw(data: bytes, filename: str = "test.csv", **extra: object) -> FileContext:
    """Create a FileContext from raw bytes."""
    return FileContext(file_name=filename, file_bytes=data, extra=extra)


def _assert_asm_compatible(result: ParsedResult) -> None:
    """Validate ASM-compatible structure on any ParsedResult."""
    assert result.parser_name, "parser_name must be set"
    assert result.parser_version, "parser_version must be set"
    assert result.instrument_type in (
        "spectrophotometer", "plate_reader", "hplc", "pcr", "balance"
    ), f"unexpected instrument_type: {result.instrument_type}"
    assert result.file_name, "file_name must be set"
    assert result.parsed_at is not None

    assert isinstance(result.instrument_settings, InstrumentSettings)
    assert isinstance(result.measurements, list)
    assert result.measurement_count == len(result.measurements)

    for m in result.measurements:
        assert isinstance(m, MeasurementValue)
        assert m.name, f"Measurement name must be set: {m}"
        assert m.unit, f"Measurement unit must be set: {m}"
        assert isinstance(m.quality, QualityFlag)

    assert isinstance(result.warnings, list)
    for w in result.warnings:
        assert isinstance(w, str)

    # JSON round-trip
    data = result.model_dump()
    restored = ParsedResult.model_validate(data)
    assert restored.parser_name == result.parser_name
    assert len(restored.measurements) == len(result.measurements)


# ===========================================================================
# Spectrophotometer Tests
# ===========================================================================


class TestSpectrophotometerParser:
    """Integration tests for spectrophotometer (NanoDrop/Cary) parser."""

    def setup_method(self):
        self.parser = SpectrophotometerParser()

    def test_is_base_parser(self):
        assert isinstance(self.parser, BaseParser)

    def test_parser_properties(self):
        assert self.parser.name == "spectrophotometer"
        assert self.parser.version == "1.0.0"
        assert ".csv" in self.parser.supported_extensions

    def test_can_handle_by_hint(self):
        ctx = _ctx_raw(b"some data", instrument_type_hint="spectrophotometer")
        ctx.instrument_type_hint = "spectrophotometer"
        assert self.parser.can_handle(ctx)

    def test_can_handle_by_content(self):
        ctx = _ctx("nanodrop_export.csv")
        assert self.parser.can_handle(ctx)

    # --- Happy path: NanoDrop ---
    def test_nanodrop_happy_path(self):
        result = self.parser.parse(_ctx("nanodrop_export.csv"))
        _assert_asm_compatible(result)

        assert result.parser_name == "spectrophotometer"
        assert result.instrument_settings.instrument_model == "NanoDrop 2000"
        assert result.measurement_count > 0
        # 5 samples x 5 measurement columns = 25
        assert result.measurement_count == 25

        sample_ids = result.sample_ids
        assert "DNA_001" in sample_ids
        assert "RNA_001" in sample_ids

        a260_dna001 = [m for m in result.measurements
                       if m.sample_id == "DNA_001" and "a260" in m.name.lower()]
        assert len(a260_dna001) == 1
        assert a260_dna001[0].value == pytest.approx(2.145)
        assert a260_dna001[0].unit == "AU"

    # --- Happy path: Cary UV-Vis ---
    def test_cary_uvvis_happy_path(self):
        result = self.parser.parse(_ctx("cary_uvvis_scan.csv"))
        _assert_asm_compatible(result)
        assert result.measurement_count > 0
        sample_ids = result.sample_ids
        assert "Sample_A" in sample_ids
        assert "Sample_B" in sample_ids

    # --- Edge case: out-of-range values ---
    def test_edge_case_flags_out_of_range(self):
        result = self.parser.parse(_ctx("spectro_edge_case.csv"))
        _assert_asm_compatible(result)

        high_abs = [m for m in result.measurements
                    if m.sample_id == "Too_High" and "a260" in m.name]
        assert len(high_abs) == 1
        assert high_abs[0].quality == QualityFlag.SUSPECT

        neg_abs = [m for m in result.measurements
                   if m.sample_id == "Negative" and "a260" in m.name]
        assert len(neg_abs) == 1
        assert neg_abs[0].quality == QualityFlag.SUSPECT

        neg_conc = [m for m in result.measurements
                    if m.sample_id == "Negative" and "ng" in m.name]
        assert len(neg_conc) == 1
        assert neg_conc[0].quality == QualityFlag.SUSPECT

        assert result.has_warnings

    # --- Malformed input ---
    def test_malformed_raises_parse_error(self):
        with pytest.raises(ParseError) as exc_info:
            self.parser.parse(_ctx("spectro_malformed.csv"))
        assert exc_info.value.suggestion

    def test_empty_file_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(b""))

    def test_single_line_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(b"just a header\n"))

    def test_binary_garbage_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(bytes(range(256)) * 10, "garbage.csv"))

    # --- Metadata extraction ---
    def test_metadata_extracted(self):
        result = self.parser.parse(_ctx("nanodrop_export.csv"))
        assert result.raw_metadata.get("Instrument") == "NanoDrop 2000"
        assert result.raw_metadata.get("Serial Number") == "ND2K-1234"

    # --- JSON serialization ---
    def test_json_round_trip(self):
        result = self.parser.parse(_ctx("nanodrop_export.csv"))
        json_str = result.model_dump_json()
        restored = ParsedResult.model_validate_json(json_str)
        assert restored.measurement_count == result.measurement_count


# ===========================================================================
# Plate Reader Tests
# ===========================================================================


class TestPlateReaderParser:
    """Integration tests for plate reader (SoftMax Pro / Gen5) parser."""

    def setup_method(self):
        self.parser = PlateReaderParser()

    def test_is_base_parser(self):
        assert isinstance(self.parser, BaseParser)

    def test_parser_properties(self):
        assert self.parser.name == "plate_reader"
        assert self.parser.version == "1.0.0"

    # --- Happy path: 96-well plate layout ---
    def test_96well_plate_layout(self):
        result = self.parser.parse(_ctx("plate_reader_96well.csv"))
        _assert_asm_compatible(result)

        assert result.parser_name == "plate_reader"
        assert result.instrument_type == "plate_reader"
        assert result.measurement_count == 96

        wells_with_pos = [m for m in result.measurements if m.well_position]
        assert len(wells_with_pos) == 96

        a1 = [m for m in result.measurements if m.well_position == "A1"]
        assert len(a1) == 1
        assert a1[0].value == pytest.approx(0.052)

        h12 = [m for m in result.measurements if m.well_position == "H12"]
        assert len(h12) == 1
        assert h12[0].value == pytest.approx(0.049)

    # --- Happy path: tabular format ---
    def test_tabular_format(self):
        result = self.parser.parse(_ctx("plate_reader_tabular.csv"))
        _assert_asm_compatible(result)
        assert result.measurement_count > 0
        wells = [m.well_position for m in result.measurements if m.well_position]
        assert "A1" in wells

    # --- Edge case: negative and missing values ---
    def test_edge_case_negative_nan(self):
        result = self.parser.parse(_ctx("plate_reader_edge.csv"))
        _assert_asm_compatible(result)

        neg = [m for m in result.measurements if m.value is not None and m.value < 0]
        assert all(m.quality == QualityFlag.SUSPECT for m in neg)
        # NaN / N/A skipped
        assert result.has_warnings or result.measurement_count < 9

    # --- Malformed ---
    def test_empty_plate_raises_parse_error(self):
        with pytest.raises(ParseError) as exc_info:
            self.parser.parse(_ctx("plate_reader_empty.csv"))
        assert exc_info.value.suggestion

    def test_empty_bytes_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(b""))

    # --- Metadata ---
    def test_metadata_from_plate_header(self):
        result = self.parser.parse(_ctx("plate_reader_96well.csv"))
        assert result.raw_metadata.get("Instrument") == "SpectraMax M5"


# ===========================================================================
# HPLC Tests
# ===========================================================================


class TestHPLCParser:
    """Integration tests for HPLC (Agilent/Shimadzu) parser."""

    def setup_method(self):
        self.parser = HPLCParser()

    def test_is_base_parser(self):
        assert isinstance(self.parser, BaseParser)

    def test_parser_properties(self):
        assert self.parser.name == "hplc"
        assert self.parser.version == "1.0.0"

    # --- Happy path: Agilent ---
    def test_agilent_happy_path(self):
        result = self.parser.parse(_ctx("hplc_agilent.csv", sample_id="Coffee_A"))
        _assert_asm_compatible(result)

        assert result.parser_name == "hplc"
        assert result.instrument_type == "hplc"
        assert result.instrument_settings.instrument_model == "Agilent 1260 Infinity II"

        # 5 peaks x (RT + Area + Height + Area%) = 20
        assert result.measurement_count == 20

        rt = [m for m in result.measurements if "retention_time" in m.name]
        assert len(rt) == 5
        assert rt[0].unit == "min"
        assert rt[0].value == pytest.approx(1.234)

        areas = [m for m in result.measurements
                 if m.name.endswith("_area") and "pct" not in m.name]
        assert len(areas) == 5
        assert areas[0].unit == "mAU*s"

    # --- Happy path: Shimadzu ---
    def test_shimadzu_happy_path(self):
        result = self.parser.parse(_ctx("hplc_shimadzu.csv"))
        _assert_asm_compatible(result)
        rt = [m for m in result.measurements if "retention_time" in m.name]
        assert len(rt) == 5
        assert rt[0].value == pytest.approx(2.145)

    # --- Edge case: negative area ---
    def test_edge_case_negative_area(self):
        result = self.parser.parse(_ctx("hplc_edge_case.csv"))
        _assert_asm_compatible(result)

        neg_area = [m for m in result.measurements
                    if "area" in m.name and "pct" not in m.name
                    and m.value is not None and m.value < 0]
        assert len(neg_area) == 1
        assert neg_area[0].quality == QualityFlag.SUSPECT

        bad_pct = [m for m in result.measurements
                   if "area_pct" in m.name and m.value is not None and m.value > 100]
        assert len(bad_pct) == 1
        assert bad_pct[0].quality == QualityFlag.SUSPECT
        assert result.has_warnings

    # --- Malformed ---
    def test_no_retention_time_raises_parse_error(self):
        with pytest.raises(ParseError) as exc_info:
            self.parser.parse(_ctx("hplc_malformed.csv"))
        assert exc_info.value.suggestion

    def test_empty_file_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(b""))

    # --- Metadata ---
    def test_metadata_agilent(self):
        result = self.parser.parse(_ctx("hplc_agilent.csv"))
        assert result.raw_metadata.get("Instrument") == "Agilent 1260 Infinity II"


# ===========================================================================
# PCR Tests
# ===========================================================================


class TestPCRParser:
    """Integration tests for PCR (Bio-Rad/Thermo) parser."""

    def setup_method(self):
        self.parser = PCRParser()

    def test_is_base_parser(self):
        assert isinstance(self.parser, BaseParser)

    def test_parser_properties(self):
        assert self.parser.name == "pcr"
        assert self.parser.version == "1.0.0"

    # --- Happy path: Bio-Rad CFX ---
    def test_biorad_happy_path(self):
        result = self.parser.parse(_ctx("pcr_biorad.csv"))
        _assert_asm_compatible(result)

        assert result.parser_name == "pcr"
        assert result.instrument_type == "pcr"
        assert result.instrument_settings.instrument_model == "CFX96 Touch"

        # 12 Ct values + 2 undetermined NTCs = 14
        assert result.measurement_count == 14

        ct = [m for m in result.measurements if m.name.startswith("ct")]
        assert len(ct) == 14
        assert all(m.unit == "cycles" for m in ct)

        missing = [m for m in result.measurements if m.quality == QualityFlag.MISSING]
        assert len(missing) == 2

        a1 = [m for m in result.measurements if m.well_position == "A1"]
        assert len(a1) == 1
        assert a1[0].value == pytest.approx(18.45)

        gapdh = [m for m in result.measurements
                 if m.metadata.get("target") == "GAPDH" and m.value is not None]
        assert len(gapdh) == 6

    # --- Happy path: Thermo QuantStudio ---
    def test_quantstudio_happy_path(self):
        result = self.parser.parse(_ctx("pcr_quantstudio.csv"))
        _assert_asm_compatible(result)

        ct_only = [m for m in result.measurements
                   if m.name.startswith("ct") and "mean" not in m.name]
        ct_mean = [m for m in result.measurements if "ct_mean" in m.name]
        quantity = [m for m in result.measurements if "quantity" in m.name]

        assert len(ct_only) >= 14  # 14 rows (8 with values + 4 undetermined + 2 positive controls)
        assert len(ct_mean) >= 8   # rows with valid Ct have means
        assert len(quantity) >= 2   # only positive controls have quantity

    # --- Edge case: extreme Ct values ---
    def test_edge_case_extreme_ct(self):
        result = self.parser.parse(_ctx("pcr_edge_case.csv"))
        _assert_asm_compatible(result)

        normal = [m for m in result.measurements
                  if m.sample_id == "Sample_1" and m.value is not None]
        assert normal[0].quality == QualityFlag.GOOD

        high_ct = [m for m in result.measurements
                   if m.sample_id == "Sample_2" and m.value is not None]
        assert high_ct[0].quality == QualityFlag.SUSPECT

        zero_ct = [m for m in result.measurements
                   if m.sample_id == "Sample_3" and m.value is not None]
        assert zero_ct[0].quality == QualityFlag.BAD

        undet = [m for m in result.measurements if m.sample_id == "Sample_4"]
        assert undet[0].quality == QualityFlag.MISSING

        assert result.has_warnings

    # --- Malformed ---
    def test_no_ct_column_raises_parse_error(self):
        with pytest.raises(ParseError) as exc_info:
            self.parser.parse(_ctx("pcr_malformed.csv"))
        assert exc_info.value.suggestion

    def test_empty_file_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(b""))


# ===========================================================================
# Balance Tests
# ===========================================================================


class TestBalanceParser:
    """Integration tests for balance (Mettler Toledo) parser."""

    def setup_method(self):
        self.parser = BalanceParser()

    def test_is_base_parser(self):
        assert isinstance(self.parser, BaseParser)

    def test_parser_properties(self):
        assert self.parser.name == "balance"
        assert self.parser.version == "1.0.0"

    # --- Happy path: Mettler Toledo ---
    def test_mettler_happy_path(self):
        result = self.parser.parse(_ctx("balance_mettler.csv"))
        _assert_asm_compatible(result)

        assert result.parser_name == "balance"
        assert result.instrument_type == "balance"
        assert result.instrument_settings.instrument_model == "XPR205"
        assert result.instrument_settings.serial_number == "B123456789"

        mass = [m for m in result.measurements if m.name == "mass"]
        assert len(mass) == 5
        tare = [m for m in result.measurements if m.name == "tare"]
        assert len(tare) == 5

        assert all(m.unit == "g" for m in mass)
        assert all(m.qudt_uri == "http://qudt.org/vocab/unit/GM" for m in mass)

        sample_ids = result.sample_ids
        assert "Compound_A" in sample_ids

        ca = [m for m in mass if m.sample_id == "Compound_A"]
        assert ca[0].value == pytest.approx(0.01523)

    # --- Happy path: simple format ---
    def test_simple_format_with_embedded_units(self):
        result = self.parser.parse(_ctx("balance_simple.csv"))
        _assert_asm_compatible(result)
        mass = [m for m in result.measurements if m.name == "mass"]
        assert len(mass) == 4
        assert mass[0].value == pytest.approx(125.4567)

    # --- Edge case: unstable, negative, zero ---
    def test_edge_case_unstable_negative(self):
        result = self.parser.parse(_ctx("balance_edge_case.csv"))
        _assert_asm_compatible(result)

        unstable = [m for m in result.measurements
                    if m.sample_id and "Unstable" in m.sample_id]
        assert all(m.quality == QualityFlag.SUSPECT for m in unstable)

        neg = [m for m in result.measurements
               if m.sample_id == "Negative" and m.name == "mass"]
        assert len(neg) == 1
        assert neg[0].quality == QualityFlag.SUSPECT
        assert neg[0].value == pytest.approx(-0.0023)

        zero = [m for m in result.measurements
                if m.sample_id == "Zero" and m.name == "mass"]
        assert len(zero) == 1
        assert zero[0].quality == QualityFlag.GOOD
        assert zero[0].value == pytest.approx(0.0)

        assert result.has_warnings

    # --- Malformed ---
    def test_no_mass_column_raises_parse_error(self):
        with pytest.raises(ParseError) as exc_info:
            self.parser.parse(_ctx("balance_malformed.csv"))
        assert exc_info.value.suggestion

    def test_empty_file_raises_parse_error(self):
        with pytest.raises(ParseError):
            self.parser.parse(_ctx_raw(b""))


# ===========================================================================
# Cross-Parser Consistency Tests
# ===========================================================================


class TestCrossParserConsistency:
    """Validate consistent behavior across all 5 parsers."""

    PARSERS = [
        SpectrophotometerParser,
        PlateReaderParser,
        HPLCParser,
        PCRParser,
        BalanceParser,
    ]

    HAPPY_FIXTURES = {
        "spectrophotometer": "nanodrop_export.csv",
        "plate_reader": "plate_reader_96well.csv",
        "hplc": "hplc_agilent.csv",
        "pcr": "pcr_biorad.csv",
        "balance": "balance_mettler.csv",
    }

    def test_all_parsers_are_base_parser(self):
        for cls in self.PARSERS:
            parser = cls()
            assert isinstance(parser, BaseParser), f"{cls.__name__} must extend BaseParser"

    def test_all_parsers_have_required_properties(self):
        for cls in self.PARSERS:
            parser = cls()
            assert parser.name, f"{cls.__name__}.name must be non-empty"
            assert parser.version, f"{cls.__name__}.version must be non-empty"
            assert parser.supported_extensions, f"{cls.__name__} must list supported extensions"
            assert all(
                ext.startswith(".") for ext in parser.supported_extensions
            ), f"{cls.__name__}: extensions must start with '.'"

    def test_all_happy_paths_produce_valid_parsed_result(self):
        for cls in self.PARSERS:
            parser = cls()
            fixture = self.HAPPY_FIXTURES[parser.name]
            result = parser.parse(_ctx(fixture))
            _assert_asm_compatible(result)
            assert result.measurement_count > 0, f"{parser.name}: expected measurements"

    def test_all_parsers_handle_empty_bytes(self):
        for cls in self.PARSERS:
            parser = cls()
            with pytest.raises(ParseError):
                parser.parse(_ctx_raw(b""))

    def test_all_parsers_handle_single_newline(self):
        for cls in self.PARSERS:
            parser = cls()
            with pytest.raises(ParseError):
                parser.parse(_ctx_raw(b"\n"))

    def test_all_parsed_results_serializable(self):
        """All ParsedResult objects must round-trip through JSON."""
        for cls in self.PARSERS:
            parser = cls()
            fixture = self.HAPPY_FIXTURES[parser.name]
            result = parser.parse(_ctx(fixture))
            json_str = result.model_dump_json()
            restored = ParsedResult.model_validate_json(json_str)
            assert restored.parser_name == result.parser_name
            assert len(restored.measurements) == len(result.measurements)

    def test_all_parsers_set_correct_instrument_type(self):
        for cls in self.PARSERS:
            parser = cls()
            fixture = self.HAPPY_FIXTURES[parser.name]
            result = parser.parse(_ctx(fixture))
            assert result.instrument_type == parser.name

    def test_parse_error_always_has_suggestion(self):
        """All ParseError exceptions should include a suggestion for agent recovery."""
        for cls in self.PARSERS:
            parser = cls()
            try:
                parser.parse(_ctx_raw(b""))
                assert False, f"{cls.__name__} should raise ParseError on empty input"
            except ParseError as e:
                assert e.suggestion, f"{cls.__name__}: ParseError should have suggestion"

    def test_parser_registry_complete(self):
        """Verify PARSER_REGISTRY has all 5 parsers."""
        from app.parsers import PARSER_REGISTRY
        expected = {"spectrophotometer", "plate_reader", "hplc", "pcr", "balance"}
        assert set(PARSER_REGISTRY.keys()) == expected
        for name, cls in PARSER_REGISTRY.items():
            assert issubclass(cls, BaseParser)
            assert cls().name == name
