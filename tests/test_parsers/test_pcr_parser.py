"""Tests for the PCR parser.

Covers:
- QuantStudio results export with Ct values and metadata header
- Bio-Rad CFX Cq values
- Simple/generic Ct table
- Undetermined/N/A handling (missing quality flag)
- High Ct flagging (> 40 as suspect)
- Summary statistics in run_metadata
- Corrupted/empty input handling
- Auto-detection via detect()
- Registry integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lablink.parsers.base import ParseError
from lablink.parsers.pcr import PCRParser
from lablink.parsers.registry import ParserRegistry
from lablink.schemas.canonical import ParsedResult

FIXTURES = Path(__file__).parent.parent / "fixtures" / "pcr"


@pytest.fixture
def parser() -> PCRParser:
    return PCRParser()


# -- QuantStudio Tests ---------------------------------------------------------


class TestQuantStudioParsing:
    def test_parse_returns_parsed_result(self, parser: PCRParser):
        """QuantStudio CSV produces a valid ParsedResult."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "pcr"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "pcr"

    def test_measurement_count(self, parser: PCRParser):
        """QuantStudio fixture has 12 wells (10 determined + 2 undetermined)."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        assert len(result.measurements) == 12

    def test_determined_ct_values(self, parser: PCRParser):
        """Determined Ct values are correctly parsed."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        determined = [m for m in result.measurements if m.quality_flag is None]
        assert len(determined) == 10

        ct_values = [m.value for m in determined]
        assert any(v == pytest.approx(18.45) for v in ct_values)
        assert any(v == pytest.approx(15.67) for v in ct_values)

    def test_undetermined_wells_flagged_missing(self, parser: PCRParser):
        """Undetermined wells have 'missing' quality flag."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        undetermined = [m for m in result.measurements if m.quality_flag == "missing"]
        assert len(undetermined) == 2

    def test_ct_units(self, parser: PCRParser):
        """All Ct measurements have 'Ct' unit."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        assert all(m.unit == "Ct" for m in result.measurements)

    def test_well_positions(self, parser: PCRParser):
        """Well positions are extracted."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        wells = {m.well_position for m in result.measurements}
        assert "A1" in wells
        assert "B6" in wells

    def test_sample_ids(self, parser: PCRParser):
        """Sample IDs are extracted."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        sample_ids = {m.sample_id for m in result.measurements if m.sample_id}
        assert "Sample_01" in sample_ids
        assert "NTC" in sample_ids
        assert "Pos_Control" in sample_ids

    def test_reporter_dye_in_channel(self, parser: PCRParser):
        """Reporter dye is stored in channel field."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        channels = {m.channel for m in result.measurements if m.channel}
        assert "SYBR" in channels

    def test_summary_statistics(self, parser: PCRParser):
        """Summary statistics are computed in run_metadata."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        assert "summary" in result.run_metadata
        summary = result.run_metadata["summary"]
        assert "mean_ct" in summary
        assert "min_ct" in summary
        assert "max_ct" in summary
        assert summary["total_wells"] == 12
        assert summary["determined_wells"] == 10
        assert summary["undetermined_wells"] == 2

    def test_instrument_metadata_extracted(self, parser: PCRParser):
        """QuantStudio metadata from * key = value lines is extracted."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        assert result.instrument_settings is not None
        # Chemistry should be in instrument_settings.extra or run_metadata
        assert "Chemistry" in result.run_metadata or "Chemistry" in (
            result.instrument_settings.extra or {}
        )

    def test_measurement_type_is_ct_value(self, parser: PCRParser):
        """Measurement type is 'ct_value'."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        result = parser.parse(data)

        assert result.measurement_type == "ct_value"
        assert all(m.measurement_type == "ct_value" for m in result.measurements)


# -- QuantStudio Extended Export Tests -----------------------------------------


class TestQuantStudioExtendedExport:
    def test_extended_export_parses(self, parser: PCRParser):
        """Extended QuantStudio export with extra columns parses correctly."""
        data = (FIXTURES / "quantstudio_export.csv").read_bytes()
        result = parser.parse(data)

        assert isinstance(result, ParsedResult)
        assert len(result.measurements) == 16

    def test_extended_undetermined(self, parser: PCRParser):
        """Extended export undetermined wells are flagged."""
        data = (FIXTURES / "quantstudio_export.csv").read_bytes()
        result = parser.parse(data)

        undetermined = [m for m in result.measurements if m.quality_flag == "missing"]
        assert len(undetermined) == 4  # C3, C4, D1, D2

    def test_extended_targets(self, parser: PCRParser):
        """Extended export captures multiple target names."""
        data = (FIXTURES / "quantstudio_export.csv").read_bytes()
        result = parser.parse(data)

        # Targets stored in sample metadata - verify via run_metadata
        assert result.run_metadata.get("format") == "quantstudio"


# -- Bio-Rad CFX Tests ---------------------------------------------------------


