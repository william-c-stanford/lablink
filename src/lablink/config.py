"""Application settings loaded from environment variables via pydantic-settings.

All settings can be overridden via environment variables prefixed with ``LABLINK_``
(e.g. ``LABLINK_DATABASE_URL``, ``LABLINK_SECRET_KEY``).  A ``.env`` file in the
project root is loaded automatically when present.

Usage::

    from lablink.config import get_settings

    settings = get_settings()
    print(settings.database_url)
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment."""

    dev = "dev"
    test = "test"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """LabLink application settings.

    Every field has a sensible default for local development so the app
    can boot with zero configuration.  In production, set the matching
    ``LABLINK_*`` environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="LABLINK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "LabLink"
    environment: Environment = Environment.dev
    debug: bool = True
    version: str = "0.1.0"

    # ── Server ───────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./lablink.db"

    # ── Auth / Security ──────────────────────────────────────────────────
    secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
    )

    # ── Celery / Task Queue ──────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    use_celery: bool = False  # False → sync inline fallback for dev/test

    # ── Storage (S3 / local filesystem mock) ─────────────────────────────
    storage_backend: str = "local"  # "local" | "s3"
    local_storage_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""  # Set to MinIO URL for local dev

    # ── Elasticsearch ────────────────────────────────────────────────────
    elasticsearch_url: str = "http://localhost:9200"
    use_elasticsearch: bool = False  # False → in-memory mock for dev

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    use_redis: bool = False  # False → in-memory mock for dev

    # ── Convenience properties ───────────────────────────────────────────

    @property
    def is_sqlite(self) -> bool:
        """True when the configured database is SQLite."""
        return "sqlite" in self.database_url

    @property
    def is_dev(self) -> bool:
        """True for dev or test environments."""
        return self.environment in (Environment.dev, Environment.test)

    @property
    def is_production(self) -> bool:
        """True only in production."""
        return self.environment == Environment.production


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton :class:`Settings` instance.

    Call :pyfunc:`get_settings.cache_clear()` in tests to reset.
    """
    return Settings()
