"""Tests for the parser registry.

Covers:
- All 5 parsers are registered
- Registry lookup by instrument type
- Registry keys match parser instrument_type
- Parser instantiation from registry
- Auto-detection via can_handle across registry
- BaseParser ABC enforcement
"""

from __future__ import annotations

import pytest

from app.parsers import (
    PARSER_REGISTRY,
    BalanceParser,
    BaseParser,
    FileContext,
    HPLCParser,
    PCRParser,
    PlateReaderParser,
    SpectrophotometerParser,
)
from app.schemas.parsed_result import ParsedResult


class TestParserRegistry:
    """Tests for PARSER_REGISTRY dict."""

    def test_registry_has_five_parsers(self):
        """Registry contains exactly 5 parsers."""
        assert len(PARSER_REGISTRY) == 5

    def test_all_instrument_types_registered(self):
        """All 5 instrument types are present as keys."""
        expected = {"spectrophotometer", "plate_reader", "hplc", "pcr", "balance"}
        assert set(PARSER_REGISTRY.keys()) == expected

    def test_spectrophotometer_registered(self):
        """SpectrophotometerParser is registered."""
        assert PARSER_REGISTRY["spectrophotometer"] is SpectrophotometerParser

    def test_plate_reader_registered(self):
        """PlateReaderParser is registered."""
        assert PARSER_REGISTRY["plate_reader"] is PlateReaderParser

    def test_hplc_registered(self):
        """HPLCParser is registered."""
        assert PARSER_REGISTRY["hplc"] is HPLCParser

    def test_pcr_registered(self):
        """PCRParser is registered."""
        assert PARSER_REGISTRY["pcr"] is PCRParser

    def test_balance_registered(self):
        """BalanceParser is registered."""
        assert PARSER_REGISTRY["balance"] is BalanceParser


