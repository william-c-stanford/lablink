"""Upload service — file upload orchestration, S3/local storage, dedup, status tracking.

Handles the full upload lifecycle:
1. Compute SHA-256 content hash for dedup
2. Check for duplicate uploads within the organization
3. Store file to S3 (or local filesystem mock)
4. Create Upload DB record with status=uploaded
5. Kick off parsing (inline or via Celery)

Zero HTTP awareness — receives raw bytes and metadata, returns domain objects.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.config import get_settings
from lablink.models import Upload, UploadStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------


class StorageBackend:
    """Abstract interface for file storage."""

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store bytes and return the storage key."""
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        """Retrieve bytes by key."""
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        """Delete file by key."""
        raise NotImplementedError

    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    """Local filesystem mock for S3 — used in dev/test."""

    def __init__(self, base_path: str | None = None) -> None:
        settings = get_settings()
        self.base_path = Path(base_path or settings.local_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        file_path = self.base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)
        return key

    async def get(self, key: str) -> bytes:
        file_path = self.base_path / key
        if not file_path.exists():
            raise FileNotFoundError(f"File not found in local storage: {key}")
        return file_path.read_bytes()

    async def delete(self, key: str) -> None:
        file_path = self.base_path / key
        if file_path.exists():
            file_path.unlink()

    async def exists(self, key: str) -> bool:
        return (self.base_path / key).exists()


class S3StorageBackend(StorageBackend):
    """AWS S3 storage backend (production).

    Requires ``boto3`` and valid AWS credentials.  Not used in dev/test
    unless ``LABLINK_STORAGE_BACKEND=s3`` is explicitly set.
    """

    def __init__(self) -> None:
        settings = get_settings()
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3 storage. Install with: pip install boto3"
            ) from exc

        kwargs: dict[str, Any] = {
            "region_name": settings.s3_region,
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url

        self._client = boto3.client("s3", **kwargs)
        self._bucket = settings.s3_bucket

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, **extra
        )
        return key

    async def get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    async def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False


def get_storage_backend() -> StorageBackend:
    """Factory: return the appropriate storage backend based on settings."""
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3StorageBackend()
    return LocalStorageBackend()


# ---------------------------------------------------------------------------
# Service errors
# ---------------------------------------------------------------------------


class UploadError(Exception):
    """Raised when an upload operation fails."""

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        self.message = message
        self.suggestion = suggestion or "Check the file and try again."
        super().__init__(message)


class DuplicateUploadError(UploadError):
    """Raised when a duplicate file is detected within the same organization."""

    def __init__(self, existing_upload_id: uuid.UUID, content_hash: str) -> None:
        self.existing_upload_id = existing_upload_id
        self.content_hash = content_hash
        super().__init__(
            message=f"Duplicate file detected (hash={content_hash[:12]}...). "
            f"Existing upload: {existing_upload_id}",
            suggestion="Use get_upload to check the existing upload status.",
        )


# ---------------------------------------------------------------------------
# Upload service
# ---------------------------------------------------------------------------


