"""Tests for audit event schemas, service layer, and API endpoints."""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Environment, Settings
from app.core.database import get_session
from app.main import create_app
from app.models.base import Base
from app.models.system import AuditAction, AuditLog
from app.schemas.audit import (
    AuditChainLink,
    AuditChainVerification,
    AuditEventCreate,
    AuditEventRead,
)
from app.services.audit import (
    create_audit_event,
    create_audit_event_from_schema,
    get_audit_event_by_id,
    list_audit_events,
    verify_audit_chain,
    verify_chain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        debug=False,
    )


@pytest_asyncio.fixture
async def engine(test_settings):
    eng = create_async_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def app(test_settings, engine):
    application = create_app(settings=test_settings)

    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def override_session():
        async with factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    application.dependency_overrides[get_session] = override_session
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestAuditEventCreateSchema:
    """Tests for AuditEventCreate Pydantic schema."""

    def test_valid_create_schema(self):
        event = AuditEventCreate(
            action=AuditAction.CREATE,
            resource_type="experiment",
            resource_id=str(uuid.uuid4()),
            actor_id=str(uuid.uuid4()),
            summary="Created experiment X",
        )
        assert event.action == AuditAction.CREATE
        assert event.resource_type == "experiment"
        assert event.actor_type == "user"  # default

    def test_create_schema_defaults(self):
        event = AuditEventCreate(
            action=AuditAction.UPLOAD,
            resource_type="file",
            summary="Uploaded a file",
        )
        assert event.resource_id is None
        assert event.actor_id is None
        assert event.actor_type == "user"
        assert event.detail is None
        assert event.metadata is None

    def test_create_schema_with_metadata(self):
        event = AuditEventCreate(
            action=AuditAction.PARSE,
            resource_type="file",
            summary="Parsed HPLC file",
            metadata={"parser": "hplc", "rows": 42},
        )
        assert event.metadata == {"parser": "hplc", "rows": 42}

    def test_create_schema_all_actor_types(self):
        for actor_type in ("user", "system", "agent"):
            event = AuditEventCreate(
                action=AuditAction.CREATE,
                resource_type="test",
                summary="test",
                actor_type=actor_type,
            )
            assert event.actor_type == actor_type

    def test_create_schema_invalid_action(self):
        with pytest.raises(Exception):
            AuditEventCreate(
                action="INVALID_ACTION",
                resource_type="test",
                summary="test",
            )


class TestAuditEventReadSchema:
    """Tests for AuditEventRead Pydantic schema."""

    def test_read_schema_from_attributes(self):
        """Schema can be constructed from ORM-like attributes."""
        data = {
            "id": str(uuid.uuid4()),
            "sequence": 1,
            "action": "CREATE",
            "resource_type": "experiment",
            "resource_id": None,
            "actor_id": None,
            "actor_type": "user",
            "summary": "Created experiment",
            "detail": None,
            "metadata_json": None,
            "previous_hash": None,
            "entry_hash": "abc123",
            "timestamp": "2026-03-06T12:00:00+00:00",
        }
        event = AuditEventRead(**data)
        assert event.sequence == 1
        assert event.entry_hash == "abc123"

    def test_read_schema_with_metadata_json(self):
        data = {
            "id": str(uuid.uuid4()),
            "sequence": 2,
            "action": "PARSE",
            "resource_type": "file",
            "resource_id": str(uuid.uuid4()),
            "actor_id": str(uuid.uuid4()),
            "actor_type": "agent",
            "summary": "Parsed file",
            "detail": "Detailed diff",
            "metadata_json": json.dumps({"parser": "hplc"}),
            "previous_hash": "prev123",
            "entry_hash": "hash456",
            "timestamp": "2026-03-06T12:00:00+00:00",
        }
        event = AuditEventRead(**data)
        assert event.parsed_metadata == {"parser": "hplc"}


class TestAuditChainVerificationSchema:
    """Tests for AuditChainVerification Pydantic schema."""

    def test_valid_chain_schema(self):
        result = AuditChainVerification(
            valid=True,
            total_entries=10,
            invalid_entries=0,
            checked_range=[1, 10],
        )
        assert result.valid is True
        assert result.suggestion is None
        assert result.details == []

    def test_broken_chain_schema(self):
        result = AuditChainVerification(
            valid=False,
            total_entries=10,
            invalid_entries=1,
            first_invalid_sequence=5,
            checked_range=[1, 10],
            suggestion="Chain integrity broken at sequence 5.",
            details=[
                AuditChainLink(
                    sequence=5,
                    id="abc",
                    expected_hash="expected",
                    stored_hash="stored",
                    valid=False,
                ),
            ],
        )
        assert result.valid is False
        assert result.first_invalid_sequence == 5
        assert len(result.details) == 1


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

