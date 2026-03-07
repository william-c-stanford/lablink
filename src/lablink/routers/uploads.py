"""Uploads router — file upload, listing, reparse, and raw download.

Endpoints:
    POST /uploads/              — Upload a file (multipart form)
    GET  /uploads/              — List uploads for the current organization
    GET  /uploads/{id}          — Get an upload by ID
    POST /uploads/{id}/reparse  — Trigger re-parsing of an upload
    GET  /uploads/{id}/raw      — Download the raw file
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.dependencies import get_current_org, get_current_user, get_db
from lablink.exceptions import NotFoundError, ValidationError
from lablink.models.organization import Organization
from lablink.models.user import User
from lablink.schemas.envelope import Envelope, PaginationMeta, success_response
from lablink.schemas.uploads import UploadResponse
from lablink.services.upload_service import DuplicateUploadError, UploadError, UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


# ---------------------------------------------------------------------------
# POST /uploads/
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=Envelope[UploadResponse],
    status_code=201,
    operation_id="upload_file",
    response_model_exclude_none=True,
)
async def upload_file(
    file: UploadFile = File(..., description="Instrument data file to upload"),
    project_id: uuid.UUID | None = Query(None, description="Associate with a project"),
    instrument_id: uuid.UUID | None = Query(None, description="Associate with an instrument"),
    allow_duplicate: bool = Query(False, description="Allow duplicate file uploads"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Upload an instrument data file for parsing and indexing."""
    file_bytes = await file.read()
    filename = file.filename or "unnamed"

    service = UploadService(db=db)
    try:
        upload = await service.upload_file(
            file_bytes=file_bytes,
            filename=filename,
            organization_id=org.id,
            project_id=project_id,
            instrument_id=instrument_id,
            uploaded_by=user.id,
            allow_duplicate=allow_duplicate,
        )
    except DuplicateUploadError as exc:
        raise ValidationError(
            message=exc.message,
            suggestion=exc.suggestion,
            field="file",
        )
    except UploadError as exc:
        raise ValidationError(
            message=exc.message,
            suggestion=exc.suggestion,
        )

    return success_response(data=UploadResponse.model_validate(upload))


# ---------------------------------------------------------------------------
# GET /uploads/
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=Envelope[list[UploadResponse]],
    operation_id="list_uploads",
    response_model_exclude_none=True,
)
async def list_uploads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by pipeline status"),
    project_id: uuid.UUID | None = Query(None, description="Filter by project"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """List uploads for the current organization with optional filters."""
    from lablink.models.upload import UploadStatus

    status_enum = None
    if status:
        try:
            status_enum = UploadStatus(status)
        except ValueError:
            raise ValidationError(
                message=f"Invalid status '{status}'",
                suggestion=f"Valid statuses: {[s.value for s in UploadStatus]}",
                field="status",
            )

    service = UploadService(db=db)
    offset = (page - 1) * page_size
    uploads, total = await service.list_uploads(
        organization_id=org.id,
        status=status_enum,
        project_id=project_id,
        limit=page_size,
        offset=offset,
    )

    upload_responses = [UploadResponse.model_validate(u) for u in uploads]

    return success_response(
        data=upload_responses,
        pagination=PaginationMeta(
            total_count=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /uploads/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{upload_id}",
    response_model=Envelope[UploadResponse],
    operation_id="get_upload",
    response_model_exclude_none=True,
)
async def get_upload(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Get an upload by ID."""
    service = UploadService(db=db)
    upload = await service.get_upload(upload_id)

    if upload is None or upload.organization_id != org.id:
        raise NotFoundError(
            message=f"Upload '{upload_id}' not found",
            suggestion="Use list_uploads to find valid upload IDs.",
        )
    return success_response(data=UploadResponse.model_validate(upload))


# ---------------------------------------------------------------------------
# POST /uploads/{id}/reparse
# ---------------------------------------------------------------------------


@router.post(
    "/{upload_id}/reparse",
    response_model=Envelope[UploadResponse],
    operation_id="reparse_upload",
    response_model_exclude_none=True,
)
async def reparse_upload(
    upload_id: uuid.UUID,
    instrument_type: str | None = Query(None, description="Instrument type hint for parser selection"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Envelope:
    """Trigger re-parsing of an upload with an optional instrument type hint."""
    from lablink.services.parser_service import ParserService

    service = UploadService(db=db)
    upload = await service.get_upload(upload_id)

    if upload is None or upload.organization_id != org.id:
        raise NotFoundError(
            message=f"Upload '{upload_id}' not found",
            suggestion="Use list_uploads to find valid upload IDs.",
        )

    parser_service = ParserService(db=db)
    try:
        await parser_service.parse_upload(upload_id, instrument_type=instrument_type)
    except Exception as exc:
        raise ValidationError(
            message=f"Re-parse failed: {exc}",
            suggestion="Check the file format and instrument type hint.",
        )

    # Refresh the upload record
    await db.refresh(upload)
    return success_response(data=UploadResponse.model_validate(upload))


# ---------------------------------------------------------------------------
# GET /uploads/{id}/raw
# ---------------------------------------------------------------------------


@router.get(
    "/{upload_id}/raw",
    operation_id="download_raw_file",
    response_class=Response,
)
async def download_raw_file(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """Download the raw uploaded file."""
    service = UploadService(db=db)

    upload = await service.get_upload(upload_id)
    if upload is None or upload.organization_id != org.id:
        raise NotFoundError(
            message=f"Upload '{upload_id}' not found",
            suggestion="Use list_uploads to find valid upload IDs.",
        )

    try:
        data, filename, mime_type = await service.download_file(upload_id)
    except UploadError as exc:
        raise NotFoundError(
            message=exc.message,
            suggestion=exc.suggestion,
        )

    return Response(
        content=data,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
