"""Tests for SHA-256 hash computation utilities."""

import hashlib
import io
from pathlib import Path

import pytest

from app.core.hashing import (
    DEFAULT_CHUNK_SIZE,
    compute_sha256,
    compute_sha256_file,
    compute_sha256_stream,
    verify_hash,
)


class TestComputeSha256:
    """Tests for in-memory SHA-256 computation."""

    def test_empty_bytes(self):
        result = compute_sha256(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_simple_content(self):
        data = b"Hello, LabLink!"
        result = compute_sha256(data)
        expected = hashlib.sha256(data).hexdigest()
        assert result == expected

    def test_returns_lowercase_hex_64_chars(self):
        result = compute_sha256(b"test")
        assert result == result.lower()
        assert len(result) == 64

    def test_deterministic(self):
        data = b"same input always same output"
        assert compute_sha256(data) == compute_sha256(data)

    def test_different_input_different_hash(self):
        assert compute_sha256(b"a") != compute_sha256(b"b")

    def test_binary_content(self):
        data = bytes(range(256))
        result = compute_sha256(data)
        assert len(result) == 64

    def test_large_content(self):
        data = b"x" * (DEFAULT_CHUNK_SIZE * 3)
        result = compute_sha256(data)
        expected = hashlib.sha256(data).hexdigest()
        assert result == expected


class TestComputeSha256Stream:
    """Tests for streaming SHA-256 computation."""

    def test_empty_stream(self):
        stream = io.BytesIO(b"")
        result = compute_sha256_stream(stream)
        assert result == hashlib.sha256(b"").hexdigest()

    def test_matches_bytes_hash(self):
        data = b"stream test data"
        stream = io.BytesIO(data)
        assert compute_sha256_stream(stream) == compute_sha256(data)

    def test_large_stream(self):
        data = b"chunk" * 100_000
        stream = io.BytesIO(data)
        result = compute_sha256_stream(stream)
        assert result == hashlib.sha256(data).hexdigest()

    def test_custom_chunk_size(self):
        data = b"test" * 1000
        stream = io.BytesIO(data)
        result = compute_sha256_stream(stream, chunk_size=16)
        assert result == compute_sha256(data)


class TestComputeSha256File:
    """Tests for file-based SHA-256 computation."""

    def test_file_hash(self, tmp_path: Path):
        file_path = tmp_path / "test.csv"
        data = b"Sample,Value\n1,42.0\n2,43.5"
        file_path.write_bytes(data)
        result = compute_sha256_file(file_path)
        assert result == compute_sha256(data)

    def test_file_hash_string_path(self, tmp_path: Path):
        file_path = tmp_path / "test.txt"
        data = b"string path test"
        file_path.write_bytes(data)
        result = compute_sha256_file(str(file_path))
        assert result == compute_sha256(data)

    def test_empty_file(self, tmp_path: Path):
        file_path = tmp_path / "empty.txt"
        file_path.write_bytes(b"")
        result = compute_sha256_file(file_path)
        assert result == hashlib.sha256(b"").hexdigest()

    def test_nonexistent_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            compute_sha256_file(tmp_path / "nonexistent.txt")

    def test_large_file(self, tmp_path: Path):
        file_path = tmp_path / "large.bin"
        data = b"x" * (DEFAULT_CHUNK_SIZE * 5)
        file_path.write_bytes(data)
        result = compute_sha256_file(file_path)
        assert result == compute_sha256(data)


class TestVerifyHash:
    """Tests for hash verification."""

    def test_valid_hash(self):
        data = b"verify me"
        expected = compute_sha256(data)
        assert verify_hash(data, expected) is True

    def test_invalid_hash(self):
        assert verify_hash(b"data", "0" * 64) is False

    def test_case_insensitive(self):
        data = b"case test"
        expected = compute_sha256(data).upper()
        assert verify_hash(data, expected) is True
