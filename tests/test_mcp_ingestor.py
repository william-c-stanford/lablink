"""Tests for MCP ingestor toolset (4 tools).

Covers:
- ingest_file: successful parse, auto-detect, unknown parser, empty content, invalid base64
- check_ingest_status: found, not_found, include_result
- retry_ingest: successful retry, not_found, wrong status
- list_parsers: all 5 parsers returned with metadata
"""

from __future__ import annotations

import base64
import pytest

from app.mcp_server.tools.ingestor import (
    _ingest_jobs,
    check_ingest_status,
    ingest_file,
    list_parsers,
    retry_ingest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SPECTRO_CSV = """\
Wavelength,Absorbance,Sample ID
260,0.523,sample_1
280,0.412,sample_1
340,0.015,sample_1
260,0.891,sample_2
280,0.654,sample_2
340,0.022,sample_2
"""

SAMPLE_BALANCE_CSV = """\
Sample ID,Mass,Unit
BAL-001,12.3456,g
BAL-002,8.7654,g
BAL-003,15.2345,g
"""


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Clear ingest jobs between tests."""
    _ingest_jobs.clear()
    yield
    _ingest_jobs.clear()


# ---------------------------------------------------------------------------
# ingest_file tests
# ---------------------------------------------------------------------------


class TestIngestFile:
    """Tests for the ingest_file tool."""

    @pytest.mark.asyncio
    async def test_ingest_with_explicit_parser_base64(self):
        """Ingest a spectrophotometer CSV with explicit parser and base64 content."""
        content_b64 = base64.b64encode(SAMPLE_SPECTRO_CSV.encode()).decode()
        result = await ingest_file(
            file_name="spectrum.csv",
            file_content_base64=content_b64,
            parser_name="spectrophotometer",
        )
        assert result["status"] == "parsed"
        assert result["parser_used"] == "spectrophotometer"
        assert result["measurement_count"] > 0
        assert result["sample_count"] > 0
        assert "job_id" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_ingest_with_raw_bytes(self):
        """Ingest with raw bytes instead of base64."""
        result = await ingest_file(
            file_name="balance_data.csv",
            file_content_bytes=SAMPLE_BALANCE_CSV.encode(),
            parser_name="balance",
        )
        assert result["status"] == "parsed"
        assert result["parser_used"] == "balance"
        assert result["measurement_count"] > 0

    @pytest.mark.asyncio
    async def test_ingest_unknown_parser(self):
        """Requesting an unknown parser returns error with available list."""
        result = await ingest_file(
            file_name="data.csv",
            file_content_bytes=b"some,data\n1,2",
            parser_name="nonexistent_parser",
        )
        assert result["status"] == "error"
        assert "nonexistent_parser" in result["error"]
        assert "available_parsers" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_ingest_no_content(self):
        """Missing file content returns error with suggestion."""
        result = await ingest_file(file_name="empty.csv")
        assert result["status"] == "error"
        assert "No file content" in result["error"]
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_ingest_both_content_types(self):
        """Providing both content types returns error."""
        result = await ingest_file(
            file_name="data.csv",
            file_content_base64="dGVzdA==",
            file_content_bytes=b"test",
        )
        assert result["status"] == "error"
        assert "not both" in result["error"]

    @pytest.mark.asyncio
    async def test_ingest_invalid_base64(self):
        """Invalid base64 returns error with suggestion."""
        result = await ingest_file(
            file_name="data.csv",
            file_content_base64="!!!not-base64!!!",
        )
        assert result["status"] == "error"
        assert "base64" in result["error"].lower()
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_ingest_empty_bytes(self):
        """Empty bytes returns error."""
        result = await ingest_file(
            file_name="empty.csv",
            file_content_bytes=b"",
        )
        assert result["status"] == "error"
        assert "empty" in result["error"].lower() or "no file content" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_ingest_corrupted_file(self):
        """Corrupted file returns failed status with suggestion."""
        result = await ingest_file(
            file_name="corrupt.csv",
            file_content_bytes=b"\x00\x01\x02\x03binary_garbage",
            parser_name="spectrophotometer",
        )
        assert result["status"] == "failed"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_ingest_stores_job(self):
        """Successful ingest stores job in tracking dict."""
        content_b64 = base64.b64encode(SAMPLE_SPECTRO_CSV.encode()).decode()
        result = await ingest_file(
            file_name="spectrum.csv",
            file_content_base64=content_b64,
            parser_name="spectrophotometer",
        )
        job_id = result["job_id"]
        assert job_id in _ingest_jobs
        assert _ingest_jobs[job_id]["status"] == "parsed"

    @pytest.mark.asyncio
    async def test_ingest_auto_detect_no_match(self):
        """Auto-detect with unrecognizable file returns error."""
        result = await ingest_file(
            file_name="mystery.xyz",
            file_content_bytes=b"completely unknown format data here\n",
        )
        assert result["status"] == "error"
        assert "auto-detect" in result["error"].lower() or "No parser" in result["error"]
        assert "available_parsers" in result


# ---------------------------------------------------------------------------
# check_ingest_status tests
# ---------------------------------------------------------------------------


class TestCheckIngestStatus:
    """Tests for the check_ingest_status tool."""

    @pytest.mark.asyncio
    async def test_check_status_not_found(self):
        """Unknown job_id returns not_found with suggestion."""
        result = await check_ingest_status(job_id="nonexistent-id")
        assert result["status"] == "not_found"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_check_status_parsed(self):
        """Check status of a successfully parsed job."""
        # First ingest a file
        content_b64 = base64.b64encode(SAMPLE_SPECTRO_CSV.encode()).decode()
        ingest_result = await ingest_file(
            file_name="spectrum.csv",
            file_content_base64=content_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        # Check status
        status = await check_ingest_status(job_id=job_id)
        assert status["status"] == "parsed"
        assert status["measurement_count"] > 0
        assert "parsed_result" not in status  # not included by default
        assert "suggestion" in status

    @pytest.mark.asyncio
    async def test_check_status_with_result(self):
        """Check status with include_result=True returns full parsed data."""
        content_b64 = base64.b64encode(SAMPLE_SPECTRO_CSV.encode()).decode()
        ingest_result = await ingest_file(
            file_name="spectrum.csv",
            file_content_base64=content_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        status = await check_ingest_status(job_id=job_id, include_result=True)
        assert status["status"] == "parsed"
        assert "parsed_result" in status
        assert status["parsed_result"] is not None

    @pytest.mark.asyncio
    async def test_check_status_failed(self):
        """Check status of a failed job shows error and suggestion."""
        result = await ingest_file(
            file_name="corrupt.csv",
            file_content_bytes=b"\x00\x01binary",
            parser_name="spectrophotometer",
        )
        job_id = result["job_id"]

        status = await check_ingest_status(job_id=job_id)
        assert status["status"] == "failed"
        assert "error" in status
        assert "suggestion" in status


# ---------------------------------------------------------------------------
# retry_ingest tests
# ---------------------------------------------------------------------------


class TestRetryIngest:
    """Tests for the retry_ingest tool."""

    @pytest.mark.asyncio
    async def test_retry_not_found(self):
        """Retry with unknown job_id returns not_found."""
        result = await retry_ingest(job_id="nonexistent-id")
        assert result["status"] == "not_found"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_retry_failed_job(self):
        """Retry a failed job re-queues it."""
        # Create a failed job
        ingest_result = await ingest_file(
            file_name="corrupt.csv",
            file_content_bytes=b"\x00\x01binary",
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]
        assert _ingest_jobs[job_id]["status"] == "failed"

        # Retry
        retry_result = await retry_ingest(job_id=job_id)
        assert retry_result["status"] == "queued"
        assert retry_result["job_id"] == job_id
        assert "suggestion" in retry_result

    @pytest.mark.asyncio
    async def test_retry_with_different_parser(self):
        """Retry with an alternative parser name."""
        ingest_result = await ingest_file(
            file_name="corrupt.csv",
            file_content_bytes=b"\x00\x01binary",
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        retry_result = await retry_ingest(job_id=job_id, parser_name="hplc")
        assert retry_result["status"] == "queued"
        assert retry_result["parser_name"] == "hplc"

    @pytest.mark.asyncio
    async def test_retry_wrong_status(self):
        """Retry a queued job returns cannot_retry."""
        # Create a failed job then re-queue it
        ingest_result = await ingest_file(
            file_name="corrupt.csv",
            file_content_bytes=b"\x00\x01binary",
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]
        await retry_ingest(job_id=job_id)  # now it's "queued"

        # Try to retry again
        result = await retry_ingest(job_id=job_id)
        assert result["status"] == "cannot_retry"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_retry_with_unknown_parser(self):
        """Retry with an unknown parser name returns error."""
        ingest_result = await ingest_file(
            file_name="corrupt.csv",
            file_content_bytes=b"\x00\x01binary",
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        result = await retry_ingest(job_id=job_id, parser_name="nonexistent")
        assert result["status"] == "error"
        assert "nonexistent" in result["error"]


# ---------------------------------------------------------------------------
# list_parsers tests
# ---------------------------------------------------------------------------


class TestListParsers:
    """Tests for the list_parsers tool."""

    @pytest.mark.asyncio
    async def test_list_parsers_returns_all_five(self):
        """All 5 MVP parsers are listed."""
        result = await list_parsers()
        assert result["total"] == 5
        assert len(result["parsers"]) == 5
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_list_parsers_has_required_fields(self):
        """Each parser entry has name, version, instrument_type, supported_extensions."""
        result = await list_parsers()
        for parser_info in result["parsers"]:
            assert "name" in parser_info
            assert "version" in parser_info
            assert "instrument_type" in parser_info
            assert "supported_extensions" in parser_info
            assert isinstance(parser_info["supported_extensions"], list)

    @pytest.mark.asyncio
    async def test_list_parsers_expected_names(self):
        """Parser names match the PARSER_REGISTRY keys."""
        result = await list_parsers()
        names = {p["name"] for p in result["parsers"]}
        expected = {"spectrophotometer", "plate_reader", "hplc", "pcr", "balance"}
        assert names == expected
