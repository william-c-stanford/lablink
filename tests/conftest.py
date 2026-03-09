"""Shared test configuration and fixtures.

Provides:
- test_settings: Settings configured for in-memory SQLite + test env
- engine: Async SQLAlchemy engine with all tables created
- session_factory / session: Async session for service-layer tests
- app: FastAPI application with DB dependency overrides
- client: HTTPX async test client
- fixtures_dir: Path to test fixtures directory
- Celery eager-mode configuration
- Per-parser fixture helpers (file bytes + FileContext)
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import Environment, Settings
from app.core.database import get_session
from app.main import create_app
from app.models.base import Base
from app.parsers.base import FileContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Celery eager-mode configuration (sync fallback for tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def celery_eager_mode():
    """Configure Celery to run tasks synchronously in tests.

    This avoids needing a running Redis/RabbitMQ broker during testing.
    Tasks execute inline, making tests deterministic.
    """
    try:
        from app.tasks.celery_app import celery_app

        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
            broker_url="memory://",
            result_backend="cache+memory://",
        )
        yield celery_app
    except (ImportError, ModuleNotFoundError):
        # Celery app may not exist yet; that's fine for tests that don't need it
        yield None


# ---------------------------------------------------------------------------
# Core fixtures: settings, engine, sessions
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    """Settings configured for testing with in-memory SQLite."""
    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        secret_key="test-secret-key-do-not-use-in-prod",
        jwt_expire_minutes=30,
        debug=False,
        use_celery=False,
        use_elasticsearch=False,
        use_redis=False,
        storage_backend="local",
        local_storage_path="/tmp/lablink-test-storage",
    )


@pytest_asyncio.fixture
async def engine(test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Create an async engine backed by in-memory SQLite with all tables."""
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
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Async session for direct service-layer tests."""
    async with session_factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# FastAPI app + HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app(test_settings: Settings, session_factory: async_sessionmaker[AsyncSession]):
    """FastAPI app with DB session dependency overridden for test isolation."""
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
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client hitting the test FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Fixture directory helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def spectrophotometer_fixtures_dir() -> Path:
    """Return path to spectrophotometer fixture files."""
    return FIXTURES_DIR / "spectrophotometer"


@pytest.fixture
def plate_reader_fixtures_dir() -> Path:
    """Return path to plate reader fixture files."""
    return FIXTURES_DIR / "plate_reader"


@pytest.fixture
def hplc_fixtures_dir() -> Path:
    """Return path to HPLC fixture files."""
    return FIXTURES_DIR / "hplc"


@pytest.fixture
def pcr_fixtures_dir() -> Path:
    """Return path to PCR fixture files."""
    return FIXTURES_DIR / "pcr"


@pytest.fixture
def balance_fixtures_dir() -> Path:
    """Return path to balance fixture files."""
    return FIXTURES_DIR / "balance"


# ---------------------------------------------------------------------------
# FileContext factory helpers for parser tests
# ---------------------------------------------------------------------------


def _load_fixture(rel_path: str) -> bytes:
    """Load fixture file bytes by path relative to fixtures dir."""
    full_path = FIXTURES_DIR / rel_path
    return full_path.read_bytes()


def _make_file_context(
    file_name: str,
    file_bytes: bytes,
    instrument_type_hint: str | None = None,
    **extra: object,
) -> FileContext:
    """Create a FileContext for parser testing."""
    return FileContext(
        file_name=file_name,
        file_bytes=file_bytes,
        instrument_type_hint=instrument_type_hint,
        extra=dict(extra) if extra else {},
    )


# --- Spectrophotometer fixtures ---


@pytest.fixture
def spectro_nanodrop_ctx() -> FileContext:
    """FileContext for NanoDrop CSV fixture."""
    data = _load_fixture("spectrophotometer/nanodrop_sample.csv")
    return _make_file_context("nanodrop_sample.csv", data, "spectrophotometer")


@pytest.fixture
def spectro_cary_ctx() -> FileContext:
    """FileContext for Cary UV-Vis scan CSV fixture."""
    data = _load_fixture("spectrophotometer/cary_uv_vis_scan.csv")
    return _make_file_context("cary_uv_vis_scan.csv", data, "spectrophotometer")


@pytest.fixture
def spectro_tsv_ctx() -> FileContext:
    """FileContext for NanoDrop TSV fixture."""
    data = _load_fixture("spectrophotometer/nanodrop_tsv.tsv")
    return _make_file_context("nanodrop_tsv.tsv", data, "spectrophotometer")


@pytest.fixture
def spectro_corrupted_ctx() -> FileContext:
    """FileContext for corrupted spectrophotometer file."""
    data = _load_fixture("spectrophotometer/corrupted.csv")
    return _make_file_context("corrupted.csv", data, "spectrophotometer")


# --- Plate reader fixtures ---


@pytest.fixture
def plate_softmax_ctx() -> FileContext:
    """FileContext for SoftMax Pro 96-well plate reader fixture."""
    data = _load_fixture("plate_reader/softmax_pro_96well.csv")
    return _make_file_context("softmax_pro_96well.csv", data, "plate_reader")


@pytest.fixture
def plate_gen5_ctx() -> FileContext:
    """FileContext for BioTek Gen5 tabular export fixture."""
    data = _load_fixture("plate_reader/gen5_tabular.csv")
    return _make_file_context("gen5_tabular.csv", data, "plate_reader")


@pytest.fixture
def plate_grid_ctx() -> FileContext:
    """FileContext for generic 96-well grid fixture."""
    data = _load_fixture("plate_reader/generic_grid_96well.csv")
    return _make_file_context("generic_grid_96well.csv", data, "plate_reader")


@pytest.fixture
def plate_corrupted_ctx() -> FileContext:
    """FileContext for corrupted plate reader file."""
    data = _load_fixture("plate_reader/corrupted.csv")
    return _make_file_context("corrupted.csv", data, "plate_reader")


# --- HPLC fixtures ---


@pytest.fixture
def hplc_agilent_ctx() -> FileContext:
    """FileContext for Agilent ChemStation HPLC export fixture."""
    data = _load_fixture("hplc/agilent_chemstation.csv")
    return _make_file_context("agilent_chemstation.csv", data, "hplc")


@pytest.fixture
def hplc_agilent_peaks_ctx() -> FileContext:
    """FileContext for Agilent peaks HPLC fixture (alt format)."""
    data = _load_fixture("hplc/agilent_peaks.csv")
    return _make_file_context("agilent_peaks.csv", data, "hplc")


@pytest.fixture
def hplc_shimadzu_ctx() -> FileContext:
    """FileContext for Shimadzu LabSolutions HPLC export fixture."""
    data = _load_fixture("hplc/shimadzu_labsolutions.csv")
    return _make_file_context("shimadzu_labsolutions.csv", data, "hplc")


@pytest.fixture
def hplc_shimadzu_export_ctx() -> FileContext:
    """FileContext for Shimadzu amino acid analysis export fixture."""
    data = _load_fixture("hplc/shimadzu_export.csv")
    return _make_file_context("shimadzu_export.csv", data, "hplc")


@pytest.fixture
def hplc_simple_ctx() -> FileContext:
    """FileContext for simple HPLC peak table fixture."""
    data = _load_fixture("hplc/simple_peak_table.csv")
    return _make_file_context("simple_peak_table.csv", data, "hplc")


@pytest.fixture
def hplc_corrupted_ctx() -> FileContext:
    """FileContext for corrupted HPLC file."""
    data = _load_fixture("hplc/corrupted.csv")
    return _make_file_context("corrupted.csv", data, "hplc")


# --- PCR fixtures ---


@pytest.fixture
def pcr_quantstudio_ctx() -> FileContext:
    """FileContext for Thermo QuantStudio qPCR export fixture."""
    data = _load_fixture("pcr/quantstudio_export.csv")
    return _make_file_context("quantstudio_export.csv", data, "pcr")


@pytest.fixture
def pcr_quantstudio_results_ctx() -> FileContext:
    """FileContext for QuantStudio results fixture (alt format with [Results] section)."""
    data = _load_fixture("pcr/quantstudio_results.csv")
    return _make_file_context("quantstudio_results.csv", data, "pcr")


@pytest.fixture
def pcr_biorad_cfx_ctx() -> FileContext:
    """FileContext for Bio-Rad CFX qPCR export fixture."""
    data = _load_fixture("pcr/biorad_cfx.csv")
    return _make_file_context("biorad_cfx.csv", data, "pcr")


@pytest.fixture
def pcr_simple_ctx() -> FileContext:
    """FileContext for simple PCR Ct table fixture."""
    data = _load_fixture("pcr/simple_ct_table.csv")
    return _make_file_context("simple_ct_table.csv", data, "pcr")


@pytest.fixture
def pcr_corrupted_ctx() -> FileContext:
    """FileContext for corrupted PCR file."""
    data = _load_fixture("pcr/corrupted.csv")
    return _make_file_context("corrupted.csv", data, "pcr")


# --- Balance fixtures ---


@pytest.fixture
def balance_mettler_ctx() -> FileContext:
    """FileContext for Mettler Toledo balance export fixture."""
    data = _load_fixture("balance/mettler_toledo.csv")
    return _make_file_context("mettler_toledo.csv", data, "balance")


@pytest.fixture
def balance_sartorius_ctx() -> FileContext:
    """FileContext for Sartorius balance export fixture."""
    data = _load_fixture("balance/sartorius_export.csv")
    return _make_file_context("sartorius_export.csv", data, "balance")


@pytest.fixture
def balance_sartorius_simple_ctx() -> FileContext:
    """FileContext for Sartorius simple CSV fixture (alt format)."""
    data = _load_fixture("balance/sartorius_simple.csv")
    return _make_file_context("sartorius_simple.csv", data, "balance")


@pytest.fixture
def balance_simple_ctx() -> FileContext:
    """FileContext for simple balance readings fixture."""
    data = _load_fixture("balance/simple_readings.csv")
    return _make_file_context("simple_readings.csv", data, "balance")


@pytest.fixture
def balance_corrupted_ctx() -> FileContext:
    """FileContext for corrupted balance file."""
    data = _load_fixture("balance/corrupted.csv")
    return _make_file_context("corrupted.csv", data, "balance")


# --- Empty file fixture (works for any parser) ---


@pytest.fixture
def empty_file_ctx() -> FileContext:
    """FileContext with empty bytes — tests empty-file handling for all parsers."""
    return _make_file_context("empty.csv", b"")