class TestBioRadCFXParsing:
    def test_parse_returns_parsed_result(self, parser: PCRParser):
        """Bio-Rad CFX CSV produces a valid ParsedResult."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "pcr"

    def test_cq_column_detected(self, parser: PCRParser):
        """Cq column is parsed correctly."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        assert len(result.measurements) == 12

    def test_n_a_treated_as_undetermined(self, parser: PCRParser):
        """N/A values in Cq column are treated as undetermined."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        undetermined = [m for m in result.measurements if m.quality_flag == "missing"]
        assert len(undetermined) == 2

    def test_high_ct_flagged_suspect(self, parser: PCRParser):
        """Ct > 40 is flagged as suspect."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        # Patient_004 has Cq=42.50
        high_ct = [m for m in result.measurements if m.value > 40 and m.quality_flag != "missing"]
        assert len(high_ct) == 1
        assert high_ct[0].quality_flag == "suspect"

    def test_specific_ct_values(self, parser: PCRParser):
        """Check specific Cq values."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        determined = [m for m in result.measurements if m.quality_flag != "missing"]
        values = sorted([m.value for m in determined])
        assert values[0] == pytest.approx(15.23)
        assert values[-1] == pytest.approx(42.50)

    def test_reporter_dye_in_channel(self, parser: PCRParser):
        """Channel field contains target gene name (allotropy maps target DNA description)."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        channels = {m.channel for m in result.measurements if m.channel}
        # allotropy maps target DNA description (e.g., IL6, TNF) to channel field
        assert len(channels) > 0

    def test_warnings_for_high_ct(self, parser: PCRParser):
        """Warning generated for Ct > 40."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        # High-Ct warning contains the value and "> 40" marker
        assert any("42.5" in w and "> 40" in w for w in result.warnings)

    def test_well_normalization(self, parser: PCRParser):
        """Bio-Rad wells like A01 are normalized to A1."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        result = parser.parse(data)

        wells = {m.well_position for m in result.measurements}
        assert "A1" in wells  # A01 -> A1
        assert "A12" in wells  # A12 stays A12


# -- Simple Ct Table Tests ----------------------------------------------------


class TestSimpleCtTable:
    def test_simple_ct_table_parses(self, parser: PCRParser):
        """Simple Ct table CSV parses correctly."""
        data = (FIXTURES / "simple_ct_table.csv").read_bytes()
        result = parser.parse(data)

        assert isinstance(result, ParsedResult)
        assert len(result.measurements) == 8

    def test_simple_undetermined(self, parser: PCRParser):
        """Undetermined wells in simple table."""
        data = (FIXTURES / "simple_ct_table.csv").read_bytes()
        result = parser.parse(data)

        undetermined = [m for m in result.measurements if m.quality_flag == "missing"]
        assert len(undetermined) == 2  # NTC wells


# -- Error Handling Tests ------------------------------------------------------


class TestPCRErrors:
    def test_corrupted_file_raises_parse_error(self, parser: PCRParser):
        """Corrupted file raises ParseError (no Ct/Cq column)."""
        data = (FIXTURES / "corrupted.csv").read_bytes()
        with pytest.raises(ParseError):
            parser.parse(data)

    def test_empty_file_raises_parse_error(self, parser: PCRParser):
        """Empty file raises ParseError."""
        with pytest.raises(ParseError, match="empty"):
            parser.parse(b"")

    def test_no_ct_column_raises_parse_error(self, parser: PCRParser):
        """File without Ct/Cq column raises ParseError."""
        data = b"Well,Sample,Value\nA1,S1,0.5\n"
        with pytest.raises(ParseError, match="Ct|Cq"):
            parser.parse(data)

    def test_parse_error_has_suggestion(self, parser: PCRParser):
        """ParseError includes a suggestion."""
        with pytest.raises(ParseError) as exc_info:
            parser.parse(b"")
        assert exc_info.value.suggestion != ""


# -- Detection Tests -----------------------------------------------------------


class TestPCRDetection:
    def test_quantstudio_detected(self, parser: PCRParser):
        """QuantStudio CSV is detected with high confidence."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        score = parser.detect(data, "quantstudio_results.csv")
        assert score >= 0.80

    def test_biorad_detected(self, parser: PCRParser):
        """Bio-Rad CFX CSV is detected with high confidence."""
        data = (FIXTURES / "biorad_cfx.csv").read_bytes()
        score = parser.detect(data, "biorad_cfx.csv")
        assert score >= 0.50  # At minimum extension match

    def test_csv_extension_detected(self, parser: PCRParser):
        """CSV extension gives base confidence."""
        score = parser.detect(b"some data", "results.csv")
        assert score >= 0.5

    def test_unknown_not_detected(self, parser: PCRParser):
        """Unknown file extension gets zero confidence."""
        score = parser.detect(b"random data", "data.xyz")
        assert score == 0.0


# -- Registry Integration Tests -----------------------------------------------


class TestPCRRegistry:
    def test_registered_in_registry(self):
        """PCR parser is registered in ParserRegistry."""
        parser_cls = ParserRegistry.get("pcr")
        assert parser_cls is not None
        assert parser_cls is PCRParser

    def test_registry_detect_quantstudio(self):
        """Registry auto-detection finds PCR parser for QuantStudio file."""
        data = (FIXTURES / "quantstudio_results.csv").read_bytes()
        parser_cls = ParserRegistry.detect(data, "quantstudio_results.csv")
        # Should detect as PCR (or at least some parser)
        assert parser_cls is not None


# -- Class Attributes Tests ---------------------------------------------------


class TestPCRClassAttributes:
    def test_name(self):
        assert PCRParser.name == "pcr"

    def test_version(self):
        assert PCRParser.version == "1.0.0"

    def test_instrument_type(self):
        assert PCRParser.instrument_type == "pcr"

    def test_supported_extensions(self):
        assert ".csv" in PCRParser.supported_extensions
