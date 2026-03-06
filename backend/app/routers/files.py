"""File upload router — thin router delegating to file_service.

Accepts multipart file uploads, computes SHA-256, checks for duplicates,
stores the file, and returns the response envelope with dedup status.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.database import get_session
from app.schemas.envelope import Envelope
from app.schemas.file_upload import FileUploadResponse
from app.services.file_service import upload_file

logger = logging.getLogger("lablink.routers.files")

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "/upload",
    response_model=Envelope[FileUploadResponse],
    status_code=201,
    summary="Upload an instrument data file",
    description=(
        "Upload a file from an instrument. Computes SHA-256 hash for "
        "content-addressable dedup. If an identical file already exists, "
        "returns the existing record with is_duplicate=True (HTTP 200)."
    ),
    responses={
        200: {
            "description": "Duplicate file — already ingested",
            "model": Envelope[FileUploadResponse],
        },
    },
)
async def upload_file_endpoint(
    request: Request,
    file: UploadFile = File(..., description="The instrument data file to upload"),
    instrument_id: str = Form(..., description="UUID of the source instrument"),
    lab_id: str = Form(..., description="UUID of the owning lab"),
    uploaded_by: str | None = Form(None, description="UUID of the uploading user (optional)"),
    watched_folder_id: str | None = Form(
        None, description="UUID of the watched folder (optional, for agent uploads)"
    ),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Upload an instrument data file with automatic deduplication.

    The endpoint:
    1. Reads the file content and computes its SHA-256 hash
    2. Checks the database for an existing file with the same hash
    3. If duplicate: returns existing record with is_duplicate=True (HTTP 200)
    4. If new: stores the file and creates an immutable FileRecord (HTTP 201)

    Returns an Envelope[FileUploadResponse] with dedup status and
    agent-friendly suggestions for next steps.
    """
    content = await file.read()
    file_name = file.filename or "unknown"
    mime_type = file.content_type

    request_id = getattr(request.state, "request_id", None)

    record, is_new = await upload_file(
        session=session,
        content=content,
        file_name=file_name,
        instrument_id=instrument_id,
        lab_id=lab_id,
        uploaded_by=uploaded_by,
        watched_folder_id=watched_folder_id,
        mime_type=mime_type,
        settings=settings,
    )

    is_duplicate = not is_new

    if is_duplicate:
        suggestion = (
            f"File already ingested as record '{record.id}'. "
            "Use GET /api/v1/files/{id} to check its processing status, "
            "or POST /api/v1/files/{id}/reparse to re-parse with a different parser version."
        )
    else:
        suggestion = (
            "File uploaded successfully. "
            f"Use POST /api/v1/files/{record.id}/parse to trigger parsing, "
            "or wait for automatic parsing if Celery is enabled."
        )

    response_data = FileUploadResponse(
        file_record_id=record.id,
        file_name=record.file_name,
        file_hash=record.file_hash,
        file_size_bytes=record.file_size_bytes,
        status=record.status,
        is_duplicate=is_duplicate,
        storage_path=record.storage_path,
        created_at=record.created_at,
        suggestion=suggestion,
    )

    envelope = Envelope.ok(response_data, request_id=request_id)
    status_code = 200 if is_duplicate else 201

    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
    )
