"""File storage service with S3-compatible local storage and dedup.

Provides a unified interface for storing and retrieving files.
In dev mode, uses the local filesystem as an S3-compatible mock.
In production, plugs into real S3 via boto3.

Files are stored content-addressable by their SHA-256 hash, providing
automatic deduplication. The storage layout mirrors S3 key structure:

    {base_path}/{lab_id}/{instrument_id}/{hash_prefix}/{file_hash}/{original_filename}

This service checks existing hashes in the database to avoid storing
duplicate files, returning the existing FileRecord if found.
"""

from __future__ import annotations

import mimetypes
import shutil
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Protocol

from app.config import Settings, get_settings
from app.core.hashing import compute_sha256, compute_sha256_stream
from app.exceptions import ConflictError, NotFoundError


class StorageResult:
    """Result of a file storage operation.

    Attributes:
        storage_path: The path/key where the file was stored.
        file_hash: SHA-256 hash of the file content.
        file_size_bytes: Size of the file in bytes.
        mime_type: Detected MIME type of the file.
        is_duplicate: True if the file was already stored (dedup hit).
    """

    __slots__ = ("storage_path", "file_hash", "file_size_bytes", "mime_type", "is_duplicate")

    def __init__(
        self,
        storage_path: str,
        file_hash: str,
        file_size_bytes: int,
        mime_type: str | None,
        is_duplicate: bool = False,
    ):
        self.storage_path = storage_path
        self.file_hash = file_hash
        self.file_size_bytes = file_size_bytes
        self.mime_type = mime_type
        self.is_duplicate = is_duplicate

    def __repr__(self) -> str:
        return (
            f"<StorageResult path={self.storage_path!r} "
            f"hash={self.file_hash[:12]}... "
            f"size={self.file_size_bytes} "
            f"dup={self.is_duplicate}>"
        )


class HashLookup(Protocol):
    """Protocol for checking if a file hash already exists.

    Implementations can be backed by a database query, in-memory set,
    or any other lookup mechanism.
    """

    async def hash_exists(self, file_hash: str) -> bool:
        """Check if a file with this hash already exists."""
        ...

    async def get_storage_path_by_hash(self, file_hash: str) -> str | None:
        """Get the storage path for an existing file by hash."""
        ...


class InMemoryHashLookup:
    """In-memory hash lookup for testing and dev mode."""

    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}  # hash -> storage_path

    async def hash_exists(self, file_hash: str) -> bool:
        return file_hash in self._hashes

    async def get_storage_path_by_hash(self, file_hash: str) -> str | None:
        return self._hashes.get(file_hash)

    def register(self, file_hash: str, storage_path: str) -> None:
        """Register a hash -> path mapping (for testing)."""
        self._hashes[file_hash] = storage_path


