"""Tests for the plate reader parser.

Covers:
- SoftMax Pro grid format (96-well)
- Gen5 tabular format
- Generic grid format
- Corrupted/empty input handling
- Well position validation
- can_handle detection
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.parsers.base import FileContext, ParseError
from app.parsers.plate_reader import PlateReaderParser
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES = Path(__file__).parent.parent / "fixtures" / "plate_reader"


@pytest.fixture
def parser() -> PlateReaderParser:
    return PlateReaderParser()


def _ctx(file_path: Path, **kwargs) -> FileContext:
    """Helper to build FileContext from a fixture file."""
    return FileContext(
        file_name=file_path.name,
        file_bytes=file_path.read_bytes(),
        **kwargs,
    )


# -- SoftMax Pro 96-well Grid Tests --------------------------------------------


class TestSoftMaxProParsing:
    def test_parse_returns_parsed_result(self, parser: PlateReaderParser):
        """SoftMax Pro CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "plate_reader"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "plate_reader"

    def test_96_well_measurement_count(self, parser: PlateReaderParser):
        """SoftMax Pro 96-well plate has 96 measurements."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        assert result.measurement_count == 96

    def test_well_positions_span_a1_to_h12(self, parser: PlateReaderParser):
        """Well positions span A1 to H12."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        wells = {m.well_position for m in result.measurements}
        assert "A1" in wells
        assert "H12" in wells
        assert "D6" in wells

    def test_specific_values(self, parser: PlateReaderParser):
        """Check specific OD values from the fixture."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        by_well = {m.well_position: m.value for m in result.measurements}
        assert by_well["A1"] == pytest.approx(0.052)
        assert by_well["A9"] == pytest.approx(2.105)
        assert by_well["H12"] == pytest.approx(0.107)

    def test_units_are_au(self, parser: PlateReaderParser):
        """Absorbance readings have AU unit."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        assert all(m.unit == "AU" for m in result.measurements)

    def test_all_quality_good(self, parser: PlateReaderParser):
        """All positive readings have GOOD quality."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        assert all(m.quality == QualityFlag.GOOD for m in result.measurements)

    def test_file_hash_populated(self, parser: PlateReaderParser):
        """Result has SHA-256 file hash."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        assert result.file_hash is not None
        assert len(result.file_hash) == 64

    def test_raw_metadata_extracted(self, parser: PlateReaderParser):
        """Metadata from header lines is extracted."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        # The SoftMax Pro file has metadata lines before the plate grid
        assert result.raw_metadata is not None

    def test_instrument_settings(self, parser: PlateReaderParser):
        """Instrument settings are populated."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        result = parser.parse(ctx)

        assert result.instrument_settings is not None


# -- Gen5 Tabular Tests --------------------------------------------------------


class TestGen5TabularParsing:
    def test_parse_returns_parsed_result(self, parser: PlateReaderParser):
        """Gen5 tabular CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "gen5_tabular.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.instrument_type == "plate_reader"

    def test_measurement_count(self, parser: PlateReaderParser):
        """Gen5 tabular fixture has correct number of readings."""
        ctx = _ctx(FIXTURES / "gen5_tabular.csv")
        result = parser.parse(ctx)

        # 36 rows of Well,Reading,Sample — each produces 1 numeric reading + possibly sample col
        assert result.measurement_count >= 36

    def test_well_positions_valid(self, parser: PlateReaderParser):
        """All well positions match plate format."""
        ctx = _ctx(FIXTURES / "gen5_tabular.csv")
        result = parser.parse(ctx)

        well_pattern = re.compile(r"^[A-H]\d{1,2}$")
        wells = [m.well_position for m in result.measurements if m.well_position]
        for w in wells:
            assert well_pattern.match(w), f"Invalid well: {w}"

    def test_specific_values(self, parser: PlateReaderParser):
        """Check specific OD values from Gen5 fixture."""
        ctx = _ctx(FIXTURES / "gen5_tabular.csv")
        result = parser.parse(ctx)

        by_well = {m.well_position: m.value for m in result.measurements if m.well_position}
        assert by_well["A1"] == pytest.approx(0.052)
        assert by_well["A7"] == pytest.approx(2.000)
        assert by_well["B12"] == pytest.approx(1.912)


# -- Generic Grid Tests -------------------------------------------------------


class TestGenericGridParsing:
    def test_parse_returns_parsed_result(self, parser: PlateReaderParser):
        """Generic grid CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "generic_grid_96well.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.instrument_type == "plate_reader"

    def test_96_well_count(self, parser: PlateReaderParser):
        """Generic grid has 96 measurements."""
        ctx = _ctx(FIXTURES / "generic_grid_96well.csv")
        result = parser.parse(ctx)

        assert result.measurement_count == 96

    def test_well_positions(self, parser: PlateReaderParser):
        """Well positions span full 96-well plate."""
        ctx = _ctx(FIXTURES / "generic_grid_96well.csv")
        result = parser.parse(ctx)

        wells = {m.well_position for m in result.measurements}
        assert "A1" in wells
        assert "H12" in wells


# -- Error Handling Tests ------------------------------------------------------


class TestPlateReaderErrors:
    def test_corrupted_file_raises_parse_error(self, parser: PlateReaderParser):
        """Corrupted file raises ParseError via safe_parse."""
        ctx = _ctx(FIXTURES / "corrupted.csv")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_empty_file_raises_parse_error(self, parser: PlateReaderParser):
        """Empty file raises ParseError."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError, match="empty"):
            parser.safe_parse(ctx)

    def test_single_line_raises_parse_error(self, parser: PlateReaderParser):
        """File with only one line raises ParseError."""
        ctx = FileContext(file_name="single.csv", file_bytes=b"just one line\n")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_parse_error_has_suggestion(self, parser: PlateReaderParser):
        """ParseError includes a suggestion for agent recovery."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)
        assert exc_info.value.suggestion != ""

    def test_no_numeric_data_raises_parse_error(self, parser: PlateReaderParser):
        """File with text but no numeric plate data raises ParseError."""
        ctx = FileContext(
            file_name="no_nums.csv",
            file_bytes=b"Header1,Header2\nfoo,bar\nbaz,qux\n",
        )
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)


# -- can_handle Detection Tests ------------------------------------------------


class TestPlateReaderCanHandle:
    def test_softmax_detected(self, parser: PlateReaderParser):
        """SoftMax Pro CSV is detected by content."""
        ctx = _ctx(FIXTURES / "softmax_pro_96well.csv")
        assert parser.can_handle(ctx) is True

    def test_gen5_detected(self, parser: PlateReaderParser):
        """Gen5 tabular CSV is detected by content."""
        ctx = _ctx(FIXTURES / "gen5_tabular.csv")
        assert parser.can_handle(ctx) is True

    def test_instrument_type_hint(self, parser: PlateReaderParser):
        """Instrument type hint bypasses content check."""
        ctx = FileContext(
            file_name="data.xyz",
            file_bytes=b"no plate keywords",
            instrument_type_hint="plate_reader",
        )
        assert parser.can_handle(ctx) is True

    def test_unknown_not_detected(self, parser: PlateReaderParser):
        """Unknown file format is not detected."""
        ctx = FileContext(file_name="data.xyz", file_bytes=b"random data")
        assert parser.can_handle(ctx) is False
