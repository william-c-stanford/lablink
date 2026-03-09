"""Seed script: inserts deterministic demo data for local dev and E2E tests.

Usage::

    uv run python -m lablink.scripts.seed

Idempotent: running it twice is safe — existing records are skipped by natural key.
Does NOT use the get_engine() singleton; creates its own fresh engine so it can
run before the app boots and in test setup scripts.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from lablink.models.base import Base
from lablink.models.organization import Organization
from lablink.models.user import User
from lablink.models.membership import Membership, MemberRole
from lablink.models.instrument import Instrument
from lablink.models.upload import Upload, UploadStatus
from lablink.models.parsed_data import ParsedData

# ---------------------------------------------------------------------------
# Constants — all deterministic so re-runs produce the same UUIDs
# ---------------------------------------------------------------------------

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # standard DNS namespace


def _uid(name: str) -> str:
    return str(uuid.uuid5(_NS, f"lablink-seed:{name}"))


# Seed credentials — safe to check in (local dev only, guarded by is_dev)
SEED_EMAIL = "demo@example.com"
SEED_PASSWORD = "demodemo"  # noqa: S105 — intentional demo credential
SEED_ORG_SLUG = "demo-lab"

ORG_ID = _uid("org:demo-lab")
USER_ID = _uid("user:demo@lablink.local")
INSTRUMENT_SPECTRO_ID = _uid("instrument:nanodrop-1")
INSTRUMENT_PLATE_ID = _uid("instrument:plate-reader-1")
UPLOAD_1_ID = _uid("upload:nanodrop-sample.csv")
UPLOAD_2_ID = _uid("upload:softmax-pro-96well.csv")

FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures"


async def _seed(session: AsyncSession) -> None:
    """Insert demo records, skipping any that already exist."""

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------
    existing_org = await session.scalar(
        select(Organization).where(Organization.slug == SEED_ORG_SLUG)
    )
    if existing_org is None:
        org = Organization(
            id=ORG_ID,
            name="Demo Lab",
            slug=SEED_ORG_SLUG,
        )
        session.add(org)
        await session.flush()
        print(f"  + org: {org.name} ({org.id})")
    else:
        print(f"  ~ org already exists: {existing_org.name}")

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------
    existing_user = await session.scalar(select(User).where(User.email == SEED_EMAIL))
    if existing_user is None:
        # Import here to avoid circular at module level
        from lablink.services.auth_service import hash_password

        user = User(
            id=USER_ID,
            email=SEED_EMAIL,
            password_hash=hash_password(SEED_PASSWORD),
            full_name="Demo User",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        print(f"  + user: {user.email} ({user.id})")
    else:
        print(f"  ~ user already exists: {existing_user.email}")

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------
    existing_membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == USER_ID,
            Membership.organization_id == ORG_ID,
        )
    )
    if existing_membership is None:
        membership = Membership(
            id=_uid("membership:demo"),
            user_id=USER_ID,
            organization_id=ORG_ID,
            role=MemberRole.admin,
        )
        session.add(membership)
        await session.flush()
        print(f"  + membership: {USER_ID} → {ORG_ID} ({membership.role})")
    else:
        print("  ~ membership already exists")

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------
    for inst_id, name, inst_type in [
        (INSTRUMENT_SPECTRO_ID, "NanoDrop 2000", "spectrophotometer"),
        (INSTRUMENT_PLATE_ID, "SpectraMax M5", "plate_reader"),
    ]:
        existing = await session.scalar(select(Instrument).where(Instrument.id == inst_id))
        if existing is None:
            instrument = Instrument(
                id=inst_id,
                organization_id=ORG_ID,
                name=name,
                instrument_type=inst_type,
                model=name,
                location="Lab Room A",
            )
            session.add(instrument)
            await session.flush()
            print(f"  + instrument: {instrument.name} ({instrument.id})")
        else:
            print(f"  ~ instrument already exists: {existing.name}")

    # ------------------------------------------------------------------
    # Uploads (copy fixture bytes into local storage)
    # ------------------------------------------------------------------
    storage_root = Path(os.environ.get("LABLINK_LOCAL_STORAGE_PATH", "./storage"))
    storage_root.mkdir(parents=True, exist_ok=True)

    upload_fixtures = [
        (
            UPLOAD_1_ID,
            FIXTURES_DIR / "spectrophotometer" / "nanodrop_sample.csv",
            "nanodrop_sample.csv",
            "spectrophotometer",
            INSTRUMENT_SPECTRO_ID,
        ),
        (
            UPLOAD_2_ID,
            FIXTURES_DIR / "plate_reader" / "softmax_pro_96well.csv",
            "softmax_pro_96well.csv",
            "plate_reader",
            INSTRUMENT_PLATE_ID,
        ),
    ]

    for upload_id, fixture_path, filename, inst_type, instrument_id in upload_fixtures:
        existing = await session.scalar(select(Upload).where(Upload.id == upload_id))
        if existing is not None:
            print(f"  ~ upload already exists: {filename}")
            continue

        if not fixture_path.exists():
            print(f"  ! fixture not found, skipping: {fixture_path}")
            continue

        file_bytes = fixture_path.read_bytes()
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # Write to storage using deterministic key
        storage_key = f"uploads/{upload_id}/{filename}"
        dest = storage_root / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(file_bytes)

        upload = Upload(
            id=upload_id,
            organization_id=ORG_ID,
            instrument_id=instrument_id,
            filename=filename,
            mime_type="text/csv",
            file_size_bytes=len(file_bytes),
            content_hash=content_hash,
            s3_key=storage_key,
            status=UploadStatus.parsed.value,
            instrument_type_detected=inst_type,
        )
        session.add(upload)
        await session.flush()
        print(f"  + upload: {filename} ({upload.id})")

        # ParsedData — minimal stub so the dashboard shows parsed records
        parsed = ParsedData(
            id=_uid(f"parsed:{upload_id}"),
            upload_id=upload_id,
            organization_id=ORG_ID,
            instrument_type=inst_type,
            parser_version="1.0.0",
            measurement_type="absorbance",
            sample_count=5,
            data_summary={},
            measurements=[],
        )
        session.add(parsed)
        await session.flush()
        print(f"  + parsed_data for upload: {filename}")

    await session.commit()


async def main() -> None:
    db_url = os.environ.get("LABLINK_DATABASE_URL", "sqlite+aiosqlite:///./lablink.db")
    print(f"Seeding: {db_url}")

    engine = create_async_engine(db_url, echo=False)

    # Enable WAL + FK pragmas for SQLite
    if "sqlite" in db_url:
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _conn_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with AsyncSessionLocal() as session:
        await _seed(session)

    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
