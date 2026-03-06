"""Tests for Ingestor toolset (4 tools): ingest_file, check_ingest_status, retry_ingest, list_parsers.

Ingestor tools are async functions called directly (not via FastMCP dispatch).
"""

import base64

import pytest

from app.mcp_server.tools.ingestor import (
    _ingest_jobs,
    check_ingest_status,
    ingest_file,
    list_parsers,
    retry_ingest,
)


@pytest.fixture(autouse=True)
def clear_ingest_jobs():
    """Clear in-memory job tracker between tests."""
    _ingest_jobs.clear()
    yield
    _ingest_jobs.clear()


class TestIngestFile:
    """Tests for ingest_file tool."""

    @pytest.mark.asyncio
    async def test_ingest_with_base64_and_parser(self, sample_spectro_csv_b64: str):
        """Ingest a spectrophotometer CSV via base64 with explicit parser."""
        result = await ingest_file(
            file_name="test_spectro.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        assert result["status"] == "parsed"
        assert result["parser_used"] == "spectrophotometer"
        assert "job_id" in result
        assert result["measurement_count"] > 0

    @pytest.mark.asyncio
    async def test_ingest_with_raw_bytes(self, sample_spectro_csv: bytes):
        """Ingest with raw bytes and explicit parser."""
        result = await ingest_file(
            file_name="test.csv",
            file_content_bytes=sample_spectro_csv,
            parser_name="spectrophotometer",
        )
        assert result["status"] == "parsed"

    @pytest.mark.asyncio
    async def test_no_content_returns_error(self):
        """Ingesting without content returns error with suggestion."""
        result = await ingest_file(file_name="empty.csv")
        assert result["status"] == "error"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_both_content_types_returns_error(
        self, sample_spectro_csv: bytes, sample_spectro_csv_b64: str
    ):
        """Providing both base64 and bytes returns error."""
        result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            file_content_bytes=sample_spectro_csv,
        )
        assert result["status"] == "error"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_unknown_parser_returns_error(self):
        """Unknown parser name returns error with available parsers."""
        result = await ingest_file(
            file_name="test.csv",
            file_content_base64=base64.b64encode(b"data").decode(),
            parser_name="nonexistent_parser",
        )
        assert result["status"] == "error"
        assert "available_parsers" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_invalid_base64_returns_error(self):
        """Invalid base64 content returns error."""
        result = await ingest_file(
            file_name="test.csv",
            file_content_base64="not-valid-base64!!!",
            parser_name="spectrophotometer",
        )
        assert result["status"] == "error"
        assert "base64" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_suggestion_on_success(self, sample_spectro_csv_b64: str):
        """Successful parse includes suggestion."""
        result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_file_hash_returned(self, sample_spectro_csv_b64: str):
        """Successful parse returns file hash."""
        result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        assert "file_hash" in result
        assert len(result["file_hash"]) == 64  # SHA-256 hex


class TestCheckIngestStatus:
    """Tests for check_ingest_status tool."""

    @pytest.mark.asyncio
    async def test_check_parsed_job(self, sample_spectro_csv_b64: str):
        """Checking a parsed job returns measurement counts."""
        ingest_result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        result = await check_ingest_status(job_id=job_id)
        assert result["status"] == "parsed"
        assert result["measurement_count"] > 0
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_check_with_include_result(self, sample_spectro_csv_b64: str):
        """include_result=True returns full parsed data."""
        ingest_result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        result = await check_ingest_status(job_id=job_id, include_result=True)
        assert "parsed_result" in result
        assert result["parsed_result"]["instrument_type"] == "spectrophotometer"

    @pytest.mark.asyncio
    async def test_nonexistent_job_returns_error(self):
        """Unknown job_id returns error with suggestion."""
        result = await check_ingest_status(job_id="fake-job-id")
        assert result["status"] == "not_found"
        assert "suggestion" in result


class TestRetryIngest:
    """Tests for retry_ingest tool."""

    @pytest.mark.asyncio
    async def test_retry_parsed_job(self, sample_spectro_csv_b64: str):
        """Can retry a parsed job (re-queue for re-processing)."""
        ingest_result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        result = await retry_ingest(job_id=job_id)
        assert result["status"] == "queued"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_retry_with_different_parser(self, sample_spectro_csv_b64: str):
        """Can retry with a different parser name."""
        ingest_result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        result = await retry_ingest(job_id=job_id, parser_name="plate_reader")
        assert result["status"] == "queued"
        assert result["parser_name"] == "plate_reader"

    @pytest.mark.asyncio
    async def test_retry_unknown_parser_returns_error(self, sample_spectro_csv_b64: str):
        """Retry with unknown parser returns error."""
        ingest_result = await ingest_file(
            file_name="test.csv",
            file_content_base64=sample_spectro_csv_b64,
            parser_name="spectrophotometer",
        )
        job_id = ingest_result["job_id"]

        result = await retry_ingest(job_id=job_id, parser_name="fake_parser")
        assert result["status"] == "error"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_retry_nonexistent_job_returns_error(self):
        """Retrying non-existent job returns error."""
        result = await retry_ingest(job_id="fake-job")
        assert result["status"] == "not_found"
        assert "suggestion" in result


class TestListParsers:
    """Tests for list_parsers tool."""

    @pytest.mark.asyncio
    async def test_returns_all_five_parsers(self):
        """list_parsers returns info for all 5 instrument parsers."""
        result = await list_parsers()
        assert result["total"] == 5
        names = {p["name"] for p in result["parsers"]}
        assert names == {"spectrophotometer", "plate_reader", "hplc", "pcr", "balance"}

    @pytest.mark.asyncio
    async def test_each_parser_has_metadata(self):
        """Each parser entry has required metadata fields."""
        result = await list_parsers()
        for parser in result["parsers"]:
            assert "name" in parser
            assert "display_name" in parser
            assert "version" in parser
            assert "instrument_type" in parser
            assert "supported_extensions" in parser
            assert isinstance(parser["supported_extensions"], list)

    @pytest.mark.asyncio
    async def test_includes_suggestion(self):
        """list_parsers includes suggestion."""
        result = await list_parsers()
        assert "suggestion" in result
        assert "ingest_file" in result["suggestion"]
