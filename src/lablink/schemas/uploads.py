"""Pydantic schemas for Upload responses and query parameters.

Provides UploadResponse and UploadListParams aligned to the Upload ORM model
in lablink.models.data_pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from lablink.models import UploadStatus


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Full upload record returned by API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique upload identifier")
    filename: str = Field(..., description="Original filename of the uploaded file")
    content_hash: str = Field(..., description="SHA-256 hash of file contents for deduplication")
    file_size_bytes: int = Field(..., description="File size in bytes")
    s3_key: str = Field(..., description="S3 object key where the file is stored")
    mime_type: str | None = Field(None, description="Detected MIME type of the file")
    status: str = Field(..., description="Pipeline status: uploaded, parsing, parsed, parse_failed, indexed")
    error_message: str | None = Field(None, description="Error details if parsing failed")
    instrument_type_detected: str | None = Field(
        None, description="Instrument type detected by the parser"
    )
    parser_used: str | None = Field(None, description="Name of the parser that processed the file")
    created_at: datetime = Field(..., description="Upload timestamp")
    parsed_at: datetime | None = Field(None, description="Timestamp when parsing completed")
    indexed_at: datetime | None = Field(None, description="Timestamp when indexing to Elasticsearch completed")
    project_id: uuid.UUID | None = Field(None, description="Associated project, if any")
    instrument_id: uuid.UUID | None = Field(None, description="Associated instrument, if any")


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------


class UploadListParams(BaseModel):
    """Query parameters for listing uploads with filtering and pagination."""

    status: UploadStatus | None = Field(
        default=None,
        description="Filter by pipeline status",
    )
    instrument_id: uuid.UUID | None = Field(
        default=None,
        description="Filter by instrument ID",
    )
    created_after: datetime | None = Field(
        default=None,
        description="Only include uploads created after this timestamp (UTC)",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (1-indexed)",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (max 100)",
    )
