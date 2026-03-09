"""Experiment service — CRUD, state-machine enforcement, and upload linking.

All functions accept an ``AsyncSession`` and return ORM model instances.
Zero HTTP awareness — this module knows nothing about FastAPI, requests,
or responses.  Routers translate results into Envelope responses.

State machine (from ``lablink.models.experiment``):
    planned -> running -> completed | failed
    planned -> cancelled

Functions:
    create_experiment   — Create with default PLANNED status
    get_experiment      — Get by ID with optional org scoping and soft-delete filter
    list_experiments    — Paginated listing with status/org/campaign filters
    update_experiment   — Update mutable fields (blocked in terminal states)
    soft_delete_experiment — Set deleted_at (idempotent-safe)
    transition_experiment — Enforce state machine, set timestamps, record outcome
    link_upload         — Associate an upload with an experiment
    unlink_upload       — Remove upload association
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.exceptions import NotFoundError, StateTransitionError, ValidationError
from lablink.models.experiment import (
    EXPERIMENT_TRANSITIONS,
    Experiment,
    ExperimentStatus,
)
from lablink.models.experiment_upload import ExperimentUpload
from lablink.models.experiment_predecessor import ExperimentPredecessor

# Fields that can be updated via ``update_experiment``
_UPDATABLE_FIELDS: set[str] = {
    "intent",
    "hypothesis",
    "parameters",
    "constraints",
    "design_method",
    "design_agent",
    "project_id",
    "campaign_id",
}

# Fields that must never be modified directly
_PROTECTED_FIELDS: set[str] = {
    "id",
    "organization_id",
    "created_at",
    "status",
    "completed_at",
    "outcome",
}


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


async def create_experiment(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    intent: str,
    hypothesis: str | None = None,
    parameters: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    design_method: str | None = None,
    design_agent: str | None = None,
    project_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    created_by_agent_token: uuid.UUID | None = None,
) -> Experiment:
    """Create a new experiment in PLANNED status.

    Args:
        session: Active async database session.
        organization_id: Owning organization UUID.
        intent: What the experiment aims to achieve (required).
        hypothesis: Optional hypothesis statement.
        parameters: Experimental conditions as JSON-serializable dict.
        constraints: Bounds on parameters.
        design_method: e.g. "manual", "bayesian_optimization".
        design_agent: ID of the agent that designed this experiment.
        project_id: Optional project grouping.
        campaign_id: Optional campaign grouping.
        created_by: User UUID who created the experiment.
        created_by_agent_token: API token UUID if agent-created.

    Returns:
        The newly created Experiment instance.
    """
    experiment = Experiment(
        organization_id=organization_id,
        intent=intent,
        hypothesis=hypothesis,
        parameters=parameters or {},
        constraints=constraints or {},
        design_method=design_method,
        design_agent=design_agent,
        project_id=project_id,
        campaign_id=campaign_id,
        created_by=created_by,
        created_by_agent_token=created_by_agent_token,
        status=ExperimentStatus.PLANNED.value,
    )
    session.add(experiment)
    await session.flush()
    return experiment


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


async def get_experiment(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
    include_deleted: bool = False,
) -> Experiment:
    """Retrieve a single experiment by ID.

    Args:
        session: Active async database session.
        experiment_id: UUID of the experiment.
        organization_id: If provided, enforce org-scoping.
        include_deleted: If True, return soft-deleted experiments.

    Returns:
        The Experiment instance.

    Raises:
        NotFoundError: If the experiment does not exist or is filtered out.
    """
    stmt = select(Experiment).where(Experiment.id == experiment_id)

    if organization_id is not None:
        stmt = stmt.where(Experiment.organization_id == organization_id)

    if not include_deleted and hasattr(Experiment, "deleted_at"):
        stmt = stmt.where(Experiment.deleted_at.is_(None))

    result = await session.execute(stmt)
    experiment = result.scalar_one_or_none()

    if experiment is None:
        raise NotFoundError(
            message=f"Experiment '{experiment_id}' not found.",
            suggestion="Use list_experiments to find valid experiment IDs.",
        )
    return experiment


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


async def list_experiments(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    status: ExperimentStatus | None = None,
    campaign_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    include_deleted: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Experiment], int]:
    """List experiments with optional filters and pagination.

    Args:
        session: Active async database session.
        organization_id: Filter by organization.
        status: Filter by experiment status.
        campaign_id: Filter by campaign.
        project_id: Filter by project.
        include_deleted: Include soft-deleted experiments.
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Tuple of (list of experiments, total count).
    """
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    offset = (page - 1) * page_size

    # Build base filter
    conditions = []
    if organization_id is not None:
        conditions.append(Experiment.organization_id == organization_id)
    if status is not None:
        conditions.append(Experiment.status == status.value)
    if campaign_id is not None:
        conditions.append(Experiment.campaign_id == campaign_id)
    if project_id is not None:
        conditions.append(Experiment.project_id == project_id)
    if not include_deleted and hasattr(Experiment, "deleted_at"):
        conditions.append(Experiment.deleted_at.is_(None))

    # Count query
    count_stmt = select(func.count(Experiment.id))
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
    total = (await session.execute(count_stmt)).scalar() or 0

    # Data query
    data_stmt = (
        select(Experiment).order_by(Experiment.created_at.desc()).offset(offset).limit(page_size)
    )
    for cond in conditions:
        data_stmt = data_stmt.where(cond)

    result = await session.execute(data_stmt)
    experiments = list(result.scalars().all())

    return experiments, total


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


async def update_experiment(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
    **kwargs: Any,
) -> Experiment:
    """Update mutable fields on an experiment.

    Fields in ``_UPDATABLE_FIELDS`` are accepted; all others are silently
    ignored.  Updates are blocked on experiments in terminal states.

    Raises:
        NotFoundError: If the experiment does not exist.
        ValidationError: If the experiment is in a terminal state.
    """
    experiment = await get_experiment(session, experiment_id, organization_id=organization_id)

    # Block updates on terminal experiments
    current_status = ExperimentStatus(experiment.status)
    if experiment.is_terminal:
        raise ValidationError(
            message=(
                f"Cannot update experiment in terminal state '{current_status.value}'. "
                f"The experiment is completed/failed/cancelled."
            ),
            suggestion=(
                f"Experiment is in terminal state '{current_status.value}'. "
                f"Create a new experiment instead."
            ),
        )

    # Apply only allowed fields
    for field, value in kwargs.items():
        if field in _UPDATABLE_FIELDS and hasattr(experiment, field):
            setattr(experiment, field, value)

    await session.flush()
    return experiment


# ---------------------------------------------------------------------------
# SOFT DELETE
# ---------------------------------------------------------------------------


async def soft_delete_experiment(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
) -> Experiment:
    """Soft-delete an experiment by setting ``deleted_at``.

    Raises:
        NotFoundError: If the experiment does not exist.
        ValidationError: If already soft-deleted.
    """
    experiment = await get_experiment(
        session,
        experiment_id,
        organization_id=organization_id,
        include_deleted=True,
    )

    if experiment.is_deleted:
        raise ValidationError(
            message=f"Experiment '{experiment_id}' is already deleted.",
            suggestion="Use include_deleted=true to view deleted experiments.",
        )

    experiment.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return experiment


# ---------------------------------------------------------------------------
# STATE TRANSITIONS
# ---------------------------------------------------------------------------


async def transition_experiment(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    new_status: ExperimentStatus,
    *,
    organization_id: uuid.UUID | None = None,
    outcome: dict[str, Any] | None = None,
) -> Experiment:
    """Transition an experiment to a new state.

    Enforces the state machine defined in ``EXPERIMENT_TRANSITIONS``.
    Automatically sets:
    - ``completed_at`` when entering completed/failed/cancelled
    - ``outcome`` when provided on completion/failure

    Args:
        session: Active async database session.
        experiment_id: UUID of the experiment.
        new_status: Target ExperimentStatus.
        organization_id: Optional org-scoping.
        outcome: Optional outcome data (only on completion/failure).

    Returns:
        The updated Experiment instance.

    Raises:
        NotFoundError: If the experiment does not exist.
        StateTransitionError: If the transition is invalid.
    """
    experiment = await get_experiment(session, experiment_id, organization_id=organization_id)

    current_status = ExperimentStatus(experiment.status)

    # Check terminal state
    if experiment.is_terminal:
        raise StateTransitionError(
            message=(
                f"Cannot transition from terminal state '{current_status.value}' "
                f"to '{new_status.value}'."
            ),
            suggestion=(
                f"Experiment is in terminal state '{current_status.value}'. "
                f"Create a new experiment instead."
            ),
        )

    # Check valid transitions
    valid = EXPERIMENT_TRANSITIONS.get(current_status, set())
    if new_status not in valid:
        valid_names = sorted(s.value for s in valid)
        raise StateTransitionError(
            message=(f"Cannot transition from '{current_status.value}' to '{new_status.value}'."),
            suggestion=(
                f"Valid transitions from '{current_status.value}': "
                f"{valid_names}. Use one of these statuses."
            ),
        )

    # Apply transition
    experiment.status = new_status.value
    now = datetime.now(timezone.utc)

    # Set timestamps based on target state
    if new_status in {
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
        ExperimentStatus.CANCELLED,
    }:
        experiment.completed_at = now

    # Record outcome on completion/failure
    if outcome is not None and new_status in {
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
    }:
        experiment.outcome = outcome

    await session.flush()
    return experiment


# ---------------------------------------------------------------------------
# UPLOAD LINKING
# ---------------------------------------------------------------------------


async def link_upload(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    upload_id: uuid.UUID,
    *,
    linked_by: uuid.UUID | None = None,
    linked_by_agent_token: uuid.UUID | None = None,
) -> ExperimentUpload:
    """Associate an upload with an experiment.

    Args:
        session: Active async database session.
        experiment_id: UUID of the experiment.
        upload_id: UUID of the upload to link.
        linked_by: User UUID who created the link.
        linked_by_agent_token: API token UUID if agent-linked.

    Returns:
        The ExperimentUpload link instance.

    Raises:
        NotFoundError: If the experiment does not exist.
        ValidationError: If the link already exists.
    """
    # Verify experiment exists
    await get_experiment(session, experiment_id)

    # Check for duplicate
    stmt = select(ExperimentUpload).where(
        ExperimentUpload.experiment_id == experiment_id,
        ExperimentUpload.upload_id == upload_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(
            message=(f"Upload '{upload_id}' is already linked to experiment '{experiment_id}'."),
            suggestion="Use unlink_upload to remove the existing link first.",
        )

    link = ExperimentUpload(
        experiment_id=experiment_id,
        upload_id=upload_id,
        linked_by=linked_by,
        linked_by_agent_token=linked_by_agent_token,
    )
    session.add(link)
    await session.flush()
    return link


async def unlink_upload(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    upload_id: uuid.UUID,
) -> None:
    """Remove the association between an upload and an experiment.

    Raises:
        NotFoundError: If the link does not exist.
    """
    stmt = select(ExperimentUpload).where(
        ExperimentUpload.experiment_id == experiment_id,
        ExperimentUpload.upload_id == upload_id,
    )
    link = (await session.execute(stmt)).scalar_one_or_none()
    if link is None:
        raise NotFoundError(
            message=(f"No link between upload '{upload_id}' and experiment '{experiment_id}'."),
            suggestion="Use get_experiment to see current upload links.",
        )

    await session.delete(link)
    await session.flush()


# ---------------------------------------------------------------------------
# PREDECESSOR LINKING
# ---------------------------------------------------------------------------


async def add_predecessor(
    session: AsyncSession,
    experiment_id: uuid.UUID,
    predecessor_id: uuid.UUID,
) -> ExperimentPredecessor:
    """Link an experiment to a predecessor in the experiment DAG.

    Raises:
        NotFoundError: If either experiment does not exist.
        ValidationError: If the link already exists or is self-referential.
    """
    if experiment_id == predecessor_id:
        raise ValidationError(
            message="An experiment cannot be its own predecessor.",
            suggestion="Provide a different experiment ID as the predecessor.",
        )

    # Verify both experiments exist
    await get_experiment(session, experiment_id)
    await get_experiment(session, predecessor_id)

    # Check duplicate
    stmt = select(ExperimentPredecessor).where(
        ExperimentPredecessor.experiment_id == experiment_id,
        ExperimentPredecessor.predecessor_id == predecessor_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(
            message=(
                f"Experiment '{predecessor_id}' is already a predecessor of '{experiment_id}'."
            ),
            suggestion="Use the experiment DAG endpoint to view existing links.",
        )

    link = ExperimentPredecessor(
        experiment_id=experiment_id,
        predecessor_id=predecessor_id,
    )
    session.add(link)
    await session.flush()
    return link
