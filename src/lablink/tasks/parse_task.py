"""Parse task — orchestrates the full file-parsing pipeline for an upload.

Lifecycle:
1. Load the Upload record from the database.
2. Retrieve raw file bytes from storage (S3 or local).
3. Detect / select the appropriate instrument parser.
4. Parse the file into a canonical ``ParsedResult``.
5. Persist the ``ParsedData`` record.
6. Update the Upload status to ``parsed`` (or ``parse_failed``).
7. Fire a webhook event (``upload.parsed`` or ``upload.parse_failed``).
8. Queue the search-index task on success.

Supports **sync mode**: when ``settings.use_celery`` is False the function
runs inline — no Celery infrastructure required.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from lablink.config import get_settings

logger = logging.getLogger(__name__)


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Return the running loop or create a new one for sync contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


async def _parse_upload_async(upload_id_str: str) -> dict[str, Any]:
    """Async implementation of the parse pipeline."""
    from lablink.database import async_session_factory
    from lablink.models import Upload
    from lablink.services.parser_service import ParserService

    upload_id = uuid.UUID(upload_id_str)

    async with async_session_factory() as session:
        async with session.begin():
            # 1. Load upload
            upload = await session.get(Upload, upload_id)
            if upload is None:
                logger.error("Upload %s not found — skipping parse task", upload_id)
                return {"status": "error", "detail": f"Upload {upload_id} not found"}

            try:
                # 2–7. Delegate to ParserService which handles the full pipeline
                parser_svc = ParserService(db=session)
                parsed_result, parsed_data = await parser_svc.parse_upload(upload_id)

                result_payload: dict[str, Any] = {
                    "status": "parsed",
                    "upload_id": upload_id_str,
                    "parsed_data_id": str(parsed_data.id),
                    "parser_name": parsed_result.parser_name,
                    "instrument_type": parsed_result.instrument_type,
                    "measurement_count": len(parsed_result.measurements),
                    "sample_count": parsed_result.sample_count,
                }

                # 7. Fire webhook event
                await _fire_webhook_event(
                    session,
                    event_type="upload.parsed",
                    payload=result_payload,
                    organization_id=upload.organization_id,
                )

                # 8. Queue index task
                _queue_index_task(upload_id_str)

                return result_payload

            except Exception as exc:
                logger.warning("Parse failed for upload %s: %s", upload_id, exc)

                # Fire failure webhook
                error_payload: dict[str, Any] = {
                    "status": "parse_failed",
                    "upload_id": upload_id_str,
                    "error": str(exc),
                }
                try:
                    await _fire_webhook_event(
                        session,
                        event_type="upload.parse_failed",
                        payload=error_payload,
                        organization_id=upload.organization_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to fire webhook for parse failure on upload %s",
                        upload_id,
                    )

                return error_payload


async def _fire_webhook_event(
    session: Any,
    *,
    event_type: str,
    payload: dict[str, Any],
    organization_id: uuid.UUID,
) -> None:
    """Dispatch a webhook event to all matching subscriptions."""
    try:
        from lablink.services.webhook_service import WebhookService

        webhook_svc = WebhookService()
        await webhook_svc.dispatch(
            session,
            event_type=event_type,
            payload=payload,
            organization_id=organization_id,
        )
    except Exception:
        logger.exception("Webhook dispatch failed for event %s", event_type)


def _queue_index_task(upload_id_str: str) -> None:
    """Queue the index task, respecting sync/async mode."""
    from lablink.tasks.dispatch import dispatch_task
    from lablink.tasks.index_task import index_parsed_data

    dispatch_task(index_parsed_data, upload_id_str)


def parse_upload_file(upload_id_str: str) -> dict[str, Any]:
    """Parse an uploaded instrument file.

    This is the top-level entry point called by :func:`dispatch_task`.
    It bridges sync/Celery contexts to the async pipeline.

    Parameters
    ----------
    upload_id_str:
        UUID of the Upload record (as a string for JSON serialization).

    Returns
    -------
    dict
        Result payload with status, upload_id, and parse details.
    """
    logger.info("Starting parse task for upload %s", upload_id_str)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Already in an async context — create a new task
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(
                asyncio.run, _parse_upload_async(upload_id_str)
            ).result()
        return result
    else:
        return asyncio.run(_parse_upload_async(upload_id_str))


# ── Celery task registration ──────────────────────────────────────────────
# Only register with Celery when it is available and configured.

try:
    settings = get_settings()
    if settings.use_celery:
        from lablink.tasks.celery_app import app

        parse_upload_file = app.task(
            name="lablink.tasks.parse_task.parse_upload_file",
            bind=False,
            max_retries=2,
            default_retry_delay=30,
        )(parse_upload_file)
except Exception:
    # Celery not configured — function stays as a plain callable
    pass
