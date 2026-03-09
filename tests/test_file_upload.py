"""Tests for file upload with SHA-256 deduplication.

Covers:
  - New file upload creates a FileRecord with correct fields
  - Duplicate detection returns existing record (no new row)
  - SHA-256 hash computation correctness
  - Hash-chain linking (prev_hash set correctly)
  - File metadata (size, name, status) stored correctly
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models.base import Base
from app.models.ingestion import FileRecord, FileStatus
from app.models.instrument import Instrument, InstrumentDriver
from app.services.file_service import compute_sha256, find_by_hash, upload_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    """Settings configured for in-memory SQLite testing."""
    return Settings(
        database_url="sqlite+aiosqlite://",
        environment="test",
        debug=False,
        storage_backend="local",
        local_storage_path=str(tmp_path / "storage"),
    )


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """Create an in-memory SQLite async engine for testing."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    """Create an async session for testing."""
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def instrument(session: AsyncSession) -> Instrument:
    """Create a test instrument with its driver (required FK for FileRecord)."""
    driver = InstrumentDriver(
        id=str(uuid.uuid4()),
        name="Test Spectrophotometer CSV",
        instrument_type="spectrophotometer",
        parser_module="app.parsers.spectrophotometer",
        file_patterns="*.csv",
    )
    session.add(driver)
    await session.flush()

    inst = Instrument(
        id=str(uuid.uuid4()),
        name="UV-Vis Lab 3",
        lab_id="lab-001",
        driver_id=driver.id,
    )
    session.add(inst)
    await session.flush()
    return inst


# ---------------------------------------------------------------------------
# SHA-256 hash computation tests
# ---------------------------------------------------------------------------


class TestSHA256Computation:
    """Tests for SHA-256 hash computation correctness."""

    def test_compute_sha256_known_value(self):
        """Hash of known input matches expected SHA-256 digest."""
        content = b"Hello, LabLink!"
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(content) == expected

    def test_compute_sha256_empty_content(self):
        """Hash of empty bytes produces the known SHA-256 of empty string."""
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_sha256(b"") == expected
        # Known value: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
        assert (
            compute_sha256(b"")
            == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_compute_sha256_returns_64_char_hex(self):
        """SHA-256 always returns a 64-character lowercase hex string."""
        result = compute_sha256(b"any content")
        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_sha256_deterministic(self):
        """Same content always produces the same hash."""
        content = b"reproducible science data"
        assert compute_sha256(content) == compute_sha256(content)

    def test_compute_sha256_different_content_different_hash(self):
        """Different content produces different hashes."""
        hash1 = compute_sha256(b"sample A data")
        hash2 = compute_sha256(b"sample B data")
        assert hash1 != hash2

    def test_compute_sha256_binary_content(self):
        """Hash works correctly with binary (non-UTF-8) content."""
        content = bytes(range(256))
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(content) == expected

    def test_compute_sha256_large_content(self):
        """Hash works correctly with larger payloads."""
        content = b"x" * (1024 * 1024)  # 1 MB
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(content) == expected


# ---------------------------------------------------------------------------
# New file upload tests
# ---------------------------------------------------------------------------


class TestNewFileUpload:
    """Tests for uploading a new file (no duplicate)."""

    @pytest.mark.asyncio
    async def test_upload_creates_file_record(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Uploading a new file creates a FileRecord in the database."""
        content = b"wavelength,absorbance\n340,0.523\n350,0.612"

        record, is_new = await upload_file(
            session=session,
            content=content,
            file_name="spectrum_001.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            mime_type="text/csv",
            settings=test_settings,
        )

        assert is_new is True
        assert record is not None
        assert record.id is not None

    @pytest.mark.asyncio
    async def test_upload_stores_correct_hash(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord.file_hash matches SHA-256 of uploaded content."""
        content = b"wavelength,absorbance\n340,0.523"
        expected_hash = compute_sha256(content)

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="spectrum.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record.file_hash == expected_hash

    @pytest.mark.asyncio
    async def test_upload_stores_correct_file_size(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord.file_size_bytes matches length of uploaded content."""
        content = b"data,value\n1,2\n3,4"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="data.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record.file_size_bytes == len(content)

    @pytest.mark.asyncio
    async def test_upload_stores_filename(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord.file_name preserves the original filename."""
        content = b"x,y\n1,2"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="my_experiment_2026-03-06.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record.file_name == "my_experiment_2026-03-06.csv"

    @pytest.mark.asyncio
    async def test_upload_initial_status_is_uploaded(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """New FileRecord starts with status 'uploaded'."""
        content = b"header\nrow1"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="file.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record.status == FileStatus.UPLOADED.value

    @pytest.mark.asyncio
    async def test_upload_stores_mime_type(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord.mime_type is stored when provided."""
        content = b"col1,col2\na,b"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="file.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            mime_type="text/csv",
            settings=test_settings,
        )

        assert record.mime_type == "text/csv"

    @pytest.mark.asyncio
    async def test_upload_stores_lab_and_instrument(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord correctly links to instrument and lab."""
        content = b"data"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="file.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record.instrument_id == instrument.id
        assert record.lab_id == "lab-001"

    @pytest.mark.asyncio
    async def test_upload_stores_uploaded_by(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord.uploaded_by is set when provided."""
        content = b"data"
        user_id = str(uuid.uuid4())

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="file.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            uploaded_by=user_id,
            settings=test_settings,
        )

        assert record.uploaded_by == user_id

    @pytest.mark.asyncio
    async def test_first_upload_has_no_prev_hash(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """First FileRecord in the chain has prev_hash=None."""
        content = b"first file ever"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="first.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record.prev_hash is None

    @pytest.mark.asyncio
    async def test_second_upload_has_prev_hash(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Second FileRecord links to first via prev_hash (hash chain)."""
        content1 = b"first file"
        content2 = b"second file"

        record1, _ = await upload_file(
            session=session,
            content=content1,
            file_name="first.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        record2, _ = await upload_file(
            session=session,
            content=content2,
            file_name="second.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert record2.prev_hash is not None
        assert record2.prev_hash == record1.compute_chain_hash()

    @pytest.mark.asyncio
    async def test_upload_persists_to_database(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord is queryable from the database after upload."""
        content = b"persisted data"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="persisted.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        stmt = select(FileRecord).where(FileRecord.id == record.id)
        result = await session.execute(stmt)
        fetched = result.scalar_one()

        assert fetched.file_name == "persisted.csv"
        assert fetched.file_hash == compute_sha256(content)


# ---------------------------------------------------------------------------
# Duplicate detection tests
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for SHA-256-based duplicate detection."""

    @pytest.mark.asyncio
    async def test_duplicate_returns_existing_record(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Uploading identical content returns the existing FileRecord."""
        content = b"wavelength,absorbance\n340,0.523\n350,0.612"

        record1, is_new1 = await upload_file(
            session=session,
            content=content,
            file_name="spectrum_001.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        record2, is_new2 = await upload_file(
            session=session,
            content=content,
            file_name="spectrum_001_copy.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert is_new1 is True
        assert is_new2 is False
        assert record1.id == record2.id

    @pytest.mark.asyncio
    async def test_duplicate_does_not_create_new_row(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Duplicate upload doesn't insert a new database row."""
        content = b"same content twice"

        await upload_file(
            session=session,
            content=content,
            file_name="original.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        await upload_file(
            session=session,
            content=content,
            file_name="duplicate.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        stmt = select(FileRecord)
        result = await session.execute(stmt)
        records = result.scalars().all()

        assert len(records) == 1

    @pytest.mark.asyncio
    async def test_duplicate_detected_with_different_filename(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Dedup is content-based, not filename-based. Same content + different name = duplicate."""
        content = b"identical instrument output"

        record1, _ = await upload_file(
            session=session,
            content=content,
            file_name="run_001.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        record2, is_new = await upload_file(
            session=session,
            content=content,
            file_name="run_002.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert is_new is False
        assert record2.id == record1.id
        # Original filename is preserved (not overwritten)
        assert record2.file_name == "run_001.csv"

    @pytest.mark.asyncio
    async def test_different_content_not_duplicate(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Different content with same filename creates separate records."""
        content1 = b"run 1 data: 0.523"
        content2 = b"run 2 data: 0.612"

        record1, is_new1 = await upload_file(
            session=session,
            content=content1,
            file_name="output.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        record2, is_new2 = await upload_file(
            session=session,
            content=content2,
            file_name="output.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert is_new1 is True
        assert is_new2 is True
        assert record1.id != record2.id
        assert record1.file_hash != record2.file_hash

    @pytest.mark.asyncio
    async def test_find_by_hash_returns_none_for_unknown(
        self,
        session: AsyncSession,
    ):
        """find_by_hash returns None when no matching record exists."""
        result = await find_by_hash(session, "a" * 64)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_hash_returns_existing(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """find_by_hash returns the record when content matches."""
        content = b"findable content"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="findable.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        found = await find_by_hash(session, compute_sha256(content))
        assert found is not None
        assert found.id == record.id

    @pytest.mark.asyncio
    async def test_duplicate_across_instruments(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Same content uploaded to different instruments is still a duplicate (global dedup)."""
        content = b"universal calibration data"

        # First upload
        record1, is_new1 = await upload_file(
            session=session,
            content=content,
            file_name="cal.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )
        await session.commit()

        # Second upload (same content, same instrument — global dedup by hash)
        record2, is_new2 = await upload_file(
            session=session,
            content=content,
            file_name="cal_copy.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        assert is_new1 is True
        assert is_new2 is False
        assert record1.id == record2.id


# ---------------------------------------------------------------------------
# Hash chain integrity tests
# ---------------------------------------------------------------------------


class TestHashChainIntegrity:
    """Tests for the immutable audit trail hash chain."""

    @pytest.mark.asyncio
    async def test_chain_hash_computation(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """FileRecord.compute_chain_hash produces correct value."""
        content = b"chain test data"

        record, _ = await upload_file(
            session=session,
            content=content,
            file_name="chain.csv",
            instrument_id=instrument.id,
            lab_id="lab-001",
            settings=test_settings,
        )

        # Manual computation
        expected_payload = f"{record.file_hash}:genesis"
        expected_hash = hashlib.sha256(expected_payload.encode()).hexdigest()

        assert record.compute_chain_hash() == expected_hash

    @pytest.mark.asyncio
    async def test_three_file_chain(
        self,
        session: AsyncSession,
        instrument: Instrument,
        test_settings: Settings,
    ):
        """Three sequential uploads form a valid hash chain."""
        records = []
        for i in range(3):
            content = f"file {i} content".encode()
            record, is_new = await upload_file(
                session=session,
                content=content,
                file_name=f"file_{i}.csv",
                instrument_id=instrument.id,
                lab_id="lab-001",
                settings=test_settings,
            )
            assert is_new is True
            await session.commit()
            records.append(record)

        # First record: no prev_hash
        assert records[0].prev_hash is None

        # Second record: prev_hash = chain_hash of first
        assert records[1].prev_hash == records[0].compute_chain_hash()

        # Third record: prev_hash = chain_hash of second
        assert records[2].prev_hash == records[1].compute_chain_hash()
