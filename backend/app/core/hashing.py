"""SHA-256 hash computation utilities for file content deduplication.

Provides streaming hash computation that handles both file paths and
in-memory byte buffers efficiently. Used by the storage service for
content-addressable deduplication and by the audit trail for hash chains.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

# Default chunk size for streaming hash computation (64 KB)
DEFAULT_CHUNK_SIZE = 65_536


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of in-memory bytes.

    Args:
        data: Raw bytes to hash.

    Returns:
        Lowercase hex-encoded SHA-256 hash string (64 chars).
    """
    return hashlib.sha256(data).hexdigest()


def compute_sha256_stream(stream: BinaryIO, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Compute SHA-256 hex digest by reading a stream in chunks.

    Memory-efficient for large files — never loads the entire file into memory.

    Args:
        stream: A readable binary stream (file object, BytesIO, etc.).
        chunk_size: Number of bytes to read per iteration.

    Returns:
        Lowercase hex-encoded SHA-256 hash string (64 chars).
    """
    hasher = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
    return hasher.hexdigest()


def compute_sha256_file(file_path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file on disk.

    Args:
        file_path: Path to the file to hash.

    Returns:
        Lowercase hex-encoded SHA-256 hash string (64 chars).

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be read.
    """
    path = Path(file_path)
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(DEFAULT_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_hash(data: bytes, expected_hash: str) -> bool:
    """Verify that data matches an expected SHA-256 hash.

    Args:
        data: Raw bytes to verify.
        expected_hash: Expected hex-encoded SHA-256 hash.

    Returns:
        True if the computed hash matches the expected hash.
    """
    return compute_sha256(data) == expected_hash.lower()
