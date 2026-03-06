"""Experiment service — fat service for experiment CRUD and state machine.

Handles all business logic for experiments including:
- CRUD operations
- State machine transitions with validation
- Soft delete
- Pagination and filtering
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError, StateTransitionError, ValidationError
from app.models.experiment import (
    EXPERIMENT_TRANSITIONS,
    Experiment,
    ExperimentStatus,
)


async def create_experiment(
    session: AsyncSession,
    *,
    org_id: str,
    name: str,
    description: str | None = None,
    hypothesis: str | None = None,
    intent: str | None = None,
    project_id: str | None = None,
    campaign_id: str | None = None,
    parameters_json: str | None = None,
    protocol: str | None = None,
    created_by: str | None = None,
) -> Experiment:
    """Create a new experiment in DRAFT state.

    Args:
        session: Async database session.
        org_id: Organization ID the experiment belongs to.
        name: Experiment display name.
        description: Optional detailed description.
        hypothesis: Optional scientific hypothesis.
        intent: Optional brief goal statement.
        project_id: Optional project ID.
        campaign_id: Optional campaign ID.
        parameters_json: Optional experiment parameters as JSON string.
        protocol: Optional protocol description.
        created_by: Optional user ID of the creator.

    Returns:
        The newly created Experiment.
    """
    experiment = Experiment(
        org_id=org_id,
        name=name,
        description=description,
        hypothesis=hypothesis,
        intent=intent,
        project_id=project_id,
        campaign_id=campaign_id,
        parameters_json=parameters_json,
        protocol=protocol,
        status=ExperimentStatus.DRAFT.value,
        created_by=created_by,
    )
    session.add(experiment)
    await session.flush()
    return experiment


async def get_experiment(
    session: AsyncSession,
    experiment_id: str,
    *,
    org_id: str | None = None,
    include_deleted: bool = False,
) -> Experiment:
    """Get an experiment by ID.

    Args:
        session: Async database session.
        experiment_id: The experiment UUID.
        org_id: If provided, scope to this organization.
        include_deleted: Whether to include soft-deleted experiments.

    Returns:
        The Experiment.

    Raises:
        NotFoundError: If the experiment does not exist.
    """
    stmt = select(Experiment).where(Experiment.id == experiment_id)

    if org_id is not None:
        stmt = stmt.where(Experiment.org_id == org_id)

    if not include_deleted:
        stmt = stmt.where(Experiment.deleted_at.is_(None))

    result = await session.execute(stmt)
    experiment = result.scalar_one_or_none()

    if experiment is None:
        raise NotFoundError(
            message=f"Experiment '{experiment_id}' not found.",
            suggestion="Check the experiment ID. Use GET /api/v1/experiments to list available experiments.",
        )

    return experiment


async def list_experiments(
    session: AsyncSession,
    *,
    org_id: str | None = None,
    status: ExperimentStatus | None = None,
    page: int = 1,
    page_size: int = 20,
    include_deleted: bool = False,
) -> tuple[list[Experiment], int]:
    """List experiments with optional filtering and pagination.

    Args:
        session: Async database session.
        org_id: Filter by organization.
        status: Filter by experiment status.
        page: Page number (1-indexed).
        page_size: Items per page.
        include_deleted: Whether to include soft-deleted experiments.

    Returns:
        Tuple of (experiments list, total count).
    """
    base = select(Experiment)
    count_base = select(func.count(Experiment.id))

    if org_id is not None:
        base = base.where(Experiment.org_id == org_id)
        count_base = count_base.where(Experiment.org_id == org_id)

    if status is not None:
        base = base.where(Experiment.status == status.value)
        count_base = count_base.where(Experiment.status == status.value)

    if not include_deleted:
        base = base.where(Experiment.deleted_at.is_(None))
        count_base = count_base.where(Experiment.deleted_at.is_(None))

    # Get total count
    total_result = await session.execute(count_base)
    total = total_result.scalar() or 0

    # Get paginated results
    offset = (page - 1) * page_size
    stmt = base.order_by(Experiment.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    experiments = list(result.scalars().all())

    return experiments, total


async def update_experiment(
    session: AsyncSession,
    experiment_id: str,
    *,
    org_id: str | None = None,
    **fields: object,
) -> Experiment:
    """Update an experiment's fields.

    Only non-None values in fields are applied. Cannot update experiments
    in terminal states (completed, failed, cancelled).

    Args:
        session: Async database session.
        experiment_id: The experiment UUID.
        org_id: If provided, scope to this organization.
        **fields: Field values to update.

    Returns:
        The updated Experiment.

    Raises:
        NotFoundError: If the experiment does not exist.
        ValidationError: If the experiment is in a terminal state.
    """
    experiment = await get_experiment(session, experiment_id, org_id=org_id)

    if experiment.is_terminal:
        raise ValidationError(
            message=f"Cannot update experiment in '{experiment.status}' state.",
            suggestion=f"Experiment is in terminal state '{experiment.status}'. Create a new experiment instead.",
            field="status",
        )

    # Apply only provided (non-None) fields
    updatable = {
        "name", "description", "hypothesis", "intent",
        "project_id", "campaign_id", "parameters_json", "protocol",
        "outcome_json", "outcome_summary", "success",
    }
    for key, value in fields.items():
        if key in updatable and value is not None:
            setattr(experiment, key, value)

    await session.flush()
    return experiment


async def soft_delete_experiment(
    session: AsyncSession,
    experiment_id: str,
    *,
    org_id: str | None = None,
) -> Experiment:
    """Soft-delete an experiment by setting deleted_at.

    Args:
        session: Async database session.
        experiment_id: The experiment UUID.
        org_id: If provided, scope to this organization.

    Returns:
        The soft-deleted Experiment.

    Raises:
        NotFoundError: If the experiment does not exist.
        ValidationError: If the experiment is already deleted.
    """
    experiment = await get_experiment(
        session, experiment_id, org_id=org_id, include_deleted=True
    )

    if experiment.is_deleted:
        raise ValidationError(
            message=f"Experiment '{experiment_id}' is already deleted.",
            suggestion="This experiment was previously deleted. No further action needed.",
        )

    experiment.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    return experiment


async def transition_experiment(
    session: AsyncSession,
    experiment_id: str,
    target_status: ExperimentStatus,
    *,
    org_id: str | None = None,
    outcome_summary: str | None = None,
    outcome_json: str | None = None,
    success: bool | None = None,
) -> Experiment:
    """Transition an experiment to a new state.

    Validates the transition against the state machine before applying.
    Automatically sets started_at and completed_at timestamps.

    Args:
        session: Async database session.
        experiment_id: The experiment UUID.
        target_status: The desired new state.
        org_id: If provided, scope to this organization.
        outcome_summary: Optional outcome summary (for completed/failed).
        outcome_json: Optional outcome data (for completed/failed).
        success: Optional success flag (for completed/failed).

    Returns:
        The updated Experiment.

    Raises:
        NotFoundError: If the experiment does not exist.
        StateTransitionError: If the transition is invalid.
    """
    experiment = await get_experiment(session, experiment_id, org_id=org_id)

    current_status = ExperimentStatus(experiment.status)
    valid_targets = EXPERIMENT_TRANSITIONS.get(current_status, set())

    if target_status not in valid_targets:
        valid_names = [s.value for s in sorted(valid_targets, key=lambda s: s.value)]
        if valid_names:
            suggestion = (
                f"Current state is '{current_status.value}'. "
                f"Valid transitions: {', '.join(valid_names)}. "
                f"Use one of these as target_status."
            )
        else:
            suggestion = (
                f"Experiment is in terminal state '{current_status.value}' "
                f"and cannot transition further. Create a new experiment instead."
            )

        raise StateTransitionError(
            message=(
                f"Cannot transition from '{current_status.value}' to '{target_status.value}'."
            ),
            suggestion=suggestion,
            field="target_status",
        )

    now = datetime.now(timezone.utc)

    # Apply the transition
    experiment.status = target_status.value

    # Set timestamps based on target state
    if target_status == ExperimentStatus.RUNNING:
        experiment.started_at = now
    elif target_status in (
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
        ExperimentStatus.CANCELLED,
    ):
        experiment.completed_at = now

    # Apply outcome fields if provided
    if outcome_summary is not None:
        experiment.outcome_summary = outcome_summary
    if outcome_json is not None:
        experiment.outcome_json = outcome_json
    if success is not None:
        experiment.success = success

    await session.flush()
    return experiment
