"""Integration tests for Celery tasks with sync fallback.

In dev/test mode (use_celery=False), tasks run inline synchronously.
These tests verify that:
1. The sync fallback mechanism works correctly
2. parse_file_task produces correct results with real parser logic
3. dispatch_parse routes correctly based on settings
4. Error cases return structured results with suggestions
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Environment, Settings
from app.tasks.parse_file import dispatch_parse, get_parser, parse_file_task

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def dev_settings() -> Settings:
    """Settings with use_celery=False (sync fallback)."""
    return Settings(
        environment=Environment.dev,
        database_url="sqlite+aiosqlite://",
        secret_key="test-key",
        use_celery=False,
    )


@pytest.fixture
def celery_settings() -> Settings:
    """Settings with use_celery=True (but still falls back to sync in our impl)."""
    return Settings(
        environment=Environment.dev,
        database_url="sqlite+aiosqlite://",
        secret_key="test-key",
        use_celery=True,
    )


# ---------------------------------------------------------------------------
# 1. get_parser tests
# ---------------------------------------------------------------------------

class TestGetParser:
    """Test parser registry lookup."""

    def test_get_known_parser(self):
        parser = get_parser("spectrophotometer")
        assert parser is not None
        assert parser.name == "spectrophotometer"

    def test_get_all_parsers(self):
        for name in ["spectrophotometer", "plate_reader", "hplc", "pcr", "balance"]:
            parser = get_parser(name)
            assert parser is not None

    def test_unknown_parser_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown parser"):
            get_parser("nonexistent_parser")


# ---------------------------------------------------------------------------
# 2. parse_file_task (sync) tests
# ---------------------------------------------------------------------------

class TestParseFileTask:
    """Test the core parse_file_task function."""

    def test_parse_spectrophotometer_success(self, dev_settings):
        fixture = FIXTURES_DIR / "spectrophotometer" / "nanodrop_sample.csv"
        content = fixture.read_bytes()

        result = parse_file_task(
            file_content=content,
            parser_name="spectrophotometer",
            file_name="nanodrop_sample.csv",
            settings=dev_settings,
        )

        assert result["success"] is True
        assert result["parser_name"] == "spectrophotometer"
        assert result["file_name"] == "nanodrop_sample.csv"
        assert "result" in result
        assert result["duration_seconds"] >= 0

        parsed = result["result"]
        assert parsed["parser_name"] == "spectrophotometer"
        assert parsed["measurement_count"] > 0

    def test_parse_plate_reader_success(self, dev_settings):
        fixture = FIXTURES_DIR / "plate_reader" / "softmax_pro_96well.csv"
        if not fixture.exists():
            pytest.skip("Plate reader fixture not available")
        content = fixture.read_bytes()

        result = parse_file_task(
            file_content=content,
            parser_name="plate_reader",
            file_name="softmax_pro_96well.csv",
            settings=dev_settings,
        )

        assert result["success"] is True
        assert result["parser_name"] == "plate_reader"

    def test_parse_with_string_content(self, dev_settings):
        fixture = FIXTURES_DIR / "spectrophotometer" / "nanodrop_sample.csv"
        content_str = fixture.read_text()

        result = parse_file_task(
            file_content=content_str,
            parser_name="spectrophotometer",
            file_name="nanodrop_sample.csv",
            settings=dev_settings,
        )

        assert result["success"] is True

    def test_parse_unknown_parser_returns_error(self, dev_settings):
        result = parse_file_task(
            file_content=b"some data",
            parser_name="unknown_instrument",
            file_name="test.csv",
            settings=dev_settings,
        )

        assert result["success"] is False
        assert "Unknown parser" in result["error"]
        assert "suggestion" in result
        assert "Available parsers" in result["suggestion"]

    def test_parse_corrupted_file_returns_error(self, dev_settings):
        fixture = FIXTURES_DIR / "spectrophotometer" / "corrupted.csv"
        content = fixture.read_bytes()

        result = parse_file_task(
            file_content=content,
            parser_name="spectrophotometer",
            file_name="corrupted.csv",
            settings=dev_settings,
        )

        assert result["success"] is False
        assert "error" in result
        assert "suggestion" in result
        assert result["duration_seconds"] >= 0

    def test_parse_empty_file_returns_error(self, dev_settings):
        result = parse_file_task(
            file_content=b"",
            parser_name="spectrophotometer",
            file_name="empty.csv",
            settings=dev_settings,
        )

        assert result["success"] is False
        assert "suggestion" in result

    def test_result_includes_duration(self, dev_settings):
        fixture = FIXTURES_DIR / "spectrophotometer" / "nanodrop_sample.csv"
        content = fixture.read_bytes()

        result = parse_file_task(
            file_content=content,
            parser_name="spectrophotometer",
            file_name="nanodrop_sample.csv",
            settings=dev_settings,
        )

        assert "duration_seconds" in result
        assert isinstance(result["duration_seconds"], float)
        assert result["duration_seconds"] >= 0


# ---------------------------------------------------------------------------
# 3. dispatch_parse (sync fallback) tests
# ---------------------------------------------------------------------------

class TestDispatchParse:
    """Test the dispatch_parse function with sync fallback."""

    def test_dispatch_sync_fallback(self, dev_settings):
        """With use_celery=False, dispatch_parse should run inline."""
        fixture = FIXTURES_DIR / "spectrophotometer" / "nanodrop_sample.csv"
        content = fixture.read_bytes()

        result = dispatch_parse(
            file_content=content,
            parser_name="spectrophotometer",
            file_name="nanodrop_sample.csv",
            settings=dev_settings,
        )

        # Should return result directly (not an AsyncResult)
        assert isinstance(result, dict)
        assert result["success"] is True
        assert "result" in result

    def test_dispatch_with_celery_enabled(self, celery_settings):
        """With use_celery=True, should still work (falls back to sync for now)."""
        fixture = FIXTURES_DIR / "spectrophotometer" / "nanodrop_sample.csv"
        content = fixture.read_bytes()

        result = dispatch_parse(
            file_content=content,
            parser_name="spectrophotometer",
            file_name="nanodrop_sample.csv",
            settings=celery_settings,
        )

        assert isinstance(result, dict)
        assert result["success"] is True

    def test_dispatch_error_propagation(self, dev_settings):
        """Errors in parsing should be caught and returned as structured results."""
        result = dispatch_parse(
            file_content=b"not valid data",
            parser_name="spectrophotometer",
            file_name="bad_data.csv",
            settings=dev_settings,
        )

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "error" in result
        assert "suggestion" in result


# ---------------------------------------------------------------------------
# 4. All parsers via dispatch (smoke tests)
# ---------------------------------------------------------------------------

class TestDispatchAllParsers:
    """Smoke test dispatch with all 5 parser types using real fixtures."""

    @pytest.mark.parametrize("parser_name,fixture_path", [
        ("spectrophotometer", "spectrophotometer/nanodrop_sample.csv"),
        ("plate_reader", "plate_reader/softmax_pro_96well.csv"),
        ("hplc", "hplc/agilent_peaks.csv"),
        ("pcr", "pcr/quantstudio_results.csv"),
        ("balance", "balance/mettler_toledo.csv"),
    ])
    def test_dispatch_parser(self, parser_name, fixture_path, dev_settings):
        fixture = FIXTURES_DIR / fixture_path
        if not fixture.exists():
            pytest.skip(f"Fixture not available: {fixture_path}")

        content = fixture.read_bytes()

        result = dispatch_parse(
            file_content=content,
            parser_name=parser_name,
            file_name=fixture.name,
            settings=dev_settings,
        )

        assert isinstance(result, dict)
        assert result["parser_name"] == parser_name
        assert result["file_name"] == fixture.name
        assert "duration_seconds" in result
        # Either success or structured error (corrupted fixtures will fail)
        if result["success"]:
            assert "result" in result
            assert result["result"]["parser_name"] == parser_name
        else:
            assert "error" in result
            assert "suggestion" in result

    @pytest.mark.parametrize("parser_name,fixture_path", [
        ("spectrophotometer", "spectrophotometer/corrupted.csv"),
        ("plate_reader", "plate_reader/corrupted.csv"),
        ("hplc", "hplc/corrupted.csv"),
        ("pcr", "pcr/corrupted.csv"),
        ("balance", "balance/corrupted.csv"),
    ])
    def test_dispatch_corrupted_files(self, parser_name, fixture_path, dev_settings):
        """All parsers should handle corrupted input gracefully via dispatch."""
        fixture = FIXTURES_DIR / fixture_path
        if not fixture.exists():
            pytest.skip(f"Fixture not available: {fixture_path}")

        content = fixture.read_bytes()
        result = dispatch_parse(
            file_content=content,
            parser_name=parser_name,
            file_name=fixture.name,
            settings=dev_settings,
        )

        assert isinstance(result, dict)
        assert result["parser_name"] == parser_name
        # Should either fail gracefully or parse with warnings
        if not result["success"]:
            assert "error" in result
            assert "suggestion" in result
