"""Admin router — system administration and health endpoints.

Endpoints:
    GET /admin/usage  — Get usage statistics for the current organization
    GET /admin/health — Detailed health check with dependency status
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.config import get_settings
from lablink.dependencies import get_current_org, get_db, require_role
from lablink.models.upload import Upload
from lablink.models.experiment import Experiment
from lablink.models.membership import Membership
from lablink.models.organization import Organization
from lablink.models.user import User
from lablink.models.agent import Agent
from lablink.models.instrument import Instrument
from lablink.schemas.envelope import Envelope, success_response

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# GET /admin/usage
# ---------------------------------------------------------------------------


@router.get(
    "/usage",
    response_model=Envelope[dict],
    operation_id="get_usage_stats",
    response_model_exclude_none=True,
)
async def get_usage_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get usage statistics for the current organization (admin only)."""
    # Count resources
    member_count = (
        await db.execute(
            select(func.count(Membership.id)).where(Membership.organization_id == org.id)
        )
    ).scalar_one()

    instrument_count = (
        await db.execute(
            select(func.count(Instrument.id)).where(Instrument.organization_id == org.id)
        )
    ).scalar_one()

    agent_count = (
        await db.execute(select(func.count(Agent.id)).where(Agent.organization_id == org.id))
    ).scalar_one()

    upload_count = (
        await db.execute(select(func.count(Upload.id)).where(Upload.organization_id == org.id))
    ).scalar_one()

    total_storage = (
        await db.execute(
            select(func.coalesce(func.sum(Upload.file_size_bytes), 0)).where(
                Upload.organization_id == org.id
            )
        )
    ).scalar_one()

    experiment_count = (
        await db.execute(
            select(func.count(Experiment.id)).where(Experiment.organization_id == org.id)
        )
    ).scalar_one()

    return success_response(
        data={
            "organization_id": str(org.id),
            "tier": org.tier,
            "members": {
                "count": member_count,
                "limit": org.user_limit,
            },
            "instruments": {
                "count": instrument_count,
                "limit": org.instrument_limit,
            },
            "agents": {
                "count": agent_count,
            },
            "uploads": {
                "count": upload_count,
            },
            "storage": {
                "used_bytes": total_storage,
                "limit_bytes": org.storage_limit_bytes,
                "used_percent": round((total_storage / org.storage_limit_bytes) * 100, 2)
                if org.storage_limit_bytes > 0
                else 0.0,
            },
            "experiments": {
                "count": experiment_count,
            },
        }
    )


# ---------------------------------------------------------------------------
# GET /admin/health
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=Envelope[dict],
    operation_id="get_detailed_health",
    response_model_exclude_none=True,
)
async def get_detailed_health(
    db: AsyncSession = Depends(get_db),
) -> Envelope:
    """Detailed health check including database connectivity and configuration."""
    settings = get_settings()

    # Check database connectivity
    db_healthy = True
    try:
        await db.execute(select(func.count()).select_from(User.__table__))
    except Exception:
        db_healthy = False

    return success_response(
        data={
            "status": "healthy" if db_healthy else "degraded",
            "version": settings.version,
            "environment": settings.environment.value,
            "checks": {
                "database": "ok" if db_healthy else "error",
                "elasticsearch": "enabled" if settings.use_elasticsearch else "disabled",
                "celery": "enabled" if settings.use_celery else "disabled (sync fallback)",
                "storage_backend": settings.storage_backend,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