class TestAuditService:
    """Tests for the audit service layer."""

    @pytest.mark.asyncio
    async def test_create_audit_event(self, session: AsyncSession):
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Created experiment",
        )
        await session.commit()

        assert entry.id is not None
        assert entry.sequence == 1
        assert entry.action == "CREATE"
        assert entry.previous_hash is None
        assert entry.entry_hash != ""

    @pytest.mark.asyncio
    async def test_hash_chain_linking(self, session: AsyncSession):
        entry1 = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="First event",
        )
        await session.flush()

        entry2 = await create_audit_event(
            session,
            action=AuditAction.UPDATE,
            resource_type="experiment",
            summary="Second event",
        )
        await session.commit()

        assert entry2.previous_hash == entry1.entry_hash
        assert entry2.sequence == 2

    @pytest.mark.asyncio
    async def test_create_from_schema(self, session: AsyncSession):
        schema = AuditEventCreate(
            action=AuditAction.UPLOAD,
            resource_type="file",
            summary="Uploaded file",
            metadata={"filename": "test.csv"},
        )
        read = await create_audit_event_from_schema(session, schema)
        await session.commit()

        assert isinstance(read, AuditEventRead)
        assert read.action == "UPLOAD"
        assert read.resource_type == "file"

    @pytest.mark.asyncio
    async def test_list_audit_events_pagination(self, session: AsyncSession):
        for i in range(5):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()
        await session.commit()

        events, total = await list_audit_events(
            session, page=1, page_size=3,
        )
        assert total == 5
        assert len(events) == 3

        events2, _ = await list_audit_events(
            session, page=2, page_size=3,
        )
        assert len(events2) == 2

    @pytest.mark.asyncio
    async def test_list_audit_events_filter_by_resource_type(self, session: AsyncSession):
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Experiment event",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.UPLOAD,
            resource_type="file",
            summary="File event",
        )
        await session.commit()

        events, total = await list_audit_events(
            session, resource_type="file",
        )
        assert total == 1
        assert events[0].resource_type == "file"

    @pytest.mark.asyncio
    async def test_list_audit_events_filter_by_action(self, session: AsyncSession):
        await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Create event",
        )
        await session.flush()
        await create_audit_event(
            session,
            action=AuditAction.DELETE,
            resource_type="experiment",
            summary="Delete event",
        )
        await session.commit()

        events, total = await list_audit_events(
            session, action="DELETE",
        )
        assert total == 1
        assert events[0].action == "DELETE"

    @pytest.mark.asyncio
    async def test_get_audit_event_by_id(self, session: AsyncSession):
        entry = await create_audit_event(
            session,
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Test event",
        )
        await session.commit()

        result = await get_audit_event_by_id(session, entry.id)
        assert result is not None
        assert result.id == entry.id

    @pytest.mark.asyncio
    async def test_get_audit_event_by_id_not_found(self, session: AsyncSession):
        result = await get_audit_event_by_id(session, str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_audit_chain_valid(self, session: AsyncSession):
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()
        await session.commit()

        result = await verify_audit_chain(session)
        assert result.valid is True
        assert result.total_entries == 3
        assert result.invalid_entries == 0
        assert result.checked_range == [1, 3]

    @pytest.mark.asyncio
    async def test_verify_audit_chain_empty(self, session: AsyncSession):
        result = await verify_audit_chain(session)
        assert result.valid is True
        assert result.total_entries == 0
        assert result.checked_range == []

    @pytest.mark.asyncio
    async def test_verify_audit_chain_verbose(self, session: AsyncSession):
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()
        await session.commit()

        result = await verify_audit_chain(session, verbose=True)
        assert result.valid is True
        assert len(result.details) == 3  # all entries included in verbose

    @pytest.mark.asyncio
    async def test_verify_audit_chain_detects_tamper(self, session: AsyncSession):
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()
        await session.commit()

        # Tamper with the second entry's hash
        await session.execute(
            text("UPDATE audit_logs SET entry_hash = 'tampered' WHERE sequence = 2")
        )
        await session.commit()

        result = await verify_audit_chain(session)
        assert result.valid is False
        assert result.invalid_entries >= 1
        assert result.suggestion is not None
        assert "tamper" in result.suggestion.lower() or "broken" in result.suggestion.lower()

    @pytest.mark.asyncio
    async def test_verify_audit_chain_range(self, session: AsyncSession):
        for i in range(5):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()
        await session.commit()

        result = await verify_audit_chain(
            session, start_sequence=2, end_sequence=4,
        )
        assert result.total_entries == 3
        assert result.checked_range == [2, 4]

    @pytest.mark.asyncio
    async def test_legacy_verify_chain(self, session: AsyncSession):
        """Test the legacy verify_chain interface still works."""
        for i in range(3):
            await create_audit_event(
                session,
                action=AuditAction.CREATE,
                resource_type="experiment",
                summary=f"Event {i}",
            )
            await session.flush()
        await session.commit()

        result = await verify_chain(session)
        assert result.is_intact is True
        assert result.total_entries == 3


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestAuditEndpoints:
    """Tests for audit API endpoints."""

    @pytest.mark.asyncio
    async def test_create_audit_event_endpoint(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "experiment",
                "summary": "Created experiment via API",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["action"] == "CREATE"
        assert body["data"]["resource_type"] == "experiment"
        assert body["data"]["entry_hash"] is not None
        assert body["errors"] == []

    @pytest.mark.asyncio
    async def test_create_audit_event_with_metadata(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "PARSE",
                "resource_type": "file",
                "summary": "Parsed HPLC file",
                "metadata": {"parser": "hplc", "rows": 42},
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["resource_type"] == "file"

    @pytest.mark.asyncio
    async def test_create_audit_event_invalid_action(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "NOT_AN_ACTION",
                "resource_type": "test",
                "summary": "test",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0

    @pytest.mark.asyncio
    async def test_list_audit_events_endpoint(self, client: AsyncClient):
        # Create some events
        for i in range(3):
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": "CREATE",
                    "resource_type": "experiment",
                    "summary": f"Event {i}",
                },
            )

        resp = await client.get("/api/v1/audit/events")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 3
        assert body["meta"]["total"] == 3
        assert body["meta"]["page"] == 1

    @pytest.mark.asyncio
    async def test_list_audit_events_with_filters(self, client: AsyncClient):
        await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "experiment",
                "summary": "Experiment event",
            },
        )
        await client.post(
            "/api/v1/audit/events",
            json={
                "action": "UPLOAD",
                "resource_type": "file",
                "summary": "File event",
            },
        )

        resp = await client.get(
            "/api/v1/audit/events",
            params={"resource_type": "file"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["total"] == 1
        assert body["data"][0]["resource_type"] == "file"

    @pytest.mark.asyncio
    async def test_list_audit_events_pagination(self, client: AsyncClient):
        for i in range(5):
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": "CREATE",
                    "resource_type": "experiment",
                    "summary": f"Event {i}",
                },
            )

        resp = await client.get(
            "/api/v1/audit/events",
            params={"page": 1, "page_size": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["meta"]["total"] == 5
        assert body["meta"]["page_size"] == 2

    @pytest.mark.asyncio
    async def test_get_audit_event_endpoint(self, client: AsyncClient):
        # Create an event
        create_resp = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "experiment",
                "summary": "Test event",
            },
        )
        event_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/audit/events/{event_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == event_id

    @pytest.mark.asyncio
    async def test_get_audit_event_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/audit/events/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["errors"][0]["code"] == "not_found"
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_verify_chain_endpoint_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/audit/verify")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid"] is True
        assert body["data"]["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_verify_chain_endpoint_valid(self, client: AsyncClient):
        for i in range(3):
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": "CREATE",
                    "resource_type": "experiment",
                    "summary": f"Event {i}",
                },
            )

        resp = await client.get("/api/v1/audit/verify")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid"] is True
        assert body["data"]["total_entries"] == 3
        assert body["data"]["invalid_entries"] == 0

    @pytest.mark.asyncio
    async def test_verify_chain_endpoint_verbose(self, client: AsyncClient):
        for i in range(3):
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": "CREATE",
                    "resource_type": "experiment",
                    "summary": f"Event {i}",
                },
            )

        resp = await client.get(
            "/api/v1/audit/verify",
            params={"verbose": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid"] is True
        assert len(body["data"]["details"]) == 3

    @pytest.mark.asyncio
    async def test_verify_chain_endpoint_range(self, client: AsyncClient):
        for i in range(5):
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": "CREATE",
                    "resource_type": "experiment",
                    "summary": f"Event {i}",
                },
            )

        resp = await client.get(
            "/api/v1/audit/verify",
            params={"start_sequence": 2, "end_sequence": 4},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total_entries"] == 3
        assert body["data"]["checked_range"] == [2, 4]

    @pytest.mark.asyncio
    async def test_envelope_structure_on_all_endpoints(self, client: AsyncClient):
        """All endpoints return proper Envelope structure."""
        # POST create
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "test",
                "summary": "test",
            },
        )
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert "timestamp" in body["meta"]

        # GET list
        resp = await client.get("/api/v1/audit/events")
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body

        # GET verify
        resp = await client.get("/api/v1/audit/verify")
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body

    @pytest.mark.asyncio
    async def test_request_id_in_response(self, client: AsyncClient):
        """X-Request-ID is echoed back."""
        request_id = str(uuid.uuid4())
        resp = await client.get(
            "/api/v1/audit/events",
            headers={"X-Request-ID": request_id},
        )
        assert resp.headers.get("X-Request-ID") == request_id
