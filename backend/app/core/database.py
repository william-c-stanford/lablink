"""SQLAlchemy async engine and session factory.

Supports both SQLite (dev/test via aiosqlite) and PostgreSQL (prod via asyncpg).
SQLite requires special handling:
  - No connection pool (StaticPool for tests, NullPool for dev)
  - connect_args with check_same_thread=False
  - Event listener to enable WAL mode and foreign keys
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.config import Settings, get_settings


def _build_engine_kwargs(settings: Settings) -> dict[str, Any]:
    """Build engine kwargs based on database type."""
    kwargs: dict[str, Any] = {
        "echo": settings.debug and settings.is_dev,
    }

    if settings.is_sqlite:
        # SQLite-specific configuration
        kwargs["connect_args"] = {"check_same_thread": False}

        if settings.environment.value == "test":
            # In-memory SQLite for tests — share a single connection
            kwargs["poolclass"] = StaticPool
            kwargs["echo"] = False
        else:
            # File-based SQLite for dev — no pooling
            kwargs["poolclass"] = NullPool
    else:
        # PostgreSQL connection pool settings
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_pre_ping"] = True

    return kwargs


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        settings: Application settings. Uses cached singleton if not provided.

    Returns:
        Configured AsyncEngine instance.
    """
    if settings is None:
        settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        **_build_engine_kwargs(settings),
    )

    # Register SQLite-specific event listeners
    if settings.is_sqlite:
        _register_sqlite_listeners(engine)

    return engine


def _register_sqlite_listeners(engine: AsyncEngine) -> None:
    """Register event listeners for SQLite connections.

    Enables:
      - Foreign key enforcement (off by default in SQLite)
      - WAL journal mode (better concurrent read performance)
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine.

    Args:
        engine: The async engine to bind sessions to.

    Returns:
        An async_sessionmaker that produces AsyncSession instances.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# ---------------------------------------------------------------------------
# Module-level convenience instances (lazy-initialized)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the module-level async engine."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the module-level session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session.

    Usage in routers:
        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextlib.asynccontextmanager
async def get_session_ctx() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for sessions outside of FastAPI request cycle.

    Usage in services/tasks:
        async with get_session_ctx() as session:
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create all tables. Used for dev/test setup.

    In production, use Alembic migrations instead.
    """
    from app.models.base import Base

    target_engine = engine or get_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine connection pool."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def check_db_connection(engine: AsyncEngine | None = None) -> bool:
    """Verify the database is reachable. Returns True on success."""
    target_engine = engine or get_engine()
    try:
        async with target_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
