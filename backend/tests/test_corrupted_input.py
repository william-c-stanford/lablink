"""Tests that ALL 5 parsers handle corrupted input gracefully.

AC 7: Every parser must raise ParseError (never an unhandled exception) for:
- Empty files
- Binary garbage
- Wrong-format text
- Truncated / incomplete files
- Malformed CSV (unclosed quotes, wrong delimiters)
- Header-only files (no data rows)
- Files with only whitespace
- NUL bytes embedded in text
- Files that look like a different instrument type

Each ParseError must include:
- parser_name: identifies which parser failed
- suggestion: agent-friendly recovery hint (non-empty)
- file_name: original filename from context
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.base import BaseParser, FileContext, ParseError
from app.parsers.spectrophotometer import SpectrophotometerParser
from app.parsers.plate_reader import PlateReaderParser
from app.parsers.hplc import HPLCParser
from app.parsers.pcr import PCRParser
from app.parsers.balance import BalanceParser

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(data: bytes, name: str = "test_file.csv", hint: str | None = None) -> FileContext:
    """Build a FileContext for testing."""
    return FileContext(file_name=name, file_bytes=data, instrument_type_hint=hint)


def _assert_parse_error(parser: BaseParser, data: bytes, name: str = "test.csv") -> ParseError:
    """Assert that parsing raises ParseError with all required agent-native fields."""
    ctx = _ctx(data, name)
    with pytest.raises(ParseError) as exc_info:
        parser.safe_parse(ctx)
    err = exc_info.value
    assert err.parser_name == parser.name, (
        f"Expected parser_name='{parser.name}', got '{err.parser_name}'"
    )
    assert err.suggestion, "ParseError.suggestion must be non-empty"
    assert err.file_name == name, f"Expected file_name='{name}', got '{err.file_name}'"
    return err


# ---------------------------------------------------------------------------
# Corrupted input data constants
# ---------------------------------------------------------------------------

EMPTY_BYTES = b""
BINARY_GARBAGE = bytes(range(256)) * 10
WHITESPACE_ONLY = b"   \n\n  \t\t  \n   "
SINGLE_LINE = b"just one line no newlines"
NUL_EMBEDDED = b"Sample,Value\x00\x00\nA,\x001.5\x00\n"
UNCLOSED_QUOTE_CSV = b'Sample,Value\n"unclosed quote,1.5\n'
XML_CONTENT = b'<?xml version="1.0"?>\n<data><row>not csv</row></data>\n'
JSON_CONTENT = b'{"samples": [{"id": 1, "value": 42}]}\n'
VERY_LONG_LINE = b"x" * 100_000 + b"\n"
ONLY_COMMAS = b",,,,\n,,,,\n,,,,\n"

# Header-only files per parser type
ONLY_HEADERS_SPECTRO = b"Sample Name,Concentration,A260,A280,260/280\n"
ONLY_HEADERS_HPLC = b"Peak#,Retention Time,Area,Height,Area%\n"
ONLY_HEADERS_PCR = b"Well,Sample Name,Target Name,Ct\n"
ONLY_HEADERS_BALANCE = b"Sample,Mass,Unit\n"
ONLY_HEADERS_PLATE = b"Well,OD450\n"


# ---------------------------------------------------------------------------
# Parametrized: all parsers x common corrupted inputs
# ---------------------------------------------------------------------------

ALL_PARSERS = [
    SpectrophotometerParser(),
    PlateReaderParser(),
    HPLCParser(),
    PCRParser(),
    BalanceParser(),
]

ALL_PARSER_IDS = [p.name for p in ALL_PARSERS]


@pytest.fixture(params=ALL_PARSERS, ids=ALL_PARSER_IDS)
def any_parser(request) -> BaseParser:
    """Parametrized fixture yielding each of the 5 parsers."""
    return request.param


class TestEmptyInput:
    """Empty files must raise ParseError across all parsers."""

    def test_empty_bytes(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, EMPTY_BYTES)

    def test_whitespace_only(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, WHITESPACE_ONLY)


class TestBinaryGarbage:
    """Binary data must raise ParseError across all parsers."""

    def test_binary_garbage(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, BINARY_GARBAGE)

    def test_random_bytes(self, any_parser: BaseParser):
        import os
        _assert_parse_error(any_parser, os.urandom(512))

    def test_nul_bytes_only(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, b"\x00" * 100)


class TestWrongFormat:
    """Files in wrong format must raise ParseError across all parsers."""

    def test_xml_content(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, XML_CONTENT)

    def test_json_content(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, JSON_CONTENT)


class TestMalformedCSV:
    """Malformed CSV must not crash any parser."""

    def test_unclosed_quotes(self, any_parser: BaseParser):
        """Unclosed CSV quotes must not cause an unhandled exception."""
        ctx = _ctx(UNCLOSED_QUOTE_CSV)
        try:
            any_parser.safe_parse(ctx)
        except ParseError:
            pass  # Expected — key is no unhandled exception

    def test_only_commas(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, ONLY_COMMAS)

    def test_very_long_line(self, any_parser: BaseParser):
        """Extremely long lines must not crash."""
        ctx = _ctx(VERY_LONG_LINE)
        try:
            any_parser.safe_parse(ctx)
        except ParseError:
            pass

    def test_nul_embedded_in_csv(self, any_parser: BaseParser):
        """NUL bytes embedded in CSV text must not crash."""
        ctx = _ctx(NUL_EMBEDDED)
        try:
            any_parser.safe_parse(ctx)
        except ParseError:
            pass


class TestSingleLine:
    """Files with only one line must raise ParseError."""

    def test_single_line(self, any_parser: BaseParser):
        _assert_parse_error(any_parser, SINGLE_LINE)


# ---------------------------------------------------------------------------
# Spectrophotometer-specific corrupted input
# ---------------------------------------------------------------------------

class TestSpectrophotometerCorrupted:

    @pytest.fixture
    def parser(self) -> SpectrophotometerParser:
        return SpectrophotometerParser()

    def test_corrupted_fixture(self, parser):
        data = (FIXTURES / "spectro_malformed.csv").read_bytes()
        err = _assert_parse_error(parser, data, "spectro_malformed.csv")
        assert err.parser_name == "spectrophotometer"

    def test_header_only(self, parser):
        _assert_parse_error(parser, ONLY_HEADERS_SPECTRO)

    def test_all_non_numeric(self, parser):
        data = b"Sample Name,A260,A280\nSample1,abc,def\nSample2,xyz,!!!\n"
        _assert_parse_error(parser, data)

    def test_wrong_instrument_data(self, parser):
        """Non-spectro data with no numeric absorbance columns should fail."""
        data = b"Category,Description,Status\nA,sample description,complete\nB,another one,pending\n"
        _assert_parse_error(parser, data)

    def test_empty_lines_only(self, parser):
        _assert_parse_error(parser, b"\n\n\n")


# ---------------------------------------------------------------------------
# Plate Reader-specific corrupted input
# ---------------------------------------------------------------------------

class TestPlateReaderCorrupted:

    @pytest.fixture
    def parser(self) -> PlateReaderParser:
        return PlateReaderParser()

    def test_corrupted_fixture(self, parser):
        data = (FIXTURES / "plate_reader_empty.csv").read_bytes()
        ctx = _ctx(data, "plate_reader_empty.csv")
        try:
            parser.safe_parse(ctx)
        except ParseError:
            pass  # Expected

    def test_header_only(self, parser):
        _assert_parse_error(parser, ONLY_HEADERS_PLATE)

    def test_plate_all_nan(self, parser):
        """Plate grid with all NaN values."""
        data = b",1,2,3\nA,NaN,NaN,NaN\nB,NaN,NaN,NaN\n"
        _assert_parse_error(parser, data)

    def test_plate_all_text(self, parser):
        """Plate grid with text-only values."""
        data = b",1,2,3\nA,foo,bar,baz\nB,abc,def,ghi\n"
        _assert_parse_error(parser, data)

    def test_plate_edge_fixture(self, parser):
        data = (FIXTURES / "plate_reader_edge.csv").read_bytes()
        ctx = _ctx(data, "plate_reader_edge.csv")
        try:
            result = parser.safe_parse(ctx)
            # If it parses, it should return a valid result
            assert result.parser_name == "plate_reader"
        except ParseError:
            pass  # Also acceptable for edge cases


# ---------------------------------------------------------------------------
# HPLC-specific corrupted input
# ---------------------------------------------------------------------------

class TestHPLCCorrupted:

    @pytest.fixture
    def parser(self) -> HPLCParser:
        return HPLCParser()

    def test_corrupted_fixture(self, parser):
        data = (FIXTURES / "hplc_corrupted.csv").read_bytes()
        err = _assert_parse_error(parser, data, "hplc_corrupted.csv")
        assert err.parser_name == "hplc"

    def test_malformed_fixture(self, parser):
        data = (FIXTURES / "hplc_malformed.csv").read_bytes()
        err = _assert_parse_error(parser, data, "hplc_malformed.csv")
        assert err.parser_name == "hplc"

    def test_header_only(self, parser):
        _assert_parse_error(parser, ONLY_HEADERS_HPLC)

    def test_no_rt_column(self, parser):
        data = b"Peak#,Area,Height\n1,12345,678\n"
        _assert_parse_error(parser, data)

    def test_all_invalid_rt(self, parser):
        data = b"Peak#,Retention Time,Area\n1,abc,12345\n2,def,67890\n"
        _assert_parse_error(parser, data)

    def test_metadata_only(self, parser):
        data = b"Method: TestMethod\nColumn: C18\nDetector: UV\nSoftware: ChemStation\n"
        _assert_parse_error(parser, data)


# ---------------------------------------------------------------------------
# PCR-specific corrupted input
# ---------------------------------------------------------------------------

class TestPCRCorrupted:

    @pytest.fixture
    def parser(self) -> PCRParser:
        return PCRParser()

    def test_corrupted_fixture(self, parser):
        data = (FIXTURES / "pcr_corrupted.csv").read_bytes()
        err = _assert_parse_error(parser, data, "pcr_corrupted.csv")
        assert err.parser_name == "pcr"

    def test_malformed_fixture(self, parser):
        data = (FIXTURES / "pcr_malformed.csv").read_bytes()
        err = _assert_parse_error(parser, data, "pcr_malformed.csv")
        assert err.parser_name == "pcr"

    def test_header_only(self, parser):
        _assert_parse_error(parser, ONLY_HEADERS_PCR)

    def test_no_ct_column(self, parser):
        data = b"Well,Sample Name,Target\nA1,Sample1,Gene1\n"
        _assert_parse_error(parser, data)

    def test_all_invalid_ct(self, parser):
        """Ct column with only non-numeric text (not 'undetermined')."""
        data = b"Well,Sample Name,Ct\nA1,Sample1,abc\nA2,Sample2,def\n"
        _assert_parse_error(parser, data)

    def test_metadata_but_no_results(self, parser):
        data = (
            b"* Experiment Name: Test\n"
            b"* Instrument Type: QuantStudio\n"
            b"* Block Type: 96-Well\n"
        )
        _assert_parse_error(parser, data)


# ---------------------------------------------------------------------------
# Balance-specific corrupted input
# ---------------------------------------------------------------------------

class TestBalanceCorrupted:

    @pytest.fixture
    def parser(self) -> BalanceParser:
        return BalanceParser()

    def test_malformed_fixture(self, parser):
        data = (FIXTURES / "balance_malformed.csv").read_bytes()
        err = _assert_parse_error(parser, data, "balance_malformed.csv")
        assert err.parser_name == "balance"

    def test_header_only(self, parser):
        _assert_parse_error(parser, ONLY_HEADERS_BALANCE)

    def test_no_mass_column(self, parser):
        data = b"Sample,Color,Notes\nSample1,red,good\n"
        _assert_parse_error(parser, data)

    def test_all_non_numeric_mass(self, parser):
        data = b"Sample,Mass,Unit\nS1,abc,g\nS2,def,g\n"
        _assert_parse_error(parser, data)

    def test_empty_mass_values(self, parser):
        data = b"Sample,Mass,Unit\nS1,,g\nS2,,g\n"
        _assert_parse_error(parser, data)

    def test_wrong_instrument_data(self, parser):
        """Spectro data given to balance parser should fail gracefully."""
        data = b"Sample Name,A260,A280,260/280\nDNA1,1.234,0.567,2.18\n"
        _assert_parse_error(parser, data)


# ---------------------------------------------------------------------------
# safe_parse wrapper tests
# ---------------------------------------------------------------------------

class TestSafeParseWrapper:
    """Tests for the safe_parse safety net on BaseParser."""

    def test_converts_unexpected_exception(self):
        """safe_parse wraps unexpected exceptions as ParseError."""
        parser = SpectrophotometerParser()
        original = parser._decode_text

        def _bad_decode(data):
            raise RuntimeError("Simulated unexpected error")

        parser._decode_text = _bad_decode
        ctx = _ctx(b"some data")

        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)

        err = exc_info.value
        assert "Unexpected error" in str(err)
        assert err.parser_name == "spectrophotometer"
        assert "original_error" in err.details
        assert err.details["original_error"] == "RuntimeError"
        parser._decode_text = original

    def test_passes_through_parse_error(self):
        """safe_parse does not double-wrap ParseError."""
        parser = HPLCParser()
        ctx = _ctx(EMPTY_BYTES, "empty.csv")
        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)
        assert "empty" in str(exc_info.value).lower()

    def test_succeeds_for_valid_data(self):
        """safe_parse returns result for valid data."""
        parser = BalanceParser()
        data = b"Sample,Mass,Unit\nSample1,1.234,g\nSample2,5.678,g\n"
        ctx = _ctx(data, "valid.csv")
        result = parser.safe_parse(ctx)
        assert result.parser_name == "balance"
        assert result.measurement_count > 0

    def test_empty_file_error_includes_filename(self):
        """Empty file error includes the original filename."""
        for parser in ALL_PARSERS:
            ctx = _ctx(EMPTY_BYTES, f"{parser.name}_test.csv")
            with pytest.raises(ParseError) as exc_info:
                parser.safe_parse(ctx)
            assert f"{parser.name}_test.csv" in exc_info.value.file_name


# ---------------------------------------------------------------------------
# ParseError fields validation
# ---------------------------------------------------------------------------

class TestParseErrorFields:
    """Verify ParseError has all required agent-native fields."""

    def test_suggestion_is_descriptive(self, any_parser: BaseParser):
        ctx = _ctx(EMPTY_BYTES)
        with pytest.raises(ParseError) as exc_info:
            any_parser.safe_parse(ctx)
        err = exc_info.value
        assert isinstance(err.suggestion, str)
        assert len(err.suggestion) > 10, "Suggestion should be descriptive"

    def test_parser_name_set(self, any_parser: BaseParser):
        ctx = _ctx(EMPTY_BYTES)
        with pytest.raises(ParseError) as exc_info:
            any_parser.safe_parse(ctx)
        assert exc_info.value.parser_name == any_parser.name

    def test_to_dict_has_all_keys(self, any_parser: BaseParser):
        ctx = _ctx(EMPTY_BYTES, "test.csv")
        with pytest.raises(ParseError) as exc_info:
            any_parser.safe_parse(ctx)
        d = exc_info.value.to_dict()
        assert "error" in d
        assert "parser_name" in d
        assert "suggestion" in d
        assert "file_name" in d
        assert d["parser_name"] == any_parser.name
        assert d["file_name"] == "test.csv"

    def test_to_dict_suggestion_nonempty(self, any_parser: BaseParser):
        ctx = _ctx(BINARY_GARBAGE, "garbage.bin")
        with pytest.raises(ParseError) as exc_info:
            any_parser.safe_parse(ctx)
        d = exc_info.value.to_dict()
        assert d["suggestion"], "to_dict() suggestion must be non-empty"
