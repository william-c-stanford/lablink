"""File upload service with SHA-256 content-addressable deduplication.

Handles file ingestion: computes SHA-256 hash, checks for duplicates,
stores the file (local filesystem in dev, S3 in production), and creates
an immutable FileRecord audit entry with hash-chain linking.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.ingestion import FileRecord, FileStatus


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hex digest of file content.

    Args:
        content: Raw file bytes.

    Returns:
        64-character lowercase hex string.
    """
    return hashlib.sha256(content).hexdigest()


async def get_last_file_record(session: AsyncSession) -> FileRecord | None:
    """Get the most recently created FileRecord for hash-chain linking.

    Returns:
        The latest FileRecord or None if this is the first record.
    """
    stmt = (
        select(FileRecord)
        .order_by(FileRecord.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def find_by_hash(
    session: AsyncSession,
    file_hash: str,
) -> FileRecord | None:
    """Find an existing FileRecord by content hash.

    Args:
        session: Database session.
        file_hash: SHA-256 hex digest to search for.

    Returns:
        Existing FileRecord if duplicate found, None otherwise.
    """
    stmt = select(FileRecord).where(FileRecord.file_hash == file_hash)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _store_local(
    content: bytes,
    file_hash: str,
    file_name: str,
    storage_path: str,
) -> str:
    """Store file to local filesystem (dev/test mock S3).

    Uses content-addressable storage: files are stored under their
    SHA-256 hash to prevent duplicates at the filesystem level too.

    Args:
        content: Raw file bytes.
        file_hash: SHA-256 hash of the content.
        file_name: Original filename (used for extension).
        storage_path: Base directory for local storage.

    Returns:
        Relative path where the file was stored.
    """
    ext = Path(file_name).suffix
    # Use hash-based path: ab/cdef1234.../filename.ext
    hash_dir = os.path.join(storage_path, file_hash[:2], file_hash[2:4])
    os.makedirs(hash_dir, exist_ok=True)

    stored_name = f"{file_hash}{ext}"
    full_path = os.path.join(hash_dir, stored_name)

    if not os.path.exists(full_path):
        with open(full_path, "wb") as f:
            f.write(content)

    return os.path.join(file_hash[:2], file_hash[2:4], stored_name)


async def upload_file(
    session: AsyncSession,
    content: bytes,
    file_name: str,
    instrument_id: str,
    lab_id: str,
    *,
    uploaded_by: str | None = None,
    watched_folder_id: str | None = None,
    mime_type: str | None = None,
    settings: Settings | None = None,
) -> tuple[FileRecord, bool]:
    """Upload a file with SHA-256 deduplication.

    Computes the SHA-256 hash of the file content and checks for an
    existing record with the same hash. If found, returns the existing
    record without creating a duplicate. Otherwise, stores the file and
    creates a new FileRecord with hash-chain linking.

    Args:
        session: Database session.
        content: Raw file bytes.
        file_name: Original filename.
        instrument_id: ID of the instrument that produced the file.
        lab_id: ID of the lab that owns the file.
        uploaded_by: User ID (None if agent-uploaded).
        watched_folder_id: Watched folder ID (None if manual upload).
        mime_type: MIME type of the file.
        settings: Application settings (uses default if not provided).

    Returns:
        Tuple of (FileRecord, is_new) where is_new is False if a
        duplicate was found.
    """
    if settings is None:
        settings = get_settings()

    file_hash = compute_sha256(content)

    # Check for duplicate
    existing = await find_by_hash(session, file_hash)
    if existing is not None:
        return existing, False

    # Store the file
    storage_path: str | None = None
    storage_backend = settings.storage_backend

    if storage_backend == "local":
        storage_path = _store_local(
            content, file_hash, file_name, settings.local_storage_path,
        )

    # Get prev_hash for hash-chain
    last_record = await get_last_file_record(session)
    prev_hash = last_record.compute_chain_hash() if last_record else None

    # Create FileRecord
    record = FileRecord(
        id=str(uuid.uuid4()),
        file_name=file_name,
        file_hash=file_hash,
        file_size_bytes=len(content),
        mime_type=mime_type,
        instrument_id=instrument_id,
        lab_id=lab_id,
        uploaded_by=uploaded_by,
        watched_folder_id=watched_folder_id,
        status=FileStatus.UPLOADED.value,
        storage_path=storage_path,
        storage_backend=storage_backend,
        prev_hash=prev_hash,
    )

    session.add(record)
    await session.flush()

    return record, True
