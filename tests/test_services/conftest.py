"""Shared fixtures for service layer tests.

Creates an in-memory SQLite database with all tables for each test function.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import Settings, Environment
from app.models import Base


@pytest.fixture
def test_settings() -> Settings:
    """Settings configured for testing with in-memory SQLite."""
    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        debug=False,
        secret_key="test-secret-key-for-jwt",
        jwt_expire_minutes=30,
        local_storage_path="/tmp/lablink-test-storage",
        storage_backend="local",
    )


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """Create in-memory SQLite async engine with all tables."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    """Async session for a single test — rolls back on teardown."""
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as sess:
        yield sess
        # Roll back any uncommitted changes
        await sess.rollback()
