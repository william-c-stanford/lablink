"""Tests for the balance parser.

Covers:
- Mettler Toledo CSV with net/tare/stability columns
- Sartorius simple format with mass/unit columns
- Unit detection (g, mg, kg)
- QUDT URI mapping
- Stability flag handling (unstable -> SUSPECT)
- Negative mass flagging
- Corrupted/empty input handling
- can_handle detection
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.balance import BalanceParser
from app.parsers.base import FileContext, ParseError
from app.schemas.parsed_result import ParsedResult, QualityFlag

FIXTURES = Path(__file__).parent.parent / "fixtures" / "balance"


@pytest.fixture
def parser() -> BalanceParser:
    return BalanceParser()


def _ctx(file_path: Path, **kwargs) -> FileContext:
    """Helper to build FileContext from a fixture file."""
    return FileContext(
        file_name=file_path.name,
        file_bytes=file_path.read_bytes(),
        **kwargs,
    )


# -- Mettler Toledo Tests ------------------------------------------------------


class TestMettlerToledoParsing:
    def test_parse_returns_parsed_result(self, parser: BalanceParser):
        """Mettler Toledo CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "balance"
        assert result.parser_version == "1.0.0"
        assert result.instrument_type == "balance"

    def test_file_name_and_hash(self, parser: BalanceParser):
        """Result includes file name and SHA-256 hash."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert result.file_name == "mettler_toledo.csv"
        assert result.file_hash is not None
        assert len(result.file_hash) == 64

    def test_sample_count(self, parser: BalanceParser):
        """Mettler Toledo fixture has 8 unique samples."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert result.sample_count == 8

    def test_mass_measurements(self, parser: BalanceParser):
        """Mass measurements are correctly parsed."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        mass_meas = [m for m in result.measurements if m.name == "mass"]
        assert len(mass_meas) == 8

    def test_tare_measurements(self, parser: BalanceParser):
        """Tare measurements are extracted."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        tare_meas = [m for m in result.measurements if m.name == "tare"]
        assert len(tare_meas) == 8

    def test_total_measurement_count(self, parser: BalanceParser):
        """Total measurements = 8 mass + 8 tare = 16."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert result.measurement_count == 16

    def test_specific_mass_values(self, parser: BalanceParser):
        """Check specific mass values from fixture."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        mass_by_sample = {
            m.sample_id: m.value for m in result.measurements if m.name == "mass" and m.sample_id
        }
        assert mass_by_sample["API_Batch_01"] == pytest.approx(125.4532)
        assert mass_by_sample["Reference_Std"] == pytest.approx(10.0001)
        assert mass_by_sample["Empty_Vial"] == pytest.approx(0.0023)

    def test_mass_units(self, parser: BalanceParser):
        """Mass measurements have g unit."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        mass_meas = [m for m in result.measurements if m.name == "mass"]
        for m in mass_meas:
            assert m.unit == "g"

    def test_qudt_uri_for_grams(self, parser: BalanceParser):
        """Mass measurements in grams have correct QUDT URI."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        mass_meas = [m for m in result.measurements if m.name == "mass"]
        for m in mass_meas:
            assert m.qudt_uri == "http://qudt.org/vocab/unit/GM"

    def test_unstable_reading_flagged_suspect(self, parser: BalanceParser):
        """Unstable readings are flagged as SUSPECT."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        # Excipient_B has Stability=Unstable
        excipient_b = [
            m for m in result.measurements if m.sample_id == "Excipient_B" and m.name == "mass"
        ]
        assert len(excipient_b) == 1
        assert excipient_b[0].quality == QualityFlag.SUSPECT

    def test_stable_readings_good_quality(self, parser: BalanceParser):
        """Stable readings have GOOD quality."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        stable_mass = [
            m for m in result.measurements if m.name == "mass" and m.sample_id != "Excipient_B"
        ]
        assert all(m.quality == QualityFlag.GOOD for m in stable_mass)

    def test_warnings_for_unstable(self, parser: BalanceParser):
        """Warning generated for unstable reading."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert any("unstable" in w.lower() for w in result.warnings)

    def test_metadata_extracted(self, parser: BalanceParser):
        """Metadata from file header is extracted."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert "Model" in result.raw_metadata or "Serial Number" in result.raw_metadata

    def test_instrument_settings(self, parser: BalanceParser):
        """Instrument settings are populated from metadata."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        result = parser.parse(ctx)

        assert result.instrument_settings is not None
        assert result.instrument_settings.instrument_model == "XPE205"
        assert result.instrument_settings.serial_number == "B123456789"


# -- Sartorius Simple Tests ----------------------------------------------------


class TestSartoriusParsing:
    def test_parse_returns_parsed_result(self, parser: BalanceParser):
        """Sartorius simple CSV produces a valid ParsedResult."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        result = parser.parse(ctx)

        assert isinstance(result, ParsedResult)
        assert result.parser_name == "balance"

    def test_sample_count(self, parser: BalanceParser):
        """Sartorius fixture has 6 samples."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        result = parser.parse(ctx)

        assert result.sample_count == 6

    def test_mass_values(self, parser: BalanceParser):
        """Mass values are correctly parsed."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        result = parser.parse(ctx)

        mass_by_sample = {
            m.sample_id: m.value for m in result.measurements if m.name == "mass" and m.sample_id
        }
        assert mass_by_sample["Compound_A"] == pytest.approx(0.5023)
        assert mass_by_sample["Compound_D"] == pytest.approx(2.3456)

    def test_negative_mass_flagged_suspect(self, parser: BalanceParser):
        """Negative mass value is flagged as SUSPECT."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        result = parser.parse(ctx)

        # Compound_E has mass -0.0012
        compound_e = [
            m for m in result.measurements if m.sample_id == "Compound_E" and m.name == "mass"
        ]
        assert len(compound_e) == 1
        assert compound_e[0].quality == QualityFlag.SUSPECT

    def test_warning_for_negative_mass(self, parser: BalanceParser):
        """Warning generated for negative mass."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        result = parser.parse(ctx)

        assert any("negative" in w.lower() for w in result.warnings)

    def test_units_from_column(self, parser: BalanceParser):
        """Unit is read from the Unit column."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        result = parser.parse(ctx)

        mass_meas = [m for m in result.measurements if m.name == "mass"]
        for m in mass_meas:
            assert m.unit == "g"


# -- Error Handling Tests ------------------------------------------------------


class TestBalanceErrors:
    def test_corrupted_file_raises_parse_error(self, parser: BalanceParser):
        """Corrupted file raises ParseError."""
        ctx = _ctx(FIXTURES / "corrupted.csv")
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)

    def test_empty_file_raises_parse_error(self, parser: BalanceParser):
        """Empty file raises ParseError."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError, match="empty"):
            parser.safe_parse(ctx)

    def test_no_mass_column_raises_parse_error(self, parser: BalanceParser):
        """File without mass/weight column raises ParseError."""
        ctx = FileContext(
            file_name="no_mass.csv",
            file_bytes=b"Name,Color,Size\nA,Red,Large\nB,Blue,Small\n",
        )
        with pytest.raises(ParseError, match="mass|weight|value"):
            parser.parse(ctx)

    def test_parse_error_has_suggestion(self, parser: BalanceParser):
        """ParseError includes a suggestion."""
        ctx = FileContext(file_name="empty.csv", file_bytes=b"")
        with pytest.raises(ParseError) as exc_info:
            parser.safe_parse(ctx)
        assert exc_info.value.suggestion != ""

    def test_binary_garbage_raises_parse_error(self, parser: BalanceParser):
        """Binary garbage raises ParseError."""
        ctx = FileContext(file_name="garbage.bin", file_bytes=bytes(range(256)) * 10)
        with pytest.raises(ParseError):
            parser.safe_parse(ctx)


# -- can_handle Detection Tests ------------------------------------------------


class TestBalanceCanHandle:
    def test_mettler_detected(self, parser: BalanceParser):
        """Mettler Toledo CSV is detected."""
        ctx = _ctx(FIXTURES / "mettler_toledo.csv")
        assert parser.can_handle(ctx) is True

    def test_sartorius_detected(self, parser: BalanceParser):
        """Sartorius CSV is detected."""
        ctx = _ctx(FIXTURES / "sartorius_simple.csv")
        assert parser.can_handle(ctx) is True

    def test_instrument_type_hint(self, parser: BalanceParser):
        """Instrument type hint bypasses content check."""
        ctx = FileContext(
            file_name="data.xyz",
            file_bytes=b"no balance keywords",
            instrument_type_hint="balance",
        )
        assert parser.can_handle(ctx) is True

    def test_unknown_not_detected(self, parser: BalanceParser):
        """Unknown file is not detected."""
        ctx = FileContext(file_name="data.xyz", file_bytes=b"random data")
        assert parser.can_handle(ctx) is False
