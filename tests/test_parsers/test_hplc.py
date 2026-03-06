"""Tests for the HPLC parser.

Covers:
- Agilent ChemStation peak table parsing
- Shimadzu LabSolutions export parsing
- Retention time, area, height, area% extraction
- Metadata extraction from file headers
- Corrupted/empty input handling
- can_handle detection
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.base import FileContext, ParseError
from app.parsers.hplc import HPLCParser
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hplc"


@pytest.fixture
def parser() -> HPLCParser:
    return HPLCParser()


def _ctx(file_path: Path, **kwargs) -> FileContext:
    """Helper to build FileContext from a fixture file."""
    return FileContext(
        file_name=file_path.name,
        file_bytes=file_path.read_bytes(),
        **kwargs,
    )


# -- Agilent Peaks Tests -------------------------------------------------------


class TestAgilentPeaksParsing:
    def test_parse_returns_parsed_result(self, parser: HPLCParser):
        """Agilent peak table produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "hplc"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "hplc"

    def test_file_name_and_hash(self, parser: HPLCParser):
        """Result includes file name and SHA-256 hash."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        assert result.file_name == "agilent_peaks.csv"
        assert result.file_hash is not None
        assert len(result.file_hash) == 64

    def test_peak_count(self, parser: HPLCParser):
        """Agilent fixture has 5 peaks, each with RT + area + height + area% = 20 measurements."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        # 5 peaks x 4 fields (RT, area, height, area%)
        assert result.measurement_count == 20

    def test_retention_time_values(self, parser: HPLCParser):
        """Retention times are correctly parsed."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        rt_values = sorted([m.value for m in rt_meas])

        assert rt_values[0] == pytest.approx(2.145)
        assert rt_values[-1] == pytest.approx(14.567)

    def test_retention_time_units(self, parser: HPLCParser):
        """Retention time measurements have min units and QUDT URI."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        for m in rt_meas:
            assert m.unit == "min"
            assert m.qudt_uri == "http://qudt.org/vocab/unit/MIN"

    def test_retention_time_min_field(self, parser: HPLCParser):
        """Retention time measurements have retention_time_min set."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        for m in rt_meas:
            assert m.retention_time_min == m.value

    def test_area_values(self, parser: HPLCParser):
        """Peak areas are correctly parsed."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        area_meas = [m for m in result.measurements if m.name.endswith("_area") and "pct" not in m.name]
        assert len(area_meas) == 5

        area_values = sorted([m.value for m in area_meas])
        assert area_values[0] == pytest.approx(15234.5)
        assert area_values[-1] == pytest.approx(125678.9)

    def test_area_units(self, parser: HPLCParser):
        """Peak area measurements have mAU*s units."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        area_meas = [m for m in result.measurements if m.name.endswith("_area") and "pct" not in m.name]
        for m in area_meas:
            assert m.unit == "mAU*s"

    def test_height_values(self, parser: HPLCParser):
        """Peak heights are correctly parsed."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        height_meas = [m for m in result.measurements if "height" in m.name]
        assert len(height_meas) == 5
        for m in height_meas:
            assert m.unit == "mAU"

    def test_area_percent_values(self, parser: HPLCParser):
        """Area percent values are correctly parsed and sum to ~100."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        pct_meas = [m for m in result.measurements if "area_pct" in m.name]
        assert len(pct_meas) == 5
        total = sum(m.value for m in pct_meas)
        assert total == pytest.approx(100.0, abs=0.1)
        for m in pct_meas:
            assert m.unit == "%"

    def test_all_quality_good(self, parser: HPLCParser):
        """All measurements have GOOD quality (no negative values)."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        assert all(m.quality == QualityFlag.GOOD for m in result.measurements)

    def test_metadata_extracted(self, parser: HPLCParser):
        """Metadata from file header is extracted."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        assert "Method" in result.raw_metadata or "Column" in result.raw_metadata

    def test_instrument_settings(self, parser: HPLCParser):
        """Instrument settings are populated from metadata."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        result = parser.parse(ctx)

        assert result.instrument_settings is not None
        assert result.instrument_settings.instrument_model == "Agilent 1260 Infinity II"
        assert result.instrument_settings.serial_number == "DE12345678"

    def test_sample_id_from_extra(self, parser: HPLCParser):
        """Sample ID can be passed via extra context."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv", extra={"sample_id": "TEST_001"})
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        for m in rt_meas:
            assert m.sample_id == "TEST_001"


# -- Shimadzu Export Tests -----------------------------------------------------


class TestShimadzuParsing:
    def test_parse_returns_parsed_result(self, parser: HPLCParser):
        """Shimadzu export produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "shimadzu_export.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "hplc"

    def test_peak_count(self, parser: HPLCParser):
        """Shimadzu fixture has 6 peaks."""
        ctx = _ctx(FIXTURES / "shimadzu_export.csv")
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        assert len(rt_meas) == 6

    def test_retention_time_values(self, parser: HPLCParser):
        """Shimadzu retention times are correctly parsed."""
        ctx = _ctx(FIXTURES / "shimadzu_export.csv")
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        rt_values = sorted([m.value for m in rt_meas])
        assert rt_values[0] == pytest.approx(1.234)
        assert rt_values[-1] == pytest.approx(15.678)

    def test_shimadzu_metadata(self, parser: HPLCParser):
        """Shimadzu metadata is extracted."""
        ctx = _ctx(FIXTURES / "shimadzu_export.csv")
        result = parser.parse(ctx)

        assert result.instrument_settings.instrument_model == "Shimadzu LC-2040C"

    def test_no_warnings_for_valid_data(self, parser: HPLCParser):
        """No warnings for clean data."""
        ctx = _ctx(FIXTURES / "shimadzu_export.csv")
        result = parser.parse(ctx)

        assert len(result.warnings) == 0


