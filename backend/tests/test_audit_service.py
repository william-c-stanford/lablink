"""Tests for the audit service layer with SHA-256 hash chain integrity."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.system import AuditAction, AuditLog
from app.services.audit import (
    ChainVerificationResult,
    compute_entry_hash,
    count_audit_entries,
    create_audit_event,
    get_audit_log,
    verify_chain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def audit_engine() -> AsyncEngine:
    """Create an in-memory SQLite async engine for audit tests."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(audit_engine: AsyncEngine) -> AsyncSession:
    """Create an async session for audit tests."""
    factory = async_sessionmaker(
        bind=audit_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# compute_entry_hash tests
# ---------------------------------------------------------------------------


class TestComputeEntryHash:
    """Test the standalone hash computation function."""

    def test_deterministic(self):
        """Same inputs produce the same hash."""
        kwargs = {
            "entry_id": "abc-123",
            "sequence": 1,
            "action": "CREATE",
            "resource_type": "experiment",
            "resource_id": "exp-001",
            "actor_id": "user-001",
            "summary": "Created experiment",
            "detail": None,
            "previous_hash": None,
        }
        h1 = compute_entry_hash(**kwargs)
        h2 = compute_entry_hash(**kwargs)
        assert h1 == h2

    def test_returns_64_char_hex(self):
        """SHA-256 produces a 64-character hex string."""
        h = compute_entry_hash(
            entry_id="x",
            sequence=1,
            action="CREATE",
            resource_type="test",
            resource_id=None,
            actor_id=None,
            summary="test",
            detail=None,
            previous_hash=None,
        )
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_inputs_different_hash(self):
        """Changing any field changes the hash."""
        base = {
            "entry_id": "id1",
            "sequence": 1,
            "action": "CREATE",
            "resource_type": "experiment",
            "resource_id": "r1",
            "actor_id": "a1",
            "summary": "summary",
            "detail": None,
            "previous_hash": None,
        }
        h_base = compute_entry_hash(**base)

        for field, alt_value in [
            ("entry_id", "id2"),
            ("sequence", 2),
            ("action", "UPDATE"),
            ("resource_type", "file"),
            ("resource_id", "r2"),
            ("actor_id", "a2"),
            ("summary", "different"),
            ("detail", "some detail"),
            ("previous_hash", "abc123"),
        ]:
            modified = {**base, field: alt_value}
            assert compute_entry_hash(**modified) != h_base, f"Hash unchanged for field={field}"

    def test_matches_model_compute_hash(self):
        """Service function matches AuditLog.compute_hash() for the same data."""
        entry_id = str(uuid.uuid4())
        entry = AuditLog(
            id=entry_id,
            sequence=5,
            action=AuditAction.UPLOAD.value,
            resource_type="file",
            resource_id="file-99",
            actor_id="user-1",
            summary="Uploaded file",
            detail="Some detail",
            previous_hash="deadbeef" * 8,
        )
        model_hash = entry.compute_hash()
        service_hash = compute_entry_hash(
            entry_id=entry_id,
            sequence=5,
            action=AuditAction.UPLOAD.value,
            resource_type="file",
            resource_id="file-99",
            actor_id="user-1",
            summary="Uploaded file",
            detail="Some detail",
            previous_hash="deadbeef" * 8,
        )
        assert model_hash == service_hash


# ---------------------------------------------------------------------------
# create_audit_event tests
# ---------------------------------------------------------------------------


class TestCreateAuditEvent:
    """Test audit event creation with hash chain linking."""

    @pytest.mark.asyncio
    async def test_first_entry_has_null_previous_hash(self, session: AsyncSession):
        """The first entry in an empty chain has previous_hash=None."""
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Created experiment X",
        )
        await session.flush()

        assert entry.previous_hash is None
        assert entry.sequence == 1
        assert entry.entry_hash is not None
        assert len(entry.entry_hash) == 64

    @pytest.mark.asyncio
    async def test_second_entry_links_to_first(self, session: AsyncSession):
        """The second entry's previous_hash equals the first entry's entry_hash."""
        e1 = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Created experiment",
        )
        await session.flush()

        e2 = await create_audit_event(
            session,
            action=AuditAction.UPDATE,
            resource_type="experiment",
            summary="Updated experiment",
        )
        await session.flush()

        assert e2.previous_hash == e1.entry_hash
        assert e2.sequence == 2
        assert e2.entry_hash != e1.entry_hash

    @pytest.mark.asyncio
    async def test_chain_of_three(self, session: AsyncSession):
        """Three entries form a proper chain."""
        entries = []
        for i in range(3):
            e = await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="dataset",
                resource_id=f"ds-{i}",
                summary=f"Created dataset {i}",
            )
            await session.flush()
            entries.append(e)

        assert entries[0].previous_hash is None
        assert entries[1].previous_hash == entries[0].entry_hash
        assert entries[2].previous_hash == entries[1].entry_hash

        # All hashes are unique
        hashes = [e.entry_hash for e in entries]
        assert len(set(hashes)) == 3

    @pytest.mark.asyncio
    async def test_entry_hash_is_valid(self, session: AsyncSession):
        """The stored entry_hash matches recomputation."""
        entry = await create_audit_event(
            session,
            action=AuditAction.PARSE,
            resource_type="file",
            resource_id="file-1",
            actor_id="agent-007",
            actor_type="agent",
            summary="Parsed HPLC file",
            detail="42 data points extracted",
        )
        await session.flush()

        recomputed = compute_entry_hash(
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
        assert entry.entry_hash == recomputed

    @pytest.mark.asyncio
    async def test_metadata_stored(self, session: AsyncSession):
        """Extra metadata is stored as JSON."""
        meta = {"file_size": 1024, "parser": "hplc"}
        entry = await create_audit_event(
            session,
            action=AuditAction.UPLOAD,
            resource_type="file",
            summary="Uploaded file",
            metadata=meta,
        )
        await session.flush()

        assert entry.extra_metadata == meta

    @pytest.mark.asyncio
    async def test_all_fields_persisted(self, session: AsyncSession):
        """All provided fields are correctly stored."""
        entry = await create_audit_event(
            session,
            action=AuditAction.CONFIG_CHANGE,
            resource_type="system_config",
            resource_id="cfg-1",
            actor_id="admin-1",
            actor_type="system",
            summary="Changed retention policy",
            detail="retention_days: 90 -> 180",
        )
        await session.flush()

        assert entry.action == AuditAction.CONFIG_CHANGE.value
        assert entry.resource_type == "system_config"
        assert entry.resource_id == "cfg-1"
        assert entry.actor_id == "admin-1"
        assert entry.actor_type == "system"
        assert entry.summary == "Changed retention policy"
        assert entry.detail == "retention_days: 90 -> 180"

    @pytest.mark.asyncio
    async def test_sequential_sequence_numbers(self, session: AsyncSession):
        """Sequence numbers increment monotonically."""
        for i in range(5):
            e = await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Entry {i}",
            )
            await session.flush()
            assert e.sequence == i + 1


