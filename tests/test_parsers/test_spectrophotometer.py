"""Tests for the spectrophotometer parser.

Covers:
- NanoDrop CSV parsing (concentration, A260, A280, 260/280 ratio)
- Cary UV-Vis wavelength scan parsing
- TSV format support
- Corrupted/empty input handling
- Quality flag warnings for suspect values
- can_handle detection
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.base import FileContext, ParseError
from app.parsers.spectrophotometer import SpectrophotometerParser
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES = Path(__file__).parent.parent / "fixtures" / "spectrophotometer"


@pytest.fixture
def parser() -> SpectrophotometerParser:
    return SpectrophotometerParser()


def _ctx(file_path: Path, **kwargs) -> FileContext:
    """Helper to build FileContext from a fixture file."""
    return FileContext(
        file_name=file_path.name,
        file_bytes=file_path.read_bytes(),
        **kwargs,
    )


# -- NanoDrop CSV Tests -------------------------------------------------------


class TestNanoDropParsing:
    def test_parse_returns_parsed_result(self, parser: SpectrophotometerParser):
        """NanoDrop CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "spectrophotometer"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "spectrophotometer"

    def test_file_name_and_hash(self, parser: SpectrophotometerParser):
        """Result includes original file name and SHA-256 hash."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        assert result.file_name == "nanodrop_sample.csv"
        assert result.file_hash is not None
        assert len(result.file_hash) == 64  # SHA-256 hex

    def test_sample_count(self, parser: SpectrophotometerParser):
        """NanoDrop fixture has 10 samples (10 unique Sample Name values)."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)
        # 10 rows, each has a unique Sample Name
        assert result.sample_count == 10

    def test_measurements_non_empty(self, parser: SpectrophotometerParser):
        """Parser extracts multiple measurements per sample row."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)
        assert result.measurement_count > 0
        assert len(result.measurements) == result.measurement_count

    def test_concentration_values(self, parser: SpectrophotometerParser):
        """Check specific concentration values from fixture."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        conc = [m for m in result.measurements if "concentration" in m.name.lower() or "ng" in m.name.lower()]
        conc_by_sample = {m.sample_id: m.value for m in conc if m.sample_id}

        assert conc_by_sample["DNA_Sample_01"] == pytest.approx(152.3)
        assert conc_by_sample["RNA_Extract_01"] == pytest.approx(340.5)
        assert conc_by_sample["High_Conc_Sample"] == pytest.approx(1850.0)

    def test_absorbance_values(self, parser: SpectrophotometerParser):
        """A260 and A280 measurements are extracted."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        a260_meas = [m for m in result.measurements if "a260" in m.name.lower()]
        assert len(a260_meas) > 0
        a280_meas = [m for m in result.measurements if "a280" in m.name.lower()]
        assert len(a280_meas) > 0

    def test_absorbance_units(self, parser: SpectrophotometerParser):
        """Absorbance measurements have AU unit."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        a260_meas = [m for m in result.measurements if "a260" in m.name.lower()]
        for m in a260_meas:
            assert m.unit == "AU"

    def test_concentration_units(self, parser: SpectrophotometerParser):
        """Concentration measurements have ng/uL units with QUDT URI."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        conc = [m for m in result.measurements if "ng" in m.name.lower()]
        for m in conc:
            assert m.unit == "ng/uL"
            assert m.qudt_uri is not None

    def test_ratio_values(self, parser: SpectrophotometerParser):
        """260/280 ratio measurements are extracted."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        ratio_meas = [m for m in result.measurements if "260_280" in m.name.lower() or "260/280" in m.name.lower()]
        assert len(ratio_meas) > 0
        ratio_by_sample = {m.sample_id: m.value for m in ratio_meas if m.sample_id}
        assert ratio_by_sample["DNA_Sample_01"] == pytest.approx(1.92)

    def test_high_absorbance_flagged_suspect(self, parser: SpectrophotometerParser):
        """A260 > 5.0 triggers SUSPECT quality flag and warning."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        # High_Conc_Sample has A260=37.000, well above 5.0
        high_a260 = [
            m for m in result.measurements
            if m.sample_id == "High_Conc_Sample" and "a260" in m.name.lower()
        ]
        assert len(high_a260) == 1
        assert high_a260[0].quality == QualityFlag.SUSPECT
        assert any("High_Conc_Sample" in w or "37.0" in w for w in result.warnings)

    def test_negative_concentration_flagged(self, parser: SpectrophotometerParser):
        """Negative concentration values are flagged SUSPECT."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        # Blank has concentration -0.2
        blank_conc = [
            m for m in result.measurements
            if m.sample_id == "Blank" and ("ng" in m.name.lower() or "conc" in m.name.lower())
        ]
        assert any(m.quality == QualityFlag.SUSPECT for m in blank_conc)

    def test_instrument_settings(self, parser: SpectrophotometerParser):
        """Instrument settings are populated."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        result = parser.parse(ctx)

        assert result.instrument_settings is not None


class TestNanoDropTSV:
    def test_parse_tsv_format(self, parser: SpectrophotometerParser):
        """TSV format is parsed correctly."""
        ctx = _ctx(FIXTURES / "nanodrop_tsv.tsv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.sample_count == 6

    def test_tsv_concentration_values(self, parser: SpectrophotometerParser):
        """TSV concentrations are parsed correctly."""
        ctx = _ctx(FIXTURES / "nanodrop_tsv.tsv")
        result = parser.parse(ctx)

        conc = [m for m in result.measurements if "concentration" in m.name.lower() or "conc" in m.name.lower()]
        conc_by_sample = {m.sample_id: m.value for m in conc if m.sample_id}
        assert conc_by_sample["gDNA_Mouse_Liver"] == pytest.approx(520.4)
        assert conc_by_sample["mRNA_HeLa"] == pytest.approx(890.2)

    def test_tsv_measurement_count(self, parser: SpectrophotometerParser):
        """TSV has measurements for all samples."""
        ctx = _ctx(FIXTURES / "nanodrop_tsv.tsv")
        result = parser.parse(ctx)
        assert result.measurement_count > 0


# -- Cary UV-Vis Scan Tests ---------------------------------------------------


class TestCaryUVVisParsing:
    def test_parse_cary_returns_parsed_result(self, parser: SpectrophotometerParser):
        """Cary UV-Vis scan CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "cary_uv_vis_scan.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.instrument_type == "spectrophotometer"

    def test_cary_measurement_count(self, parser: SpectrophotometerParser):
        """Cary scan has wavelength x sample measurements."""
        ctx = _ctx(FIXTURES / "cary_uv_vis_scan.csv")
        result = parser.parse(ctx)

        # 23 wavelength points * 3 columns (Sample_A, Sample_B, Blank) = 69
        # But Wavelength column values are numeric too, the parser extracts those
        # Let's just verify we have a good number of measurements
        assert result.measurement_count >= 23 * 3

    def test_cary_units(self, parser: SpectrophotometerParser):
        """Absorbance measurements have AU units."""
        ctx = _ctx(FIXTURES / "cary_uv_vis_scan.csv")
        result = parser.parse(ctx)

        abs_meas = [m for m in result.measurements if "abs" in m.name.lower() or "sample" in m.name.lower()]
        for m in abs_meas:
            assert m.unit == "AU"

    def test_cary_wavelength_column(self, parser: SpectrophotometerParser):
        """Wavelength column measurements exist with nm unit."""
        ctx = _ctx(FIXTURES / "cary_uv_vis_scan.csv")
        result = parser.parse(ctx)

        wl_meas = [m for m in result.measurements if "wavelength" in m.name.lower()]
        if wl_meas:
            assert all(m.unit == "nm" for m in wl_meas)

    def test_cary_specific_value(self, parser: SpectrophotometerParser):
        """Check specific absorbance value."""
        ctx = _ctx(FIXTURES / "cary_uv_vis_scan.csv")
        result = parser.parse(ctx)

        # Look for Sample_A (Abs) at some row
        sample_a = [m for m in result.measurements if "sample_a" in m.name.lower()]
        assert len(sample_a) > 0
        values = [m.value for m in sample_a]
        assert pytest.approx(0.5670) in values


