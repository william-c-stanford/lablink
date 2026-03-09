"""Audit service: append-only audit trail with SHA-256 hash chain.

Provides functions to:
- Create audit log entries with computed and linked hashes
- Verify the integrity of the hash chain
- Query audit logs by resource, actor, action, or organization

The audit trail is immutable: rows are never updated or deleted.
Each event is hash-chained to its predecessor so that any tampering
with historical records is detectable by verifying the chain.

Public API:
    - compute_event_hash -- deterministic SHA-256 for chain integrity
    - create_audit_event -- append a new event to the trail
    - create_audit_event_from_schema -- create from Pydantic schema
    - list_audit_events -- paginated query with filters
    - get_audit_event_by_id -- single event lookup
    - count_audit_events -- count with filters
    - verify_audit_chain -- walk the chain and check integrity
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.models import AuditEvent
from lablink.schemas.audit import (
    AuditChainLink,
    AuditChainVerification,
    AuditEventCreate,
    AuditEventRead,
)


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


def compute_event_hash(
    *,
    event_id: str,
    organization_id: str,
    actor_type: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None,
    previous_hash: str | None,
) -> str:
    """Compute SHA-256 hash for an audit event.

    The hash covers all immutable content fields plus the previous hash,
    forming a tamper-evident chain. The ``created_at`` timestamp is
    intentionally excluded to allow deterministic hashing before the
    server default fires.
    """
    payload = json.dumps(
        {
            "id": event_id,
            "organization_id": organization_id,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_latest_event(
    session: AsyncSession, organization_id: uuid.UUID | str
) -> AuditEvent | None:
    """Fetch the most recent audit event for an organization by created_at."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Create audit events
# ---------------------------------------------------------------------------


async def create_audit_event(
    session: AsyncSession,
    *,
    organization_id: str | uuid.UUID,
    actor_type: str = "user",
    actor_id: str | uuid.UUID | None = None,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    """Create a new audit event with hash chain linking.

    Steps:
    1. Fetch the latest event for this org to get its hash (previous_hash).
    2. Build the AuditEvent with a fresh UUID.
    3. Compute the event hash covering all content fields + previous_hash.
    4. Add to session (caller controls commit).

    Returns:
        The newly created AuditEvent (added to session, not yet committed).
    """
    # Validate actor_type
    if actor_type not in AuditEvent.VALID_ACTOR_TYPES:
        raise ValueError(
            f"Invalid actor_type '{actor_type}'; must be one of {AuditEvent.VALID_ACTOR_TYPES}"
        )

    # Get previous hash for chain linking
    latest = await _get_latest_event(session, organization_id)
    previous_hash = latest.hash if latest else None

    # Build event with explicit UUID
    event_id = uuid.uuid4()
    event = AuditEvent(
        id=event_id,
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Compute and set hash
    event.hash = compute_event_hash(
        event_id=str(event_id),
        organization_id=str(organization_id),
        actor_type=actor_type,
        actor_id=str(actor_id) if actor_id else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        details=details,
        previous_hash=previous_hash,
    )

    session.add(event)
    return event


async def create_audit_event_from_schema(
    session: AsyncSession,
    event_data: AuditEventCreate,
) -> AuditEventRead:
    """Create an audit event from a Pydantic schema (used by routers).

    Returns:
        AuditEventRead schema for the new event.
    """
    event = await create_audit_event(
        session,
        organization_id=event_data.organization_id,
        actor_type=event_data.actor_type,
        actor_id=event_data.actor_id,
        action=event_data.action,
        resource_type=event_data.resource_type,
        resource_id=event_data.resource_id,
        details=event_data.details,
        ip_address=event_data.ip_address,
        user_agent=event_data.user_agent,
    )
    await session.flush()
    return AuditEventRead.model_validate(event)


# ---------------------------------------------------------------------------
# Query audit events
# ---------------------------------------------------------------------------


async def list_audit_events(
    session: AsyncSession,
    *,
    organization_id: str | uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditEventRead], int]:
    """Query audit events with filters and pagination.

    Returns:
        Tuple of (events, total_count).
    """
    total = await count_audit_events(
        session,
        organization_id=organization_id,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        action=action,
    )

    offset = (page - 1) * page_size
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc())

    if organization_id is not None:
        stmt = stmt.where(AuditEvent.organization_id == organization_id)
    if resource_type is not None:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)

    stmt = stmt.offset(offset).limit(page_size)
    result = await session.execute(stmt)
    events = [AuditEventRead.model_validate(e) for e in result.scalars().all()]

    return events, total


async def get_audit_event_by_id(
    session: AsyncSession, event_id: str | uuid.UUID
) -> AuditEventRead | None:
    """Get a single audit event by ID."""
    stmt = select(AuditEvent).where(AuditEvent.id == event_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return AuditEventRead.model_validate(row)


async def count_audit_events(
    session: AsyncSession,
    *,
    organization_id: str | uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
) -> int:
    """Count total audit events with optional filters."""
    stmt = select(func.count(AuditEvent.id))

    if organization_id is not None:
        stmt = stmt.where(AuditEvent.organization_id == organization_id)
    if resource_type is not None:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)

    return (await session.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------


async def verify_audit_chain(
    session: AsyncSession,
    *,
    organization_id: str | uuid.UUID,
    verbose: bool = False,
) -> AuditChainVerification:
    """Verify the hash chain integrity of audit events for an organization.

    Walks through all events in chronological order, recomputing each
    event's hash and checking:
    1. The stored hash matches the recomputed hash.
    2. The chain links are consistent (each event's previous_hash matches
       the prior event's stored hash -- though with org-scoped events,
       we verify the hash content itself).

    Args:
        session: Active async database session.
        organization_id: Organization to verify.
        verbose: If True, include valid entries in the details list.

    Returns:
        AuditChainVerification with integrity results.
    """
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return AuditChainVerification(
            valid=True,
            total_entries=0,
            invalid_entries=0,
            details=[],
        )

    invalid_entries = 0
    first_invalid_id: str | None = None
    details: list[AuditChainLink] = []

    for i, event in enumerate(rows):
        expected_hash = compute_event_hash(
            event_id=str(event.id),
            organization_id=str(event.organization_id),
            actor_type=event.actor_type,
            actor_id=str(event.actor_id) if event.actor_id else None,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=str(event.resource_id),
            details=event.details,
            previous_hash=rows[i - 1].hash if i > 0 else None,
        )

        hash_valid = event.hash == expected_hash
        entry_valid = hash_valid

        link = AuditChainLink(
            sequence=i + 1,
            id=str(event.id),
            expected_hash=expected_hash,
            stored_hash=event.hash,
            valid=entry_valid,
        )

        if not entry_valid:
            invalid_entries += 1
            if first_invalid_id is None:
                first_invalid_id = str(event.id)
            details.append(link)
        elif verbose:
            details.append(link)

    suggestion = None
    if invalid_entries > 0:
        suggestion = (
            f"Chain integrity broken at event {first_invalid_id}. "
            "This may indicate data tampering or a software bug. "
            "Contact your administrator and do not modify the audit log."
        )

    return AuditChainVerification(
        valid=invalid_entries == 0,
        total_entries=len(rows),
        invalid_entries=invalid_entries,
        first_invalid_id=first_invalid_id,
        details=details,
        suggestion=suggestion,
    )
