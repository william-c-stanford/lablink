"""Async SQLAlchemy database engine, session factory, and helpers.

Provides:
- ``async_engine`` – lazily-created async engine (SQLite + aiosqlite for dev)
- ``async_session_factory`` – bound ``async_sessionmaker``
- ``get_db`` – FastAPI dependency yielding an ``AsyncSession``
- ``init_db`` / ``close_db`` – lifespan helpers for startup/shutdown

Usage::

    from lablink.database import get_db

    @router.get("/items")
    async def list_items(db: AsyncSession = Depends(get_db)):
        ...

All configuration is read from :func:`lablink.config.get_settings`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from lablink.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Declarative base — single source of truth for all ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Abstract declarative base for all LabLink ORM models."""

    pass


# ---------------------------------------------------------------------------
# Module-level singletons (populated lazily via ``init_db`` or on first use)
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine_kwargs(settings: Settings) -> dict[str, Any]:
    """Return engine kwargs appropriate for the configured database."""
    kwargs: dict[str, Any] = {
        "echo": settings.debug and settings.is_dev,
    }

    if settings.is_sqlite:
        # SQLite-specific: no pool for aiosqlite, enable WAL via connect event
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL / other async drivers
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_pre_ping"] = True

    return kwargs


def _enable_sqlite_wal(dbapi_conn: Any, _connection_record: Any) -> None:
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the async engine, creating it on first call.

    Parameters
    ----------
    settings:
        Optional override; defaults to :func:`get_settings`.
    """
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        _engine = create_async_engine(
            settings.database_url,
            **_build_engine_kwargs(settings),
        )
        # Attach SQLite pragmas if needed
        if settings.is_sqlite:
            event.listen(_engine.sync_engine, "connect", _enable_sqlite_wal)
    return _engine


def get_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Return the async session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an ``AsyncSession``.

    The session is committed on success and rolled back on exception.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(settings: Settings | None = None) -> None:
    """Create engine and (in dev/test) create all tables.

    Call during FastAPI lifespan startup.  In production, tables are
    managed by Alembic migrations.
    """
    import lablink.models  # noqa: F401 — ensure all models are registered

    settings = settings or get_settings()
    engine = get_engine(settings)

    if settings.is_dev:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine and reset module singletons.

    Call during FastAPI lifespan shutdown.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
