"""Instruments router — CRUD for lab instruments.

Endpoints:
    POST  /instruments/     — Register a new instrument
    GET   /instruments/     — List instruments for the current organization
    GET   /instruments/{id} — Get an instrument by ID
    PATCH /instruments/{id} — Update an instrument
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError
from lablink.models import Organization, User
from lablink.models import Instrument
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.schemas.instruments import (
    InstrumentCreate,
    InstrumentResponse,
    InstrumentUpdate,
)

router = APIRouter(prefix="/instruments", tags=["instruments"])


# ---------------------------------------------------------------------------
# POST /instruments/
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=Envelope[InstrumentResponse],
    status_code=201,
    operation_id="create_instrument",
    response_model_exclude_none=True,
)
async def create_instrument(
    body: InstrumentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Register a new instrument within the current organization."""
    instrument = Instrument(
        organization_id=org.id,
        name=body.name,
        instrument_type=body.instrument_type.value,
        manufacturer=body.manufacturer,
        model=body.model,
        serial_number=body.serial_number,
        location=body.location,
    )
    db.add(instrument)
    await db.flush()
    return success_response(data=InstrumentResponse.model_validate(instrument))


# ---------------------------------------------------------------------------
# GET /instruments/
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=Envelope[list[InstrumentResponse]],
    operation_id="list_instruments",
    response_model_exclude_none=True,
)
async def list_instruments(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    instrument_type: str | None = Query(None, description="Filter by instrument type"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List instruments for the current organization."""
    base = select(Instrument).where(Instrument.organization_id == org.id)
    if instrument_type:
        base = base.where(Instrument.instrument_type == instrument_type)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        base
        .order_by(Instrument.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    instruments = [InstrumentResponse.model_validate(i) for i in result.scalars().all()]

    return success_response(
        data=instruments,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /instruments/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{instrument_id}",
    response_model=Envelope[InstrumentResponse],
    operation_id="get_instrument",
    response_model_exclude_none=True,
)
async def get_instrument(
    instrument_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get an instrument by ID."""
    stmt = select(Instrument).where(
        Instrument.id == instrument_id,
        Instrument.organization_id == org.id,
    )
    result = await db.execute(stmt)
    instrument = result.scalar_one_or_none()

    if instrument is None:
        raise NotFoundError(
            message=f"Instrument '{instrument_id}' not found",
            suggestion="Use list_instruments to find valid instrument IDs.",
        )
    return success_response(data=InstrumentResponse.model_validate(instrument))


# ---------------------------------------------------------------------------
# PATCH /instruments/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{instrument_id}",
    response_model=Envelope[InstrumentResponse],
    operation_id="update_instrument",
    response_model_exclude_none=True,
)
async def update_instrument(
    instrument_id: uuid.UUID,
    body: InstrumentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Update an instrument's fields (PATCH semantics)."""
    stmt = select(Instrument).where(
        Instrument.id == instrument_id,
        Instrument.organization_id == org.id,
    )
    result = await db.execute(stmt)
    instrument = result.scalar_one_or_none()

    if instrument is None:
        raise NotFoundError(
            message=f"Instrument '{instrument_id}' not found",
            suggestion="Use list_instruments to find valid instrument IDs.",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "metadata":
            instrument.metadata_ = value
        else:
            setattr(instrument, field, value)

    await db.flush()
    return success_response(data=InstrumentResponse.model_validate(instrument))
