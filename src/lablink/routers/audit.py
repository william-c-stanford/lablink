"""Audit router — query immutable audit trail events.

Endpoints:
    GET /audit/                             — List audit events for the organization
    GET /audit/{resource_type}/{resource_id} — List audit events for a specific resource
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.models.identity import Organization, User
from lablink.schemas.audit import AuditEventRead
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.services.audit_service import list_audit_events

router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# GET /audit/
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=Envelope[list[AuditEventRead]],
    operation_id="list_audit_events",
    response_model_exclude_none=True,
)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    action: str | None = Query(None, description="Filter by action, e.g. 'upload.created'"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List audit events for the current organization."""
    events, total = await list_audit_events(
        db,
        organization_id=org.id,
        action=action,
        actor_id=actor_id,
        page=page,
        page_size=page_size,
    )

    return success_response(
        data=events,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /audit/{resource_type}/{resource_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{resource_type}/{resource_id}",
    response_model=Envelope[list[AuditEventRead]],
    operation_id="list_resource_audit_events",
    response_model_exclude_none=True,
)
async def list_resource_events(
    resource_type: str,
    resource_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List audit events for a specific resource (e.g., all events for upload X)."""
    events, total = await list_audit_events(
        db,
        organization_id=org.id,
        resource_type=resource_type,
        resource_id=resource_id,
        page=page,
        page_size=page_size,
    )

    return success_response(
        data=events,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )
