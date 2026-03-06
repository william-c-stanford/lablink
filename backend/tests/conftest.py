"""Shared test configuration and fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Settings fixtures (shared by AC 1 and AC 2)
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_settings():
    """Create isolated test settings with in-memory SQLite."""
    from app.config import Environment, Settings

    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        debug=False,
        use_celery=False,
        use_elasticsearch=False,
        use_redis=False,
    )


# ---------------------------------------------------------------------------
# AC 1: FastAPI app factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(test_settings):
    """Create a FastAPI test app."""
    from app.main import create_app

    return create_app(settings=test_settings)


@pytest.fixture()
async def client(app):
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# AC 2: Database / SQLAlchemy fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def engine(test_settings) -> AsyncEngine:
    """Create an async engine for testing (in-memory SQLite)."""
    from app.core.database import create_engine

    eng = create_engine(test_settings)
    yield eng
    await eng.dispose()
