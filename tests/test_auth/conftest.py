"""Auth test fixtures — app, client, and DB session with tables created."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.database import get_session
from app.main import create_app
from app.models.base import Base


@pytest.fixture
def test_settings() -> Settings:
    """Settings configured for testing with in-memory SQLite."""
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite://",
        secret_key="test-secret-key-for-auth-tests",
        jwt_expire_minutes=30,
        debug=False,
    )


@pytest_asyncio.fixture
async def engine(test_settings):
    """Create async engine with all tables."""
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
async def session_factory(engine):
    """Session factory bound to test engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def session(session_factory):
    """Async session for direct service-layer tests."""
    async with session_factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def app(test_settings, session_factory):
    """FastAPI app with DB session dependency overridden."""
    application = create_app(settings=test_settings)

    async def _override_get_session():
        async with session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    application.dependency_overrides[get_session] = _override_get_session
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    """HTTPX async client for endpoint testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
