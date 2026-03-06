"""Tests for the AuditEvent model — append-only, hash-chained audit trail."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import Base
from app.models.system import AuditAction, AuditEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def session(engine):
    """Async session backed by the shared in-memory engine (from conftest)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Table structure tests
# ---------------------------------------------------------------------------


class TestAuditEventSchema:
    """Verify the table DDL matches the specification."""

    def test_tablename(self):
        assert AuditEvent.__tablename__ == "audit_events"

    async def test_table_columns(self, engine):
        """All required columns exist."""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with engine.connect() as conn:
            columns = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in inspect(sync_conn).get_columns("audit_events")
                }
            )

        expected = [
            "id", "sequence", "actor", "actor_type", "action",
            "resource_type", "resource_id", "detail",
            "previous_hash", "event_hash", "timestamp",
        ]
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    async def test_indexes_exist(self, engine):
        """Key indexes are created."""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: {
                    idx["name"]
                    for idx in inspect(sync_conn).get_indexes("audit_events")
                }
            )

        assert "ix_audit_events_resource" in indexes
        assert "ix_audit_events_actor" in indexes
        assert "ix_audit_events_action" in indexes
        assert "ix_audit_events_timestamp" in indexes


# ---------------------------------------------------------------------------
# Hash chain tests
# ---------------------------------------------------------------------------


class TestHashChain:
    """Verify hash computation and chain integrity."""

    def _make_event(
        self,
        *,
        actor: str = "user-1",
        action: AuditAction = AuditAction.CREATE,
        resource_type: str = "experiment",
        resource_id: str | None = None,
        detail: str | None = None,
        previous_hash: str | None = None,
        sequence: int = 1,
    ) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid.uuid4()),
            sequence=sequence,
            actor=actor,
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id or str(uuid.uuid4()),
            detail=detail,
            previous_hash=previous_hash,
            event_hash="",
        )
        event.event_hash = event.compute_hash()
        return event

    def test_compute_hash_deterministic(self):
        """Same inputs produce same hash."""
        evt = self._make_event()
        h1 = evt.compute_hash()
        h2 = evt.compute_hash()
        assert h1 == h2

    def test_compute_hash_is_sha256_hex(self):
        """Hash is 64-char hex string."""
        evt = self._make_event()
        h = evt.compute_hash()
        assert len(h) == 64
        int(h, 16)  # must parse as hex

    def test_different_actions_produce_different_hashes(self):
        """Changing action changes the hash."""
        fixed_id = str(uuid.uuid4())
        fixed_rid = str(uuid.uuid4())
        e1 = self._make_event(action=AuditAction.CREATE, resource_id=fixed_rid)
        e1.id = fixed_id
        e2 = self._make_event(action=AuditAction.UPDATE, resource_id=fixed_rid)
        e2.id = fixed_id
        assert e1.compute_hash() != e2.compute_hash()

    def test_hash_chain_links(self):
        """Second event's previous_hash equals first event's event_hash."""
        e1 = self._make_event(sequence=1)
        e2 = self._make_event(sequence=2, previous_hash=e1.event_hash)
        assert e2.previous_hash == e1.event_hash
        assert e2.event_hash != e1.event_hash

    def test_genesis_event_has_null_previous_hash(self):
        """First event in chain has previous_hash=None."""
        e = self._make_event(previous_hash=None)
        assert e.previous_hash is None
        assert e.event_hash  # still has a hash

    def test_tampering_detected(self):
        """If we modify a field after hashing, the hash no longer matches."""
        evt = self._make_event()
        original_hash = evt.event_hash
        evt.actor = "tampered-actor"
        assert evt.compute_hash() != original_hash


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------


