"""Data router — parsed data retrieval, search, chart data, and exports.

Endpoints:
    GET  /data/{upload_id}       — Get parsed data for an upload
    POST /search                 — Full-text search across instrument data
    GET  /data/{upload_id}/chart — Get chart-ready data for an upload
    POST /exports                — Create a data export job
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError
from lablink.models.parsed_data import ParsedData
from lablink.models.upload import Upload
from lablink.models.organization import Organization
from lablink.models.user import User
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.services.export_service import ExportRequest, ExportService
from lablink.services.search_service import get_search_service

router = APIRouter(tags=["data"])


# ---------------------------------------------------------------------------
# Request / Response schemas (local to this router)
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Full-text search request body."""

    query: str | None = Field(None, description="Free-text search query")
    instrument_type: str | None = Field(None, description="Filter by instrument type")
    measurement_type: str | None = Field(None, description="Filter by measurement type")
    project_id: str | None = Field(None, description="Filter by project ID")
    date_from: datetime | None = Field(None, description="Start of date range")
    date_to: datetime | None = Field(None, description="End of date range")
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")


class ExportCreateRequest(BaseModel):
    """Request body to create a data export."""

    format: str = Field(..., description="Export format: csv, json, xlsx, pdf")
    upload_ids: list[str] = Field(default_factory=list, description="Specific upload IDs to export")
    filters: dict[str, Any] = Field(default_factory=dict, description="Filter criteria for the export")


class ParsedDataResponse(BaseModel):
    """Parsed data record returned by API."""

    id: uuid.UUID
    upload_id: uuid.UUID
    instrument_type: str
    parser_version: str
    measurement_type: str | None = None
    sample_count: int | None = None
    data_summary: dict[str, Any]
    measurements: list[dict[str, Any]]
    instrument_settings: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GET /data/{upload_id}
# ---------------------------------------------------------------------------


@router.get(
    "/data/{upload_id}",
    response_model=Envelope[list[ParsedDataResponse]],
    operation_id="get_parsed_data",
    response_model_exclude_none=True,
)
async def get_parsed_data(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get parsed instrument data for a specific upload."""
    # Verify upload exists and belongs to the org
    upload = await db.get(Upload, upload_id)
    if upload is None or upload.organization_id != org.id:
        raise NotFoundError(
            message=f"Upload '{upload_id}' not found",
            suggestion="Use list_uploads to find valid upload IDs.",
        )

    stmt = select(ParsedData).where(ParsedData.upload_id == upload_id)
    result = await db.execute(stmt)
    parsed_records = [ParsedDataResponse.model_validate(p) for p in result.scalars().all()]

    return success_response(data=parsed_records)


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


@router.post(
    "/search",
    response_model=Envelope[dict],
    operation_id="search_data",
    response_model_exclude_none=True,
)
async def search_data(
    body: SearchRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Full-text search across parsed instrument data."""
    search_svc = get_search_service()
    result = await search_svc.search(
        org_id=org.id,
        query=body.query,
        instrument_type=body.instrument_type,
        measurement_type=body.measurement_type,
        project_id=body.project_id,
        date_from=body.date_from,
        date_to=body.date_to,
        page=body.page,
        page_size=body.page_size,
    )

    return success_response(
        data=result,
        pagination=PaginationMeta(
            total_count=result["total"],
            page=body.page,
            page_size=body.page_size,
            has_more=(body.page * body.page_size) < result["total"],
        ),
    )


# ---------------------------------------------------------------------------
# GET /data/{upload_id}/chart
# ---------------------------------------------------------------------------


@router.get(
    "/data/{upload_id}/chart",
    response_model=Envelope[dict],
    operation_id="get_chart_data",
    response_model_exclude_none=True,
)
async def get_chart_data(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get chart-ready data for a specific upload (structured for Plotly.js)."""
    upload = await db.get(Upload, upload_id)
    if upload is None or upload.organization_id != org.id:
        raise NotFoundError(
            message=f"Upload '{upload_id}' not found",
            suggestion="Use list_uploads to find valid upload IDs.",
        )

    stmt = select(ParsedData).where(ParsedData.upload_id == upload_id)
    result = await db.execute(stmt)
    parsed_list = result.scalars().all()

    if not parsed_list:
        return success_response(data={"traces": [], "layout": {}})

    # Build Plotly-compatible traces from parsed data
    traces: list[dict[str, Any]] = []
    for parsed in parsed_list:
        x_vals: list[Any] = []
        y_vals: list[Any] = []
        labels: list[str] = []

        for i, measurement in enumerate(parsed.measurements or []):
            if isinstance(measurement, dict):
                x_vals.append(measurement.get("sample_name") or measurement.get("sample_id") or i)
                y_vals.append(measurement.get("value", 0))
                labels.append(measurement.get("measurement_type", ""))

        traces.append({
            "x": x_vals,
            "y": y_vals,
            "type": "scatter",
            "mode": "lines+markers",
            "name": parsed.measurement_type or parsed.instrument_type,
        })

    layout = {
        "title": f"{upload.filename} - {parsed_list[0].instrument_type}",
        "xaxis": {"title": "Sample"},
        "yaxis": {"title": "Value"},
    }

    return success_response(data={"traces": traces, "layout": layout})


# ---------------------------------------------------------------------------
# POST /exports
# ---------------------------------------------------------------------------


@router.post(
    "/exports",
    response_model=Envelope[dict],
    status_code=201,
    operation_id="create_export",
    response_model_exclude_none=True,
)
async def create_export(
    body: ExportCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Create a data export job in the requested format."""
    from lablink.services.export_service import ExportFormat

    try:
        fmt = ExportFormat(body.format)
    except ValueError:
        from lablink.exceptions import ValidationError

        raise ValidationError(
            message=f"Unsupported export format: '{body.format}'",
            suggestion=f"Supported formats: {[f.value for f in ExportFormat]}",
            field="format",
        )

    export_svc = ExportService.from_settings()
    request = ExportRequest(
        format=fmt,
        upload_ids=body.upload_ids,
        filters=body.filters,
    )
    job = await export_svc.create_export(db, organization_id=org.id, request=request)

    return success_response(data=job.model_dump(mode="json"))
