"""Experiment router — thin layer delegating to experiment service.

Endpoints:
  POST   /experiments               — Create experiment
  GET    /experiments                — List experiments (paginated)
  GET    /experiments/{id}           — Get single experiment
  PATCH  /experiments/{id}           — Update experiment fields
  DELETE /experiments/{id}           — Soft-delete experiment
  POST   /experiments/{id}/transition — Transition experiment state
"""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.experiment import ExperimentStatus
from app.schemas.envelope import Envelope
from app.schemas.experiment import (
    ExperimentCreate,
    ExperimentListResponse,
    ExperimentRead,
    ExperimentStateTransition,
    ExperimentUpdate,
)
from app.services.experiment import (
    create_experiment,
    get_experiment,
    list_experiments,
    soft_delete_experiment,
    transition_experiment,
    update_experiment,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _to_response(experiment) -> ExperimentRead:
    """Convert an Experiment ORM model to a response schema.

    ExperimentRead's model_validator(mode='before') handles ORM -> dict
    conversion, JSON deserialization, and computing agent-native fields.
    """
    return ExperimentRead.model_validate(experiment)


@router.post("", response_model=Envelope[ExperimentRead], status_code=201)
async def create(
    body: ExperimentCreate,
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExperimentRead]:
    """Create a new experiment in DRAFT state.

    Requires org_id from the authenticated user context. For now, uses a
    default org_id placeholder until auth dependency is wired in.
    """
    # TODO: Get org_id from authenticated user once auth is wired into this router
    org_id = "default-org"

    orm_dict = body.to_orm_dict()
    experiment = await create_experiment(
        session,
        org_id=org_id,
        name=orm_dict.pop("name"),
        description=orm_dict.get("description"),
        hypothesis=orm_dict.get("hypothesis"),
        intent=orm_dict.get("intent"),
        project_id=orm_dict.get("project_id"),
        campaign_id=orm_dict.get("campaign_id"),
        parameters_json=orm_dict.get("parameters_json"),
        protocol=orm_dict.get("protocol"),
    )
    return Envelope.ok(_to_response(experiment))


@router.get("", response_model=Envelope[ExperimentListResponse])
async def list_all(
    status: ExperimentStatus | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExperimentListResponse]:
    """List experiments with optional filtering and pagination."""
    experiments, total = await list_experiments(
        session,
        status=status,
        page=page,
        page_size=page_size,
    )
    items = [_to_response(e) for e in experiments]
    return Envelope.ok(
        ExperimentListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{experiment_id}", response_model=Envelope[ExperimentRead])
async def get_one(
    experiment_id: str,
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExperimentRead]:
    """Get a single experiment by ID."""
    experiment = await get_experiment(session, experiment_id)
    return Envelope.ok(_to_response(experiment))


@router.patch("/{experiment_id}", response_model=Envelope[ExperimentRead])
async def update(
    experiment_id: str,
    body: ExperimentUpdate,
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExperimentRead]:
    """Update experiment fields (partial update)."""
    orm_dict = body.to_orm_dict()
    experiment = await update_experiment(
        session,
        experiment_id,
        **orm_dict,
    )
    return Envelope.ok(_to_response(experiment))


@router.delete("/{experiment_id}", response_model=Envelope[ExperimentRead])
async def delete(
    experiment_id: str,
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExperimentRead]:
    """Soft-delete an experiment."""
    experiment = await soft_delete_experiment(session, experiment_id)
    return Envelope.ok(_to_response(experiment))


@router.post(
    "/{experiment_id}/transition",
    response_model=Envelope[ExperimentRead],
)
async def transition(
    experiment_id: str,
    body: ExperimentStateTransition,
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExperimentRead]:
    """Transition an experiment to a new state.

    Valid transitions:
      draft -> running | cancelled
      running -> completed | failed

    Returns an error with suggestion field for invalid transitions.
    """
    # Convert outcome dict to JSON string for the service layer
    outcome_json = None
    if body.outcome is not None:
        outcome_json = _json.dumps(body.outcome)

    experiment = await transition_experiment(
        session,
        experiment_id,
        target_status=body.target_status,
        outcome_summary=body.outcome_summary,
        outcome_json=outcome_json,
        success=body.success,
    )
    return Envelope.ok(_to_response(experiment))
