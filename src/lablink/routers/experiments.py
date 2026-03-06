"""Experiments router — CRUD, state transitions, outcome recording, and upload linking.

Endpoints:
    POST   /experiments/                         — Create an experiment
    GET    /experiments/                         — List experiments
    GET    /experiments/{id}                     — Get an experiment by ID
    PATCH  /experiments/{id}                     — Update experiment (status transition)
    POST   /experiments/{id}/outcome             — Record experiment outcome
    POST   /experiments/{id}/link-upload         — Link an upload to an experiment
    DELETE /experiments/{id}/link-upload/{upload_id} — Unlink an upload
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.models.identity import Organization, User
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.schemas.experiments import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
    LinkUploadRequest,
    OutcomeRequest,
)
from lablink.services.experiment_service import (
    create_experiment,
    get_experiment,
    link_upload,
    list_experiments,
    transition_experiment,
    unlink_upload,
    update_experiment,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


# ---------------------------------------------------------------------------
# POST /experiments/
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=Envelope[ExperimentResponse],
    status_code=201,
    operation_id="create_experiment",
    response_model_exclude_none=True,
)
async def create_exp(
    body: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Create a new experiment in PLANNED status."""
    experiment = await create_experiment(
        db,
        organization_id=org.id,
        intent=body.intent,
        hypothesis=body.hypothesis,
        parameters=body.parameters,
        campaign_id=body.campaign_id,
        created_by=user.id,
    )
    return success_response(data=ExperimentResponse.model_validate(experiment))


# ---------------------------------------------------------------------------
# GET /experiments/
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=Envelope[list[ExperimentResponse]],
    operation_id="list_experiments",
    response_model_exclude_none=True,
)
async def list_exps(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by experiment status"),
    campaign_id: uuid.UUID | None = Query(None, description="Filter by campaign"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List experiments for the current organization."""
    from lablink.models.experiment import ExperimentStatus

    status_enum = None
    if status:
        try:
            status_enum = ExperimentStatus(status)
        except ValueError:
            from lablink.exceptions import ValidationError

            raise ValidationError(
                message=f"Invalid status '{status}'",
                suggestion=f"Valid statuses: {[s.value for s in ExperimentStatus]}",
                field="status",
            )

    experiments, total = await list_experiments(
        db,
        organization_id=org.id,
        status=status_enum,
        campaign_id=campaign_id,
        page=page,
        page_size=page_size,
    )

    return success_response(
        data=[ExperimentResponse.model_validate(e) for e in experiments],
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /experiments/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{experiment_id}",
    response_model=Envelope[ExperimentResponse],
    operation_id="get_experiment",
    response_model_exclude_none=True,
)
async def get_exp(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get an experiment by ID."""
    experiment = await get_experiment(db, experiment_id, organization_id=org.id)
    return success_response(data=ExperimentResponse.model_validate(experiment))


# ---------------------------------------------------------------------------
# PATCH /experiments/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{experiment_id}",
    response_model=Envelope[ExperimentResponse],
    operation_id="update_experiment",
    response_model_exclude_none=True,
)
async def update_exp(
    experiment_id: uuid.UUID,
    body: ExperimentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Update an experiment. Status changes follow the experiment state machine."""
    if body.status is not None:
        experiment = await transition_experiment(
            db,
            experiment_id,
            body.status,
            organization_id=org.id,
        )
    else:
        experiment = await update_experiment(
            db,
            experiment_id,
            organization_id=org.id,
        )
    return success_response(data=ExperimentResponse.model_validate(experiment))


# ---------------------------------------------------------------------------
# POST /experiments/{id}/outcome
# ---------------------------------------------------------------------------


@router.post(
    "/{experiment_id}/outcome",
    response_model=Envelope[ExperimentResponse],
    operation_id="record_experiment_outcome",
    response_model_exclude_none=True,
)
async def record_outcome(
    experiment_id: uuid.UUID,
    body: OutcomeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Record the outcome of an experiment and transition to completed/failed."""
    from lablink.models.experiment import ExperimentStatus

    target_status = ExperimentStatus.COMPLETED if body.success else ExperimentStatus.FAILED
    outcome_data = {"results": body.results, "success": body.success}

    experiment = await transition_experiment(
        db,
        experiment_id,
        target_status,
        organization_id=org.id,
        outcome=outcome_data,
    )
    return success_response(data=ExperimentResponse.model_validate(experiment))


# ---------------------------------------------------------------------------
# POST /experiments/{id}/link-upload
# ---------------------------------------------------------------------------


@router.post(
    "/{experiment_id}/link-upload",
    response_model=Envelope[dict],
    status_code=201,
    operation_id="link_upload_to_experiment",
    response_model_exclude_none=True,
)
async def link_upload_to_exp(
    experiment_id: uuid.UUID,
    body: LinkUploadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Link an upload (instrument data file) to an experiment."""
    link = await link_upload(
        db,
        experiment_id=experiment_id,
        upload_id=body.upload_id,
        linked_by=user.id,
    )
    return success_response(
        data={
            "experiment_id": str(link.experiment_id),
            "upload_id": str(link.upload_id),
            "linked_at": link.linked_at.isoformat() if link.linked_at else None,
        }
    )


# ---------------------------------------------------------------------------
# DELETE /experiments/{id}/link-upload/{upload_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{experiment_id}/link-upload/{upload_id}",
    response_model=Envelope[dict],
    operation_id="unlink_upload_from_experiment",
    response_model_exclude_none=True,
)
async def unlink_upload_from_exp(
    experiment_id: uuid.UUID,
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Remove the association between an upload and an experiment."""
    await unlink_upload(db, experiment_id=experiment_id, upload_id=upload_id)
    return success_response(data={"unlinked": True})
