"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

Supports both SQLite (dev/test via ``aiosqlite``) and PostgreSQL
(production via ``asyncpg``).  SQLite connections automatically enable
WAL mode and foreign-key enforcement.

Usage in routers::

    from lablink.db.session import get_session

    @router.get("/orgs")
    async def list_orgs(db: AsyncSession = Depends(get_session)):
        ...

Usage outside the request cycle::

    from lablink.db.session import get_session_ctx

    async with get_session_ctx() as db:
        ...
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from lablink.config import Settings, get_settings

# ---------------------------------------------------------------------------
# Module-level singletons (populated lazily)
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------


def _build_engine_kwargs(settings: Settings) -> dict[str, Any]:
    """Return engine kwargs appropriate for the configured database."""
    kwargs: dict[str, Any] = {
        "echo": settings.debug and settings.is_dev,
    }

    if settings.is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if settings.environment.value == "test":
            kwargs["poolclass"] = StaticPool
            kwargs["echo"] = False
        else:
            kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_pre_ping"] = True

    return kwargs


def _enable_sqlite_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Parameters
    ----------
    settings:
        Optional override; defaults to :func:`get_settings`.
    """
    if settings is None:
        settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        **_build_engine_kwargs(settings),
    )

    if settings.is_sqlite:
        event.listen(engine.sync_engine, "connect", _enable_sqlite_pragmas)

    return engine


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to *engine*."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the module-level async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_engine(settings)
    return _engine


def get_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine(settings))
    return _session_factory


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_session(
    settings: Settings | None = None,
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an ``AsyncSession``.

    The session is committed on success and rolled back on exception.
    """
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Context manager for non-request usage
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def get_session_ctx(
    settings: Settings | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for sessions outside the FastAPI request cycle.

    Example::

        async with get_session_ctx() as db:
            result = await db.execute(select(Organization))
    """
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------


async def init_db(settings: Settings | None = None) -> None:
    """Create engine and (in dev/test) create all tables.

    In production, tables are managed by Alembic migrations.
    """
    import lablink.models  # noqa: F401 — ensure all models are registered
    from lablink.database import Base

    settings = settings or get_settings()
    engine = get_engine(settings)

    if settings.is_dev:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine and reset module singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None


async def check_db_connection(engine: AsyncEngine | None = None) -> bool:
    """Verify the database is reachable. Returns *True* on success."""
    target = engine or get_engine()
    try:
        async with target.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
