"""Pydantic schemas for file upload endpoint responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """Response data for a file upload operation.

    Returned inside an Envelope[FileUploadResponse] wrapper.
    Includes deduplication status so agents can decide next steps.
    """

    file_record_id: str = Field(..., description="UUID of the FileRecord created or found")
    file_name: str = Field(..., description="Original filename as uploaded")
    file_hash: str = Field(..., description="SHA-256 hex digest of the file content")
    file_size_bytes: int = Field(..., description="File size in bytes")
    status: str = Field(..., description="Current processing status of the file")
    is_duplicate: bool = Field(
        ...,
        description="True if a file with the same SHA-256 hash already existed",
    )
    storage_path: str | None = Field(
        None,
        description="Local or S3 path where the file is stored",
    )
    created_at: datetime = Field(..., description="Timestamp when the record was created")
    suggestion: str | None = Field(
        None,
        description="Agent-friendly next-step suggestion",
    )
