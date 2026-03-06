"""Tests for the HPLC parser.

Covers:
- Agilent ChemStation peak table parsing
- Shimadzu LabSolutions export parsing
- Extended Agilent/Shimadzu formats with more metadata
- Simple/generic peak table parsing
- Retention time, area, height, area% extraction
- Metadata extraction from file headers
- Instrument settings population
- Corrupted/empty input handling
- detect() confidence scoring
- Registry integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lablink.parsers.base import ParseError
from lablink.parsers.hplc import HPLCParser
from lablink.parsers.registry import ParserRegistry
from lablink.schemas.canonical import ParsedResult

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hplc"


@pytest.fixture
def parser() -> HPLCParser:
    return HPLCParser()


# -- Agilent Peaks Tests -------------------------------------------------------


class TestAgilentPeaksParsing:
    def test_parse_returns_parsed_result(self, parser: HPLCParser):
        """Agilent peak table produces a valid ParsedResult."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "hplc"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "hplc"

    def test_measurement_type_is_chromatography(self, parser: HPLCParser):
        """Primary measurement type is chromatography."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)
        assert result.measurement_type == "chromatography"

    def test_peak_count(self, parser: HPLCParser):
        """Agilent fixture has 5 peaks, each with RT + area + height + area% = 20 measurements."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        assert len(rt_meas) == 5

        # 5 peaks x 4 fields (RT, area, height, area%)
        assert len(result.measurements) == 20

    def test_retention_time_values(self, parser: HPLCParser):
        """Retention times are correctly parsed."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        rt_values = sorted([m.value for m in rt_meas])

        assert rt_values[0] == pytest.approx(2.145)
        assert rt_values[-1] == pytest.approx(14.567)

    def test_retention_time_units(self, parser: HPLCParser):
        """Retention time measurements have min units and QUDT URI."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        for m in rt_meas:
            assert m.unit == "min"
            assert m.qudt_uri == "http://qudt.org/vocab/unit/MIN"

    def test_area_values(self, parser: HPLCParser):
        """Peak areas are correctly parsed."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        area_meas = [m for m in result.measurements if m.measurement_type == "area"]
        assert len(area_meas) == 5

        area_values = sorted([m.value for m in area_meas])
        assert area_values[0] == pytest.approx(15234.5)
        assert area_values[-1] == pytest.approx(125678.9)

    def test_area_units(self, parser: HPLCParser):
        """Peak area measurements have mAU*s units."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        area_meas = [m for m in result.measurements if m.measurement_type == "area"]
        for m in area_meas:
            assert m.unit == "mAU*s"

    def test_height_values(self, parser: HPLCParser):
        """Peak heights are correctly parsed with mAU units."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        height_meas = [m for m in result.measurements if m.measurement_type == "height"]
        assert len(height_meas) == 5
        for m in height_meas:
            assert m.unit == "mAU"

    def test_area_percent_values(self, parser: HPLCParser):
        """Area percent values are correctly parsed and sum to ~100."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        pct_meas = [m for m in result.measurements if m.measurement_type == "area_percent"]
        assert len(pct_meas) == 5
        total = sum(m.value for m in pct_meas)
        assert total == pytest.approx(100.0, abs=0.1)
        for m in pct_meas:
            assert m.unit == "%"

    def test_instrument_settings(self, parser: HPLCParser):
        """Instrument settings populated from header metadata."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        assert result.instrument_settings is not None
        assert result.instrument_settings.method_name == "Reversed Phase C18"
        assert result.instrument_settings.column_type is not None
        assert "ZORBAX" in result.instrument_settings.column_type
        assert result.instrument_settings.wavelength_nm == pytest.approx(254.0)

    def test_instrument_model_in_extra(self, parser: HPLCParser):
        """Instrument model stored in settings extra."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)

        assert result.instrument_settings.extra.get("instrument_model") == "Agilent 1260 Infinity II"
        assert result.instrument_settings.extra.get("serial_number") == "DE12345678"

    def test_format_detected_as_agilent(self, parser: HPLCParser):
        """Run metadata identifies format as agilent."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)
        assert result.run_metadata.get("format") == "agilent_chemstation"

    def test_raw_headers_present(self, parser: HPLCParser):
        """Raw column headers are preserved."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data)
        assert result.raw_headers is not None
        assert len(result.raw_headers) >= 4


