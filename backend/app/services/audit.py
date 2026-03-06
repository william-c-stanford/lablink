"""Audit service layer with SHA-256 hash chain integrity.

Provides functions to:
- Create audit log entries with computed and linked hashes
- Verify the integrity of the full hash chain
- Query audit logs by resource, actor, or action
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import AuditAction, AuditLog
from app.schemas.audit import (
    AuditChainLink,
    AuditChainVerification,
    AuditEventCreate,
    AuditEventRead,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_latest_entry(session: AsyncSession) -> AuditLog | None:
    """Fetch the most recent audit log entry by sequence number."""
    stmt = select(AuditLog).order_by(AuditLog.sequence.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def compute_entry_hash(
    *,
    entry_id: str,
    sequence: int,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor_id: str | None,
    summary: str,
    detail: str | None,
    previous_hash: str | None,
) -> str:
    """Compute SHA-256 hash for an audit log entry.

    The hash covers all immutable content fields plus the previous hash,
    forming a chain. This matches AuditLog.compute_hash() but can be
    called before the ORM object exists.
    """
    payload = json.dumps(
        {
            "id": entry_id,
            "sequence": sequence,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "actor_id": actor_id,
            "summary": summary,
            "detail": detail,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Router-facing service functions (use Pydantic schemas)
# ---------------------------------------------------------------------------


async def create_audit_event_from_schema(
    session: AsyncSession,
    event: AuditEventCreate,
) -> AuditEventRead:
    """Create audit event from a Pydantic schema (used by router)."""
    entry = await create_audit_event(
        session,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        actor_id=event.actor_id,
        actor_type=event.actor_type,
        summary=event.summary,
        detail=event.detail,
        metadata=event.metadata,
    )
    return AuditEventRead.model_validate(entry)


async def list_audit_events(
    session: AsyncSession,
    *,
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
    total = await count_audit_entries(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        action=action,
    )

    offset = (page - 1) * page_size
    entries = await get_audit_log(
        session,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        action=AuditAction(action) if action else None,
        limit=page_size,
        offset=offset,
        order_asc=True,
    )

    events = [AuditEventRead.model_validate(e) for e in entries]
    return events, total


async def get_audit_event_by_id(
    session: AsyncSession,
    event_id: str,
) -> AuditEventRead | None:
    """Get a single audit event by ID."""
    stmt = select(AuditLog).where(AuditLog.id == event_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return AuditEventRead.model_validate(row)


async def verify_audit_chain(
    session: AsyncSession,
    *,
    start_sequence: int | None = None,
    end_sequence: int | None = None,
    verbose: bool = False,
) -> AuditChainVerification:
    """Verify the hash chain integrity of the audit log.

    Walks the chain from start to end, recomputing each entry's hash
    and checking it matches the stored hash. Also verifies that each
    entry's previous_hash matches the prior entry's entry_hash.
    """
    stmt = select(AuditLog).order_by(AuditLog.sequence.asc())

    if start_sequence is not None:
        stmt = stmt.where(AuditLog.sequence >= start_sequence)
    if end_sequence is not None:
        stmt = stmt.where(AuditLog.sequence <= end_sequence)

    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return AuditChainVerification(
            valid=True,
            total_entries=0,
            invalid_entries=0,
            checked_range=[],
            details=[],
        )

    invalid_entries = 0
    first_invalid_sequence: int | None = None
    details: list[AuditChainLink] = []
    prev_hash: str | None = None

    for i, entry in enumerate(rows):
        expected_hash = entry.compute_hash()
        hash_valid = entry.entry_hash == expected_hash

        # Check chain link
        if i == 0 and start_sequence is None:
            chain_valid = entry.previous_hash is None
        elif i == 0:
            chain_valid = True  # can't verify backwards from mid-chain
        else:
            chain_valid = entry.previous_hash == prev_hash

        entry_valid = hash_valid and chain_valid

        link = AuditChainLink(
            sequence=entry.sequence,
            id=entry.id,
            expected_hash=expected_hash,
            stored_hash=entry.entry_hash,
            valid=entry_valid,
        )

        if not entry_valid:
            invalid_entries += 1
            if first_invalid_sequence is None:
                first_invalid_sequence = entry.sequence
            details.append(link)
        elif verbose:
            details.append(link)

        prev_hash = entry.entry_hash

    checked_range = [rows[0].sequence, rows[-1].sequence]

    suggestion = None
    if invalid_entries > 0:
        suggestion = (
            f"Chain integrity broken at sequence {first_invalid_sequence}. "
            "This may indicate data tampering or a software bug. "
            "Contact your administrator and do not modify the audit log."
        )

    return AuditChainVerification(
        valid=invalid_entries == 0,
        total_entries=len(rows),
        invalid_entries=invalid_entries,
        first_invalid_sequence=first_invalid_sequence,
        checked_range=checked_range,
        details=details,
        suggestion=suggestion,
    )


# ---------------------------------------------------------------------------
# Core service functions (used internally and by other services)
# ---------------------------------------------------------------------------


async def create_audit_event(
    session: AsyncSession,
    *,
    action: AuditAction,
    resource_type: str,
    resource_id: str | None = None,
    actor_id: str | None = None,
    actor_type: str = "user",
    summary: str,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Create a new audit log entry with hash chain linking.

    Steps:
    1. Fetch the latest entry to get its entry_hash (becomes our previous_hash)
    2. Determine the next sequence number
    3. Construct the AuditLog entry
    4. Compute and set the entry_hash
    5. Add to the session (caller controls commit)

    Args:
        session: Active async database session.
        action: The audit action type.
        resource_type: Type of resource being audited (e.g. "experiment").
        resource_id: UUID of the resource, if applicable.
        actor_id: UUID of the acting user/agent, if known.
        actor_type: Category of actor ("user", "system", "agent").
        summary: Human-readable one-line summary.
        detail: Optional longer description or diff.
        metadata: Optional dict of extra structured data.

    Returns:
        The newly created AuditLog entry (added to session, not yet committed).
    """
    # 1. Get the previous entry for chain linking
    latest = await _get_latest_entry(session)
    previous_hash = latest.entry_hash if latest else None
    next_sequence = (latest.sequence + 1) if latest else 1

    # 2. Build the entry (explicitly generate UUID since SQLAlchemy default
    #    doesn't fire in the constructor, and we need it for hash computation)
    entry = AuditLog(
        id=str(uuid.uuid4()),
        action=action.value if isinstance(action, AuditAction) else action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        actor_type=actor_type,
        summary=summary,
        detail=detail,
        previous_hash=previous_hash,
        sequence=next_sequence,
        timestamp=datetime.now(timezone.utc),
    )

    # Set metadata if provided
    if metadata is not None:
        entry.extra_metadata = metadata

    # 3. Compute entry hash (uses the entry's own id which is auto-generated)
    entry.entry_hash = compute_entry_hash(
        entry_id=entry.id,
        sequence=entry.sequence,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        actor_id=entry.actor_id,
        summary=entry.summary,
        detail=entry.detail,
        previous_hash=entry.previous_hash,
    )

    session.add(entry)
    return entry


