"""Shared fixtures for experiment tests."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Environment, Settings
from app.core.database import get_session
from app.main import create_app
from app.models.base import Base
from app.models.experiment import Experiment, ExperimentStatus
from app.models.identity import Organization


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


@pytest.fixture
def org_id() -> str:
    """Return a consistent org ID for tests."""
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def organization(session: AsyncSession, org_id: str) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=org_id,
        name="Test Lab",
        slug=f"test-lab-{uuid.uuid4().hex[:8]}",
        plan="free",
    )
    session.add(org)
    await session.flush()
    return org


@pytest_asyncio.fixture
async def draft_experiment(
    session: AsyncSession, organization: Organization,
) -> Experiment:
    """Create an experiment in DRAFT state."""
    exp = Experiment(
        org_id=organization.id,
        name="Test Experiment",
        description="A test experiment",
        hypothesis="Test hypothesis",
        status=ExperimentStatus.DRAFT.value,
    )
    session.add(exp)
    await session.flush()
    return exp


@pytest_asyncio.fixture
async def running_experiment(
    session: AsyncSession, organization: Organization,
) -> Experiment:
    """Create an experiment in RUNNING state."""
    exp = Experiment(
        org_id=organization.id,
        name="Running Experiment",
        status=ExperimentStatus.RUNNING.value,
    )
    session.add(exp)
    await session.flush()
    return exp


@pytest_asyncio.fixture
async def completed_experiment(
    session: AsyncSession, organization: Organization,
) -> Experiment:
    """Create an experiment in COMPLETED state."""
    exp = Experiment(
        org_id=organization.id,
        name="Completed Experiment",
        status=ExperimentStatus.COMPLETED.value,
        outcome_summary="Experiment succeeded",
        success=True,
    )
    session.add(exp)
    await session.flush()
    return exp