# -- Shimadzu Export Tests -----------------------------------------------------


class TestShimadzuParsing:
    def test_parse_returns_parsed_result(self, parser: HPLCParser):
        """Shimadzu export produces a valid ParsedResult."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "hplc"

    def test_peak_count(self, parser: HPLCParser):
        """Shimadzu fixture has 6 peaks."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        assert len(rt_meas) == 6

    def test_retention_time_values(self, parser: HPLCParser):
        """Shimadzu retention times are correctly parsed."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        rt_values = sorted([m.value for m in rt_meas])
        assert rt_values[0] == pytest.approx(1.234)
        assert rt_values[-1] == pytest.approx(15.678)

    def test_compound_names_used_as_sample_names(self, parser: HPLCParser):
        """Compound names from Shimadzu format are used as peak labels."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        sample_names = {m.sample_name for m in rt_meas}
        assert "Aspartate" in sample_names
        assert "Glycine" in sample_names

    def test_shimadzu_instrument_model(self, parser: HPLCParser):
        """Shimadzu instrument model is extracted."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)

        assert result.instrument_settings is not None
        assert result.instrument_settings.extra.get("instrument_model") == "Shimadzu LC-2040C"

    def test_format_detected_as_shimadzu(self, parser: HPLCParser):
        """Run metadata identifies format as shimadzu."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)
        assert result.run_metadata.get("format") == "shimadzu_labsolutions"

    def test_no_warnings_for_valid_data(self, parser: HPLCParser):
        """No warnings for clean data."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        result = parser.parse(data)
        assert len(result.warnings) == 0


# -- Extended Format Tests -----------------------------------------------------


class TestExtendedFormats:
    def test_agilent_chemstation_with_width(self, parser: HPLCParser):
        """Agilent ChemStation format with Width column parses correctly."""
        data = (FIXTURES / "agilent_chemstation.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        assert len(rt_meas) == 7

    def test_agilent_chemstation_metadata(self, parser: HPLCParser):
        """Extended Agilent format extracts flow rate and injection volume."""
        data = (FIXTURES / "agilent_chemstation.csv").read_bytes()
        result = parser.parse(data)

        settings = result.instrument_settings
        assert settings.flow_rate_ml_min == pytest.approx(1.0)
        assert settings.injection_volume_ul == pytest.approx(10.0)

    def test_shimadzu_labsolutions(self, parser: HPLCParser):
        """Shimadzu LabSolutions format parses correctly."""
        data = (FIXTURES / "shimadzu_labsolutions.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        assert len(rt_meas) == 5


# -- Simple Peak Table Tests --------------------------------------------------


class TestSimplePeakTable:
    def test_simple_peak_table_parses(self, parser: HPLCParser):
        """Simple peak table without header metadata parses correctly."""
        data = (FIXTURES / "simple_peak_table.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        assert len(rt_meas) == 3

    def test_simple_peak_table_values(self, parser: HPLCParser):
        """Simple table values are correct."""
        data = (FIXTURES / "simple_peak_table.csv").read_bytes()
        result = parser.parse(data)

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        rt_values = sorted([m.value for m in rt_meas])
        assert rt_values[0] == pytest.approx(2.34)
        assert rt_values[-1] == pytest.approx(8.90)

    def test_simple_table_generic_format(self, parser: HPLCParser):
        """Simple table detected as generic format."""
        data = (FIXTURES / "simple_peak_table.csv").read_bytes()
        result = parser.parse(data)
        assert result.run_metadata.get("format") == "generic_hplc"


# -- Error Handling Tests ------------------------------------------------------


class TestHPLCErrors:
    def test_empty_file_raises_parse_error(self, parser: HPLCParser):
        """Empty file raises ParseError."""
        with pytest.raises(ParseError, match="empty"):
            parser.parse(b"")

    def test_single_line_no_data_raises_parse_error(self, parser: HPLCParser):
        """File with only a header and no data raises ParseError."""
        with pytest.raises(ParseError):
            parser.parse(b"Retention Time (min),Area,Height\n")

    def test_no_rt_column_raises_parse_error(self, parser: HPLCParser):
        """File without retention time column raises ParseError."""
        with pytest.raises(ParseError, match="retention time"):
            parser.parse(b"Peak#,Area,Height\n1,1234,567\n")

    def test_corrupted_file_raises_parse_error(self, parser: HPLCParser):
        """Corrupted file raises ParseError (no valid peaks)."""
        data = (FIXTURES / "corrupted.csv").read_bytes()
        with pytest.raises(ParseError):
            parser.parse(data)

    def test_binary_garbage_raises_parse_error(self, parser: HPLCParser):
        """Binary garbage raises ParseError."""
        with pytest.raises(ParseError):
            parser.parse(bytes(range(256)) * 10)

    def test_parse_error_has_suggestion(self, parser: HPLCParser):
        """ParseError includes a suggestion."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse(b"")
        assert exc_info.value.suggestion is not None
        assert len(exc_info.value.suggestion) > 0