class TestAuditEventPersistence:
    """Round-trip database tests."""

    async def test_insert_and_retrieve(self, session: AsyncSession):
        """Insert an event and read it back."""
        event_id = str(uuid.uuid4())
        resource_id = str(uuid.uuid4())
        evt = AuditEvent(
            id=event_id,
            sequence=1,
            actor="test-user",
            action=AuditAction.CREATE.value,
            resource_type="experiment",
            resource_id=resource_id,
            detail=json.dumps({"key": "value"}),
            previous_hash=None,
            event_hash="abc123",
        )
        session.add(evt)
        await session.commit()

        result = await session.execute(
            select(AuditEvent).where(AuditEvent.id == event_id)
        )
        loaded = result.scalar_one()

        assert loaded.actor == "test-user"
        assert loaded.action == AuditAction.CREATE.value
        assert loaded.resource_type == "experiment"
        assert loaded.resource_id == resource_id
        assert loaded.previous_hash is None
        assert loaded.event_hash == "abc123"
        assert loaded.timestamp is not None

    async def test_detail_json_roundtrip(self, session: AsyncSession):
        """detail_dict property parses/sets JSON correctly."""
        evt = AuditEvent(
            id=str(uuid.uuid4()),
            sequence=2,
            actor="agent-007",
            action=AuditAction.UPLOAD.value,
            resource_type="file_record",
            resource_id=str(uuid.uuid4()),
            previous_hash=None,
            event_hash="dummy",
        )
        evt.detail_dict = {"filename": "data.csv", "size_bytes": 1024}
        session.add(evt)
        await session.commit()

        result = await session.execute(
            select(AuditEvent).where(AuditEvent.id == evt.id)
        )
        loaded = result.scalar_one()
        assert loaded.detail_dict == {"filename": "data.csv", "size_bytes": 1024}

    async def test_detail_dict_none(self, session: AsyncSession):
        """detail_dict returns None when detail is null."""
        evt = AuditEvent(
            id=str(uuid.uuid4()),
            sequence=3,
            actor="sys",
            action=AuditAction.LOGIN.value,
            resource_type="session",
            detail=None,
            previous_hash=None,
            event_hash="dummy",
        )
        assert evt.detail_dict is None

    async def test_hash_chain_persists(self, session: AsyncSession):
        """Insert a two-event chain and verify linkage after retrieval."""
        e1 = AuditEvent(
            id=str(uuid.uuid4()),
            sequence=4,
            actor="user-a",
            action=AuditAction.CREATE.value,
            resource_type="dataset",
            resource_id=str(uuid.uuid4()),
            previous_hash=None,
            event_hash="",
        )
        e1.event_hash = e1.compute_hash()

        e2 = AuditEvent(
            id=str(uuid.uuid4()),
            sequence=5,
            actor="user-a",
            action=AuditAction.UPDATE.value,
            resource_type="dataset",
            resource_id=e1.resource_id,
            previous_hash=e1.event_hash,
            event_hash="",
        )
        e2.event_hash = e2.compute_hash()

        session.add_all([e1, e2])
        await session.commit()

        result = await session.execute(
            select(AuditEvent).where(
                AuditEvent.sequence.in_([4, 5])
            ).order_by(AuditEvent.sequence)
        )
        events = result.scalars().all()
        assert len(events) == 2
        assert events[0].previous_hash is None
        assert events[1].previous_hash == events[0].event_hash
        # Verify hashes are still valid
        assert events[0].event_hash == events[0].compute_hash()
        assert events[1].event_hash == events[1].compute_hash()

    async def test_actor_type_default(self, session: AsyncSession):
        """actor_type defaults to 'user'."""
        evt = AuditEvent(
            id=str(uuid.uuid4()),
            sequence=6,
            actor="someone",
            action=AuditAction.LOGIN.value,
            resource_type="session",
            previous_hash=None,
            event_hash="h",
        )
        session.add(evt)
        await session.commit()

        result = await session.execute(
            select(AuditEvent).where(AuditEvent.id == evt.id)
        )
        loaded = result.scalar_one()
        assert loaded.actor_type == "user"


# ---------------------------------------------------------------------------
# Repr test
# ---------------------------------------------------------------------------


class TestAuditEventRepr:
    def test_repr(self):
        evt = AuditEvent(
            id="abc",
            actor="u1",
            action="CREATE",
            resource_type="experiment",
        )
        r = repr(evt)
        assert "AuditEvent" in r
        assert "CREATE" in r
        assert "experiment" in r
