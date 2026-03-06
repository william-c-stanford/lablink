"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.envelope import Envelope

router = APIRouter(tags=["health"])


class HealthData(dict):
    pass


@router.get("/health", response_model=Envelope[dict])
async def health_check() -> Envelope[dict]:
    """Health check endpoint."""
    settings = get_settings()
    return Envelope.ok(
        {
            "status": "healthy",
            "version": settings.version,
            "environment": settings.environment.value,
        }
    )


@router.get("/", response_model=Envelope[dict])
async def root() -> Envelope[dict]:
    """Root endpoint with API info."""
    settings = get_settings()
    return Envelope.ok(
        {
            "name": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "openapi": "/openapi.json",
        }
    )
