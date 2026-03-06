"""Audit log router — thin router, delegates to audit service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.exceptions import NotFoundError
from app.schemas.audit import (
    AuditChainVerification,
    AuditEventCreate,
    AuditEventRead,
)
from app.schemas.envelope import Envelope
from app.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post(
    "/events",
    response_model=Envelope[AuditEventRead],
    status_code=201,
    summary="Create an audit event",
)
async def create_audit_event(
    event: AuditEventCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Envelope[AuditEventRead]:
    """Append an immutable audit event to the log."""
    result = await audit_service.create_audit_event_from_schema(session, event)
    return Envelope.ok(
        result,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/events",
    response_model=Envelope[list[AuditEventRead]],
    summary="List audit events",
)
async def list_audit_events(
    request: Request,
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    action: str | None = Query(None, description="Filter by action type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[AuditEventRead]]:
    """Query audit events with optional filters and pagination."""
    events, total = await audit_service.list_audit_events(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        action=action,
        page=page,
        page_size=page_size,
    )
    return Envelope.ok(
        events,
        request_id=getattr(request.state, "request_id", None),
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/events/{event_id}",
    response_model=Envelope[AuditEventRead],
    summary="Get a single audit event",
)
async def get_audit_event(
    event_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Envelope[AuditEventRead]:
    """Retrieve a single audit event by ID."""
    result = await audit_service.get_audit_event_by_id(session, event_id)
    if result is None:
        raise NotFoundError(
            message=f"Audit event '{event_id}' not found",
            suggestion="Use GET /api/v1/audit/events to list available audit events.",
        )
    return Envelope.ok(
        result,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/verify",
    response_model=Envelope[AuditChainVerification],
    summary="Verify audit chain integrity",
)
async def verify_audit_chain(
    request: Request,
    start_sequence: int | None = Query(None, ge=1, description="Start of sequence range to verify"),
    end_sequence: int | None = Query(None, ge=1, description="End of sequence range to verify"),
    verbose: bool = Query(False, description="Include all chain links in response, not just invalid"),
    session: AsyncSession = Depends(get_session),
) -> Envelope[AuditChainVerification]:
    """Verify the hash chain integrity of the audit log.

    Walks the chain and recomputes hashes to detect tampering.
    """
    result = await audit_service.verify_audit_chain(
        session,
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        verbose=verbose,
    )
    return Envelope.ok(
        result,
        request_id=getattr(request.state, "request_id", None),
    )
