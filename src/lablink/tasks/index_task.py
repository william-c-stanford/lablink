"""Index task — push parsed data into the search index (Elasticsearch or mock).

Lifecycle:
1. Load the ParsedData record(s) for the given upload.
2. Build a search-indexable document from the parsed data.
3. Index the document via :class:`~lablink.services.search_service.SearchService`.
4. Update the Upload status to ``indexed``.

Supports **sync mode**: when ``settings.use_celery`` is False the function
runs inline — no Celery infrastructure required.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from lablink.config import get_settings

logger = logging.getLogger(__name__)


async def _index_parsed_data_async(upload_id_str: str) -> dict[str, Any]:
    """Async implementation of the search-indexing pipeline."""
    from sqlalchemy import select

    from lablink.database import async_session_factory
    from lablink.models import ParsedData, Upload, UploadStatus
    from lablink.services.search_service import get_search_service

    upload_id = uuid.UUID(upload_id_str)
    search_svc = get_search_service()

    async with async_session_factory() as session:
        async with session.begin():
            # 1. Load upload
            upload = await session.get(Upload, upload_id)
            if upload is None:
                logger.error("Upload %s not found — skipping index task", upload_id)
                return {"status": "error", "detail": f"Upload {upload_id} not found"}

            # 2. Load parsed data for this upload
            stmt = select(ParsedData).where(ParsedData.upload_id == upload_id)
            result = await session.execute(stmt)
            parsed_records = result.scalars().all()

            if not parsed_records:
                logger.warning("No parsed data for upload %s — skipping indexing", upload_id)
                return {
                    "status": "skipped",
                    "detail": "No parsed data found",
                    "upload_id": upload_id_str,
                }

            # 3. Ensure the org index exists
            await search_svc.ensure_index(upload.organization_id)

            # 4. Index each parsed-data record
            indexed_count = 0
            for parsed_data in parsed_records:
                document = _build_index_document(parsed_data, upload)
                await search_svc.index_document(
                    org_id=upload.organization_id,
                    doc_id=str(parsed_data.id),
                    document=document,
                )
                indexed_count += 1

            # 5. Update upload status to indexed
            upload.status = UploadStatus.indexed
            upload.indexed_at = datetime.now(timezone.utc)
            await session.flush()

            logger.info(
                "Indexed %d document(s) for upload %s",
                indexed_count,
                upload_id,
            )

            return {
                "status": "indexed",
                "upload_id": upload_id_str,
                "documents_indexed": indexed_count,
            }


def _build_index_document(parsed_data: Any, upload: Any) -> dict[str, Any]:
    """Build a search-indexable document from a ParsedData record.

    The document schema matches the Elasticsearch mapping defined in
    :func:`lablink.services.search_service.build_index_mapping`.
    """
    return {
        "upload_id": str(parsed_data.upload_id),
        "organization_id": str(parsed_data.organization_id),
        "instrument_type": parsed_data.instrument_type,
        "measurement_type": parsed_data.measurement_type,
        "parser_version": parsed_data.parser_version,
        "filename": upload.filename,
        "sample_count": parsed_data.sample_count,
        "data_summary": parsed_data.data_summary or {},
        "metadata": parsed_data.metadata_ or {},
        "created_at": (
            upload.created_at.isoformat()
            if hasattr(upload, "created_at") and upload.created_at
            else datetime.now(timezone.utc).isoformat()
        ),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }


def index_parsed_data(upload_id_str: str) -> dict[str, Any]:
    """Index parsed data for an upload into the search service.

    This is the top-level entry point called by :func:`dispatch_task`.
    It bridges sync/Celery contexts to the async indexing logic.

    Parameters
    ----------
    upload_id_str:
        UUID of the Upload record (as string for JSON serialization).

    Returns
    -------
    dict
        Result payload with status, upload_id, and count of indexed documents.
    """
    logger.info("Starting index task for upload %s", upload_id_str)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, _index_parsed_data_async(upload_id_str)).result()
        return result
    else:
        return asyncio.run(_index_parsed_data_async(upload_id_str))


# ── Celery task registration ──────────────────────────────────────────────

try:
    settings = get_settings()
    if settings.use_celery:
        from lablink.tasks.celery_app import app

        index_parsed_data = app.task(
            name="lablink.tasks.index_task.index_parsed_data",
            bind=False,
            max_retries=3,
            default_retry_delay=60,
        )(index_parsed_data)
except Exception:
    pass
