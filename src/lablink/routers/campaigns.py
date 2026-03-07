"""Campaigns router — CRUD and progress tracking for experiment campaigns.

Endpoints:
    POST /campaigns/              — Create a new campaign
    GET  /campaigns/              — List campaigns
    GET  /campaigns/{id}          — Get a campaign by ID
    GET  /campaigns/{id}/progress — Get campaign progress metrics
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.models.organization import Organization
from lablink.models.user import User
from lablink.schemas.campaigns import (
    CampaignCreate,
    CampaignProgressResponse,
    CampaignResponse,
)
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.services.campaign_service import (
    create_campaign,
    get_campaign,
    get_campaign_progress,
    list_campaigns,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ---------------------------------------------------------------------------
# POST /campaigns/
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=Envelope[CampaignResponse],
    status_code=201,
    operation_id="create_campaign",
    response_model_exclude_none=True,
)
async def create_camp(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Create a new experiment campaign in ACTIVE status."""
    campaign = await create_campaign(
        db,
        organization_id=org.id,
        name=body.name,
        objective=body.objective,
        optimization_method=body.optimization_method,
        created_by=user.id,
    )
    return success_response(data=CampaignResponse.model_validate(campaign))


# ---------------------------------------------------------------------------
# GET /campaigns/
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=Envelope[list[CampaignResponse]],
    operation_id="list_campaigns",
    response_model_exclude_none=True,
)
async def list_camps(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by campaign status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List campaigns for the current organization."""
    from lablink.models.experiment import CampaignStatus

    status_enum = None
    if status:
        try:
            status_enum = CampaignStatus(status)
        except ValueError:
            from lablink.exceptions import ValidationError

            raise ValidationError(
                message=f"Invalid status '{status}'",
                suggestion=f"Valid statuses: {[s.value for s in CampaignStatus]}",
                field="status",
            )

    campaigns, total = await list_campaigns(
        db,
        organization_id=org.id,
        status=status_enum,
        page=page,
        page_size=page_size,
    )

    return success_response(
        data=[CampaignResponse.model_validate(c) for c in campaigns],
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /campaigns/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{campaign_id}",
    response_model=Envelope[CampaignResponse],
    operation_id="get_campaign",
    response_model_exclude_none=True,
)
async def get_camp(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get a campaign by ID."""
    campaign = await get_campaign(db, campaign_id, organization_id=org.id)
    return success_response(data=CampaignResponse.model_validate(campaign))


# ---------------------------------------------------------------------------
# GET /campaigns/{id}/progress
# ---------------------------------------------------------------------------


@router.get(
    "/{campaign_id}/progress",
    response_model=Envelope[CampaignProgressResponse],
    operation_id="get_campaign_progress",
    response_model_exclude_none=True,
)
async def get_camp_progress(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get aggregated progress metrics for a campaign."""
    progress = await get_campaign_progress(db, campaign_id, organization_id=org.id)

    return success_response(
        data=CampaignProgressResponse(
            campaign_id=campaign_id,
            experiment_count=progress["total_experiments"],
            completed_count=progress["completed"],
            failed_count=progress["failed"],
            best_result=None,
        )
    )