class ChainVerificationResult:
    """Result of a hash chain verification (legacy interface)."""

    def __init__(self) -> None:
        self.valid: bool = True
        self.total_entries: int = 0
        self.verified_entries: int = 0
        self.broken_links: list[dict[str, Any]] = []
        self.hash_mismatches: list[dict[str, Any]] = []

    @property
    def is_intact(self) -> bool:
        """True if the entire chain is valid with no issues."""
        return self.valid and not self.broken_links and not self.hash_mismatches

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "valid": self.valid,
            "is_intact": self.is_intact,
            "total_entries": self.total_entries,
            "verified_entries": self.verified_entries,
            "broken_links": self.broken_links,
            "hash_mismatches": self.hash_mismatches,
        }


async def verify_chain(
    session: AsyncSession,
    *,
    resource_type: str | None = None,
    limit: int | None = None,
) -> ChainVerificationResult:
    """Verify the integrity of the audit log hash chain (legacy interface).

    Walks through every entry in sequence order and checks:
    1. Each entry's entry_hash matches its recomputed hash
    2. Each entry's previous_hash matches the prior entry's entry_hash
    """
    result = ChainVerificationResult()

    stmt = select(AuditLog).order_by(AuditLog.sequence.asc())
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = await session.execute(stmt)
    entries = list(rows.scalars().all())

    result.total_entries = len(entries)
    if not entries:
        return result

    previous_entry_hash: str | None = None

    for entry in entries:
        expected_hash = compute_entry_hash(
            entry_id=entry.id,
            sequence=entry.sequence,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            actor_id=entry.actor_id,
            summary=entry.summary,
            detail=entry.detail,
            previous_hash=entry.previous_hash,
        )

        if entry.entry_hash != expected_hash:
            result.valid = False
            result.hash_mismatches.append({
                "sequence": entry.sequence,
                "entry_id": entry.id,
                "stored_hash": entry.entry_hash,
                "expected_hash": expected_hash,
            })
        else:
            result.verified_entries += 1

        if entry.previous_hash != previous_entry_hash:
            if not (entry.sequence == entries[0].sequence and previous_entry_hash is None):
                result.valid = False
                result.broken_links.append({
                    "sequence": entry.sequence,
                    "entry_id": entry.id,
                    "stored_previous_hash": entry.previous_hash,
                    "expected_previous_hash": previous_entry_hash,
                })

        previous_entry_hash = entry.entry_hash

    return result


async def get_audit_log(
    session: AsyncSession,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_id: str | None = None,
    action: AuditAction | None = None,
    limit: int = 50,
    offset: int = 0,
    order_asc: bool = False,
) -> list[AuditLog]:
    """Query audit log entries with optional filters.

    Results are returned in reverse chronological order by default.
    """
    if order_asc:
        stmt = select(AuditLog).order_by(AuditLog.sequence.asc())
    else:
        stmt = select(AuditLog).order_by(AuditLog.sequence.desc())

    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(
            AuditLog.action == (action.value if isinstance(action, AuditAction) else action)
        )

    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_audit_entries(
    session: AsyncSession,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
) -> int:
    """Count total audit log entries with optional filters."""
    stmt = select(func.count(AuditLog.id))
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    result = await session.execute(stmt)
    return result.scalar_one()
