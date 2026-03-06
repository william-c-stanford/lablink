"""Tests for HPLC parser — happy path, edge cases, and corrupted input."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.base import FileContext, ParseError
from app.parsers.hplc import HPLCParser
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _ctx(fixture_name: str, **kwargs) -> FileContext:
    """Create a FileContext from a fixture file."""
    path = FIXTURES / fixture_name
    return FileContext(
        file_name=fixture_name,
        file_bytes=path.read_bytes(),
        **kwargs,
    )


@pytest.fixture
def parser() -> HPLCParser:
    return HPLCParser()


# ------------------------------------------------------------------
# can_handle
# ------------------------------------------------------------------

class TestCanHandle:
    def test_handles_csv_with_hplc_hint(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv", instrument_type_hint="hplc")
        assert parser.can_handle(ctx) is True

    def test_handles_csv_by_header_detection(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        assert parser.can_handle(ctx) is True

    def test_rejects_non_csv(self, parser: HPLCParser):
        ctx = FileContext(file_name="data.xlsx", file_bytes=b"PK\x03\x04...")
        assert parser.can_handle(ctx) is False

    def test_rejects_pcr_file(self, parser: HPLCParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        # PCR data shouldn't match HPLC patterns
        assert parser.can_handle(ctx) is False


# ------------------------------------------------------------------
# parse — happy path
# ------------------------------------------------------------------

class TestParseAgilent:
    def test_produces_valid_parsed_result(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "hplc"
        assert result.parser_version == "1.0.0"
        assert result.file_name == "hplc_agilent.csv"

    def test_extracts_correct_peak_count(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        # 5 peaks x (RT + area + height + area%) = up to 20 measurements
        rt_measurements = [m for m in result.measurements if "retention_time" in m.name]
        assert len(rt_measurements) == 5

    def test_retention_times_are_correct(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        rt_values = sorted(
            m.value for m in result.measurements if "retention_time" in m.name
        )
        assert rt_values == pytest.approx([1.234, 2.891, 5.672, 8.145, 11.923])

    def test_areas_are_correct(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        areas = [m for m in result.measurements if "area" in m.name and "pct" not in m.name]
        assert len(areas) == 5
        # Largest peak should be ~312456.7
        max_area = max(a.value for a in areas)
        assert max_area == pytest.approx(312456.7)

    def test_units_are_set(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        for m in result.measurements:
            if "retention_time" in m.name:
                assert m.unit == "min"
            elif "area" in m.name and "pct" not in m.name:
                assert m.unit == "mAU*s"
            elif "height" in m.name:
                assert m.unit == "mAU"

    def test_instrument_settings(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        assert result.instrument_type == "hplc"
        assert result.instrument_settings.instrument_model == "Agilent 1260 Infinity II"
        assert result.instrument_settings.serial_number == "DE64250812"

    def test_metadata_extraction(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        assert "Column" in result.raw_metadata or "column" in str(result.instrument_settings.parameters)

    def test_quality_flags_are_good(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        for m in result.measurements:
            assert m.quality == QualityFlag.GOOD

    def test_no_warnings(self, parser: HPLCParser):
        ctx = _ctx("hplc_agilent.csv")
        result = parser.parse(ctx)

        assert len(result.warnings) == 0


class TestParseShimadzu:
    def test_produces_valid_result(self, parser: HPLCParser):
        ctx = _ctx("hplc_shimadzu.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "hplc"

    def test_correct_peak_count(self, parser: HPLCParser):
        ctx = _ctx("hplc_shimadzu.csv")
        result = parser.parse(ctx)

        rt_measurements = [m for m in result.measurements if "retention_time" in m.name]
        assert len(rt_measurements) == 5

    def test_shimadzu_metadata(self, parser: HPLCParser):
        ctx = _ctx("hplc_shimadzu.csv")
        result = parser.parse(ctx)

        assert result.instrument_type == "hplc"


# ------------------------------------------------------------------
# parse — error handling
# ------------------------------------------------------------------

class TestParseErrors:
    def test_empty_file_raises_parse_error(self, parser: HPLCParser):
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError):
            parser.parse(ctx)

    def test_single_line_raises_parse_error(self, parser: HPLCParser):
        ctx = FileContext(file_name="one_line.csv", file_bytes=b"just one line")
        with pytest.raises(ParseError):
            parser.parse(ctx)

    def test_corrupted_file_raises_parse_error(self, parser: HPLCParser):
        ctx = _ctx("hplc_corrupted.csv")
        with pytest.raises(ParseError) as exc_info:
            parser.parse(ctx)
        assert exc_info.value.suggestion  # Should have a suggestion

    def test_no_retention_time_column(self, parser: HPLCParser):
        data = b"Name,Weight,Color\nApple,150,Red\nBanana,120,Yellow\n"
        ctx = FileContext(file_name="no_rt.csv", file_bytes=data)
        with pytest.raises(ParseError, match="retention time"):
            parser.parse(ctx)

    def test_parse_error_has_suggestion(self, parser: HPLCParser):
        ctx = FileContext(file_name="bad.csv", file_bytes=b"\n\n")
        with pytest.raises(ParseError) as exc_info:
            parser.parse(ctx)
        assert exc_info.value.suggestion != ""


class TestParseEdgeCases:
    def test_negative_area_flagged_suspect(self, parser: HPLCParser):
        data = b"Retention Time,Area,Height\n5.0,-100.0,50.0\n"
        ctx = FileContext(file_name="neg_area.csv", file_bytes=data)
        result = parser.parse(ctx)

        area_meas = [m for m in result.measurements if "area" in m.name]
        assert len(area_meas) == 1
        assert area_meas[0].quality == QualityFlag.SUSPECT
        assert len(result.warnings) > 0

    def test_area_percent_outside_range(self, parser: HPLCParser):
        data = b"Retention Time,Area,Height,Area %\n5.0,1000.0,50.0,150.0\n"
        ctx = FileContext(file_name="bad_pct.csv", file_bytes=data)
        result = parser.parse(ctx)

        pct_meas = [m for m in result.measurements if "area_pct" in m.name]
        assert len(pct_meas) == 1
        assert pct_meas[0].quality == QualityFlag.SUSPECT

    def test_skips_rows_with_invalid_rt(self, parser: HPLCParser):
        data = b"Retention Time,Area\n5.0,1000.0\nBAD,2000.0\n10.0,3000.0\n"
        ctx = FileContext(file_name="mixed.csv", file_bytes=data)
        result = parser.parse(ctx)

        rt_meas = [m for m in result.measurements if "retention_time" in m.name]
        assert len(rt_meas) == 2
        assert len(result.warnings) > 0  # Warning for the bad row