class TestParserInstantiation:
    """Test that all registered parsers can be instantiated."""

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_instantiate_from_registry(self, instrument_type: str):
        """Each registered parser class can be instantiated."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert isinstance(parser, BaseParser)

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_parser_has_required_class_attrs(self, instrument_type: str):
        """Each parser has name, version, instrument_type, supported_extensions."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert hasattr(parser, "name")
        assert hasattr(parser, "version")
        assert hasattr(parser, "instrument_type")
        assert hasattr(parser, "supported_extensions")
        assert isinstance(parser.supported_extensions, tuple)

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_registry_key_matches_parser_instrument_type(self, instrument_type: str):
        """Registry key matches the parser's instrument_type attribute."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert parser.instrument_type == instrument_type

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_registry_key_matches_parser_name(self, instrument_type: str):
        """Registry key matches the parser's name attribute."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert parser.name == instrument_type

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_parser_has_parse_method(self, instrument_type: str):
        """Each parser has a parse() method."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert callable(getattr(parser, "parse", None))

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_parser_has_can_handle_method(self, instrument_type: str):
        """Each parser has a can_handle() method."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert callable(getattr(parser, "can_handle", None))

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_parser_has_safe_parse_method(self, instrument_type: str):
        """Each parser inherits safe_parse() from BaseParser."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert callable(getattr(parser, "safe_parse", None))

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_parser_version_is_semver(self, instrument_type: str):
        """Parser version follows semver pattern."""
        import re

        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        assert re.match(r"^\d+\.\d+\.\d+$", parser.version)

    @pytest.mark.parametrize("instrument_type", list(PARSER_REGISTRY.keys()))
    def test_supported_extensions_start_with_dot(self, instrument_type: str):
        """Supported extensions start with a dot."""
        parser_cls = PARSER_REGISTRY[instrument_type]
        parser = parser_cls()
        for ext in parser.supported_extensions:
            assert ext.startswith("."), f"Extension '{ext}' should start with '.'"


class TestAutoDetection:
    """Test auto-detection across the whole registry."""

    def test_detect_spectrophotometer_file(self):
        """Spectrophotometer file is detected by the right parser."""
        from pathlib import Path

        fixture = (
            Path(__file__).parent.parent / "fixtures" / "spectrophotometer" / "nanodrop_sample.csv"
        )
        ctx = FileContext(file_name=fixture.name, file_bytes=fixture.read_bytes())

        matching = [(key, PARSER_REGISTRY[key]()) for key in PARSER_REGISTRY]
        detected = [(key, p) for key, p in matching if p.can_handle(ctx)]
        keys = [key for key, _ in detected]
        assert "spectrophotometer" in keys

    def test_detect_hplc_file(self):
        """HPLC file is detected by the right parser."""
        from pathlib import Path

        fixture = Path(__file__).parent.parent / "fixtures" / "hplc" / "agilent_peaks.csv"
        ctx = FileContext(file_name=fixture.name, file_bytes=fixture.read_bytes())

        matching = [(key, PARSER_REGISTRY[key]()) for key in PARSER_REGISTRY]
        detected = [(key, p) for key, p in matching if p.can_handle(ctx)]
        keys = [key for key, _ in detected]
        assert "hplc" in keys

    def test_detect_pcr_file(self):
        """PCR file is detected by the right parser."""
        from pathlib import Path

        fixture = Path(__file__).parent.parent / "fixtures" / "pcr" / "quantstudio_results.csv"
        ctx = FileContext(file_name=fixture.name, file_bytes=fixture.read_bytes())

        matching = [(key, PARSER_REGISTRY[key]()) for key in PARSER_REGISTRY]
        detected = [(key, p) for key, p in matching if p.can_handle(ctx)]
        keys = [key for key, _ in detected]
        assert "pcr" in keys

    def test_detect_balance_file(self):
        """Balance file is detected by the right parser."""
        from pathlib import Path

        fixture = Path(__file__).parent.parent / "fixtures" / "balance" / "mettler_toledo.csv"
        ctx = FileContext(file_name=fixture.name, file_bytes=fixture.read_bytes())

        matching = [(key, PARSER_REGISTRY[key]()) for key in PARSER_REGISTRY]
        detected = [(key, p) for key, p in matching if p.can_handle(ctx)]
        keys = [key for key, _ in detected]
        assert "balance" in keys

    def test_instrument_type_hint_narrows_detection(self):
        """Instrument type hint ensures only matching parser detects."""
        ctx = FileContext(
            file_name="data.csv",
            file_bytes=b"some data",
            instrument_type_hint="balance",
        )
        matching = [(key, PARSER_REGISTRY[key]()) for key in PARSER_REGISTRY]
        detected = [key for key, p in matching if p.can_handle(ctx)]
        assert detected == ["balance"]

    def test_unknown_file_not_detected(self):
        """Unknown file format is not detected by any parser."""
        ctx = FileContext(file_name="data.xyz", file_bytes=b"completely random data")
        matching = [(key, PARSER_REGISTRY[key]()) for key in PARSER_REGISTRY]
        detected = [key for key, p in matching if p.can_handle(ctx)]
        assert len(detected) == 0


class TestBaseParserABC:
    """Test BaseParser abstract class enforcement."""

    def test_cannot_instantiate_base_parser(self):
        """BaseParser cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseParser()  # type: ignore[abstract]

    def test_subclass_must_implement_parse(self):
        """Subclass without parse() raises TypeError."""

        class IncompleteParser(BaseParser):
            name = "test"
            version = "0.0.1"
            instrument_type = "test"
            supported_extensions = (".csv",)

            def can_handle(self, ctx: FileContext) -> bool:
                return True

        with pytest.raises(TypeError):
            IncompleteParser()  # type: ignore[abstract]

    def test_subclass_must_implement_can_handle(self):
        """Subclass without can_handle() raises TypeError."""

        class IncompleteParser(BaseParser):
            name = "test"
            version = "0.0.1"
            instrument_type = "test"
            supported_extensions = (".csv",)

            def parse(self, ctx: FileContext) -> ParsedResult:
                return ParsedResult(
                    parser_name="test",
                    parser_version="0.0.1",
                    instrument_type="test",
                    file_name="test.csv",
                )

        with pytest.raises(TypeError):
            IncompleteParser()  # type: ignore[abstract]