# ---------------------------------------------------------------------------
# verify_chain tests
# ---------------------------------------------------------------------------


class TestVerifyChain:
    """Test the hash chain verification function."""

    @pytest.mark.asyncio
    async def test_empty_chain_is_valid(self, session: AsyncSession):
        """An empty audit log verifies successfully."""
        result = await verify_chain(session)
        assert result.is_intact
        assert result.total_entries == 0
        assert result.verified_entries == 0

    @pytest.mark.asyncio
    async def test_single_entry_chain_valid(self, session: AsyncSession):
        """A chain with one entry verifies successfully."""
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="First entry",
        )
        await session.flush()

        result = await verify_chain(session)
        assert result.is_intact
        assert result.total_entries == 1
        assert result.verified_entries == 1

    @pytest.mark.asyncio
    async def test_valid_chain_of_ten(self, session: AsyncSession):
        """A chain of 10 properly created entries verifies."""
        for i in range(10):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                resource_id=f"exp-{i}",
                summary=f"Created experiment {i}",
            )
            await session.flush()

        result = await verify_chain(session)
        assert result.is_intact
        assert result.total_entries == 10
        assert result.verified_entries == 10
        assert result.broken_links == []
        assert result.hash_mismatches == []

    @pytest.mark.asyncio
    async def test_detects_tampered_hash(self, session: AsyncSession):
        """Verification detects when an entry's hash has been tampered with."""
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Entry {i}",
            )
            await session.flush()

        # Tamper: change the second entry's hash directly
        stmt = text(
            "UPDATE audit_logs SET entry_hash = 'tampered_hash_value_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' "
            "WHERE sequence = 2"
        )
        await session.execute(stmt)

        result = await verify_chain(session)
        assert not result.is_intact
        assert len(result.hash_mismatches) >= 1
        tampered = result.hash_mismatches[0]
        assert tampered["sequence"] == 2
        assert tampered["stored_hash"] == "tampered_hash_value_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    @pytest.mark.asyncio
    async def test_detects_broken_chain_link(self, session: AsyncSession):
        """Verification detects when previous_hash doesn't match prior entry."""
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Entry {i}",
            )
            await session.flush()

        # Break the chain: change entry 3's previous_hash
        stmt = text(
            "UPDATE audit_logs SET previous_hash = 'wrong_previous_hash_xxxxxxxxxxxxxxxxxxxxxxxxxxx' "
            "WHERE sequence = 3"
        )
        await session.execute(stmt)

        result = await verify_chain(session)
        assert not result.is_intact
        # Should detect both a hash mismatch (previous_hash is in the hash input) and broken link
        assert len(result.broken_links) >= 1
        broken = result.broken_links[0]
        assert broken["sequence"] == 3

    @pytest.mark.asyncio
    async def test_detects_tampered_summary(self, session: AsyncSession):
        """Verification detects when content fields are altered."""
        for i in range(2):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="test",
                summary=f"Entry {i}",
            )
            await session.flush()

        # Tamper: change summary without updating hash
        stmt = text(
            "UPDATE audit_logs SET summary = 'Maliciously altered' WHERE sequence = 1"
        )
        await session.execute(stmt)

        result = await verify_chain(session)
        assert not result.is_intact
        assert len(result.hash_mismatches) >= 1
        assert result.hash_mismatches[0]["sequence"] == 1

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self, session: AsyncSession):
        """Verification can be scoped to a specific resource type."""
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="experiment", summary="Exp"
        )
        await session.flush()
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="file", summary="File"
        )
        await session.flush()
        await create_audit_event(
            session, action=AuditAction.UPDATE, resource_type="experiment", summary="Exp2"
        )
        await session.flush()

        result = await verify_chain(session, resource_type="experiment")
        assert result.total_entries == 2

    @pytest.mark.asyncio
    async def test_limit_parameter(self, session: AsyncSession):
        """Limit restricts how many entries are verified."""
        for i in range(5):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="test", summary=f"E{i}"
            )
            await session.flush()

        result = await verify_chain(session, limit=3)
        assert result.total_entries == 3
        assert result.verified_entries == 3

    @pytest.mark.asyncio
    async def test_verification_result_to_dict(self, session: AsyncSession):
        """ChainVerificationResult serializes correctly."""
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="test", summary="E1"
        )
        await session.flush()

        result = await verify_chain(session)
        d = result.to_dict()
        assert d["valid"] is True
        assert d["is_intact"] is True
        assert d["total_entries"] == 1
        assert d["verified_entries"] == 1
        assert d["broken_links"] == []
        assert d["hash_mismatches"] == []


