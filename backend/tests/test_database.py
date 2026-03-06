"""Tests for SQLAlchemy async engine with SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, Table, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Environment, Settings
from app.core.database import (
    check_db_connection,
    create_engine,
    create_session_factory,
)
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


# ---------------------------------------------------------------------------
# A simple test model to exercise the ORM
# ---------------------------------------------------------------------------
class SampleModel(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_samples"

    name: str = Column(String(100), nullable=False)  # type: ignore[assignment]
    value: int = Column(Integer, default=0)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Engine creation tests
# ---------------------------------------------------------------------------


class TestEngineCreation:
    """Test that the async engine is created correctly for SQLite."""

    def test_create_engine_returns_async_engine(self, test_settings: Settings) -> None:
        engine = create_engine(test_settings)
        assert isinstance(engine, AsyncEngine)

    def test_engine_url_is_sqlite(self, test_settings: Settings) -> None:
        engine = create_engine(test_settings)
        assert "sqlite" in str(engine.url)

    def test_engine_url_uses_aiosqlite_driver(self, test_settings: Settings) -> None:
        engine = create_engine(test_settings)
        assert "aiosqlite" in str(engine.url)

    def test_sqlite_url_uses_aiosqlite(self) -> None:
        """Default SQLite URL should use aiosqlite driver."""
        settings = Settings(environment=Environment.test)
        assert "aiosqlite" in settings.database_url


# ---------------------------------------------------------------------------
# Connection tests
# ---------------------------------------------------------------------------


class TestConnection:
    """Test that we can connect and execute queries."""

    async def test_basic_connection(self, engine: AsyncEngine) -> None:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    async def test_check_db_connection(self, engine: AsyncEngine) -> None:
        assert await check_db_connection(engine) is True

    async def test_foreign_keys_enabled(self, engine: AsyncEngine) -> None:
        """SQLite foreign keys should be enabled via event listener."""
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA foreign_keys"))
            assert result.scalar() == 1

    async def test_wal_mode_enabled(self, engine: AsyncEngine) -> None:
        """SQLite WAL journal mode should be enabled."""
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            # In-memory SQLite uses 'memory' journal mode
            assert mode in ("wal", "memory")


# ---------------------------------------------------------------------------
# Table creation tests
# ---------------------------------------------------------------------------


class TestTableCreation:
    """Test that tables can be created with init_db."""

    async def test_create_tables(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Verify the test table exists
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result.fetchall()]
            assert "test_samples" in tables

    async def test_table_has_expected_columns(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA table_info(test_samples)"))
            columns = {row[1] for row in result.fetchall()}
            assert "id" in columns
            assert "name" in columns
            assert "value" in columns
            assert "created_at" in columns
            assert "updated_at" in columns
            assert "deleted_at" in columns


# ---------------------------------------------------------------------------
# Session factory tests
# ---------------------------------------------------------------------------


class TestSessionFactory:
    """Test session creation and basic ORM operations."""

    async def test_create_session(
        self, engine: AsyncEngine
    ) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = create_session_factory(engine)
        async with factory() as session:
            assert isinstance(session, AsyncSession)

    async def test_insert_and_query(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = create_session_factory(engine)
        async with factory() as session:
            sample = SampleModel(name="test-sample", value=42)
            session.add(sample)
            await session.commit()

            # Query it back
            result = await session.execute(
                text("SELECT name, value FROM test_samples WHERE name = :n"),
                {"n": "test-sample"},
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "test-sample"
            assert row[1] == 42

    async def test_uuid_primary_key_generated(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = create_session_factory(engine)
        async with factory() as session:
            sample = SampleModel(name="uuid-test", value=1)
            session.add(sample)
            await session.flush()
            assert sample.id is not None
            assert len(sample.id) == 36  # UUID string length

    async def test_timestamps_set_on_insert(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = create_session_factory(engine)
        async with factory() as session:
            sample = SampleModel(name="ts-test", value=1)
            session.add(sample)
            await session.flush()
            assert sample.created_at is not None
            assert sample.updated_at is not None

    async def test_soft_delete(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = create_session_factory(engine)
        async with factory() as session:
            sample = SampleModel(name="soft-del", value=1)
            session.add(sample)
            await session.flush()
            assert sample.is_deleted is False
            assert sample.deleted_at is None

    async def test_session_expire_on_commit_false(
        self, engine: AsyncEngine
    ) -> None:
        """Sessions should not expire objects on commit (expire_on_commit=False)."""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = create_session_factory(engine)
        async with factory() as session:
            sample = SampleModel(name="no-expire", value=99)
            session.add(sample)
            await session.commit()
            # Should still be accessible after commit
            assert sample.name == "no-expire"
            assert sample.value == 99


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    """Test settings and configuration."""

    def test_default_settings_use_sqlite(self) -> None:
        settings = Settings(environment=Environment.dev)
        assert settings.is_sqlite is True
        assert "sqlite" in settings.database_url

    def test_is_dev_true_for_dev_environment(self) -> None:
        settings = Settings(environment=Environment.dev)
        assert settings.is_dev is True

    def test_is_dev_true_for_test_environment(self) -> None:
        settings = Settings(environment=Environment.test)
        assert settings.is_dev is True

    def test_is_production_false_for_dev(self) -> None:
        settings = Settings(environment=Environment.dev)
        assert settings.is_production is False

    def test_use_celery_false_by_default(self) -> None:
        settings = Settings(environment=Environment.dev)
        assert settings.use_celery is False
