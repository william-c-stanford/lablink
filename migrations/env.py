"""Alembic environment configuration for LabLink.

Supports both online (async) and offline migration modes.
Reads the database URL from lablink.config.Settings so that
the single source of truth is always the LABLINK_DATABASE_URL
environment variable (or its default).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# -- LabLink imports ---------------------------------------------------------
# Import all models so Base.metadata is fully populated before autogenerate.
import lablink.models  # noqa: F401
from lablink.config import get_settings
from lablink.database import Base

# -- Alembic config object --------------------------------------------------
config = context.config

# Interpret the config file for Python logging (unless we're in a test).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata

# -- Resolve the database URL -----------------------------------------------
settings = get_settings()
db_url = settings.database_url

# For Alembic we need a *synchronous* driver.  Swap async drivers to sync
# equivalents so the migration runner can use plain DB-API connections.
_ASYNC_TO_SYNC = {
    "sqlite+aiosqlite": "sqlite",
    "postgresql+asyncpg": "postgresql+psycopg2",
    "postgresql+aiopg": "postgresql+psycopg2",
}
for async_scheme, sync_scheme in _ASYNC_TO_SYNC.items():
    if db_url.startswith(async_scheme):
        db_url = db_url.replace(async_scheme, sync_scheme, 1)
        break

# Push the resolved URL into the alembic config so %(sqlalchemy.url)s works
# and so run_migrations_online picks it up.
config.set_main_option("sqlalchemy.url", db_url)


# ---------------------------------------------------------------------------
# Offline mode — emits SQL to stdout without a live DB connection
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connects to the database and runs migrations
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a sync connection."""
    from sqlalchemy import create_engine

    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
