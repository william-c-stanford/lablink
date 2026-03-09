"""Webhook service — registration, event dispatch, HMAC signing, retry logic.

Manages outbound webhook subscriptions and delivers event payloads with
HMAC-SHA256 signatures.  All functions are HTTP-unaware; they operate on
SQLAlchemy ``AsyncSession`` and domain models.

Usage::

    from lablink.services.webhook_service import WebhookService

    svc = WebhookService()
    webhook = await svc.create(db, org_id=..., url=..., events=[...], secret=..., created_by=...)
    await svc.dispatch(db, event_type="upload.completed", payload={...}, org_id=...)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.models import (
    DeliveryStatus,
    Webhook,
    WebhookDelivery,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DELIVERY_ATTEMPTS = WebhookDelivery.MAX_ATTEMPTS  # 5
WEBHOOK_SECRET_LENGTH = 32  # bytes → 64 hex chars


# ---------------------------------------------------------------------------
# HMAC-SHA256 signing
# ---------------------------------------------------------------------------


def generate_secret() -> str:
    """Generate a cryptographically secure webhook secret (hex-encoded)."""
    return secrets.token_hex(WEBHOOK_SECRET_LENGTH)


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """Compute HMAC-SHA256 signature for a JSON payload.

    Parameters
    ----------
    payload:
        The event payload dict.
    secret:
        The webhook secret (hex string).

    Returns
    -------
    str
        Hex-encoded HMAC-SHA256 digest prefixed with ``sha256=``.
    """
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(payload: dict[str, Any], secret: str, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature against a payload.

    Parameters
    ----------
    payload:
        The event payload dict.
    secret:
        The webhook secret (hex string).
    signature:
        The ``sha256=<hex>`` signature to verify.

    Returns
    -------
    bool
        True if the signature is valid.
    """
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class WebhookService:
    """Stateless service for webhook registration, dispatch, and retry."""

    # ── Registration ──────────────────────────────────────────────────

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        url: str,
        events: list[str],
        created_by: uuid.UUID,
        secret: str | None = None,
    ) -> Webhook:
        """Register a new webhook subscription.

        Parameters
        ----------
        db:
            Async database session.
        organization_id:
            Owning organization UUID.
        url:
            HTTPS callback URL.
        events:
            Event types to subscribe to (validated against Webhook.SUPPORTED_EVENTS).
        created_by:
            User UUID who registered the webhook.
        secret:
            Optional shared secret; auto-generated if not provided.

        Returns
        -------
        Webhook
            The persisted webhook record.

        Raises
        ------
        ValueError
            If ``events`` is empty or contains unsupported event types, or
            if ``url`` is empty.
        """
        if not url or not url.strip():
            raise ValueError("Webhook URL must not be empty")

        if not events:
            raise ValueError("At least one event type must be specified")

        unsupported = set(events) - Webhook.SUPPORTED_EVENTS
        if unsupported:
            raise ValueError(
                f"Unsupported event types: {', '.join(sorted(unsupported))}. "
                f"Supported: {', '.join(sorted(Webhook.SUPPORTED_EVENTS))}"
            )

        webhook = Webhook(
            organization_id=organization_id,
            url=url.strip(),
            secret=secret or generate_secret(),
            events=list(set(events)),  # deduplicate
            is_active=True,
            created_by=created_by,
        )
        db.add(webhook)
        await db.flush()
        return webhook

    async def get(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
    ) -> Webhook | None:
        """Fetch a webhook by ID, optionally scoped to an org."""
        stmt = select(Webhook).where(Webhook.id == webhook_id)
        if organization_id is not None:
            stmt = stmt.where(Webhook.organization_id == organization_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Webhook], int]:
        """List webhooks for an organization with pagination.

        Returns
        -------
        tuple[Sequence[Webhook], int]
            (webhooks, total_count)
        """
        base = select(Webhook).where(Webhook.organization_id == organization_id)
        if is_active is not None:
            base = base.where(Webhook.is_active == is_active)

        # Total count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_stmt)).scalar_one()

        # Paginated results
        stmt = (
            base.order_by(Webhook.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        result = await db.execute(stmt)
        return result.scalars().all(), total

    async def update(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        url: str | None = None,
        events: list[str] | None = None,
        is_active: bool | None = None,
        secret: str | None = None,
    ) -> Webhook | None:
        """Update a webhook's URL, events, active status, or secret.

        Returns
        -------
        Webhook | None
            The updated webhook, or None if not found.

        Raises
        ------
        ValueError
            If events contains unsupported types.
        """
        webhook = await self.get(db, webhook_id, organization_id=organization_id)
        if webhook is None:
            return None

        if url is not None:
            if not url.strip():
                raise ValueError("Webhook URL must not be empty")
            webhook.url = url.strip()

        if events is not None:
            if not events:
                raise ValueError("At least one event type must be specified")
            unsupported = set(events) - Webhook.SUPPORTED_EVENTS
            if unsupported:
                raise ValueError(f"Unsupported event types: {', '.join(sorted(unsupported))}")
            webhook.events = list(set(events))

        if is_active is not None:
            webhook.is_active = is_active

        if secret is not None:
            webhook.secret = secret

        await db.flush()
        return webhook

    async def delete(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
    ) -> bool:
        """Delete a webhook. Returns True if deleted, False if not found."""
        webhook = await self.get(db, webhook_id, organization_id=organization_id)
        if webhook is None:
            return False
        await db.delete(webhook)
        await db.flush()
        return True

    # ── Event dispatch ────────────────────────────────────────────────

    async def dispatch(
        self,
        db: AsyncSession,
        *,
        event_type: str,
        payload: dict[str, Any],
        organization_id: uuid.UUID,
    ) -> list[WebhookDelivery]:
        """Fan out an event to all active webhooks subscribed to it.

        Creates a ``WebhookDelivery`` record for each matching webhook
        and attempts delivery synchronously (inline fallback when Celery
        is disabled).

        Parameters
        ----------
        db:
            Async database session.
        event_type:
            The event type string (e.g. ``"upload.completed"``).
        payload:
            JSON-serialisable event payload.
        organization_id:
            The organization to scope webhook lookup.

        Returns
        -------
        list[WebhookDelivery]
            Delivery records created for this event.
        """
        # Find all active webhooks for the org that subscribe to this event
        stmt = select(Webhook).where(
            Webhook.organization_id == organization_id,
            Webhook.is_active.is_(True),
        )
        result = await db.execute(stmt)
        webhooks = result.scalars().all()

        deliveries: list[WebhookDelivery] = []
        for webhook in webhooks:
            if not webhook.subscribes_to(event_type):
                continue

            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_type=event_type,
                payload=payload,
                status=DeliveryStatus.pending,
                attempts=0,
            )
            db.add(delivery)
            deliveries.append(delivery)

        if deliveries:
            await db.flush()

        # Attempt delivery for each (sync inline fallback)
        for delivery in deliveries:
            webhook = await self._get_webhook_for_delivery(db, delivery.webhook_id)
            if webhook:
                await self._attempt_delivery(db, delivery, webhook)

        return deliveries

    async def _get_webhook_for_delivery(
        self, db: AsyncSession, webhook_id: uuid.UUID
    ) -> Webhook | None:
        """Fetch webhook for delivery attempt."""
        result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
        return result.scalar_one_or_none()

    async def _attempt_delivery(
        self,
        db: AsyncSession,
        delivery: WebhookDelivery,
        webhook: Webhook,
    ) -> None:
        """Attempt to deliver a webhook payload via HTTP POST.

        In the sync fallback mode (no Celery), this performs the HTTP
        request inline. Failures are logged and the delivery status is
        updated accordingly.

        Uses ``httpx`` if available, otherwise marks as failed with a
        note that no HTTP client is configured (useful for testing).
        """
        now = datetime.now(timezone.utc)
        delivery.attempts += 1
        delivery.last_attempt_at = now

        signature = sign_payload(delivery.payload, webhook.secret)

        try:
            # Try to use httpx for actual HTTP delivery
            import httpx  # noqa: F811

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook.url,
                    json=delivery.payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-LabLink-Signature": signature,
                        "X-LabLink-Event": delivery.event_type,
                        "X-LabLink-Delivery": str(delivery.id),
                    },
                )
                delivery.response_status = response.status_code
                delivery.response_body = response.text[:2000]  # truncate

                if 200 <= response.status_code < 300:
                    delivery.status = DeliveryStatus.delivered
                else:
                    delivery.status = DeliveryStatus.failed

        except ImportError:
            # httpx not installed — mark delivery based on test/dev mode
            logger.warning(
                "httpx not installed; marking delivery %s as failed "
                "(install httpx for real webhook delivery)",
                delivery.id,
            )
            delivery.status = DeliveryStatus.failed
            delivery.response_body = "httpx not installed"

        except Exception as exc:
            logger.error(
                "Webhook delivery %s to %s failed: %s",
                delivery.id,
                webhook.url,
                exc,
            )
            delivery.status = DeliveryStatus.failed
            delivery.response_body = str(exc)[:2000]

        await db.flush()

    # ── Retry ─────────────────────────────────────────────────────────

    async def retry_delivery(
        self,
        db: AsyncSession,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery | None:
        """Retry a failed delivery if attempts remain.

        Returns
        -------
        WebhookDelivery | None
            The updated delivery, or None if not found or not retryable.
        """
        result = await db.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
        delivery = result.scalar_one_or_none()
        if delivery is None or not delivery.can_retry:
            return None

        # Reset to pending for retry
        delivery.status = DeliveryStatus.pending

        webhook = await self._get_webhook_for_delivery(db, delivery.webhook_id)
        if webhook:
            await self._attempt_delivery(db, delivery, webhook)

        return delivery

    async def retry_failed_deliveries(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None = None,
        max_retries: int = 50,
    ) -> list[WebhookDelivery]:
        """Batch-retry all failed deliveries that haven't exhausted attempts.

        Parameters
        ----------
        organization_id:
            If provided, only retry deliveries for webhooks in this org.
        max_retries:
            Maximum number of deliveries to retry in one batch.

        Returns
        -------
        list[WebhookDelivery]
            Deliveries that were retried.
        """
        stmt = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == DeliveryStatus.failed,
                WebhookDelivery.attempts < MAX_DELIVERY_ATTEMPTS,
            )
            .limit(max_retries)
        )

        if organization_id is not None:
            stmt = stmt.join(Webhook).where(Webhook.organization_id == organization_id)

        result = await db.execute(stmt)
        deliveries = result.scalars().all()

        retried: list[WebhookDelivery] = []
        for delivery in deliveries:
            webhook = await self._get_webhook_for_delivery(db, delivery.webhook_id)
            if webhook:
                delivery.status = DeliveryStatus.pending
                await self._attempt_delivery(db, delivery, webhook)
                retried.append(delivery)

        return retried

    # ── Delivery listing ──────────────────────────────────────────────

    async def list_deliveries(
        self,
        db: AsyncSession,
        webhook_id: uuid.UUID,
        *,
        status: DeliveryStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[WebhookDelivery], int]:
        """List delivery attempts for a webhook with pagination.

        Returns
        -------
        tuple[Sequence[WebhookDelivery], int]
            (deliveries, total_count)
        """
        base = select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
        if status is not None:
            base = base.where(WebhookDelivery.status == status)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_stmt)).scalar_one()

        stmt = (
            base.order_by(WebhookDelivery.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        return result.scalars().all(), total

    async def get_delivery(
        self,
        db: AsyncSession,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery | None:
        """Fetch a single delivery by ID."""
        result = await db.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
        return result.scalar_one_or_none()
