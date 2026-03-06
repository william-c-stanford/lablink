"""Application settings loaded from environment via pydantic-settings."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Environment(str, Enum):
    dev = "dev"
    test = "test"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """LabLink application settings.

    All settings can be overridden via environment variables prefixed with LABLINK_.
    """

    model_config = SettingsConfigDict(
        env_prefix="LABLINK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "LabLink"
    environment: Environment = Environment.dev
    debug: bool = True
    version: str = "0.1.0"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./lablink.db"

    # Auth
    secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Celery / Task queue
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    use_celery: bool = False  # False = sync fallback for dev

    # Storage (mock S3 in dev)
    storage_backend: str = "local"  # "local" or "s3"
    local_storage_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"

    # Elasticsearch (mock in dev)
    elasticsearch_url: str = "http://localhost:9200"
    use_elasticsearch: bool = False  # False = in-memory mock for dev

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    use_redis: bool = False  # False = in-memory mock for dev

    @property
    def is_sqlite(self) -> bool:
        """Check if the database URL points to SQLite."""
        return "sqlite" in self.database_url

    @property
    def is_dev(self) -> bool:
        return self.environment in (Environment.dev, Environment.test)

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.production


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
