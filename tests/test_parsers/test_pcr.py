"""Tests for the PCR parser.

Covers:
- QuantStudio results export with Ct values
- Bio-Rad CFX Cq values
- Undetermined/N/A handling (MISSING quality)
- High Ct flagging (> 40 as SUSPECT)
- Summary statistics
- Corrupted/empty input handling
- can_handle detection
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.base import FileContext, ParseError
from app.parsers.pcr import PCRParser
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES = Path(__file__).parent.parent / "fixtures" / "pcr"


@pytest.fixture
def parser() -> PCRParser:
    return PCRParser()


def _ctx(file_path: Path, **kwargs) -> FileContext:
    """Helper to build FileContext from a fixture file."""
    return FileContext(
        file_name=file_path.name,
        file_bytes=file_path.read_bytes(),
        **kwargs,
    )


# -- QuantStudio Tests ---------------------------------------------------------


class TestQuantStudioParsing:
    def test_parse_returns_parsed_result(self, parser: PCRParser):
        """QuantStudio CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "pcr"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "pcr"

    def test_file_name_and_hash(self, parser: PCRParser):
        """Result includes file name and SHA-256 hash."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        assert result.file_name == "quantstudio_results.csv"
        assert result.file_hash is not None
        assert len(result.file_hash) == 64

    def test_measurement_count(self, parser: PCRParser):
        """QuantStudio fixture has 12 wells (10 determined + 2 undetermined)."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        assert result.measurement_count == 12

    def test_determined_ct_values(self, parser: PCRParser):
        """Determined Ct values are correctly parsed."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        determined = [m for m in result.measurements if m.value is not None]
        assert len(determined) == 10

        # Check specific values
        ct_values = [m.value for m in determined]
        assert any(v == pytest.approx(18.45) for v in ct_values)
        assert any(v == pytest.approx(15.67) for v in ct_values)

    def test_undetermined_wells_are_missing(self, parser: PCRParser):
        """Undetermined wells have MISSING quality and None value."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        undetermined = [m for m in result.measurements if m.value is None]
        assert len(undetermined) == 2
        for m in undetermined:
            assert m.quality == QualityFlag.MISSING

    def test_ct_units(self, parser: PCRParser):
        """All Ct measurements have 'Ct' unit."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        assert all(m.unit == "Ct" for m in result.measurements)

    def test_well_positions(self, parser: PCRParser):
        """Well positions are extracted."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        wells = {m.well_position for m in result.measurements}
        assert "A1" in wells
        assert "B6" in wells

    def test_sample_ids(self, parser: PCRParser):
        """Sample IDs are extracted."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        sample_ids = {m.sample_id for m in result.measurements if m.sample_id}
        assert "Sample_01" in sample_ids
        assert "NTC" in sample_ids
        assert "Pos_Control" in sample_ids

    def test_target_in_metadata(self, parser: PCRParser):
        """Target name is stored in measurement metadata."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        meas_with_meta = [m for m in result.measurements if m.metadata.get("target_name")]
        assert len(meas_with_meta) > 0
        targets = {m.metadata["target_name"] for m in meas_with_meta}
        assert "GAPDH" in targets
        assert "ACTB" in targets

    def test_quality_all_good_for_normal_ct(self, parser: PCRParser):
        """Normal Ct values (0 < Ct <= 40) have GOOD quality."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        determined = [m for m in result.measurements if m.value is not None]
        for m in determined:
            assert m.quality == QualityFlag.GOOD

    def test_summary_statistics_in_metadata(self, parser: PCRParser):
        """Summary statistics are computed."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        assert "summary" in result.raw_metadata
        summary = result.raw_metadata["summary"]
        assert "mean_ct" in summary
        assert "min_ct" in summary
        assert "max_ct" in summary
        assert summary["total_wells"] == 12
        assert summary["determined_wells"] == 10
        assert summary["undetermined_wells"] == 2

    def test_instrument_metadata_extracted(self, parser: PCRParser):
        """QuantStudio metadata from file header is extracted."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        assert result.instrument_settings is not None
        # Metadata from * key = value lines
        assert "Chemistry" in result.raw_metadata or result.instrument_settings.parameters.get("chemistry")

    def test_measurement_name_includes_target_and_well(self, parser: PCRParser):
        """Measurement names follow ct_target_well pattern."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        result = parser.parse(ctx)

        for m in result.measurements:
            assert m.name.startswith("ct_")