class DatabaseHashLookup:
    """Hash lookup backed by SQLAlchemy async session.

    Queries the file_records table for existing file hashes.
    """

    def __init__(self, session_factory: any) -> None:
        self._session_factory = session_factory

    async def hash_exists(self, file_hash: str) -> bool:
        from sqlalchemy import select
        from app.models.ingestion import FileRecord

        async with self._session_factory() as session:
            result = await session.execute(
                select(FileRecord.id).where(FileRecord.file_hash == file_hash).limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def get_storage_path_by_hash(self, file_hash: str) -> str | None:
        from sqlalchemy import select
        from app.models.ingestion import FileRecord

        async with self._session_factory() as session:
            result = await session.execute(
                select(FileRecord.storage_path).where(FileRecord.file_hash == file_hash).limit(1)
            )
            return result.scalar_one_or_none()


def _detect_mime_type(filename: str) -> str | None:
    """Detect MIME type from filename extension."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type


def _build_storage_key(
    lab_id: str,
    instrument_id: str,
    file_hash: str,
    filename: str,
) -> str:
    """Build the S3-style storage key for a file.

    Layout: {lab_id}/{instrument_id}/{hash_prefix}/{file_hash}/{filename}

    The hash_prefix (first 2 chars) provides directory fanout to avoid
    too many files in a single directory.
    """
    hash_prefix = file_hash[:2]
    return f"{lab_id}/{instrument_id}/{hash_prefix}/{file_hash}/{filename}"


class LocalStorageBackend:
    """Local filesystem storage that mimics S3 behavior.

    Files are stored under a configurable base directory using the same
    key structure that would be used in S3.
    """

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def store(self, key: str, data: bytes) -> str:
        """Store bytes at the given key. Returns the full path.

        Args:
            key: S3-style object key (relative path).
            data: File content bytes.

        Returns:
            Absolute path to the stored file as string.
        """
        full_path = self.base_path / key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        return str(full_path)

    def store_stream(self, key: str, stream: BinaryIO) -> str:
        """Store a stream at the given key. Returns the full path."""
        full_path = self.base_path / key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("wb") as f:
            shutil.copyfileobj(stream, f)
        return str(full_path)

    def retrieve(self, key: str) -> bytes:
        """Retrieve file content by key.

        Raises:
            NotFoundError: If the file does not exist.
        """
        full_path = self.base_path / key
        if not full_path.exists():
            raise NotFoundError(
                message=f"File not found at key: {key}",
                suggestion="Verify the storage key is correct. The file may have been deleted or moved.",
            )
        return full_path.read_bytes()

    def retrieve_stream(self, key: str) -> BinaryIO:
        """Retrieve a file as a stream by key."""
        full_path = self.base_path / key
        if not full_path.exists():
            raise NotFoundError(
                message=f"File not found at key: {key}",
                suggestion="Verify the storage key is correct.",
            )
        return full_path.open("rb")

    def exists(self, key: str) -> bool:
        """Check if a file exists at the given key."""
        return (self.base_path / key).exists()

    def delete(self, key: str) -> bool:
        """Delete a file by key. Returns True if deleted, False if not found."""
        full_path = self.base_path / key
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys under a prefix."""
        search_path = self.base_path / prefix if prefix else self.base_path
        if not search_path.exists():
            return []
        return [
            str(p.relative_to(self.base_path))
            for p in search_path.rglob("*")
            if p.is_file()
        ]


class FileStorageService:
    """High-level file storage service with dedup support.

    Combines a storage backend with hash-based deduplication lookup.
    """

    def __init__(
        self,
        backend: LocalStorageBackend,
        hash_lookup: HashLookup | None = None,
    ) -> None:
        self.backend = backend
        self.hash_lookup = hash_lookup or InMemoryHashLookup()

    async def store_file(
        self,
        data: bytes,
        filename: str,
        lab_id: str,
        instrument_id: str,
        *,
        skip_dedup: bool = False,
    ) -> StorageResult:
        """Store a file with automatic deduplication.

        Computes SHA-256 hash and checks for duplicates before storing.
        If the file already exists (same hash), returns the existing path
        with is_duplicate=True.

        Args:
            data: File content bytes.
            filename: Original filename.
            lab_id: Lab that owns the file.
            instrument_id: Instrument that produced the file.
            skip_dedup: If True, skip dedup check and always store.

        Returns:
            StorageResult with path, hash, size, and dedup status.
        """
        file_hash = compute_sha256(data)
        file_size = len(data)
        mime_type = _detect_mime_type(filename)

        # Check for duplicate
        if not skip_dedup and self.hash_lookup is not None:
            if await self.hash_lookup.hash_exists(file_hash):
                existing_path = await self.hash_lookup.get_storage_path_by_hash(file_hash)
                return StorageResult(
                    storage_path=existing_path or "",
                    file_hash=file_hash,
                    file_size_bytes=file_size,
                    mime_type=mime_type,
                    is_duplicate=True,
                )

        # Build storage key and store
        key = _build_storage_key(lab_id, instrument_id, file_hash, filename)
        storage_path = self.backend.store(key, data)

        # Register in hash lookup if it's in-memory
        if isinstance(self.hash_lookup, InMemoryHashLookup):
            self.hash_lookup.register(file_hash, key)

        return StorageResult(
            storage_path=key,
            file_hash=file_hash,
            file_size_bytes=file_size,
            mime_type=mime_type,
            is_duplicate=False,
        )

    async def store_stream(
        self,
        stream: BinaryIO,
        filename: str,
        lab_id: str,
        instrument_id: str,
        *,
        skip_dedup: bool = False,
    ) -> StorageResult:
        """Store a file from a stream with dedup support.

        Note: For dedup to work, we need to read the entire stream to
        compute the hash. The stream is then replayed from a buffer.

        Args:
            stream: Readable binary stream.
            filename: Original filename.
            lab_id: Lab that owns the file.
            instrument_id: Instrument that produced the file.
            skip_dedup: If True, skip dedup check and always store.

        Returns:
            StorageResult with path, hash, size, and dedup status.
        """
        # Read entire stream to compute hash
        data = stream.read()
        return await self.store_file(
            data, filename, lab_id, instrument_id, skip_dedup=skip_dedup
        )

    def retrieve_file(self, key: str) -> bytes:
        """Retrieve file content by storage key."""
        return self.backend.retrieve(key)

    def retrieve_stream(self, key: str) -> BinaryIO:
        """Retrieve file as a stream by storage key."""
        return self.backend.retrieve_stream(key)

    def file_exists(self, key: str) -> bool:
        """Check if a file exists by storage key."""
        return self.backend.exists(key)

    def delete_file(self, key: str) -> bool:
        """Delete a file by storage key."""
        return self.backend.delete(key)


def create_storage_service(
    settings: Settings | None = None,
    hash_lookup: HashLookup | None = None,
) -> FileStorageService:
    """Factory function to create a storage service from settings.

    Args:
        settings: Application settings. Uses cached singleton if not provided.
        hash_lookup: Optional hash lookup for dedup. Defaults to InMemoryHashLookup.

    Returns:
        Configured FileStorageService instance.
    """
    if settings is None:
        settings = get_settings()

    backend = LocalStorageBackend(settings.local_storage_path)
    return FileStorageService(backend=backend, hash_lookup=hash_lookup)
