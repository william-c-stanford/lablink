"""Webhooks router — CRUD for webhook subscriptions and delivery listing.

Endpoints:
    POST   /webhooks/                 — Create a webhook subscription
    GET    /webhooks/                 — List webhooks for the current organization
    PATCH  /webhooks/{id}             — Update a webhook
    DELETE /webhooks/{id}             — Delete a webhook
    GET    /webhooks/{id}/deliveries  — List delivery attempts for a webhook
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError, ValidationError
from lablink.models.identity import Organization, User
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.schemas.webhooks import (
    WebhookCreate,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookUpdate,
)
from lablink.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_webhook_svc = WebhookService()


# ---------------------------------------------------------------------------
# POST /webhooks/
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=Envelope[WebhookResponse],
    status_code=201,
    operation_id="create_webhook",
    response_model_exclude_none=True,
)
async def create_webhook(
    body: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Create a new webhook subscription."""
    try:
        webhook = await _webhook_svc.create(
            db,
            organization_id=org.id,
            url=body.url,
            events=body.events,
            secret=body.secret,
            created_by=user.id,
        )
    except ValueError as exc:
        raise ValidationError(
            message=str(exc),
            suggestion="Check the URL and event types.",
        )
    return success_response(data=WebhookResponse.model_validate(webhook))


# ---------------------------------------------------------------------------
# GET /webhooks/
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=Envelope[list[WebhookResponse]],
    operation_id="list_webhooks",
    response_model_exclude_none=True,
)
async def list_webhooks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List webhook subscriptions for the current organization."""
    webhooks, total = await _webhook_svc.list(
        db, organization_id=org.id, page=page, page_size=page_size
    )
    return success_response(
        data=[WebhookResponse.model_validate(w) for w in webhooks],
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# PATCH /webhooks/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{webhook_id}",
    response_model=Envelope[WebhookResponse],
    operation_id="update_webhook",
    response_model_exclude_none=True,
)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Update a webhook's URL, events, or active status."""
    try:
        webhook = await _webhook_svc.update(
            db,
            webhook_id,
            organization_id=org.id,
            url=body.url,
            events=body.events,
            is_active=body.is_active,
        )
    except ValueError as exc:
        raise ValidationError(
            message=str(exc),
            suggestion="Check the URL and event types.",
        )

    if webhook is None:
        raise NotFoundError(
            message=f"Webhook '{webhook_id}' not found",
            suggestion="Use list_webhooks to find valid webhook IDs.",
        )
    return success_response(data=WebhookResponse.model_validate(webhook))


# ---------------------------------------------------------------------------
# DELETE /webhooks/{id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{webhook_id}",
    response_model=Envelope[dict],
    operation_id="delete_webhook",
    response_model_exclude_none=True,
)
async def delete_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Delete a webhook subscription."""
    deleted = await _webhook_svc.delete(db, webhook_id, organization_id=org.id)
    if not deleted:
        raise NotFoundError(
            message=f"Webhook '{webhook_id}' not found",
            suggestion="Use list_webhooks to find valid webhook IDs.",
        )
    return success_response(data={"deleted": True})


# ---------------------------------------------------------------------------
# GET /webhooks/{id}/deliveries
# ---------------------------------------------------------------------------


@router.get(
    "/{webhook_id}/deliveries",
    response_model=Envelope[list[WebhookDeliveryResponse]],
    operation_id="list_webhook_deliveries",
    response_model_exclude_none=True,
)
async def list_deliveries(
    webhook_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List delivery attempts for a specific webhook."""
    # Verify webhook exists and belongs to org
    webhook = await _webhook_svc.get(db, webhook_id, organization_id=org.id)
    if webhook is None:
        raise NotFoundError(
            message=f"Webhook '{webhook_id}' not found",
            suggestion="Use list_webhooks to find valid webhook IDs.",
        )

    deliveries, total = await _webhook_svc.list_deliveries(
        db, webhook_id, page=page, page_size=page_size
    )

    return success_response(
        data=[WebhookDeliveryResponse.model_validate(d) for d in deliveries],
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )
