"""Tests for the file upload endpoint.

Covers:
- Successful file upload with SHA-256 computation
- Duplicate detection (same content returns is_duplicate=True, HTTP 200)
- Response envelope structure with suggestions
- HTTP status codes (201 for new, 200 for duplicate)
- File storage on local filesystem
- Required form fields validation
- Multipart upload mechanics
- Service layer (compute_sha256, find_by_hash, upload_file)
"""

from __future__ import annotations

import hashlib
import io
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.database import get_session
from app.main import create_app
from app.models.base import Base
from app.models.instrument import Instrument, InstrumentDriver
from app.services.file_service import compute_sha256, find_by_hash, upload_file


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UPLOAD_URL = "/api/v1/files/upload"

SAMPLE_CSV = b"""Sample,Wavelength,Absorbance
Sample_1,260,1.234
Sample_1,280,0.987
Sample_2,260,2.345
Sample_2,280,1.876
"""

DIFFERENT_CSV = b"""Sample,Wavelength,Absorbance
Sample_X,300,0.555
"""

# Pre-computed seed data IDs
_DRIVER_ID = str(uuid.uuid4())
_INSTRUMENT_ID = str(uuid.uuid4())
_LAB_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def instrument_id() -> str:
    return _INSTRUMENT_ID


@pytest.fixture
def lab_id() -> str:
    return _LAB_ID


@pytest.fixture
def upload_test_settings(tmp_path) -> Settings:
    """Settings with tmp storage path for upload tests."""
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite://",
        secret_key="test-secret-key",
        debug=False,
        local_storage_path=str(tmp_path / "storage"),
        storage_backend="local",
    )


