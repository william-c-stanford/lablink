"""Tests for file storage service with dedup and local backend."""

import io
from pathlib import Path

import pytest

from app.core.hashing import compute_sha256
from app.exceptions import NotFoundError
from app.services.storage import (
    FileStorageService,
    InMemoryHashLookup,
    LocalStorageBackend,
    StorageResult,
    _build_storage_key,
    _detect_mime_type,
    create_storage_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    """Temporary directory for local storage."""
    d = tmp_path / "storage"
    d.mkdir()
    return d


@pytest.fixture
def backend(storage_dir: Path) -> LocalStorageBackend:
    return LocalStorageBackend(storage_dir)


@pytest.fixture
def hash_lookup() -> InMemoryHashLookup:
    return InMemoryHashLookup()


@pytest.fixture
def storage_service(
    backend: LocalStorageBackend, hash_lookup: InMemoryHashLookup
) -> FileStorageService:
    return FileStorageService(backend=backend, hash_lookup=hash_lookup)


# ---------------------------------------------------------------------------
# Helper constants
# ---------------------------------------------------------------------------

SAMPLE_DATA = b"Sample,Absorbance\nA1,0.523\nA2,0.891"
SAMPLE_FILENAME = "spectro_output.csv"
LAB_ID = "lab-001"
INSTRUMENT_ID = "inst-001"


# ---------------------------------------------------------------------------
# Tests: utility functions
# ---------------------------------------------------------------------------


class TestBuildStorageKey:
    def test_key_format(self):
        file_hash = "abcdef1234567890" + "0" * 48
        key = _build_storage_key("lab1", "inst1", file_hash, "data.csv")
        assert key == f"lab1/inst1/ab/{file_hash}/data.csv"

    def test_key_uses_hash_prefix(self):
        file_hash = "ff" + "0" * 62
        key = _build_storage_key("lab1", "inst1", file_hash, "data.csv")
        assert "/ff/" in key


class TestDetectMimeType:
    def test_csv(self):
        assert _detect_mime_type("data.csv") == "text/csv"

    def test_json(self):
        assert _detect_mime_type("results.json") == "application/json"

    def test_xml(self):
        mime = _detect_mime_type("output.xml")
        assert mime is not None
        assert "xml" in mime

    def test_unknown_extension(self):
        result = _detect_mime_type("data.xyz123")
        assert result is None or isinstance(result, str)

    def test_txt(self):
        assert _detect_mime_type("log.txt") == "text/plain"


# ---------------------------------------------------------------------------
# Tests: LocalStorageBackend
# ---------------------------------------------------------------------------


class TestLocalStorageBackend:
    def test_store_and_retrieve(self, backend: LocalStorageBackend):
        key = "lab/inst/ab/hash123/file.csv"
        backend.store(key, SAMPLE_DATA)
        assert backend.retrieve(key) == SAMPLE_DATA

    def test_store_creates_directories(self, backend: LocalStorageBackend):
        key = "deep/nested/dir/structure/file.csv"
        backend.store(key, b"data")
        assert backend.exists(key)

    def test_store_stream(self, backend: LocalStorageBackend):
        key = "lab/inst/ab/hash456/stream.csv"
        stream = io.BytesIO(SAMPLE_DATA)
        backend.store_stream(key, stream)
        assert backend.retrieve(key) == SAMPLE_DATA

    def test_retrieve_nonexistent_raises_not_found(self, backend: LocalStorageBackend):
        with pytest.raises(NotFoundError) as exc_info:
            backend.retrieve("nonexistent/key")
        assert exc_info.value.suggestion is not None

    def test_retrieve_stream(self, backend: LocalStorageBackend):
        key = "lab/inst/ab/hash789/data.csv"
        backend.store(key, SAMPLE_DATA)
        stream = backend.retrieve_stream(key)
        assert stream.read() == SAMPLE_DATA
        stream.close()

    def test_retrieve_stream_nonexistent(self, backend: LocalStorageBackend):
        with pytest.raises(NotFoundError):
            backend.retrieve_stream("no/such/file")

    def test_exists_true_and_false(self, backend: LocalStorageBackend):
        key = "lab/inst/ab/hash/file.csv"
        assert backend.exists(key) is False
        backend.store(key, b"data")
        assert backend.exists(key) is True

    def test_delete_existing(self, backend: LocalStorageBackend):
        key = "lab/inst/ab/hash/deleteme.csv"
        backend.store(key, b"data")
        assert backend.delete(key) is True
        assert backend.exists(key) is False

    def test_delete_nonexistent(self, backend: LocalStorageBackend):
        assert backend.delete("no/such/key") is False

    def test_list_keys_all(self, backend: LocalStorageBackend):
        backend.store("lab1/a.csv", b"a")
        backend.store("lab1/b.csv", b"b")
        backend.store("lab2/c.csv", b"c")
        keys = backend.list_keys()
        assert len(keys) == 3

    def test_list_keys_with_prefix(self, backend: LocalStorageBackend):
        backend.store("lab1/a.csv", b"a")
        backend.store("lab1/b.csv", b"b")
        backend.store("lab2/c.csv", b"c")
        keys = backend.list_keys("lab1")
        assert len(keys) == 2

    def test_list_keys_empty_prefix(self, backend: LocalStorageBackend):
        keys = backend.list_keys("nonexistent")
        assert keys == []

    def test_creates_base_dir_on_init(self, tmp_path: Path):
        new_dir = tmp_path / "new_storage_dir"
        assert not new_dir.exists()
        LocalStorageBackend(new_dir)
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# Tests: InMemoryHashLookup
# ---------------------------------------------------------------------------


class TestInMemoryHashLookup:
    async def test_hash_not_found(self, hash_lookup: InMemoryHashLookup):
        assert await hash_lookup.hash_exists("abc123") is False

    async def test_register_and_find(self, hash_lookup: InMemoryHashLookup):
        hash_lookup.register("abc123", "/path/to/file")
        assert await hash_lookup.hash_exists("abc123") is True

    async def test_get_storage_path(self, hash_lookup: InMemoryHashLookup):
        hash_lookup.register("abc123", "/path/to/file")
        path = await hash_lookup.get_storage_path_by_hash("abc123")
        assert path == "/path/to/file"

    async def test_get_storage_path_not_found(self, hash_lookup: InMemoryHashLookup):
        path = await hash_lookup.get_storage_path_by_hash("unknown")
        assert path is None


# ---------------------------------------------------------------------------
# Tests: FileStorageService
# ---------------------------------------------------------------------------


class TestFileStorageService:
    async def test_store_file_basic(self, storage_service: FileStorageService):
        result = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        assert isinstance(result, StorageResult)
        assert result.file_hash == compute_sha256(SAMPLE_DATA)
        assert result.file_size_bytes == len(SAMPLE_DATA)
        assert result.is_duplicate is False
        assert result.mime_type == "text/csv"
        assert LAB_ID in result.storage_path
        assert INSTRUMENT_ID in result.storage_path

    async def test_dedup_returns_duplicate(self, storage_service: FileStorageService):
        result1 = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        result2 = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        assert result1.is_duplicate is False
        assert result2.is_duplicate is True
        assert result1.file_hash == result2.file_hash

    async def test_dedup_different_files_not_duplicate(
        self, storage_service: FileStorageService
    ):
        result1 = await storage_service.store_file(
            b"file one", "a.csv", LAB_ID, INSTRUMENT_ID
        )
        result2 = await storage_service.store_file(
            b"file two", "b.csv", LAB_ID, INSTRUMENT_ID
        )
        assert result1.is_duplicate is False
        assert result2.is_duplicate is False
        assert result1.file_hash != result2.file_hash

    async def test_skip_dedup(self, storage_service: FileStorageService):
        await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        result = await storage_service.store_file(
            SAMPLE_DATA,
            SAMPLE_FILENAME,
            LAB_ID,
            INSTRUMENT_ID,
            skip_dedup=True,
        )
        assert result.is_duplicate is False

    async def test_store_stream(self, storage_service: FileStorageService):
        stream = io.BytesIO(SAMPLE_DATA)
        result = await storage_service.store_stream(
            stream, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        assert result.file_hash == compute_sha256(SAMPLE_DATA)
        assert result.is_duplicate is False

    async def test_store_and_retrieve(self, storage_service: FileStorageService):
        result = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        retrieved = storage_service.retrieve_file(result.storage_path)
        assert retrieved == SAMPLE_DATA

    async def test_file_exists(self, storage_service: FileStorageService):
        result = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        assert storage_service.file_exists(result.storage_path) is True
        assert storage_service.file_exists("nonexistent") is False

    async def test_delete_file(self, storage_service: FileStorageService):
        result = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        assert storage_service.delete_file(result.storage_path) is True
        assert storage_service.file_exists(result.storage_path) is False

    async def test_storage_result_repr(self, storage_service: FileStorageService):
        result = await storage_service.store_file(
            SAMPLE_DATA, SAMPLE_FILENAME, LAB_ID, INSTRUMENT_ID
        )
        repr_str = repr(result)
        assert "StorageResult" in repr_str
        assert "dup=False" in repr_str


# ---------------------------------------------------------------------------
# Tests: create_storage_service factory
# ---------------------------------------------------------------------------


class TestCreateStorageService:
    def test_creates_service(self, tmp_path: Path):
        from app.config import Settings

        settings = Settings(local_storage_path=str(tmp_path / "store"))
        service = create_storage_service(settings=settings)
        assert isinstance(service, FileStorageService)
        assert isinstance(service.backend, LocalStorageBackend)

    def test_default_hash_lookup_is_in_memory(self, tmp_path: Path):
        from app.config import Settings

        settings = Settings(local_storage_path=str(tmp_path / "store"))
        service = create_storage_service(settings=settings)
        assert isinstance(service.hash_lookup, InMemoryHashLookup)
