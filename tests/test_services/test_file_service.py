"""Tests for the file upload service: SHA-256 dedup, hash chain, storage.

Uses in-memory SQLite via the session fixture from conftest.py.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, Environment
from app.models.identity import Organization
from app.models.ingestion import FileStatus
from app.models.instrument import Instrument, InstrumentDriver
from app.services.file_service import (
    compute_sha256,
    find_by_hash,
    upload_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_instrument(session: AsyncSession) -> tuple[str, str]:
    """Create org + driver + instrument, return (instrument_id, lab_id)."""
    org = Organization(id="org-1", name="Lab", slug="lab")
    session.add(org)
    await session.flush()

    driver = InstrumentDriver(
        id="drv-1", name="Spec CSV",
        instrument_type="spectrophotometer",
        parser_module="app.parsers.spectrophotometer",
    )
    session.add(driver)
    await session.flush()

    inst = Instrument(
        id="inst-1", name="UV-Vis", lab_id="org-1", driver_id="drv-1",
    )
    session.add(inst)
    await session.flush()
    return "inst-1", "org-1"


@pytest.fixture
def file_settings(tmp_path) -> Settings:
    """Settings with local storage pointing to a temp directory."""
    return Settings(
        environment=Environment.test,
        database_url="sqlite+aiosqlite://",
        local_storage_path=str(tmp_path / "storage"),
        storage_backend="local",
        secret_key="test-key",
    )


# ===========================================================================
# compute_sha256
# ===========================================================================


class TestComputeSha256:
    def test_deterministic(self) -> None:
        content = b"Hello, World!"
        assert compute_sha256(content) == compute_sha256(content)

    def test_correct_length(self) -> None:
        h = compute_sha256(b"test data")
        assert len(h) == 64

    def test_different_content_different_hash(self) -> None:
        assert compute_sha256(b"aaa") != compute_sha256(b"bbb")

    def test_empty_content(self) -> None:
        h = compute_sha256(b"")
        assert isinstance(h, str)
        assert len(h) == 64


# ===========================================================================
# upload_file
# ===========================================================================


class TestUploadFile:
    async def test_upload_new_file(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)
        content = b"Sample,Absorbance\nS1,0.5\nS2,0.7\n"

        record, is_new = await upload_file(
            session,
            content=content,
            file_name="scan.csv",
            instrument_id=inst_id,
            lab_id=lab_id,
            mime_type="text/csv",
            settings=file_settings,
        )

        assert is_new is True
        assert record.file_name == "scan.csv"
        assert record.file_hash == compute_sha256(content)
        assert record.file_size_bytes == len(content)
        assert record.status == FileStatus.UPLOADED.value
        assert record.mime_type == "text/csv"
        assert record.instrument_id == inst_id
        assert record.lab_id == lab_id

    async def test_upload_duplicate_returns_existing(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)
        content = b"duplicate content here"

        rec1, is_new1 = await upload_file(
            session, content=content, file_name="file1.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )
        await session.flush()

        rec2, is_new2 = await upload_file(
            session, content=content, file_name="file2.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )

        assert is_new1 is True
        assert is_new2 is False
        assert rec2.id == rec1.id

    async def test_different_content_creates_new(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)

        rec1, _ = await upload_file(
            session, content=b"content A", file_name="a.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )
        await session.flush()

        rec2, _ = await upload_file(
            session, content=b"content B", file_name="b.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )

        assert rec1.id != rec2.id
        assert rec1.file_hash != rec2.file_hash

    async def test_hash_chain_linking(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)

        rec1, _ = await upload_file(
            session, content=b"first file", file_name="first.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )
        await session.flush()

        rec2, _ = await upload_file(
            session, content=b"second file", file_name="second.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )

        # First record has no prev_hash (genesis)
        assert rec1.prev_hash is None
        # Second record chains to first
        assert rec2.prev_hash is not None
        assert rec2.prev_hash == rec1.compute_chain_hash()

    async def test_local_storage(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)
        content = b"stored content"

        record, _ = await upload_file(
            session, content=content, file_name="data.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )

        assert record.storage_path is not None
        assert record.storage_backend == "local"

        # Verify file exists on disk
        full_path = os.path.join(file_settings.local_storage_path, record.storage_path)
        assert os.path.exists(full_path)
        with open(full_path, "rb") as f:
            assert f.read() == content

    async def test_uploaded_by_tracked(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)

        record, _ = await upload_file(
            session, content=b"data", file_name="x.csv",
            instrument_id=inst_id, lab_id=lab_id,
            uploaded_by="user-42",
            settings=file_settings,
        )
        assert record.uploaded_by == "user-42"

    async def test_agent_upload_no_user(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)

        record, _ = await upload_file(
            session, content=b"agent data", file_name="auto.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )
        assert record.uploaded_by is None


# ===========================================================================
# find_by_hash
# ===========================================================================


class TestFindByHash:
    async def test_find_existing(
        self, session: AsyncSession, file_settings: Settings,
    ) -> None:
        inst_id, lab_id = await _seed_instrument(session)
        content = b"findable content"
        file_hash = compute_sha256(content)

        await upload_file(
            session, content=content, file_name="find.csv",
            instrument_id=inst_id, lab_id=lab_id,
            settings=file_settings,
        )
        await session.flush()

        found = await find_by_hash(session, file_hash)
        assert found is not None
        assert found.file_hash == file_hash

    async def test_find_nonexistent(self, session: AsyncSession) -> None:
        found = await find_by_hash(session, "nonexistent_hash")
        assert found is None
