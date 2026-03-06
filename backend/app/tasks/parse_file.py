"""Celery task for file parsing with sync fallback.

In production (use_celery=True), tasks are dispatched to Celery workers.
In dev/test mode (use_celery=False), tasks run inline/synchronously.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import Settings, get_settings
from app.parsers import PARSER_REGISTRY
from app.parsers.base import FileContext, ParseError

logger = logging.getLogger("lablink.tasks.parse_file")


def get_parser(parser_name: str):
    """Look up a parser by name in the registry.

    Args:
        parser_name: Key in PARSER_REGISTRY (e.g. 'spectrophotometer').

    Returns:
        An instance of the parser.

    Raises:
        ValueError: If the parser name is not found.
    """
    cls = PARSER_REGISTRY.get(parser_name)
    if cls is None:
        available = ", ".join(sorted(PARSER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown parser '{parser_name}'. Available: {available}"
        )
    return cls()


def parse_file_task(
    file_content: str | bytes,
    parser_name: str,
    file_name: str = "unknown",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Parse an instrument file and return the result as a dict.

    This function is the core task logic, designed to work both as a
    Celery task and as a synchronous function for dev/test mode.

    Args:
        file_content: Raw file content as string or bytes.
        parser_name: Name of the parser to use (e.g. 'spectrophotometer').
        file_name: Original filename for context.
        settings: Application settings (optional).

    Returns:
        Dict with keys: success, parser_name, file_name, result (or error).
    """
    cfg = settings or get_settings()
    start_time = time.monotonic()

    try:
        parser = get_parser(parser_name)
    except (KeyError, ValueError) as e:
        return {
            "success": False,
            "parser_name": parser_name,
            "file_name": file_name,
            "error": f"Unknown parser: {parser_name}",
            "suggestion": "Available parsers: spectrophotometer, plate_reader, hplc, pcr, balance",
            "duration_seconds": time.monotonic() - start_time,
        }

    try:
        # Build FileContext from raw content
        if isinstance(file_content, str):
            file_bytes = file_content.encode("utf-8")
        else:
            file_bytes = file_content

        ctx = FileContext(
            file_name=file_name,
            file_bytes=file_bytes,
            instrument_type_hint=parser_name,
        )

        result = parser.safe_parse(ctx)
        duration = time.monotonic() - start_time

        return {
            "success": True,
            "parser_name": parser_name,
            "file_name": file_name,
            "result": result.model_dump(mode="json"),
            "duration_seconds": duration,
        }
    except ParseError as e:
        duration = time.monotonic() - start_time
        return {
            "success": False,
            "parser_name": parser_name,
            "file_name": file_name,
            "error": str(e),
            "suggestion": e.suggestion or "Verify the file is a valid instrument export and not corrupted.",
            "duration_seconds": duration,
        }
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.exception("Unexpected error parsing file %s with %s", file_name, parser_name)
        return {
            "success": False,
            "parser_name": parser_name,
            "file_name": file_name,
            "error": f"Unexpected error: {e}",
            "suggestion": "Check the file format and try again. If the problem persists, contact support.",
            "duration_seconds": duration,
        }


def dispatch_parse(
    file_content: str | bytes,
    parser_name: str,
    file_name: str = "unknown",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Dispatch file parsing -- Celery async or sync fallback.

    In dev mode (use_celery=False), runs the task inline.
    In production (use_celery=True), dispatches to Celery.

    Args:
        file_content: Raw file content.
        parser_name: Parser name.
        file_name: Original filename.
        settings: Application settings.

    Returns:
        Task result dict (sync) or Celery AsyncResult info (async).
    """
    cfg = settings or get_settings()

    if not cfg.use_celery:
        # Sync fallback: run inline
        logger.info("Running parse task inline (sync fallback) for %s", file_name)
        return parse_file_task(
            file_content=file_content,
            parser_name=parser_name,
            file_name=file_name,
            settings=cfg,
        )
    else:
        # Celery dispatch (would use .delay() in production)
        # For now, still run inline since we don't have a real Celery app configured
        logger.info("Would dispatch to Celery for %s (falling back to sync)", file_name)
        return parse_file_task(
            file_content=file_content,
            parser_name=parser_name,
            file_name=file_name,
            settings=cfg,
        )
