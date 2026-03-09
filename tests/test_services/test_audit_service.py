"""Tests for the audit service: create events, hash chain, verification.

Uses in-memory SQLite via the session fixture from conftest.py.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import AuditAction, AuditLog
from app.services.audit import (
    compute_entry_hash,
    create_audit_event,
    count_audit_entries,
    get_audit_log,
    verify_chain,
    verify_audit_chain,
    list_audit_events,
    get_audit_event_by_id,
    create_audit_event_from_schema,
)
from app.schemas.audit import AuditEventCreate


# ===========================================================================
# compute_entry_hash
# ===========================================================================


class TestComputeEntryHash:
    def test_deterministic(self) -> None:
        h1 = compute_entry_hash(
            entry_id="e1",
            sequence=1,
            action="CREATE",
            resource_type="experiment",
            resource_id="exp-1",
            actor_id="u1",
            summary="Created",
            detail=None,
            previous_hash=None,
        )
        h2 = compute_entry_hash(
            entry_id="e1",
            sequence=1,
            action="CREATE",
            resource_type="experiment",
            resource_id="exp-1",
            actor_id="u1",
            summary="Created",
            detail=None,
            previous_hash=None,
        )
        assert h1 == h2
        assert len(h1) == 64

    def test_different_content_different_hash(self) -> None:
        h1 = compute_entry_hash(
            entry_id="e1",
            sequence=1,
            action="CREATE",
            resource_type="experiment",
            resource_id=None,
            actor_id=None,
            summary="A",
            detail=None,
            previous_hash=None,
        )
        h2 = compute_entry_hash(
            entry_id="e1",
            sequence=1,
            action="UPDATE",
            resource_type="experiment",
            resource_id=None,
            actor_id=None,
            summary="A",
            detail=None,
            previous_hash=None,
        )
        assert h1 != h2


# ===========================================================================
# create_audit_event
# ===========================================================================


class TestCreateAuditEvent:
    async def test_creates_genesis_event(self, session: AsyncSession) -> None:
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            resource_id="exp-1",
            actor_id="user-1",
            summary="Created experiment",
        )
        assert entry.id is not None
        assert entry.sequence == 1
        assert entry.previous_hash is None
        assert entry.entry_hash is not None
        assert len(entry.entry_hash) == 64
        assert entry.action == AuditAction.CREATE.value

    async def test_chains_to_previous(self, session: AsyncSession) -> None:
        e1 = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="First event",
        )
        await session.flush()

        e2 = await create_audit_event(
            session,
            action=AuditAction.UPDATE,
            resource_type="experiment",
            summary="Second event",
        )

        assert e2.sequence == 2
        assert e2.previous_hash == e1.entry_hash
        assert e2.entry_hash != e1.entry_hash

    async def test_hash_matches_compute(self, session: AsyncSession) -> None:
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="dataset",
            actor_id="u1",
            summary="Created dataset",
            detail="With 100 data points",
        )
        expected = compute_entry_hash(
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
        assert entry.entry_hash == expected

    async def test_with_metadata(self, session: AsyncSession) -> None:
        entry = await create_audit_event(
            session,
            action=AuditAction.UPDATE,
            resource_type="experiment",
            summary="Updated fields",
            metadata={"changed_fields": ["name", "description"]},
        )
        assert entry.extra_metadata == {"changed_fields": ["name", "description"]}

    async def test_actor_type_defaults(self, session: AsyncSession) -> None:
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="test",
            summary="Test",
        )
        assert entry.actor_type == "user"

    async def test_actor_type_agent(self, session: AsyncSession) -> None:
        entry = await create_audit_event(
            session,
            action=AuditAction.UPLOAD,
            resource_type="file",
            summary="Agent upload",
            actor_type="agent",
        )
        assert entry.actor_type == "agent"


# ===========================================================================
# Hash chain verification (legacy)
# ===========================================================================


class TestVerifyChain:
    async def test_empty_chain_valid(self, session: AsyncSession) -> None:
        result = await verify_chain(session)
        assert result.is_intact is True
        assert result.total_entries == 0

    async def test_single_entry_valid(self, session: AsyncSession) -> None:
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="test",
            summary="Only entry",
        )
        await session.flush()

        result = await verify_chain(session)
        assert result.is_intact is True
        assert result.total_entries == 1
        assert result.verified_entries == 1

    async def test_multi_entry_chain_valid(self, session: AsyncSession) -> None:
        for i in range(5):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()

        result = await verify_chain(session)
        assert result.is_intact is True
        assert result.total_entries == 5
        assert result.verified_entries == 5
        assert result.broken_links == []
        assert result.hash_mismatches == []

    async def test_tampered_hash_detected(self, session: AsyncSession) -> None:
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        # Tamper with the second entry's hash
        from sqlalchemy import select

        stmt = select(AuditLog).where(AuditLog.sequence == 2)
        row = (await session.execute(stmt)).scalar_one()
        row.entry_hash = "tampered_hash_value_" + "0" * 44  # 64 chars

        result = await verify_chain(session)
        assert result.is_intact is False
        assert len(result.hash_mismatches) >= 1

    async def test_filter_by_resource_type(self, session: AsyncSession) -> None:
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Exp event",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="dataset",
            summary="Dataset event",
        )
        await session.flush()

        result = await verify_chain(session, resource_type="experiment")
        assert result.total_entries == 1

    async def test_limit_entries(self, session: AsyncSession) -> None:
        for i in range(10):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        result = await verify_chain(session, limit=5)
        assert result.total_entries == 5


# ===========================================================================
# Hash chain verification (Pydantic schema-based)
# ===========================================================================


class TestVerifyAuditChain:
    async def test_empty_chain(self, session: AsyncSession) -> None:
        result = await verify_audit_chain(session)
        assert result.valid is True
        assert result.total_entries == 0

    async def test_valid_chain(self, session: AsyncSession) -> None:
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        result = await verify_audit_chain(session)
        assert result.valid is True
        assert result.total_entries == 3
        assert result.invalid_entries == 0
        assert result.suggestion is None

    async def test_broken_chain_has_suggestion(self, session: AsyncSession) -> None:
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        # Tamper
        from sqlalchemy import select

        stmt = select(AuditLog).where(AuditLog.sequence == 2)
        row = (await session.execute(stmt)).scalar_one()
        row.entry_hash = "x" * 64

        result = await verify_audit_chain(session)
        assert result.valid is False
        assert result.suggestion is not None
        assert "tamper" in result.suggestion.lower() or "broken" in result.suggestion.lower()

    async def test_verbose_mode(self, session: AsyncSession) -> None:
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        result = await verify_audit_chain(session, verbose=True)
        assert result.valid is True
        assert len(result.details) == 3  # All entries in verbose


# ===========================================================================
# get_audit_log / count / query
# ===========================================================================


class TestGetAuditLog:
    async def test_query_by_resource_type(self, session: AsyncSession) -> None:
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Exp",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="dataset",
            summary="DS",
        )
        await session.flush()

        entries = await get_audit_log(session, resource_type="experiment")
        assert len(entries) == 1
        assert entries[0].resource_type == "experiment"

    async def test_query_by_action(self, session: AsyncSession) -> None:
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="test",
            summary="Create",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.DELETE,
            resource_type="test",
            summary="Delete",
        )
        await session.flush()

        entries = await get_audit_log(session, action=AuditAction.DELETE)
        assert len(entries) == 1
        assert entries[0].action == AuditAction.DELETE.value

    async def test_pagination(self, session: AsyncSession) -> None:
        for i in range(10):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        page1 = await get_audit_log(session, limit=3, offset=0)
        page2 = await get_audit_log(session, limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].id != page2[0].id

    async def test_count(self, session: AsyncSession) -> None:
        for i in range(5):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        total = await count_audit_entries(session)
        assert total == 5

    async def test_count_filtered(self, session: AsyncSession) -> None:
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Exp",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="dataset",
            summary="DS",
        )
        await session.flush()

        count = await count_audit_entries(session, resource_type="experiment")
        assert count == 1


# ===========================================================================
# Schema-based service functions
# ===========================================================================


class TestAuditEventFromSchema:
    async def test_create_from_schema(self, session: AsyncSession) -> None:
        schema = AuditEventCreate(
            action=AuditAction.CREATE,
            resource_type="experiment",
            resource_id="exp-1",
            summary="Created experiment",
        )
        read = await create_audit_event_from_schema(session, schema)
        assert read.id is not None
        assert read.action == "CREATE"
        assert read.resource_type == "experiment"
        assert read.entry_hash is not None


class TestListAuditEvents:
    async def test_list_with_pagination(self, session: AsyncSession) -> None:
        for i in range(5):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Event {i}",
            )
            await session.flush()

        events, total = await list_audit_events(session, page=1, page_size=2)
        assert total == 5
        assert len(events) == 2

    async def test_list_filtered(self, session: AsyncSession) -> None:
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Exp",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.UPDATE,
            resource_type="experiment",
            summary="Updated",
        )
        await session.flush()

        events, total = await list_audit_events(
            session,
            action="UPDATE",
        )
        assert total == 1
        assert events[0].action == "UPDATE"


class TestGetAuditEventById:
    async def test_found(self, session: AsyncSession) -> None:
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="test",
            summary="Test",
        )
        await session.flush()

        result = await get_audit_event_by_id(session, entry.id)
        assert result is not None
        assert result.id == entry.id

    async def test_not_found(self, session: AsyncSession) -> None:
        result = await get_audit_event_by_id(session, "nonexistent")
        assert result is None
