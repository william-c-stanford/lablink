"""Ingestor toolset — 4 MCP tools for data ingestion.

Tools:
    ingest_file       — Submit a file for parsing by a specific or auto-detected parser.
    check_ingest_status — Check the processing status of an ingested file.
    retry_ingest      — Re-queue a failed ingestion for another parsing attempt.
    list_parsers      — List all available instrument parsers with metadata.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.ingestion import FileStatus
from app.parsers import PARSER_REGISTRY
from app.parsers.base import BaseParser, FileContext, ParseError

# ---------------------------------------------------------------------------
# In-memory ingest job tracking (dev/test — production uses Celery + Redis)
# ---------------------------------------------------------------------------

_ingest_jobs: dict[str, dict[str, Any]] = {}


def _new_job_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tool: ingest_file
# ---------------------------------------------------------------------------


async def ingest_file(
    *,
    file_name: str,
    file_content_base64: str | None = None,
    file_content_bytes: bytes | None = None,
    parser_name: str | None = None,
    instrument_id: str | None = None,
    lab_id: str | None = None,
    org_id: str | None = None,
) -> dict[str, Any]:
    """Submit a file for parsing by a specific or auto-detected parser.

    Accepts file content as base64 string or raw bytes. When parser_name is
    omitted, auto-detection tries each registered parser's can_handle() method.

    Args:
        file_name: Original filename (used for extension-based parser matching).
        file_content_base64: Base64-encoded file content (mutually exclusive with file_content_bytes).
        file_content_bytes: Raw file bytes (mutually exclusive with file_content_base64).
        parser_name: Explicit parser to use (e.g. 'spectrophotometer', 'hplc').
                     If omitted, auto-detection is attempted.
        instrument_id: ID of the instrument that produced the file.
        lab_id: ID of the lab that owns the file.
        org_id: Organization ID for context.

    Returns:
        dict with job_id, status, parser_used, and parsed result or error details.
    """
    import base64

    # Resolve file bytes
    if file_content_base64 and file_content_bytes:
        return {
            "status": "error",
            "error": "Provide either file_content_base64 or file_content_bytes, not both.",
            "suggestion": "Use file_content_base64 for text transport or file_content_bytes for binary.",
        }

    if file_content_base64:
        try:
            raw_bytes = base64.b64decode(file_content_base64)
        except Exception:
            return {
                "status": "error",
                "error": "Invalid base64 encoding in file_content_base64.",
                "suggestion": "Ensure the content is valid base64. Use base64.b64encode(data).decode() to encode.",
            }
    elif file_content_bytes:
        raw_bytes = file_content_bytes
    else:
        return {
            "status": "error",
            "error": "No file content provided.",
            "suggestion": "Provide file content via file_content_base64 or file_content_bytes parameter.",
        }

    if not raw_bytes:
        return {
            "status": "error",
            "error": "File content is empty.",
            "suggestion": "Upload a non-empty file.",
        }

    ctx = FileContext(
        file_name=file_name,
        file_bytes=raw_bytes,
        instrument_type_hint=parser_name,
        org_id=org_id,
    )

    job_id = _new_job_id()

    # Resolve parser
    parser: BaseParser | None = None
    used_parser_name: str | None = parser_name

    if parser_name:
        parser_cls = PARSER_REGISTRY.get(parser_name)
        if parser_cls is None:
            available = list(PARSER_REGISTRY.keys())
            return {
                "job_id": job_id,
                "status": "error",
                "error": f"Unknown parser: {parser_name!r}",
                "suggestion": f"Available parsers: {', '.join(available)}. Use list_parsers for details.",
                "available_parsers": available,
            }
        parser = parser_cls()
    else:
        # Auto-detect
        for name, cls in PARSER_REGISTRY.items():
            instance = cls()
            if instance.can_handle(ctx):
                parser = instance
                used_parser_name = name
                break

        if parser is None:
            return {
                "job_id": job_id,
                "status": "error",
                "error": f"No parser could auto-detect the format of {file_name!r}.",
                "suggestion": "Specify parser_name explicitly. Use list_parsers to see available parsers and their supported extensions.",
                "available_parsers": list(PARSER_REGISTRY.keys()),
            }

    # Execute parse (sync fallback — Celery would handle this async in production)
    try:
        result = parser.safe_parse(ctx)
        job_record = {
            "job_id": job_id,
            "status": FileStatus.PARSED.value,
            "parser_name": used_parser_name,
            "file_name": file_name,
            "file_hash": ctx.file_hash,
            "measurement_count": result.measurement_count,
            "sample_count": result.sample_count,
            "warning_count": len(result.warnings),
            "warnings": result.warnings,
            "instrument_type": result.instrument_type,
            "created_at": datetime.now(UTC).isoformat(),
            "parsed_result": result.model_dump(mode="json"),
        }
        _ingest_jobs[job_id] = job_record

        return {
            "job_id": job_id,
            "status": "parsed",
            "parser_used": used_parser_name,
            "file_name": file_name,
            "file_hash": ctx.file_hash,
            "measurement_count": result.measurement_count,
            "sample_count": result.sample_count,
            "warning_count": len(result.warnings),
            "warnings": result.warnings[:5],  # Truncate for summary
            "suggestion": (
                "File parsed successfully. Use check_ingest_status to retrieve full results."
                if not result.warnings
                else f"Parsed with {len(result.warnings)} warning(s). Review warnings before proceeding."
            ),
        }

    except ParseError as exc:
        job_record = {
            "job_id": job_id,
            "status": FileStatus.FAILED.value,
            "parser_name": used_parser_name,
            "file_name": file_name,
            "error": str(exc),
            "suggestion": exc.suggestion,
            "created_at": datetime.now(UTC).isoformat(),
        }
        _ingest_jobs[job_id] = job_record

        return {
            "job_id": job_id,
            "status": "failed",
            "parser_used": used_parser_name,
            "error": str(exc),
            "suggestion": exc.suggestion,
        }


# ---------------------------------------------------------------------------
# Tool: check_ingest_status
# ---------------------------------------------------------------------------


async def check_ingest_status(
    *,
    job_id: str,
    include_result: bool = False,
) -> dict[str, Any]:
    """Check the processing status of an ingested file.

    Args:
        job_id: The job ID returned by ingest_file.
        include_result: If True and status is 'parsed', include the full parsed result.

    Returns:
        dict with job status, parser info, and optionally the parsed result.
    """
    job = _ingest_jobs.get(job_id)
    if job is None:
        return {
            "status": "not_found",
            "error": f"No ingest job found with id {job_id!r}.",
            "suggestion": "Verify the job_id. Use ingest_file to start a new ingestion.",
        }

    response: dict[str, Any] = {
        "job_id": job_id,
        "status": job["status"],
        "parser_name": job.get("parser_name"),
        "file_name": job.get("file_name"),
        "created_at": job.get("created_at"),
    }

    if job["status"] == FileStatus.PARSED.value:
        response["measurement_count"] = job.get("measurement_count", 0)
        response["sample_count"] = job.get("sample_count", 0)
        response["warning_count"] = job.get("warning_count", 0)
        if include_result:
            response["parsed_result"] = job.get("parsed_result")
        response["suggestion"] = "Ingestion complete. Set include_result=True to retrieve full parsed data."

    elif job["status"] == FileStatus.FAILED.value:
        response["error"] = job.get("error")
        response["suggestion"] = job.get("suggestion", "Use retry_ingest to attempt re-parsing.")

    else:
        response["suggestion"] = f"Job is in '{job['status']}' state. Check back later."

    return response


# ---------------------------------------------------------------------------
# Tool: retry_ingest
# ---------------------------------------------------------------------------


async def retry_ingest(
    *,
    job_id: str,
    parser_name: str | None = None,
) -> dict[str, Any]:
    """Re-queue a failed ingestion for another parsing attempt.

    Optionally specify a different parser_name to try a different parser.

    Args:
        job_id: The job ID of the failed ingestion to retry.
        parser_name: Optional alternative parser to use for the retry.

    Returns:
        dict with the new job status or error if the original job cannot be retried.
    """
    job = _ingest_jobs.get(job_id)
    if job is None:
        return {
            "status": "not_found",
            "error": f"No ingest job found with id {job_id!r}.",
            "suggestion": "Verify the job_id. Use ingest_file to start a new ingestion.",
        }

    if job["status"] not in (FileStatus.FAILED.value, FileStatus.PARSED.value):
        return {
            "job_id": job_id,
            "status": "cannot_retry",
            "error": f"Job is in '{job['status']}' state, which cannot be retried.",
            "suggestion": "Only 'failed' or 'parsed' jobs can be retried. Check status with check_ingest_status.",
        }

    # We don't have original file bytes in the job record (they'd be in storage),
    # so in dev mode we report what would happen
    new_parser = parser_name or job.get("parser_name")
    if new_parser and new_parser not in PARSER_REGISTRY:
        return {
            "job_id": job_id,
            "status": "error",
            "error": f"Unknown parser: {new_parser!r}",
            "suggestion": f"Available parsers: {', '.join(PARSER_REGISTRY.keys())}",
        }

    # Mark as re-queued
    job["status"] = FileStatus.QUEUED.value
    job["parser_name"] = new_parser
    job["retry_requested_at"] = datetime.now(UTC).isoformat()

    return {
        "job_id": job_id,
        "status": "queued",
        "parser_name": new_parser,
        "suggestion": (
            "Job has been re-queued for parsing. "
            "Use check_ingest_status to monitor progress. "
            "In dev mode, re-parsing requires re-submitting file content via ingest_file."
        ),
    }


# ---------------------------------------------------------------------------
# Tool: list_parsers
# ---------------------------------------------------------------------------


async def list_parsers() -> dict[str, Any]:
    """List all available instrument parsers with metadata.

    Returns:
        dict with a list of parser descriptions including name, version,
        instrument type, and supported file extensions.
    """
    parsers_info: list[dict[str, Any]] = []

    for name, cls in PARSER_REGISTRY.items():
        instance = cls()
        parsers_info.append({
            "name": name,
            "display_name": getattr(instance, "name", name),
            "version": getattr(instance, "version", "unknown"),
            "instrument_type": getattr(instance, "instrument_type", "unknown"),
            "supported_extensions": list(getattr(instance, "supported_extensions", ())),
        })

    return {
        "total": len(parsers_info),
        "parsers": parsers_info,
        "suggestion": "Use the 'name' field as parser_name when calling ingest_file.",
    }


# ---------------------------------------------------------------------------
# Toolset registration helper
# ---------------------------------------------------------------------------


def get_ingestor_tools() -> list[dict[str, Any]]:
    """Return metadata for all ingestor tools (used by discovery)."""
    return [
        {
            "name": "ingest_file",
            "description": "Submit a file for parsing by a specific or auto-detected instrument parser.",
            "toolset": "ingestor",
            "parameters": ["file_name", "file_content_base64", "file_content_bytes", "parser_name", "instrument_id", "lab_id", "org_id"],
        },
        {
            "name": "check_ingest_status",
            "description": "Check the processing status of an ingested file by job ID.",
            "toolset": "ingestor",
            "parameters": ["job_id", "include_result"],
        },
        {
            "name": "retry_ingest",
            "description": "Re-queue a failed ingestion for another parsing attempt, optionally with a different parser.",
            "toolset": "ingestor",
            "parameters": ["job_id", "parser_name"],
        },
        {
            "name": "list_parsers",
            "description": "List all available instrument parsers with name, version, type, and supported extensions.",
            "toolset": "ingestor",
            "parameters": [],
        },
    ]