# -- Error Handling Tests ------------------------------------------------------


class TestHPLCErrors:
    def test_corrupted_file_raises_parse_error(self, parser: HPLCParser):
        """Corrupted file raises ParseError."""
        ctx = _ctx(FIXTURES / "corrupted.csv")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_empty_file_raises_parse_error(self, parser: HPLCParser):
        """Empty file raises ParseError."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError, match="empty"):
            parser.safe_parse(ctx)

    def test_single_line_raises_parse_error(self, parser: HPLCParser):
        """File with only one line raises ParseError."""
        ctx = FileContext(file_name="single.csv", file_bytes=b"just one line\n")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_no_rt_column_raises_parse_error(self, parser: HPLCParser):
        """File without retention time column raises ParseError."""
        ctx = FileContext(
            file_name="no_rt.csv",
            file_bytes=b"Peak#,Area,Height\n1,1234,567\n",
        )
        with pytest.raises(ParseError, match="retention time"):
            parser.parse(ctx)

    def test_parse_error_has_suggestion(self, parser: HPLCParser):
        """ParseError includes a suggestion."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)
        assert exc_info.value.suggestion != ""

    def test_binary_garbage_raises_parse_error(self, parser: HPLCParser):
        """Binary garbage raises ParseError."""
        ctx = FileContext(file_name="garbage.bin", file_bytes=bytes(range(256)) * 10)
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)


# -- can_handle Detection Tests ------------------------------------------------


class TestHPLCCanHandle:
    def test_agilent_detected(self, parser: HPLCParser):
        """Agilent peak table is detected."""
        ctx = _ctx(FIXTURES / "agilent_peaks.csv")
        assert parser.can_handle(ctx) is True

    def test_shimadzu_detected(self, parser: HPLCParser):
        """Shimadzu export is detected."""
        ctx = _ctx(FIXTURES / "shimadzu_export.csv")
        assert parser.can_handle(ctx) is True

    def test_instrument_type_hint(self, parser: HPLCParser):
        """Instrument type hint bypasses content check."""
        ctx = FileContext(
            file_name="data.xyz",
            file_bytes=b"no hplc keywords",
            instrument_type_hint="hplc",
        )
        assert parser.can_handle(ctx) is True

    def test_unknown_not_detected(self, parser: HPLCParser):
        """Unknown file is not detected."""
        ctx = FileContext(file_name="data.xyz", file_bytes=b"random data")
        assert parser.can_handle(ctx) is False

    def test_csv_without_rt_keywords_not_detected(self, parser: HPLCParser):
        """CSV without retention time keywords is not detected."""
        ctx = FileContext(
            file_name="data.csv",
            file_bytes=b"Name,Value\nfoo,123\n",
        )
        assert parser.can_handle(ctx) is False
