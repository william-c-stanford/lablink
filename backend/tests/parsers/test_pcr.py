"""Tests for PCR parser — happy path, edge cases, and corrupted input."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.base import FileContext, ParseError
from app.parsers.pcr import PCRParser
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
def parser() -> PCRParser:
    return PCRParser()


# ------------------------------------------------------------------
# can_handle
# ------------------------------------------------------------------

class TestCanHandle:
    def test_handles_csv_with_pcr_hint(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv", instrument_type_hint="pcr")
        assert parser.can_handle(ctx) is True

    def test_handles_csv_by_header_detection(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        assert parser.can_handle(ctx) is True

    def test_handles_quantstudio_format(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        assert parser.can_handle(ctx) is True

    def test_rejects_non_csv(self, parser: PCRParser):
        ctx = FileContext(file_name="data.xlsx", file_bytes=b"PK\x03\x04...")
        assert parser.can_handle(ctx) is False

    def test_rejects_hplc_file(self, parser: PCRParser):
        ctx = _ctx("hplc_agilent.csv")
        # HPLC data shouldn't match PCR patterns (no Ct/Cq columns)
        assert parser.can_handle(ctx) is False


# ------------------------------------------------------------------
# parse — Bio-Rad CFX format
# ------------------------------------------------------------------

class TestParseBioRad:
    def test_produces_valid_parsed_result(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "pcr"
        assert result.parser_version == "1.0.0"
        assert result.file_name == "pcr_biorad_cfx.csv"

    def test_correct_measurement_count(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        # 16 rows = 16 Ct measurements (including undetermined)
        assert len(result.measurements) == 16

    def test_determined_ct_values(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        determined = [m for m in result.measurements if m.value is not None]
        assert len(determined) == 14  # 16 total - 2 NTC undetermined

    def test_undetermined_ct_flagged_missing(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        undetermined = [m for m in result.measurements if m.quality == QualityFlag.MISSING]
        assert len(undetermined) == 2
        for m in undetermined:
            assert m.value is None

    def test_ct_units(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        for m in result.measurements:
            assert m.unit == "Ct"

    def test_well_positions_present(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        wells = {m.well_position for m in result.measurements if m.well_position}
        assert "A1" in wells
        assert "E1" in wells

    def test_sample_ids_present(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        sample_ids = {m.sample_id for m in result.measurements if m.sample_id}
        assert "Control_1" in sample_ids
        assert "Treatment_1" in sample_ids
        assert "NTC" in sample_ids

    def test_target_names_in_metadata(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        targets = {m.metadata.get("target_name") for m in result.measurements}
        assert "GAPDH" in targets
        assert "ACTB" in targets

    def test_instrument_settings(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        assert result.instrument_type == "pcr"
        assert result.instrument_settings.instrument_model == "Bio-Rad CFX96 Touch"
        assert result.instrument_settings.serial_number == "BR041256"

    def test_ct_value_accuracy(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        # First measurement should be Control_1 GAPDH at A1 with Ct=18.45
        a1_meas = [m for m in result.measurements if m.well_position == "A1"]
        assert len(a1_meas) == 1
        assert a1_meas[0].value == pytest.approx(18.45)

    def test_summary_in_metadata(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        summary = result.raw_metadata.get("summary", {})
        assert "mean_ct" in summary
        assert "determined_wells" in summary
        assert summary["determined_wells"] == 14
        assert summary["undetermined_wells"] == 2


# ------------------------------------------------------------------
# parse — QuantStudio format (with [Results] section)
# ------------------------------------------------------------------

class TestParseQuantStudio:
    def test_produces_valid_result(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "pcr"

    def test_parses_results_section(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        result = parser.parse(ctx)

        # 14 rows in the Results section
        assert len(result.measurements) == 14

    def test_undetermined_in_quantstudio(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        result = parser.parse(ctx)

        undetermined = [m for m in result.measurements if m.quality == QualityFlag.MISSING]
        # Patient_003 N gene, Patient_003 ORF1ab, NTC N gene, NTC ORF1ab
        assert len(undetermined) == 4

    def test_reporter_dye_extracted(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        result = parser.parse(ctx)

        reporters = {m.metadata.get("reporter_dye") for m in result.measurements}
        assert "FAM" in reporters
        assert "VIC" in reporters

    def test_task_extracted(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        result = parser.parse(ctx)

        tasks = {m.metadata.get("task") for m in result.measurements if m.metadata.get("task")}
        assert "Unknown" in tasks
        assert "Positive Control" in tasks
        assert "Negative Control" in tasks

    def test_multiple_targets(self, parser: PCRParser):
        ctx = _ctx("pcr_quantstudio.csv")
        result = parser.parse(ctx)

        targets = {m.metadata.get("target_name") for m in result.measurements}
        assert "N gene" in targets
        assert "ORF1ab" in targets


# ------------------------------------------------------------------
# parse — quality flagging edge cases
# ------------------------------------------------------------------

class TestQualityFlags:
    def test_high_ct_flagged_suspect(self, parser: PCRParser):
        ctx = _ctx("pcr_high_ct.csv")
        result = parser.parse(ctx)

        high_ct = [m for m in result.measurements if m.value is not None and m.value > 40]
        assert len(high_ct) == 1
        assert high_ct[0].quality == QualityFlag.SUSPECT
        assert high_ct[0].value == pytest.approx(42.5)

    def test_negative_ct_flagged_bad(self, parser: PCRParser):
        ctx = _ctx("pcr_high_ct.csv")
        result = parser.parse(ctx)

        bad = [m for m in result.measurements if m.quality == QualityFlag.BAD]
        assert len(bad) == 1
        assert bad[0].value == pytest.approx(-1.0)

    def test_normal_ct_flagged_good(self, parser: PCRParser):
        ctx = _ctx("pcr_high_ct.csv")
        result = parser.parse(ctx)

        good = [m for m in result.measurements if m.quality == QualityFlag.GOOD]
        assert len(good) == 1
        assert good[0].value == pytest.approx(25.0)

    def test_warnings_for_suspect_values(self, parser: PCRParser):
        ctx = _ctx("pcr_high_ct.csv")
        result = parser.parse(ctx)

        assert len(result.warnings) >= 2  # High Ct + negative Ct


# ------------------------------------------------------------------
# parse — error handling
# ------------------------------------------------------------------

class TestParseErrors:
    def test_empty_file_raises_parse_error(self, parser: PCRParser):
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError):
            parser.parse(ctx)

    def test_empty_fixture_raises_parse_error(self, parser: PCRParser):
        ctx = _ctx("pcr_empty.csv")
        with pytest.raises(ParseError):
            parser.parse(ctx)

    def test_corrupted_file_raises_parse_error(self, parser: PCRParser):
        ctx = _ctx("pcr_corrupted.csv")
        with pytest.raises(ParseError) as exc_info:
            parser.parse(ctx)
        assert exc_info.value.suggestion

    def test_no_ct_column_raises_parse_error(self, parser: PCRParser):
        data = b"Well,Sample,Value\nA1,Test,100\n"
        ctx = FileContext(file_name="no_ct.csv", file_bytes=data)
        with pytest.raises(ParseError, match="Ct"):
            parser.parse(ctx)

    def test_parse_error_includes_suggestion(self, parser: PCRParser):
        ctx = FileContext(file_name="bad.csv", file_bytes=b"")
        with pytest.raises(ParseError) as exc_info:
            parser.parse(ctx)
        err = exc_info.value
        assert err.suggestion != ""
        assert err.parser_name == "pcr"
        assert err.file_name == "bad.csv"


# ------------------------------------------------------------------
# ParsedResult contract validation
# ------------------------------------------------------------------

class TestParsedResultContract:
    """Verify that all parsers produce valid ParsedResult objects."""

    def test_all_required_fields_present(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        assert result.parser_name
        assert result.parser_version
        assert result.file_name
        assert result.parsed_at is not None
        assert result.instrument_settings is not None
        assert isinstance(result.measurements, list)
        assert isinstance(result.warnings, list)

    def test_measurement_values_have_names_and_units(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        for m in result.measurements:
            assert m.name, "Measurement must have a name"
            assert m.unit, "Measurement must have a unit"

    def test_result_serializes_to_json(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        json_str = result.model_dump_json()
        assert len(json_str) > 100
        assert "pcr" in json_str

    def test_result_roundtrips_through_json(self, parser: PCRParser):
        ctx = _ctx("pcr_biorad_cfx.csv")
        result = parser.parse(ctx)

        json_str = result.model_dump_json()
        restored = ParsedResult.model_validate_json(json_str)
        assert restored.parser_name == result.parser_name
        assert len(restored.measurements) == len(result.measurements)
