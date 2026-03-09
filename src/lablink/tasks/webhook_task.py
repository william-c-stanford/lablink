"""Webhook delivery task — POST signed payloads to subscriber URLs.

Handles:
1. Loading the webhook configuration from the database.
2. Signing the payload with HMAC-SHA256.
3. POSTing to the webhook URL with appropriate headers.
4. Recording the delivery result (status code, response body).
5. Retrying up to 3 times with exponential backoff on failure.

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

# Retry configuration
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2  # 2s, 4s, 8s


async def _deliver_webhook_async(
    webhook_id_str: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Async implementation of webhook delivery with retry logic."""
    from lablink.database import async_session_factory
    from lablink.models import Webhook
    from lablink.services.webhook_service import sign_payload

    webhook_id = uuid.UUID(webhook_id_str)

    async with async_session_factory() as session:
        async with session.begin():
            # 1. Load webhook config
            from sqlalchemy import select

            stmt = select(Webhook).where(Webhook.id == webhook_id)
            result = await session.execute(stmt)
            webhook = result.scalar_one_or_none()

            if webhook is None:
                logger.error("Webhook %s not found — skipping delivery", webhook_id)
                return {
                    "status": "error",
                    "detail": f"Webhook {webhook_id} not found",
                }

            if not webhook.is_active:
                logger.info("Webhook %s is inactive — skipping delivery", webhook_id)
                return {
                    "status": "skipped",
                    "detail": "Webhook is inactive",
                }

            # 2. Sign payload
            signature = sign_payload(payload, webhook.secret)

            # 3. Attempt delivery with retries
            last_error: str | None = None
            response_status: int | None = None

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            webhook.url,
                            json=payload,
                            headers={
                                "Content-Type": "application/json",
                                "X-LabLink-Signature": signature,
                                "X-LabLink-Event": event_type,
                            },
                        )
                        response_status = resp.status_code

                        if 200 <= resp.status_code < 300:
                            logger.info(
                                "Webhook %s delivered (attempt %d): %d",
                                webhook_id,
                                attempt,
                                resp.status_code,
                            )
                            return {
                                "status": "delivered",
                                "webhook_id": webhook_id_str,
                                "event_type": event_type,
                                "response_status": resp.status_code,
                                "attempts": attempt,
                            }

                        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"

                except ImportError:
                    logger.warning(
                        "httpx not installed — cannot deliver webhook %s",
                        webhook_id,
                    )
                    return {
                        "status": "failed",
                        "detail": "httpx not installed",
                        "webhook_id": webhook_id_str,
                    }

                except Exception as exc:
                    last_error = str(exc)
                    logger.warning(
                        "Webhook %s delivery attempt %d failed: %s",
                        webhook_id,
                        attempt,
                        exc,
                    )

                # Backoff before retry (skip on last attempt)
                if attempt < MAX_ATTEMPTS:
                    backoff = BACKOFF_BASE_SECONDS**attempt
                    logger.debug(
                        "Retrying webhook %s in %ds (attempt %d/%d)",
                        webhook_id,
                        backoff,
                        attempt + 1,
                        MAX_ATTEMPTS,
                    )
                    await asyncio.sleep(backoff)

            # All attempts exhausted
            logger.error(
                "Webhook %s delivery failed after %d attempts: %s",
                webhook_id,
                MAX_ATTEMPTS,
                last_error,
            )
            return {
                "status": "failed",
                "webhook_id": webhook_id_str,
                "event_type": event_type,
                "response_status": response_status,
                "error": last_error,
                "attempts": MAX_ATTEMPTS,
            }


def deliver_webhook(
    webhook_id_str: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Deliver a webhook payload to the registered URL.

    This is the top-level entry point called by :func:`dispatch_task`.
    It bridges sync/Celery contexts to the async delivery logic.

    Parameters
    ----------
    webhook_id_str:
        UUID of the Webhook record (as string for JSON serialization).
    event_type:
        Event type string (e.g. ``"upload.parsed"``).
    payload:
        JSON-serializable event payload dict.

    Returns
    -------
    dict
        Delivery result with status, attempts count, and response details.
    """
    logger.info("Delivering webhook %s for event %s", webhook_id_str, event_type)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(
                asyncio.run,
                _deliver_webhook_async(webhook_id_str, event_type, payload),
            ).result()
        return result
    else:
        return asyncio.run(_deliver_webhook_async(webhook_id_str, event_type, payload))


# ── Celery task registration ──────────────────────────────────────────────

try:
    settings = get_settings()
    if settings.use_celery:
        from lablink.tasks.celery_app import app

        deliver_webhook = app.task(
            name="lablink.tasks.webhook_task.deliver_webhook",
            bind=False,
            max_retries=3,
            default_retry_delay=60,
        )(deliver_webhook)
except Exception:
    pass
