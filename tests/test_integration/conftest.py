"""Integration test fixtures: full app with in-memory SQLite DB.

Provides a real FastAPI test client backed by an in-memory SQLite database
with all tables created. Tests run against real endpoints with real DB
operations — no mocking except for the database engine itself (in-memory).
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Environment, Settings
from app.core.database import get_session
from app.main import create_app
from app.models.base import Base


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Settings for integration tests: in-memory SQLite, test env."""
    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        secret_key="test-secret-key-for-integration-tests",
        jwt_expire_minutes=30,
        use_celery=False,
        storage_backend="local",
        local_storage_path="/tmp/lablink-test-storage",
        debug=False,
    )


@pytest_asyncio.fixture
async def engine(test_settings):
    """Create an in-memory async engine and initialize all tables."""
    eng = create_async_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """Session factory bound to the test engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """A single async session for direct DB operations in tests."""
    async with session_factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def app(test_settings, session_factory):
    """Create the FastAPI app with dependency overrides for testing."""
    application = create_app(settings=test_settings)

    async def _override_get_session():
        async with session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    async def _override_get_settings():
        return test_settings

    application.dependency_overrides[get_session] = _override_get_session
    # Override get_settings at module level to ensure settings injection
    from app.config import get_settings as _gs
    application.dependency_overrides[_gs] = lambda: test_settings

    yield application

    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# User / auth helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def registered_user(client) -> dict:
    """Register a user and return the registration response data.

    Returns dict with keys: access_token, email, password, display_name, org_name, org_slug
    """
    email = f"test-{uuid.uuid4().hex[:8]}@lablink.io"
    password = "SecurePass123!"
    payload = {
        "email": email,
        "password": password,
        "display_name": "Test User",
        "org_name": "Test Lab",
        "org_slug": f"test-lab-{uuid.uuid4().hex[:6]}",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    body = resp.json()
    token = body["data"]["access_token"]
    return {
        "access_token": token,
        "email": email,
        "password": password,
        "display_name": "Test User",
        "org_name": "Test Lab",
        "org_slug": payload["org_slug"],
    }


@pytest_asyncio.fixture
async def auth_headers(registered_user) -> dict[str, str]:
    """Authorization headers for an authenticated user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seed_org_and_instrument(session):
    """Create an organization and instrument for file upload tests.

    Returns dict with org_id, instrument_id, lab_id.
    """
    from app.models.identity import Organization
    from app.models.instrument import Instrument, InstrumentDriver

    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="Test Org", slug=f"test-{uuid.uuid4().hex[:6]}")
    session.add(org)

    driver_id = str(uuid.uuid4())
    driver = InstrumentDriver(
        id=driver_id,
        name="Test CSV Driver",
        instrument_type="spectrophotometer",
        parser_module="app.parsers.spectrophotometer",
        file_patterns="*.csv",
    )
    session.add(driver)
    await session.flush()

    instrument_id = str(uuid.uuid4())
    instrument = Instrument(
        id=instrument_id,
        name="Test UV-Vis",
        lab_id=org_id,
        driver_id=driver_id,
    )
    session.add(instrument)
    await session.commit()

    return {
        "org_id": org_id,
        "instrument_id": instrument_id,
        "lab_id": org_id,
    }
