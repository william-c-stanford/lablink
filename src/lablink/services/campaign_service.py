"""Campaign service — lifecycle management, experiment grouping, progress tracking.

Campaigns group related experiments (e.g., an optimization campaign).
This service handles:
- Campaign CRUD with state-machine enforcement
- Experiment association (via campaign_id on Experiment)
- Progress tracking (counts by experiment status)

State machine:
    active -> paused | completed
    paused -> active | completed
    completed -> (terminal)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.exceptions import NotFoundError, StateTransitionError, ValidationError
from lablink.models.campaign import (
    CAMPAIGN_TRANSITIONS,
    Campaign,
    CampaignStatus,
)
from lablink.models.experiment import Experiment, ExperimentStatus

# Fields that can be updated via ``update_campaign``
_UPDATABLE_FIELDS: set[str] = {
    "name",
    "objective",
    "optimization_method",
    "project_id",
}


class CampaignProgress(TypedDict):
    """Progress summary for a campaign."""

    total_experiments: int
    planned: int
    running: int
    completed: int
    failed: int
    cancelled: int
    completion_rate: float  # 0.0 – 1.0


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


async def create_campaign(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    objective: str | None = None,
    optimization_method: str | None = None,
    project_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> Campaign:
    """Create a new campaign in ACTIVE status.

    Args:
        session: Active async database session.
        organization_id: Owning organization UUID.
        name: Campaign name (required).
        objective: What this campaign aims to achieve.
        optimization_method: bayesian, grid_search, manual, etc.
        project_id: Optional project grouping.
        created_by: User UUID who created the campaign.

    Returns:
        The newly created Campaign instance.
    """
    campaign = Campaign(
        organization_id=organization_id,
        name=name,
        objective=objective,
        optimization_method=optimization_method,
        project_id=project_id,
        created_by=created_by,
        status=CampaignStatus.ACTIVE.value,
    )
    session.add(campaign)
    await session.flush()
    return campaign


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


async def get_campaign(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
) -> Campaign:
    """Retrieve a single campaign by ID.

    Args:
        session: Active async database session.
        campaign_id: UUID of the campaign.
        organization_id: If provided, enforce org-scoping.

    Returns:
        The Campaign instance (with experiments eager-loaded).

    Raises:
        NotFoundError: If the campaign does not exist or is filtered out.
    """
    stmt = select(Campaign).where(Campaign.id == campaign_id)

    if organization_id is not None:
        stmt = stmt.where(Campaign.organization_id == organization_id)

    result = await session.execute(stmt)
    campaign = result.scalar_one_or_none()

    if campaign is None:
        raise NotFoundError(
            message=f"Campaign '{campaign_id}' not found.",
            suggestion="Use list_campaigns to find valid campaign IDs.",
        )
    return campaign


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


async def list_campaigns(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    status: CampaignStatus | None = None,
    project_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Campaign], int]:
    """List campaigns with optional filters and pagination.

    Args:
        session: Active async database session.
        organization_id: Filter by organization.
        status: Filter by campaign status.
        project_id: Filter by project.
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Tuple of (list of campaigns, total count).
    """
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    offset = (page - 1) * page_size

    conditions = []
    if organization_id is not None:
        conditions.append(Campaign.organization_id == organization_id)
    if status is not None:
        conditions.append(Campaign.status == status.value)
    if project_id is not None:
        conditions.append(Campaign.project_id == project_id)

    # Count
    count_stmt = select(func.count(Campaign.id))
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
    total = (await session.execute(count_stmt)).scalar() or 0

    # Data
    data_stmt = (
        select(Campaign)
        .order_by(Campaign.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    for cond in conditions:
        data_stmt = data_stmt.where(cond)

    result = await session.execute(data_stmt)
    campaigns = list(result.scalars().all())

    return campaigns, total


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


async def update_campaign(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
    **kwargs: Any,
) -> Campaign:
    """Update mutable fields on a campaign.

    Only fields in ``_UPDATABLE_FIELDS`` are accepted. Updates are
    blocked on campaigns in terminal (completed) state.

    Raises:
        NotFoundError: If the campaign does not exist.
        ValidationError: If the campaign is in a terminal state.
    """
    campaign = await get_campaign(
        session, campaign_id, organization_id=organization_id
    )

    if campaign.is_terminal:
        raise ValidationError(
            message=(
                f"Cannot update campaign in terminal state "
                f"'{campaign.status}'. The campaign is completed."
            ),
            suggestion="Create a new campaign instead.",
        )

    for field, value in kwargs.items():
        if field in _UPDATABLE_FIELDS and hasattr(campaign, field):
            setattr(campaign, field, value)

    await session.flush()
    return campaign


# ---------------------------------------------------------------------------
# STATE TRANSITIONS
# ---------------------------------------------------------------------------


async def transition_campaign(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    new_status: CampaignStatus,
    *,
    organization_id: uuid.UUID | None = None,
) -> Campaign:
    """Transition a campaign to a new state.

    Enforces the state machine defined in ``CAMPAIGN_TRANSITIONS``.

    Raises:
        NotFoundError: If the campaign does not exist.
        StateTransitionError: If the transition is invalid.
    """
    campaign = await get_campaign(
        session, campaign_id, organization_id=organization_id
    )

    current = CampaignStatus(campaign.status)

    if campaign.is_terminal:
        raise StateTransitionError(
            message=(
                f"Cannot transition from terminal state '{current.value}' "
                f"to '{new_status.value}'."
            ),
            suggestion=(
                f"Campaign is in terminal state '{current.value}'. "
                f"Create a new campaign instead."
            ),
        )

    valid = CAMPAIGN_TRANSITIONS.get(current, set())
    if new_status not in valid:
        valid_names = sorted(s.value for s in valid)
        raise StateTransitionError(
            message=(
                f"Cannot transition campaign from '{current.value}' to "
                f"'{new_status.value}'."
            ),
            suggestion=(
                f"Valid transitions from '{current.value}': "
                f"{valid_names}. Use one of these statuses."
            ),
        )

    campaign.status = new_status.value
    await session.flush()
    return campaign


# ---------------------------------------------------------------------------
# PROGRESS TRACKING
# ---------------------------------------------------------------------------


async def get_campaign_progress(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
) -> CampaignProgress:
    """Calculate progress metrics for a campaign.

    Returns counts of experiments by status and an overall completion rate.

    Raises:
        NotFoundError: If the campaign does not exist.
    """
    # Verify campaign exists
    await get_campaign(session, campaign_id, organization_id=organization_id)

    # Count experiments by status in a single query
    stmt = (
        select(
            func.count(Experiment.id).label("total"),
            func.sum(
                case(
                    (Experiment.status == ExperimentStatus.PLANNED.value, 1),
                    else_=0,
                )
            ).label("planned"),
            func.sum(
                case(
                    (Experiment.status == ExperimentStatus.RUNNING.value, 1),
                    else_=0,
                )
            ).label("running"),
            func.sum(
                case(
                    (Experiment.status == ExperimentStatus.COMPLETED.value, 1),
                    else_=0,
                )
            ).label("completed"),
            func.sum(
                case(
                    (Experiment.status == ExperimentStatus.FAILED.value, 1),
                    else_=0,
                )
            ).label("failed"),
            func.sum(
                case(
                    (Experiment.status == ExperimentStatus.CANCELLED.value, 1),
                    else_=0,
                )
            ).label("cancelled"),
        )
        .where(Experiment.campaign_id == campaign_id)
        .where(Experiment.deleted_at.is_(None))
    )

    row = (await session.execute(stmt)).one()
    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    cancelled = row.cancelled or 0

    # Completion rate: (completed + failed + cancelled) / total
    terminal_count = completed + failed + cancelled
    completion_rate = terminal_count / total if total > 0 else 0.0

    return CampaignProgress(
        total_experiments=total,
        planned=row.planned or 0,
        running=row.running or 0,
        completed=completed,
        failed=failed,
        cancelled=cancelled,
        completion_rate=round(completion_rate, 4),
    )


# ---------------------------------------------------------------------------
# EXPERIMENT ASSOCIATION HELPERS
# ---------------------------------------------------------------------------


async def add_experiment_to_campaign(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    experiment_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
) -> Experiment:
    """Associate an experiment with a campaign.

    Sets the experiment's ``campaign_id`` field.

    Raises:
        NotFoundError: If the campaign or experiment does not exist.
        ValidationError: If the campaign is completed.
    """
    campaign = await get_campaign(
        session, campaign_id, organization_id=organization_id
    )

    if campaign.is_terminal:
        raise ValidationError(
            message=f"Cannot add experiments to completed campaign '{campaign_id}'.",
            suggestion="Create a new campaign instead.",
        )

    # Import here to avoid circular dependency at module level
    from lablink.services.experiment_service import get_experiment

    experiment = await get_experiment(
        session, experiment_id, organization_id=organization_id
    )
    experiment.campaign_id = campaign_id
    await session.flush()
    return experiment


async def remove_experiment_from_campaign(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
) -> Experiment:
    """Remove an experiment's campaign association.

    Sets the experiment's ``campaign_id`` to None.

    Raises:
        NotFoundError: If the experiment does not exist.
    """
    from lablink.services.experiment_service import get_experiment

    experiment = await get_experiment(
        session, experiment_id, organization_id=organization_id
    )
    experiment.campaign_id = None
    await session.flush()
    return experiment


async def list_campaign_experiments(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
    status: ExperimentStatus | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Experiment], int]:
    """List experiments belonging to a campaign.

    Args:
        session: Active async database session.
        campaign_id: UUID of the campaign.
        organization_id: Optional org-scoping.
        status: Filter by experiment status.
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        Tuple of (experiments, total count).
    """
    # Verify campaign exists
    await get_campaign(session, campaign_id, organization_id=organization_id)

    from lablink.services.experiment_service import list_experiments

    return await list_experiments(
        session,
        organization_id=organization_id,
        campaign_id=campaign_id,
        status=status,
        page=page,
        page_size=page_size,
    )