class UploadService:
    """Orchestrates file uploads: hashing, dedup, storage, DB record creation.

    Usage::

        service = UploadService(db=session)
        upload = await service.upload_file(
            file_bytes=raw_bytes,
            filename="sample.csv",
            organization_id=org_uuid,
        )
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageBackend | None = None,
    ) -> None:
        self.db = db
        self.storage = storage or get_storage_backend()

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def compute_hash(data: bytes) -> str:
        """Compute SHA-256 hex digest of file bytes."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def guess_mime_type(filename: str) -> str:
        """Guess MIME type from filename, defaulting to application/octet-stream."""
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/octet-stream"

    @staticmethod
    def generate_s3_key(organization_id: uuid.UUID, filename: str) -> str:
        """Generate a unique S3-style key: uploads/<org_id>/<uuid>/<filename>."""
        return f"uploads/{organization_id}/{uuid.uuid4()}/{filename}"

    # -- Core operations ---------------------------------------------------

    async def check_duplicate(
        self,
        organization_id: uuid.UUID,
        content_hash: str,
    ) -> Upload | None:
        """Check if a file with the same hash already exists in this org.

        Returns the existing Upload if found, None otherwise.
        """
        stmt = (
            select(Upload)
            .where(
                Upload.organization_id == organization_id,
                Upload.content_hash == content_hash,
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        instrument_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        uploaded_by: uuid.UUID | None = None,
        allow_duplicate: bool = False,
    ) -> Upload:
        """Upload a file: hash, dedup check, store, create DB record.

        Args:
            file_bytes: Raw file content.
            filename: Original filename.
            organization_id: Owning organization UUID.
            project_id: Optional project association.
            instrument_id: Optional instrument association.
            agent_id: Optional agent that submitted the file.
            uploaded_by: Optional user who uploaded.
            allow_duplicate: If True, skip dedup check.

        Returns:
            The created Upload ORM instance.

        Raises:
            DuplicateUploadError: If a duplicate is found and allow_duplicate is False.
            UploadError: If storage fails.
        """
        if not file_bytes:
            raise UploadError(
                "File is empty.",
                suggestion="Provide a non-empty file.",
            )

        # 1. Compute content hash
        content_hash = self.compute_hash(file_bytes)

        # 2. Dedup check
        if not allow_duplicate:
            existing = await self.check_duplicate(organization_id, content_hash)
            if existing is not None:
                raise DuplicateUploadError(
                    existing_upload_id=existing.id,
                    content_hash=content_hash,
                )

        # 3. Generate storage key and store
        s3_key = self.generate_s3_key(organization_id, filename)
        mime_type = self.guess_mime_type(filename)

        try:
            await self.storage.put(s3_key, file_bytes, content_type=mime_type)
        except Exception as exc:
            logger.error("Storage write failed for %s: %s", s3_key, exc)
            raise UploadError(
                f"Failed to store file: {exc}",
                suggestion="Check storage configuration and try again.",
            ) from exc

        # 4. Create DB record
        upload = Upload(
            organization_id=organization_id,
            project_id=project_id,
            instrument_id=instrument_id,
            agent_id=agent_id,
            uploaded_by=uploaded_by,
            filename=filename,
            content_hash=content_hash,
            file_size_bytes=len(file_bytes),
            s3_key=s3_key,
            mime_type=mime_type,
            status=UploadStatus.uploaded,
        )
        self.db.add(upload)
        await self.db.flush()

        logger.info(
            "Uploaded %s (%d bytes, hash=%s) -> %s",
            filename,
            len(file_bytes),
            content_hash[:12],
            upload.id,
        )

        return upload

    async def get_upload(self, upload_id: uuid.UUID) -> Upload | None:
        """Retrieve a single upload by ID."""
        return await self.db.get(Upload, upload_id)

    async def list_uploads(
        self,
        organization_id: uuid.UUID,
        *,
        status: UploadStatus | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Upload], int]:
        """List uploads for an organization with optional filters.

        Returns:
            Tuple of (uploads, total_count).
        """
        from sqlalchemy import func as sa_func

        base = select(Upload).where(Upload.organization_id == organization_id)

        if status is not None:
            base = base.where(Upload.status == status)
        if project_id is not None:
            base = base.where(Upload.project_id == project_id)

        # Count
        count_stmt = select(sa_func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Fetch
        stmt = base.order_by(Upload.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        uploads = result.scalars().all()

        return uploads, total

    async def update_status(
        self,
        upload_id: uuid.UUID,
        status: UploadStatus,
        *,
        error_message: str | None = None,
        parser_used: str | None = None,
        instrument_type_detected: str | None = None,
    ) -> Upload:
        """Update the status of an upload (pipeline state transitions).

        Args:
            upload_id: Upload UUID.
            status: New status.
            error_message: Error message if status is parse_failed.
            parser_used: Parser name used for successful parse.
            instrument_type_detected: Detected instrument type.

        Returns:
            Updated Upload instance.

        Raises:
            UploadError: If upload not found.
        """
        upload = await self.db.get(Upload, upload_id)
        if upload is None:
            raise UploadError(
                f"Upload {upload_id} not found.",
                suggestion="Use list_uploads to find valid upload IDs.",
            )

        upload.status = status

        if error_message is not None:
            upload.error_message = error_message
        if parser_used is not None:
            upload.parser_used = parser_used
        if instrument_type_detected is not None:
            upload.instrument_type_detected = instrument_type_detected

        now = datetime.now(timezone.utc)
        if status == UploadStatus.parsed:
            upload.parsed_at = now
        elif status == UploadStatus.indexed:
            upload.indexed_at = now

        await self.db.flush()

        logger.info("Upload %s status -> %s", upload_id, status.value)
        return upload

    async def download_file(self, upload_id: uuid.UUID) -> tuple[bytes, str, str]:
        """Download raw file bytes for an upload.

        Returns:
            Tuple of (file_bytes, filename, mime_type).

        Raises:
            UploadError: If upload not found or file missing from storage.
        """
        upload = await self.db.get(Upload, upload_id)
        if upload is None:
            raise UploadError(
                f"Upload {upload_id} not found.",
                suggestion="Use list_uploads to find valid upload IDs.",
            )

        try:
            data = await self.storage.get(upload.s3_key)
        except FileNotFoundError as exc:
            raise UploadError(
                f"File not found in storage: {upload.s3_key}",
                suggestion="The file may have been removed from storage.",
            ) from exc

        return data, upload.filename, upload.mime_type or "application/octet-stream"