@pytest_asyncio.fixture
async def upload_engine(upload_test_settings):
    """Async engine with all tables created."""
    eng = create_async_engine(
        upload_test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def upload_session_factory(upload_engine):
    """Session factory bound to test engine."""
    return async_sessionmaker(
        bind=upload_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def upload_session(upload_session_factory):
    """Async session for direct service-layer tests."""
    async with upload_session_factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def seed_instrument(upload_session_factory):
    """Create an instrument driver and instrument for FK constraints."""
    async with upload_session_factory() as sess:
        driver = InstrumentDriver(
            id=_DRIVER_ID,
            name="Test Spectrophotometer CSV",
            instrument_type="spectrophotometer",
            parser_module="app.parsers.spectrophotometer",
            file_patterns="*.csv",
            is_active=True,
        )
        sess.add(driver)
        await sess.flush()

        instrument = Instrument(
            id=_INSTRUMENT_ID,
            name="Test UV-Vis",
            lab_id=_LAB_ID,
            driver_id=_DRIVER_ID,
            serial_number="SN-12345",
            is_active=True,
        )
        sess.add(instrument)
        await sess.commit()


@pytest_asyncio.fixture
async def upload_app(upload_test_settings, upload_session_factory, seed_instrument):
    """FastAPI app with DB session overridden for upload tests."""
    application = create_app(settings=upload_test_settings)

    async def _override_get_session():
        async with upload_session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    application.dependency_overrides[get_session] = _override_get_session
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def upload_client(upload_app):
    """HTTPX async client for file upload testing."""
    transport = ASGITransport(app=upload_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upload_form(
    content: bytes,
    filename: str,
    instrument_id: str,
    lab_id: str,
    *,
    uploaded_by: str | None = None,
    content_type: str = "text/csv",
):
    """Build the multipart form data for upload."""
    files = {"file": (filename, io.BytesIO(content), content_type)}
    data = {
        "instrument_id": instrument_id,
        "lab_id": lab_id,
    }
    if uploaded_by is not None:
        data["uploaded_by"] = uploaded_by
    return files, data


# ---------------------------------------------------------------------------
# SHA-256 computation tests (service layer)
# ---------------------------------------------------------------------------


class TestSHA256Computation:
    """Tests for compute_sha256 utility."""

    def test_matches_hashlib(self):
        expected = hashlib.sha256(SAMPLE_CSV).hexdigest()
        assert compute_sha256(SAMPLE_CSV) == expected

    def test_empty_content(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_sha256(b"") == expected

    def test_deterministic(self):
        assert compute_sha256(SAMPLE_CSV) == compute_sha256(SAMPLE_CSV)

    def test_different_content_different_hash(self):
        assert compute_sha256(SAMPLE_CSV) != compute_sha256(DIFFERENT_CSV)

    def test_returns_64_char_hex(self):
        h = compute_sha256(SAMPLE_CSV)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Service layer tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFileServiceUpload:
    """Tests for the upload_file service function."""

    async def test_upload_creates_file_record(
        self, upload_session, upload_test_settings, seed_instrument
    ):
        record, is_new = await upload_file(
            session=upload_session,
            content=SAMPLE_CSV,
            file_name="test.csv",
            instrument_id=_INSTRUMENT_ID,
            lab_id=_LAB_ID,
            settings=upload_test_settings,
        )
        assert is_new is True
        assert record.file_name == "test.csv"
        assert record.file_hash == compute_sha256(SAMPLE_CSV)
        assert record.file_size_bytes == len(SAMPLE_CSV)
        assert record.status == "uploaded"

    async def test_upload_duplicate_returns_existing(
        self, upload_session, upload_test_settings, seed_instrument
    ):
        record1, is_new1 = await upload_file(
            session=upload_session,
            content=SAMPLE_CSV,
            file_name="first.csv",
            instrument_id=_INSTRUMENT_ID,
            lab_id=_LAB_ID,
            settings=upload_test_settings,
        )
        await upload_session.commit()

        record2, is_new2 = await upload_file(
            session=upload_session,
            content=SAMPLE_CSV,
            file_name="second.csv",
            instrument_id=_INSTRUMENT_ID,
            lab_id=_LAB_ID,
            settings=upload_test_settings,
        )

        assert is_new1 is True
        assert is_new2 is False
        assert record2.id == record1.id

    async def test_upload_stores_file_locally(
        self, upload_session, upload_test_settings, seed_instrument, tmp_path
    ):
        record, _ = await upload_file(
            session=upload_session,
            content=SAMPLE_CSV,
            file_name="stored.csv",
            instrument_id=_INSTRUMENT_ID,
            lab_id=_LAB_ID,
            settings=upload_test_settings,
        )
        assert record.storage_path is not None
        assert record.storage_backend == "local"

    async def test_find_by_hash_returns_none_for_unknown(
        self, upload_session, seed_instrument
    ):
        result = await find_by_hash(upload_session, "0" * 64)
        assert result is None

    async def test_find_by_hash_returns_record(
        self, upload_session, upload_test_settings, seed_instrument
    ):
        record, _ = await upload_file(
            session=upload_session,
            content=SAMPLE_CSV,
            file_name="findme.csv",
            instrument_id=_INSTRUMENT_ID,
            lab_id=_LAB_ID,
            settings=upload_test_settings,
        )
        await upload_session.commit()

        found = await find_by_hash(upload_session, record.file_hash)
        assert found is not None
        assert found.id == record.id


# ---------------------------------------------------------------------------
# Endpoint tests: successful upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFileUploadEndpoint:
    """Tests for POST /api/v1/files/upload."""

    async def test_successful_upload_returns_201(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert resp.status_code == 201

    async def test_envelope_structure(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        body = resp.json()

        assert set(body.keys()) == {"data", "meta", "errors"}
        assert body["errors"] == []
        assert body["meta"]["timestamp"] is not None

    async def test_response_data_fields(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        upload_data = resp.json()["data"]

        assert upload_data["file_name"] == "test.csv"
        assert upload_data["file_hash"] == compute_sha256(SAMPLE_CSV)
        assert upload_data["file_size_bytes"] == len(SAMPLE_CSV)
        assert upload_data["status"] == "uploaded"
        assert upload_data["is_duplicate"] is False
        assert upload_data["file_record_id"] is not None
        assert upload_data["created_at"] is not None
        assert upload_data["storage_path"] is not None

    async def test_includes_suggestion(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        suggestion = resp.json()["data"]["suggestion"]
        assert suggestion is not None
        assert "uploaded successfully" in suggestion

    async def test_computes_correct_sha256(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        expected_hash = hashlib.sha256(SAMPLE_CSV).hexdigest()
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert resp.json()["data"]["file_hash"] == expected_hash

    async def test_response_includes_request_id_header(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert "x-request-id" in resp.headers

    async def test_upload_with_uploaded_by(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        user_id = str(uuid.uuid4())
        files, data = _upload_form(
            SAMPLE_CSV, "test.csv", instrument_id, lab_id, uploaded_by=user_id
        )
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFileDuplication:
    """Tests for duplicate file detection via endpoint."""

    async def test_duplicate_upload_returns_200(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp1 = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert resp1.status_code == 201

        files2, data2 = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp2 = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        assert resp2.status_code == 200

    async def test_duplicate_returns_is_duplicate_true(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        await upload_client.post(UPLOAD_URL, files=files, data=data)

        files2, data2 = _upload_form(SAMPLE_CSV, "copy.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        assert resp.json()["data"]["is_duplicate"] is True

    async def test_duplicate_returns_original_record_id(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp1 = await upload_client.post(UPLOAD_URL, files=files, data=data)
        original_id = resp1.json()["data"]["file_record_id"]

        files2, data2 = _upload_form(SAMPLE_CSV, "test2.csv", instrument_id, lab_id)
        resp2 = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        assert resp2.json()["data"]["file_record_id"] == original_id

    async def test_duplicate_suggestion_mentions_existing(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp1 = await upload_client.post(UPLOAD_URL, files=files, data=data)
        record_id = resp1.json()["data"]["file_record_id"]

        files2, data2 = _upload_form(SAMPLE_CSV, "test2.csv", instrument_id, lab_id)
        resp2 = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        suggestion = resp2.json()["data"]["suggestion"]
        assert "already ingested" in suggestion
        assert record_id in suggestion

    async def test_different_content_not_duplicate(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files1, data1 = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp1 = await upload_client.post(UPLOAD_URL, files=files1, data=data1)
        assert resp1.status_code == 201

        files2, data2 = _upload_form(DIFFERENT_CSV, "test2.csv", instrument_id, lab_id)
        resp2 = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        assert resp2.status_code == 201
        assert resp2.json()["data"]["is_duplicate"] is False

    async def test_same_filename_different_content_creates_new(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files1, data1 = _upload_form(SAMPLE_CSV, "data.csv", instrument_id, lab_id)
        resp1 = await upload_client.post(UPLOAD_URL, files=files1, data=data1)

        files2, data2 = _upload_form(DIFFERENT_CSV, "data.csv", instrument_id, lab_id)
        resp2 = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        assert resp1.json()["data"]["file_record_id"] != resp2.json()["data"]["file_record_id"]

    async def test_same_content_different_filename_is_duplicate(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files1, data1 = _upload_form(SAMPLE_CSV, "original.csv", instrument_id, lab_id)
        await upload_client.post(UPLOAD_URL, files=files1, data=data1)

        files2, data2 = _upload_form(SAMPLE_CSV, "renamed.csv", instrument_id, lab_id)
        resp2 = await upload_client.post(UPLOAD_URL, files=files2, data=data2)
        assert resp2.json()["data"]["is_duplicate"] is True


# ---------------------------------------------------------------------------
# File storage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFileStorage:
    """Tests for file storage on local filesystem."""

    async def test_stored_file_has_storage_path(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        storage_path = resp.json()["data"]["storage_path"]
        assert storage_path is not None
        assert len(storage_path) > 0

    async def test_storage_path_contains_hash_prefix(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        storage_path = resp.json()["data"]["storage_path"]
        file_hash = resp.json()["data"]["file_hash"]
        assert file_hash[:2] in storage_path


# ---------------------------------------------------------------------------
# Validation / error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUploadValidation:
    """Tests for upload validation and error handling."""

    async def test_missing_file_returns_422(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        resp = await upload_client.post(
            UPLOAD_URL,
            data={"instrument_id": instrument_id, "lab_id": lab_id},
        )
        assert resp.status_code == 422

    async def test_missing_instrument_id_returns_422(
        self, upload_client: AsyncClient, lab_id: str
    ):
        files = {"file": ("test.csv", io.BytesIO(SAMPLE_CSV), "text/csv")}
        resp = await upload_client.post(UPLOAD_URL, files=files, data={"lab_id": lab_id})
        assert resp.status_code == 422

    async def test_missing_lab_id_returns_422(
        self, upload_client: AsyncClient, instrument_id: str
    ):
        files = {"file": ("test.csv", io.BytesIO(SAMPLE_CSV), "text/csv")}
        resp = await upload_client.post(
            UPLOAD_URL, files=files, data={"instrument_id": instrument_id}
        )
        assert resp.status_code == 422

    async def test_validation_error_has_envelope_format(
        self, upload_client: AsyncClient, instrument_id: str
    ):
        files = {"file": ("test.csv", io.BytesIO(SAMPLE_CSV), "text/csv")}
        resp = await upload_client.post(
            UPLOAD_URL, files=files, data={"instrument_id": instrument_id}
        )
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}
        assert body["data"] is None
        assert len(body["errors"]) > 0
        assert body["errors"][0]["code"] == "validation_error"

    async def test_validation_error_includes_suggestion(
        self, upload_client: AsyncClient
    ):
        resp = await upload_client.post(UPLOAD_URL)
        body = resp.json()
        assert resp.status_code == 422
        for error in body["errors"]:
            assert "suggestion" in error
            assert error["suggestion"] is not None


# ---------------------------------------------------------------------------
# Envelope response contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEnvelopeContract:
    """Verify that every response follows the Envelope[T] contract."""

    async def test_success_envelope_keys(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert set(resp.json().keys()) == {"data", "meta", "errors"}

    async def test_success_meta_has_timestamp(
        self, upload_client: AsyncClient, instrument_id: str, lab_id: str
    ):
        files, data = _upload_form(SAMPLE_CSV, "test.csv", instrument_id, lab_id)
        resp = await upload_client.post(UPLOAD_URL, files=files, data=data)
        assert resp.json()["meta"]["timestamp"] is not None

    async def test_error_envelope_keys(self, upload_client: AsyncClient):
        resp = await upload_client.post(UPLOAD_URL)
        body = resp.json()
        assert set(body.keys()) == {"data", "meta", "errors"}
        assert body["data"] is None
        assert len(body["errors"]) > 0