# -- Bio-Rad CFX Tests ---------------------------------------------------------


class TestBioRadCFXParsing:
    def test_parse_returns_parsed_result(self, parser: PCRParser):
        """Bio-Rad CFX CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "pcr"

    def test_cq_column_detected(self, parser: PCRParser):
        """Cq column is mapped as Ct."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        assert result.measurement_count == 12

    def test_n_a_treated_as_undetermined(self, parser: PCRParser):
        """N/A values in Cq column are treated as undetermined."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        undetermined = [m for m in result.measurements if m.value is None]
        assert len(undetermined) == 2

    def test_high_ct_flagged_suspect(self, parser: PCRParser):
        """Ct > 40 is flagged as SUSPECT."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        # Patient_004 has Cq=42.50
        high_ct = [m for m in result.measurements if m.value is not None and m.value > 40]
        assert len(high_ct) == 1
        assert high_ct[0].quality == QualityFlag.SUSPECT

    def test_specific_ct_values(self, parser: PCRParser):
        """Check specific Cq values."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        determined = [m for m in result.measurements if m.value is not None]
        values = sorted([m.value for m in determined])
        assert values[0] == pytest.approx(15.23)
        assert values[-1] == pytest.approx(42.50)

    def test_target_names_in_metadata(self, parser: PCRParser):
        """Target names from Bio-Rad export are captured."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        targets = {m.metadata.get("target_name") for m in result.measurements if m.metadata.get("target_name")}
        assert "IL6" in targets
        assert "TNF" in targets

    def test_reporter_dye_in_metadata(self, parser: PCRParser):
        """Reporter dye is captured in metadata."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        reporters = {m.metadata.get("reporter_dye") for m in result.measurements if m.metadata.get("reporter_dye")}
        assert "SYBR" in reporters

    def test_warnings_for_high_ct(self, parser: PCRParser):
        """Warning generated for Ct > 40."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        result = parser.parse(ctx)

        assert any("42.5" in w and "> 40" in w for w in result.warnings)


# -- Error Handling Tests ------------------------------------------------------


class TestPCRErrors:
    def test_corrupted_file_raises_parse_error(self, parser: PCRParser):
        """Corrupted file raises ParseError."""
        ctx = _ctx(FIXTURES / "corrupted.csv")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_empty_file_raises_parse_error(self, parser: PCRParser):
        """Empty file raises ParseError."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError, match="empty"):
            parser.safe_parse(ctx)

    def test_no_ct_column_raises_parse_error(self, parser: PCRParser):
        """File without Ct/Cq column raises ParseError."""
        ctx = FileContext(
            file_name="no_ct.csv",
            file_bytes=b"Well,Sample,Value\nA1,S1,0.5\n",
        )
        with pytest.raises(ParseError, match="Ct|Cq"):
            parser.parse(ctx)

    def test_parse_error_has_suggestion(self, parser: PCRParser):
        """ParseError includes a suggestion."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)
        assert exc_info.value.suggestion != ""


# -- can_handle Detection Tests ------------------------------------------------


class TestPCRCanHandle:
    def test_quantstudio_detected(self, parser: PCRParser):
        """QuantStudio CSV is detected."""
        ctx = _ctx(FIXTURES / "quantstudio_results.csv")
        assert parser.can_handle(ctx) is True

    def test_biorad_detected(self, parser: PCRParser):
        """Bio-Rad CFX CSV is detected."""
        ctx = _ctx(FIXTURES / "biorad_cfx.csv")
        assert parser.can_handle(ctx) is True

    def test_instrument_type_hint(self, parser: PCRParser):
        """Instrument type hint bypasses content check."""
        ctx = FileContext(
            file_name="data.xyz",
            file_bytes=b"no pcr keywords",
            instrument_type_hint="pcr",
        )
        assert parser.can_handle(ctx) is True

    def test_unknown_not_detected(self, parser: PCRParser):
        """Unknown file is not detected."""
        ctx = FileContext(file_name="data.xyz", file_bytes=b"random data")
        assert parser.can_handle(ctx) is False