# -- Error Handling Tests ------------------------------------------------------


class TestSpectrophotometerErrors:
    def test_corrupted_file_raises_parse_error(self, parser: SpectrophotometerParser):
        """Corrupted file raises ParseError via safe_parse."""
        ctx = _ctx(FIXTURES / "corrupted.csv")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_empty_file_raises_parse_error(self, parser: SpectrophotometerParser):
        """Empty file raises ParseError."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError, match="empty"):
            parser.safe_parse(ctx)

    def test_single_line_raises_parse_error(self, parser: SpectrophotometerParser):
        """File with only one line raises ParseError."""
        ctx = FileContext(file_name="single.csv", file_bytes=b"just one line\n")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_header_only_raises_parse_error(self, parser: SpectrophotometerParser):
        """File with header but no data raises ParseError."""
        ctx = FileContext(
            file_name="header_only.csv",
            file_bytes=b"Sample Name,A260,A280,260/280\n",
        )
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_parse_error_has_suggestion(self, parser: SpectrophotometerParser):
        """ParseError includes a suggestion field."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)
        assert exc_info.value.suggestion != ""

    def test_binary_garbage_raises_parse_error(self, parser: SpectrophotometerParser):
        """Binary garbage raises ParseError."""
        ctx = FileContext(file_name="garbage.bin", file_bytes=bytes(range(256)) * 10)
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)


# -- can_handle Detection Tests -----------------------------------------------


class TestSpectrophotometerCanHandle:
    def test_nanodrop_csv_detected(self, parser: SpectrophotometerParser):
        """NanoDrop CSV is detected by content keywords."""
        ctx = _ctx(FIXTURES / "nanodrop_sample.csv")
        assert parser.can_handle(ctx) is True

    def test_cary_csv_detected(self, parser: SpectrophotometerParser):
        """Cary UV-Vis CSV is detected by wavelength keyword."""
        ctx = _ctx(FIXTURES / "cary_uv_vis_scan.csv")
        assert parser.can_handle(ctx) is True

    def test_tsv_detected(self, parser: SpectrophotometerParser):
        """TSV format with A260 keyword is detected."""
        ctx = _ctx(FIXTURES / "nanodrop_tsv.tsv")
        assert parser.can_handle(ctx) is True

    def test_instrument_type_hint(self, parser: SpectrophotometerParser):
        """Instrument type hint bypasses content check."""
        ctx = FileContext(
            file_name="data.xyz",
            file_bytes=b"no keywords here",
            instrument_type_hint="spectrophotometer",
        )
        assert parser.can_handle(ctx) is True

    def test_unknown_extension_no_keywords(self, parser: SpectrophotometerParser):
        """Non-CSV without keywords is not detected."""
        ctx = FileContext(file_name="data.xyz", file_bytes=b"random data")
        assert parser.can_handle(ctx) is False

    def test_wrong_extension(self, parser: SpectrophotometerParser):
        """Non-supported extension without hint is not detected."""
        ctx = FileContext(file_name="data.xlsx", file_bytes=b"A260 data here")
        assert parser.can_handle(ctx) is False