# ---------------------------------------------------------------------------
# get_audit_log tests
# ---------------------------------------------------------------------------


class TestGetAuditLog:
    """Test querying audit log entries."""

    @pytest.mark.asyncio
    async def test_returns_newest_first(self, session: AsyncSession):
        """Entries are returned in reverse chronological order."""
        for i in range(3):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="test", summary=f"E{i}"
            )
            await session.flush()

        entries = await get_audit_log(session)
        assert len(entries) == 3
        assert entries[0].sequence == 3
        assert entries[2].sequence == 1

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self, session: AsyncSession):
        """Filter by resource_type."""
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="experiment", summary="Exp"
        )
        await session.flush()
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="file", summary="File"
        )
        await session.flush()

        entries = await get_audit_log(session, resource_type="experiment")
        assert len(entries) == 1
        assert entries[0].resource_type == "experiment"

    @pytest.mark.asyncio
    async def test_filter_by_action(self, session: AsyncSession):
        """Filter by action type."""
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="test", summary="Create"
        )
        await session.flush()
        await create_audit_event(
            session, action=AuditAction.DELETE, resource_type="test", summary="Delete"
        )
        await session.flush()

        entries = await get_audit_log(session, action=AuditAction.DELETE)
        assert len(entries) == 1
        assert entries[0].action == AuditAction.DELETE.value

    @pytest.mark.asyncio
    async def test_filter_by_actor_id(self, session: AsyncSession):
        """Filter by actor."""
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="test",
            actor_id="user-1", summary="By user 1"
        )
        await session.flush()
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="test",
            actor_id="user-2", summary="By user 2"
        )
        await session.flush()

        entries = await get_audit_log(session, actor_id="user-1")
        assert len(entries) == 1
        assert entries[0].actor_id == "user-1"

    @pytest.mark.asyncio
    async def test_filter_by_resource_id(self, session: AsyncSession):
        """Filter by resource_id."""
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="experiment",
            resource_id="exp-1", summary="Exp 1"
        )
        await session.flush()
        await create_audit_event(
            session, action=AuditAction.CREATE, resource_type="experiment",
            resource_id="exp-2", summary="Exp 2"
        )
        await session.flush()

        entries = await get_audit_log(session, resource_id="exp-1")
        assert len(entries) == 1
        assert entries[0].resource_id == "exp-1"

    @pytest.mark.asyncio
    async def test_pagination(self, session: AsyncSession):
        """Limit and offset work for pagination."""
        for i in range(10):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="test", summary=f"E{i}"
            )
            await session.flush()

        page1 = await get_audit_log(session, limit=3, offset=0)
        page2 = await get_audit_log(session, limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        # No overlap
        ids1 = {e.id for e in page1}
        ids2 = {e.id for e in page2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_order_asc(self, session: AsyncSession):
        """order_asc=True returns oldest first."""
        for i in range(3):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="test", summary=f"E{i}"
            )
            await session.flush()

        entries = await get_audit_log(session, order_asc=True)
        assert entries[0].sequence == 1
        assert entries[2].sequence == 3


# ---------------------------------------------------------------------------
# count_audit_entries tests
# ---------------------------------------------------------------------------


class TestCountAuditEntries:
    """Test counting audit entries."""

    @pytest.mark.asyncio
    async def test_count_empty(self, session: AsyncSession):
        """Empty table returns 0."""
        count = await count_audit_entries(session)
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_all(self, session: AsyncSession):
        """Count all entries."""
        for i in range(5):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="test", summary=f"E{i}"
            )
            await session.flush()

        count = await count_audit_entries(session)
        assert count == 5

    @pytest.mark.asyncio
    async def test_count_filtered_by_resource_type(self, session: AsyncSession):
        """Count with resource_type filter."""
        for i in range(3):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="experiment", summary=f"Exp{i}"
            )
            await session.flush()
        for i in range(2):
            await create_audit_event(
                session, action=AuditAction.CREATE, resource_type="file", summary=f"File{i}"
            )
            await session.flush()

        assert await count_audit_entries(session, resource_type="experiment") == 3
        assert await count_audit_entries(session, resource_type="file") == 2


# ---------------------------------------------------------------------------
# ChainVerificationResult tests
# ---------------------------------------------------------------------------


class TestChainVerificationResult:
    """Test the result object directly."""

    def test_default_is_intact(self):
        """Fresh result is valid and intact."""
        r = ChainVerificationResult()
        assert r.valid is True
        assert r.is_intact is True

    def test_not_intact_with_broken_links(self):
        """Not intact when broken links exist."""
        r = ChainVerificationResult()
        r.broken_links.append({"sequence": 2})
        assert not r.is_intact

    def test_not_intact_when_invalid(self):
        """Not intact when valid is False."""
        r = ChainVerificationResult()
        r.valid = False
        assert not r.is_intact

    def test_to_dict_keys(self):
        """to_dict includes all expected keys."""
        r = ChainVerificationResult()
        d = r.to_dict()
        expected_keys = {
            "valid", "is_intact", "total_entries",
            "verified_entries", "broken_links", "hash_mismatches",
        }
        assert set(d.keys()) == expected_keys
