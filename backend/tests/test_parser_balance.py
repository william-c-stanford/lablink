"""Tests for the Mettler Toledo balance/scale parser.

Covers:
- Happy path: parse realistic fixture -> valid ParsedResult
- All measurements correctly extracted with values, units, quality flags
- Instrument settings extracted from header metadata
- Unstable readings flagged as SUSPECT
- Error readings (---) flagged as BAD with None value
- Corrupted/empty input -> ParseError
- can_handle detection
- Edge cases: missing columns, empty rows, encoding
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.balance import BalanceParser
from app.parsers.base import FileContext, ParseError
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _ctx(data: bytes, file_name: str = "test.csv", **kwargs) -> FileContext:
    """Helper to build a FileContext for testing."""
    return FileContext(file_name=file_name, file_bytes=data, **kwargs)


@pytest.fixture
def parser() -> BalanceParser:
    return BalanceParser()


@pytest.fixture
def fixture_bytes() -> bytes:
    return (FIXTURES_DIR / "balance_mettler_toledo.csv").read_bytes()


@pytest.fixture
def fixture_ctx(fixture_bytes: bytes) -> FileContext:
    return _ctx(fixture_bytes, "balance_mettler_toledo.csv")


class TestBalanceParserHappyPath:
    """Test successful parsing of realistic Mettler Toledo CSV."""

    def test_parse_returns_parsed_result(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert isinstance(result, ParsedResult)

    def test_parser_name_and_version(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.parser_name == "balance_parser"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "balance"

    def test_file_name_preserved(self, parser: BalanceParser, fixture_bytes: bytes):
        ctx = _ctx(fixture_bytes, "my_balance_data.csv")
        result = parser.parse(ctx)
        assert result.file_name == "my_balance_data.csv"

    def test_measurement_count(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        # 12 data rows in fixture
        assert result.measurement_count == 12
        assert len(result.measurements) == 12

    def test_sample_count(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        # 12 unique sample IDs in fixture
        assert result.sample_count == 12

    def test_all_measurements_are_mass(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        for m in result.measurements:
            assert m.name == "mass"

    def test_measurement_units(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        for m in result.measurements:
            assert m.unit == "mg"

    def test_qudt_uri_mapped(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        for m in result.measurements:
            assert m.qudt_uri == "http://qudt.org/vocab/unit/MilliGM"

    def test_specific_measurement_values(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        # First row: CAL-STD-100, 100.0002 mg
        cal1 = result.measurements[0]
        assert cal1.sample_id == "CAL-STD-100"
        assert cal1.value == pytest.approx(100.0002)
        assert cal1.quality == QualityFlag.GOOD

        # Small weight: SAMPLE-006, 0.5012 mg
        small = result.measurements[7]
        assert small.sample_id == "SAMPLE-006"
        assert small.value == pytest.approx(0.5012)

    def test_tare_in_metadata(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        m = result.measurements[0]
        assert m.metadata.get("tare_weight") == pytest.approx(15.234)

    def test_gross_weight_in_metadata(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        m = result.measurements[0]
        assert m.metadata.get("gross_weight") == pytest.approx(115.2342)

    def test_weighing_mode_in_metadata(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        # SAMPLE-005 (index 6) uses Fine mode
        fine_sample = result.measurements[6]
        assert fine_sample.metadata.get("weighing_mode") == "Fine"

    def test_file_hash_populated(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.file_hash is not None
        assert len(result.file_hash) == 64  # SHA-256 hex digest


class TestBalanceParserQualityFlags:
    """Test quality flag assignment for various conditions."""

    def test_stable_reading_is_good(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.measurements[0].quality == QualityFlag.GOOD

    def test_unstable_reading_is_suspect(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        # Row 5 (index 4) SAMPLE-003 is Unstable
        unstable = result.measurements[4]
        assert unstable.sample_id == "SAMPLE-003"
        assert unstable.quality == QualityFlag.SUSPECT
        assert unstable.value == pytest.approx(78.9243)

    def test_error_reading_is_bad(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        # Row 10 (index 9) SAMPLE-007 has "---"
        error_row = result.measurements[9]
        assert error_row.sample_id == "SAMPLE-007"
        assert error_row.quality == QualityFlag.BAD
        assert error_row.value is None


class TestBalanceParserInstrumentSettings:
    """Test extraction of instrument settings from header block."""

    def test_instrument_model(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.instrument_model == "XPE205"

    def test_serial_number(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.serial_number == "B415678901"

    def test_software_version(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.software_version == "V2.30"

    def test_operator(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.operator == "Dr. Sarah Chen"

    def test_method(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.method_name == "Standard Weighing"

    def test_temperature(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.temperature_celsius == pytest.approx(22.5)

    def test_readability_in_parameters(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.parameters.get("readability") == "0.01 mg"

    def test_calibration_date_in_parameters(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.instrument_settings.parameters.get("calibration_date") == "2026-02-28"


class TestBalanceParserRawMetadata:
    """Test that raw header metadata is preserved."""

    def test_raw_metadata_keys(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert "Model" in result.raw_metadata
        assert "Serial Number" in result.raw_metadata
        assert "Operator" in result.raw_metadata

    def test_raw_metadata_values(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        assert result.raw_metadata["Instrument"] == "Mettler Toledo XPE205"


class TestBalanceParserSummary:
    """Test the summary method."""

    def test_summary_structure(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        summary = result.summary()
        assert summary["parser_name"] == "balance_parser"
        assert summary["instrument_type"] == "balance"
        assert summary["measurement_count"] == 12
        assert summary["sample_count"] == 12
        assert "parsed_at" in summary


class TestBalanceParserCorruptedInput:
    """Test graceful handling of bad input data."""

    def test_empty_bytes_raises_parse_error(self, parser: BalanceParser):
        with pytest.raises(ParseError, match="Empty file"):
            parser.parse(_ctx(b"", "empty.csv"))

    def test_whitespace_only_raises_parse_error(self, parser: BalanceParser):
        with pytest.raises(ParseError, match="Empty file"):
            parser.parse(_ctx(b"   \n  \n  ", "blank.csv"))

    def test_no_data_rows_raises_parse_error(self, parser: BalanceParser):
        data = b"Model: XPE205\nSerial Number: B415678901\n"
        with pytest.raises(ParseError, match="No data rows"):
            parser.parse(_ctx(data, "header_only.csv"))

    def test_missing_weight_column_raises_parse_error(self, parser: BalanceParser):
        data = b"Date,Time,Sample ID,Unit\n2026-03-01,09:00:00,S1,mg\n"
        with pytest.raises(ParseError, match="Missing required column"):
            parser.parse(_ctx(data, "no_weight.csv"))

    def test_non_numeric_weight_raises_parse_error(self, parser: BalanceParser):
        data = b"Net Weight,Unit\nabc,mg\n"
        with pytest.raises(ParseError, match="Cannot convert"):
            parser.parse(_ctx(data, "bad_values.csv"))

    def test_parse_error_has_suggestion(self, parser: BalanceParser):
        with pytest.raises(ParseError) as exc_info:
            parser.parse(_ctx(b"", "empty.csv"))
        assert exc_info.value.suggestion
        assert len(exc_info.value.suggestion) > 0


class TestBalanceParserEdgeCases:
    """Test edge cases and format variations."""

    def test_no_metadata_header(self, parser: BalanceParser):
        """CSV with no header metadata block — just data."""
        data = b"Net Weight,Unit,Sample ID\n50.1234,g,S1\n75.5678,g,S2\n"
        result = parser.parse(_ctx(data, "simple.csv"))
        assert result.measurement_count == 2
        assert result.measurements[0].value == pytest.approx(50.1234)
        assert result.measurements[0].unit == "g"
        assert result.measurements[0].qudt_uri == "http://qudt.org/vocab/unit/GM"

    def test_grams_unit(self, parser: BalanceParser):
        data = b"Net Weight,Unit\n1.2345,g\n"
        result = parser.parse(_ctx(data, "grams.csv"))
        assert result.measurements[0].unit == "g"
        assert result.measurements[0].qudt_uri == "http://qudt.org/vocab/unit/GM"

    def test_kg_unit(self, parser: BalanceParser):
        data = b"Net Weight,Unit\n1.5000,kg\n"
        result = parser.parse(_ctx(data, "kg.csv"))
        assert result.measurements[0].unit == "kg"
        assert result.measurements[0].qudt_uri == "http://qudt.org/vocab/unit/KiloGM"

    def test_default_unit_when_missing(self, parser: BalanceParser):
        """When no Unit column exists, default to 'g'."""
        data = b"Net Weight,Sample ID\n10.0,S1\n"
        result = parser.parse(_ctx(data, "no_unit.csv"))
        assert result.measurements[0].unit == "g"

    def test_bom_encoding(self, parser: BalanceParser):
        """Handle UTF-8 BOM from Windows exports."""
        data = b"\xef\xbb\xbfNet Weight,Unit\n99.99,mg\n"
        result = parser.parse(_ctx(data, "bom.csv"))
        assert result.measurement_count == 1
        assert result.measurements[0].value == pytest.approx(99.99)

    def test_latin1_encoding(self, parser: BalanceParser):
        """Handle Latin-1 encoded files."""
        data = "Net Weight,Unit\n50.00,mg\n".encode("latin-1")
        result = parser.parse(_ctx(data, "latin1.csv"))
        assert result.measurement_count == 1

    def test_skipped_empty_weight_rows(self, parser: BalanceParser):
        data = b"Net Weight,Unit\n10.0,g\n,g\n20.0,g\n"
        result = parser.parse(_ctx(data, "gaps.csv"))
        assert result.measurement_count == 2

    def test_alternative_column_names(self, parser: BalanceParser):
        """Parser should handle 'Mass' as an alias for 'Net Weight'."""
        data = b"Mass,Units,Sample\n25.5,mg,S1\n"
        result = parser.parse(_ctx(data, "alt_cols.csv"))
        assert result.measurement_count == 1
        assert result.measurements[0].value == pytest.approx(25.5)


class TestBalanceParserCanHandle:
    """Test file detection via can_handle."""

    def test_can_handle_csv_with_balance_keywords(self, parser: BalanceParser):
        data = b"Model: Mettler Toledo\nNet Weight,Unit\n10.0,g\n"
        assert parser.can_handle(_ctx(data, "data.csv")) is True

    def test_cannot_handle_non_csv(self, parser: BalanceParser):
        data = b"some binary data"
        assert parser.can_handle(_ctx(data, "data.xlsx")) is False

    def test_cannot_handle_csv_without_keywords(self, parser: BalanceParser):
        data = b"Wavelength,Absorbance\n260,1.5\n"
        assert parser.can_handle(_ctx(data, "data.csv")) is False

    def test_can_handle_txt_extension(self, parser: BalanceParser):
        data = b"Instrument: Balance\nNet Weight,Unit\n10.0,g\n"
        assert parser.can_handle(_ctx(data, "export.txt")) is True

    def test_can_handle_with_instrument_type_hint(self, parser: BalanceParser):
        data = b"Net Weight,Unit\n10.0,g\n"
        ctx = _ctx(data, "data.csv", instrument_type_hint="balance")
        assert parser.can_handle(ctx) is True

    def test_cannot_handle_wrong_instrument_type_hint(self, parser: BalanceParser):
        data = b"Net Weight,Unit\n10.0,g\n"
        ctx = _ctx(data, "data.csv", instrument_type_hint="hplc")
        assert parser.can_handle(ctx) is False


class TestParsedResultValidation:
    """Ensure ParsedResult from balance parser passes Pydantic validation."""

    def test_result_serializes_to_json(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        json_str = result.model_dump_json()
        assert len(json_str) > 0

    def test_result_roundtrips_through_json(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        json_str = result.model_dump_json()
        restored = ParsedResult.model_validate_json(json_str)
        assert restored.measurement_count == result.measurement_count
        assert len(restored.measurements) == len(result.measurements)
        assert restored.parser_name == result.parser_name

    def test_result_model_dump(self, parser: BalanceParser, fixture_ctx: FileContext):
        result = parser.parse(fixture_ctx)
        data = result.model_dump()
        assert data["parser_name"] == "balance_parser"
        assert data["instrument_type"] == "balance"
        assert len(data["measurements"]) == 12
