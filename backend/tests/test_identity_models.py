"""Tests for identity models: Organization, User, Role, ApiKey and mixins."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_engine, create_session_factory
from app.models.base import AuditMixin, Base
from app.models.identity import (
    ApiKey,
    ApiKeyStatus,
    Organization,
    PlanTier,
    Role,
    RoleName,
    User,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session(test_settings):
    """Create tables and yield a session, then tear down."""
    engine = create_engine(test_settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = create_session_factory(engine)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture()
def sample_org() -> Organization:
    return Organization(
        name="Acme Labs",
        slug="acme-labs",
        plan=PlanTier.starter.value,
        description="A test lab",
    )


@pytest.fixture()
def sample_user(sample_org: Organization) -> User:
    return User(
        org_id=sample_org.id,
        email="alice@acme.test",
        display_name="Alice",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# AuditMixin tests
# ---------------------------------------------------------------------------


class TestAuditMixin:
    def test_compute_hash_returns_64_char_hex(self):
        class FakeModel(AuditMixin):
            id = "test-id"
            actor_id = "user-1"
            action = "create"
            prev_hash = None
            record_hash = None

        obj = FakeModel()
        h = obj.compute_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_compute_hash_deterministic(self):
        class FakeModel(AuditMixin):
            id = "abc"
            actor_id = "u1"
            action = "create"
            prev_hash = None
            record_hash = None

        h1 = FakeModel().compute_hash()
        h2 = FakeModel().compute_hash()
        assert h1 == h2

    def test_compute_hash_with_custom_fields(self):
        class FakeModel(AuditMixin):
            id = "x"
            actor_id = None
            action = None
            prev_hash = None
            record_hash = None

        obj = FakeModel()
        fields = {"foo": "bar", "num": 42}
        h = obj.compute_hash(fields)
        expected = hashlib.sha256(
            json.dumps(fields, sort_keys=True, default=str).encode()
        ).hexdigest()
        assert h == expected

    def test_hash_chain_linking(self):
        """Verify prev_hash creates a chain."""

        class FakeModel(AuditMixin):
            id = "r1"
            actor_id = "u1"
            action = "create"
            prev_hash = None
            record_hash = None

        first = FakeModel()
        first.record_hash = first.compute_hash()

        class FakeModel2(AuditMixin):
            id = "r2"
            actor_id = "u1"
            action = "update"
            prev_hash = first.record_hash
            record_hash = None

        second = FakeModel2()
        second.record_hash = second.compute_hash()

        assert second.prev_hash == first.record_hash
        assert second.record_hash != first.record_hash


# ---------------------------------------------------------------------------
# Organization tests
# ---------------------------------------------------------------------------


class TestOrganization:
    async def test_create_organization(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.commit()

        result = await db_session.execute(
            select(Organization).where(Organization.slug == "acme-labs")
        )
        org = result.scalar_one()
        assert org.name == "Acme Labs"
        assert org.plan == PlanTier.starter.value
        assert org.id is not None
        assert len(org.id) == 36  # UUID format

    async def test_organization_timestamps(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.commit()

        result = await db_session.execute(
            select(Organization).where(Organization.id == sample_org.id)
        )
        org = result.scalar_one()
        assert org.created_at is not None
        assert org.updated_at is not None

    async def test_organization_soft_delete(
        self, db_session: AsyncSession, sample_org
    ):
        db_session.add(sample_org)
        await db_session.commit()

        assert sample_org.is_deleted is False
        sample_org.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()
        assert sample_org.is_deleted is True

    async def test_organization_default_plan_is_free(self, db_session: AsyncSession):
        org = Organization(name="Free Lab", slug="free-lab")
        db_session.add(org)
        await db_session.commit()

        result = await db_session.execute(
            select(Organization).where(Organization.slug == "free-lab")
        )
        fetched = result.scalar_one()
        assert fetched.plan == PlanTier.free.value

    async def test_organization_slug_unique(
        self, db_session: AsyncSession, sample_org
    ):
        db_session.add(sample_org)
        await db_session.commit()

        dup = Organization(name="Duplicate", slug="acme-labs")
        db_session.add(dup)
        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    def test_organization_repr(self, sample_org):
        assert "acme-labs" in repr(sample_org)


# ---------------------------------------------------------------------------
# User tests
# ---------------------------------------------------------------------------


class TestUser:
    async def test_create_user(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id,
            email="bob@acme.test",
            display_name="Bob",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.email == "bob@acme.test")
        )
        fetched = result.scalar_one()
        assert fetched.display_name == "Bob"
        assert fetched.is_active is True
        assert fetched.is_service_account is False

    async def test_user_email_unique(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        u1 = User(
            org_id=sample_org.id, email="same@acme.test", display_name="One"
        )
        u2 = User(
            org_id=sample_org.id, email="same@acme.test", display_name="Two"
        )
        db_session.add_all([u1, u2])
        with pytest.raises(Exception):
            await db_session.commit()

    async def test_user_has_audit_fields(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id,
            email="audit@acme.test",
            display_name="Auditor",
            actor_id="system",
            action="create",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.email == "audit@acme.test")
        )
        fetched = result.scalar_one()
        assert fetched.actor_id == "system"
        assert fetched.action == "create"

    async def test_user_soft_delete(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="del@acme.test", display_name="Del"
        )
        db_session.add(user)
        await db_session.commit()

        assert user.is_deleted is False
        user.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()
        assert user.is_deleted is True

    def test_user_repr(self, sample_user):
        assert "alice@acme.test" in repr(sample_user)


# ---------------------------------------------------------------------------
# Role tests
# ---------------------------------------------------------------------------


class TestRole:
    async def test_create_role(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="role@acme.test", display_name="Roled"
        )
        db_session.add(user)
        await db_session.flush()

        role = Role(
            user_id=user.id,
            org_id=sample_org.id,
            role_name=RoleName.admin.value,
        )
        db_session.add(role)
        await db_session.commit()

        result = await db_session.execute(
            select(Role).where(Role.user_id == user.id)
        )
        fetched = result.scalar_one()
        assert fetched.role_name == "admin"

    async def test_role_default_is_member(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="mem@acme.test", display_name="Mem"
        )
        db_session.add(user)
        await db_session.flush()

        role = Role(user_id=user.id, org_id=sample_org.id)
        db_session.add(role)
        await db_session.commit()

        assert role.role_name == RoleName.member.value

    async def test_unique_user_org_role(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="dup@acme.test", display_name="Dup"
        )
        db_session.add(user)
        await db_session.flush()

        r1 = Role(
            user_id=user.id,
            org_id=sample_org.id,
            role_name=RoleName.member.value,
        )
        r2 = Role(
            user_id=user.id,
            org_id=sample_org.id,
            role_name=RoleName.admin.value,
        )
        db_session.add_all([r1, r2])
        with pytest.raises(Exception):
            await db_session.commit()

    def test_role_repr(self):
        role = Role(user_id="u1", org_id="o1", role_name="admin")
        assert "admin" in repr(role)


# ---------------------------------------------------------------------------
# ApiKey tests
# ---------------------------------------------------------------------------


class TestApiKey:
    async def test_create_api_key(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="key@acme.test", display_name="Key"
        )
        db_session.add(user)
        await db_session.flush()

        key = ApiKey(
            org_id=sample_org.id,
            user_id=user.id,
            name="Test Key",
            key_hash=hashlib.sha256(b"secret-key-123").hexdigest(),
        )
        db_session.add(key)
        await db_session.commit()

        result = await db_session.execute(
            select(ApiKey).where(ApiKey.name == "Test Key")
        )
        fetched = result.scalar_one()
        assert fetched.status == ApiKeyStatus.active.value
        assert fetched.key_prefix.startswith("ll_")
        assert fetched.is_active is True

    async def test_api_key_expired(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="exp@acme.test", display_name="Exp"
        )
        db_session.add(user)
        await db_session.flush()

        key = ApiKey(
            org_id=sample_org.id,
            user_id=user.id,
            name="Expired Key",
            key_hash=hashlib.sha256(b"expired-key").hexdigest(),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(key)
        await db_session.commit()

        assert key.is_active is False

    async def test_api_key_revoked(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="rev@acme.test", display_name="Rev"
        )
        db_session.add(user)
        await db_session.flush()

        key = ApiKey(
            org_id=sample_org.id,
            user_id=user.id,
            name="Revoked Key",
            key_hash=hashlib.sha256(b"revoked-key").hexdigest(),
            status=ApiKeyStatus.revoked.value,
        )
        db_session.add(key)
        await db_session.commit()

        assert key.is_active is False

    async def test_api_key_has_audit_fields(
        self, db_session: AsyncSession, sample_org
    ):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="aud@acme.test", display_name="Aud"
        )
        db_session.add(user)
        await db_session.flush()

        key = ApiKey(
            org_id=sample_org.id,
            user_id=user.id,
            name="Audited Key",
            key_hash=hashlib.sha256(b"audited-key").hexdigest(),
            actor_id=user.id,
            action="create",
        )
        db_session.add(key)
        await db_session.commit()

        result = await db_session.execute(
            select(ApiKey).where(ApiKey.name == "Audited Key")
        )
        fetched = result.scalar_one()
        assert fetched.actor_id == user.id
        assert fetched.action == "create"

    async def test_api_key_repr(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="repr@acme.test", display_name="Repr"
        )
        db_session.add(user)
        await db_session.flush()

        key = ApiKey(
            org_id=sample_org.id,
            user_id=user.id,
            name="Repr Key",
            key_hash=hashlib.sha256(b"repr-key").hexdigest(),
            key_prefix="ll_abc123",
        )
        db_session.add(key)
        await db_session.commit()
        assert "ll_abc123" in repr(key)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_plan_tier_values(self):
        assert set(PlanTier) == {
            PlanTier.free,
            PlanTier.starter,
            PlanTier.pro,
            PlanTier.enterprise,
        }

    def test_role_name_values(self):
        assert RoleName.agent.value == "agent"
        assert len(RoleName) == 5

    def test_api_key_status_values(self):
        assert len(ApiKeyStatus) == 3


# ---------------------------------------------------------------------------
# Relationship tests
# ---------------------------------------------------------------------------


class TestRelationships:
    async def test_org_has_users(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        u1 = User(
            org_id=sample_org.id, email="r1@acme.test", display_name="R1"
        )
        u2 = User(
            org_id=sample_org.id, email="r2@acme.test", display_name="R2"
        )
        db_session.add_all([u1, u2])
        await db_session.commit()

        result = await db_session.execute(
            select(Organization).where(Organization.id == sample_org.id)
        )
        org = result.scalar_one()
        assert len(org.users) == 2

    async def test_user_belongs_to_org(self, db_session: AsyncSession, sample_org):
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="belong@acme.test", display_name="B"
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.id == user.id)
        )
        fetched = result.scalar_one()
        assert fetched.organization.slug == "acme-labs"

    async def test_cascade_delete_org_removes_users(
        self, db_session: AsyncSession, sample_org
    ):
        """Verify FK cascade on organization delete."""
        db_session.add(sample_org)
        await db_session.flush()

        user = User(
            org_id=sample_org.id, email="cas@acme.test", display_name="Cas"
        )
        db_session.add(user)
        await db_session.commit()

        # Delete org directly via SQL to trigger FK cascade
        await db_session.execute(
            text(f"DELETE FROM organizations WHERE id = '{sample_org.id}'")
        )
        await db_session.commit()

        result = await db_session.execute(select(User))
        assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# Table schema tests
# ---------------------------------------------------------------------------


class TestTableSchema:
    async def test_all_identity_tables_exist(self, db_session: AsyncSession):
        """All four identity tables should be created."""
        conn = await db_session.connection()
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = {row[0] for row in result.fetchall()}
        assert "organizations" in tables
        assert "users" in tables
        assert "roles" in tables
        assert "api_keys" in tables

    async def test_users_table_has_audit_columns(self, db_session: AsyncSession):
        conn = await db_session.connection()
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = {row[1] for row in result.fetchall()}
        assert "actor_id" in columns
        assert "action" in columns
        assert "prev_hash" in columns
        assert "record_hash" in columns

    async def test_api_keys_table_has_audit_columns(self, db_session: AsyncSession):
        conn = await db_session.connection()
        result = await conn.execute(text("PRAGMA table_info(api_keys)"))
        columns = {row[1] for row in result.fetchall()}
        assert "actor_id" in columns
        assert "record_hash" in columns