# -- detect() Confidence Tests ------------------------------------------------


class TestHPLCDetect:
    def test_agilent_detected_high_confidence(self, parser: HPLCParser):
        """Agilent peak table gets high confidence score."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        score = parser.detect(data, "agilent_peaks.csv")
        assert score >= 0.8

    def test_shimadzu_detected_high_confidence(self, parser: HPLCParser):
        """Shimadzu export gets high confidence score."""
        data = (FIXTURES / "shimadzu_export.csv").read_bytes()
        score = parser.detect(data, "shimadzu_export.csv")
        assert score >= 0.8

    def test_csv_extension_gives_base_score(self, parser: HPLCParser):
        """CSV extension alone gives base confidence."""
        score = parser.detect(b"Name,Value\nfoo,123\n", "data.csv")
        assert score >= 0.5

    def test_unknown_extension_zero_score(self, parser: HPLCParser):
        """Unknown extension with no HPLC keywords gives zero."""
        score = parser.detect(b"random data", "data.xyz")
        assert score == 0.0

    def test_rt_keywords_boost_score(self, parser: HPLCParser):
        """Content with retention time keywords boosts score."""
        content = b"Peak#,Retention Time (min),Area\n1,2.3,1234\n"
        score = parser.detect(content, "data.csv")
        assert score >= 0.8

    def test_no_filename_still_detects(self, parser: HPLCParser):
        """Detection works without filename if content has markers."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        score = parser.detect(data)
        assert score >= 0.8


# -- Registry Integration Tests -----------------------------------------------


class TestHPLCRegistry:
    def test_registered_in_registry(self):
        """HPLC parser is registered in ParserRegistry."""
        parser_cls = ParserRegistry.get("hplc")
        assert parser_cls is not None
        assert parser_cls is HPLCParser

    def test_auto_detect_agilent(self):
        """Registry auto-detection finds HPLC parser for Agilent files."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        parser_cls = ParserRegistry.detect(data, "agilent_peaks.csv")
        assert parser_cls is HPLCParser

    def test_metadata_passthrough(self, parser: HPLCParser):
        """Metadata dict is passed through to measurements."""
        data = (FIXTURES / "agilent_peaks.csv").read_bytes()
        result = parser.parse(data, metadata={"sample_id": "TEST_001"})

        rt_meas = [m for m in result.measurements if m.measurement_type == "retention_time"]
        for m in rt_meas:
            assert m.sample_id == "TEST_001"
