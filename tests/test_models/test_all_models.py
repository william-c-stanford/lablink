"""Unit tests for all SQLAlchemy ORM models: identity, instrument, ingestion, data, system.

Tests model construction, column defaults (via metadata inspection), enums,
computed properties, hash computation, and repr formatting.

NOTE: SQLAlchemy column `default=` values are NOT applied at constructor time.
They are applied at flush/insert time. So in-memory tests must either:
  (a) Explicitly pass values, or
  (b) Inspect the column default metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.base import (
    Base,
)
from app.models.identity import (
    ApiKey,
    ApiKeyStatus,
    Organization,
    PlanTier,
    Role,
    RoleName,
    User,
)
from app.models.instrument import (
    Instrument,
    InstrumentDriver,
    WatchedFolder,
)
from app.models.ingestion import (
    FileRecord,
    FileStatus,
    ParseResult,
)
from app.models.data import (
    DataPoint,
    Dataset,
    Tag,
    TagAssociation,
)
from app.models.system import (
    AuditAction,
    AuditEvent,
    AuditLog,
    Notification,
    NotificationLevel,
    NotificationStatus,
    SystemConfig,
)


# ===========================================================================
# Base Mixins
# ===========================================================================


class TestSoftDeleteMixin:
    """SoftDeleteMixin.is_deleted property."""

    def test_not_deleted_by_default(self) -> None:
        org = Organization(id="o1", name="Lab", slug="lab")
        assert org.is_deleted is False
        assert org.deleted_at is None

    def test_is_deleted_when_set(self) -> None:
        org = Organization(id="o1", name="Lab", slug="lab")
        org.deleted_at = datetime.now(timezone.utc)
        assert org.is_deleted is True


class TestAuditMixin:
    """AuditMixin.compute_hash for hash chain integrity."""

    def test_compute_hash_default_fields(self) -> None:
        user = User(
            id="u1",
            org_id="o1",
            email="a@b.com",
            display_name="A",
            actor_id="actor-1",
            action="create",
            prev_hash=None,
        )
        h = user.compute_hash()
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_compute_hash_deterministic(self) -> None:
        user = User(
            id="u1",
            org_id="o1",
            email="a@b.com",
            display_name="A",
            actor_id="actor-1",
            action="create",
            prev_hash="abc",
        )
        assert user.compute_hash() == user.compute_hash()

    def test_compute_hash_with_custom_fields(self) -> None:
        user = User(id="u1", org_id="o1", email="a@b.com", display_name="A")
        h1 = user.compute_hash({"foo": "bar"})
        h2 = user.compute_hash({"foo": "baz"})
        assert h1 != h2

    def test_compute_hash_changes_with_prev_hash(self) -> None:
        user = User(
            id="u1", org_id="o1", email="a@b.com", display_name="A",
            actor_id="a", action="create",
        )
        user.prev_hash = None
        h1 = user.compute_hash()
        user.prev_hash = "somehash"
        h2 = user.compute_hash()
        assert h1 != h2


# ===========================================================================
# Identity Enums
# ===========================================================================


class TestPlanTier:
    def test_values(self) -> None:
        assert set(PlanTier) == {
            PlanTier.free, PlanTier.starter, PlanTier.pro, PlanTier.enterprise
        }

    def test_is_str(self) -> None:
        assert isinstance(PlanTier.free, str)
        assert PlanTier.free == "free"


class TestRoleName:
    def test_values(self) -> None:
        assert set(RoleName) == {
            RoleName.owner, RoleName.admin, RoleName.member,
            RoleName.viewer, RoleName.agent,
        }


class TestApiKeyStatus:
    def test_values(self) -> None:
        assert set(ApiKeyStatus) == {
            ApiKeyStatus.active, ApiKeyStatus.revoked, ApiKeyStatus.expired,
        }


# ===========================================================================
# Identity Models
# ===========================================================================


class TestOrganization:
    def test_construct(self) -> None:
        org = Organization(id="o1", name="My Lab", slug="my-lab")
        assert org.name == "My Lab"
        assert org.slug == "my-lab"

    def test_column_default_plan(self) -> None:
        """The column default for plan should be 'free'."""
        col = Organization.__table__.columns["plan"]
        assert col.default.arg == PlanTier.free.value

    def test_repr(self) -> None:
        org = Organization(id="o1", name="Lab", slug="lab-one")
        r = repr(org)
        assert "Organization" in r
        assert "lab-one" in r

    def test_tablename(self) -> None:
        assert Organization.__tablename__ == "organizations"

    def test_soft_delete_mixin(self) -> None:
        assert hasattr(Organization, "deleted_at")
        assert hasattr(Organization, "is_deleted")


class TestUser:
    def test_construct(self) -> None:
        user = User(
            id="u1", org_id="o1", email="test@lab.com",
            display_name="Test User",
        )
        assert user.email == "test@lab.com"
        assert user.display_name == "Test User"
        assert user.hashed_password is None
        assert user.last_login_at is None

    def test_column_defaults(self) -> None:
        tbl = User.__table__
        assert tbl.columns["is_active"].default.arg is True
        assert tbl.columns["is_service_account"].default.arg is False

    def test_repr(self) -> None:
        user = User(id="u1", org_id="o1", email="x@y.com", display_name="X")
        assert "x@y.com" in repr(user)

    def test_tablename(self) -> None:
        assert User.__tablename__ == "users"

    def test_has_audit_mixin(self) -> None:
        assert hasattr(User, "actor_id")
        assert hasattr(User, "record_hash")
        assert hasattr(User, "compute_hash")


class TestRole:
    def test_column_default_role_name(self) -> None:
        col = Role.__table__.columns["role_name"]
        assert col.default.arg == RoleName.member.value

    def test_repr(self) -> None:
        role = Role(id="r1", user_id="u1", org_id="o1", role_name="owner")
        r = repr(role)
        assert "owner" in r

    def test_tablename(self) -> None:
        assert Role.__tablename__ == "roles"


class TestApiKey:
    def test_construct(self) -> None:
        key = ApiKey(
            id="k1", org_id="o1", user_id="u1",
            name="My Key", key_hash="abc123",
        )
        assert key.name == "My Key"

    def test_column_default_status(self) -> None:
        col = ApiKey.__table__.columns["status"]
        assert col.default.arg == ApiKeyStatus.active.value

    def test_is_active_when_active(self) -> None:
        key = ApiKey(
            id="k1", org_id="o1", user_id="u1",
            name="K", key_hash="h1",
            status=ApiKeyStatus.active.value,
        )
        assert key.is_active is True

    def test_is_not_active_when_revoked(self) -> None:
        key = ApiKey(
            id="k1", org_id="o1", user_id="u1",
            name="K", key_hash="h1",
            status=ApiKeyStatus.revoked.value,
        )
        assert key.is_active is False

    def test_is_not_active_when_expired(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(days=1)
        key = ApiKey(
            id="k1", org_id="o1", user_id="u1",
            name="K", key_hash="h1",
            status=ApiKeyStatus.active.value,
            expires_at=past,
        )
        assert key.is_active is False

    def test_is_active_when_future_expiry(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=30)
        key = ApiKey(
            id="k1", org_id="o1", user_id="u1",
            name="K", key_hash="h1",
            status=ApiKeyStatus.active.value,
            expires_at=future,
        )
        assert key.is_active is True

    def test_repr(self) -> None:
        key = ApiKey(
            id="k1", org_id="o1", user_id="u1",
            name="K", key_hash="h1", key_prefix="ll_abc",
        )
        r = repr(key)
        assert "ApiKey" in r
        assert "ll_abc" in r

    def test_tablename(self) -> None:
        assert ApiKey.__tablename__ == "api_keys"


# ===========================================================================
# Instrument Models
# ===========================================================================


class TestInstrumentDriver:
    def test_construct(self) -> None:
        driver = InstrumentDriver(
            id="d1", name="Spec CSV",
            instrument_type="spectrophotometer",
            parser_module="app.parsers.spectrophotometer",
        )
        assert driver.name == "Spec CSV"

    def test_column_defaults(self) -> None:
        tbl = InstrumentDriver.__table__
        assert tbl.columns["file_patterns"].default.arg == "*.csv"
        assert tbl.columns["is_active"].default.arg is True

    def test_repr(self) -> None:
        driver = InstrumentDriver(
            id="d1", name="HPLC CSV",
            instrument_type="hplc",
            parser_module="app.parsers.hplc",
        )
        assert "HPLC CSV" in repr(driver)
        assert "hplc" in repr(driver)

    def test_tablename(self) -> None:
        assert InstrumentDriver.__tablename__ == "instrument_drivers"


class TestInstrument:
    def test_construct(self) -> None:
        inst = Instrument(
            id="i1", name="UV-Vis Lab 3",
            lab_id="lab-1", driver_id="d1",
        )
        assert inst.serial_number is None
        assert inst.manufacturer is None

    def test_column_default_is_active(self) -> None:
        col = Instrument.__table__.columns["is_active"]
        assert col.default.arg is True

    def test_soft_delete(self) -> None:
        inst = Instrument(id="i1", name="X", lab_id="l1", driver_id="d1")
        assert inst.is_deleted is False
        inst.deleted_at = datetime.now(timezone.utc)
        assert inst.is_deleted is True

    def test_repr(self) -> None:
        inst = Instrument(id="i1", name="Cary 60", lab_id="lab-1", driver_id="d1")
        assert "Cary 60" in repr(inst)

    def test_tablename(self) -> None:
        assert Instrument.__tablename__ == "instruments"


class TestWatchedFolder:
    def test_construct(self) -> None:
        wf = WatchedFolder(
            id="wf1", instrument_id="i1",
            folder_path="/data/instrument_output",
        )
        assert wf.agent_id is None

    def test_column_default_is_active(self) -> None:
        col = WatchedFolder.__table__.columns["is_active"]
        assert col.default.arg is True

    def test_repr(self) -> None:
        wf = WatchedFolder(
            id="wf1", instrument_id="i1", folder_path="/data/out",
        )
        assert "/data/out" in repr(wf)

    def test_tablename(self) -> None:
        assert WatchedFolder.__tablename__ == "watched_folders"


# ===========================================================================
# Ingestion Models
# ===========================================================================


class TestFileStatus:
    def test_all_statuses(self) -> None:
        expected = {"UPLOADED", "QUEUED", "PARSING", "PARSED", "FAILED", "STORED"}
        assert {s.name for s in FileStatus} == expected

    def test_is_str_enum(self) -> None:
        assert isinstance(FileStatus.UPLOADED, str)
        assert FileStatus.UPLOADED == "uploaded"


class TestFileRecord:
    def test_construct(self) -> None:
        rec = FileRecord(
            id="fr1", file_name="data.csv",
            file_hash="abc123", file_size_bytes=1024,
            instrument_id="i1", lab_id="l1",
        )
        assert rec.prev_hash is None

    def test_column_defaults(self) -> None:
        tbl = FileRecord.__table__
        assert tbl.columns["status"].default.arg == FileStatus.UPLOADED.value
        assert tbl.columns["storage_backend"].default.arg == "local"

    def test_compute_chain_hash(self) -> None:
        rec = FileRecord(
            id="fr1", file_name="data.csv",
            file_hash="abcdef1234567890", file_size_bytes=100,
            instrument_id="i1", lab_id="l1",
        )
        h = rec.compute_chain_hash()
        assert isinstance(h, str)
        assert len(h) == 64

    def test_chain_hash_genesis(self) -> None:
        """When prev_hash is None, uses 'genesis' as placeholder."""
        rec = FileRecord(
            id="fr1", file_name="x.csv", file_hash="abc",
            file_size_bytes=10, instrument_id="i1", lab_id="l1",
            prev_hash=None,
        )
        h1 = rec.compute_chain_hash()
        rec.prev_hash = "something"
        h2 = rec.compute_chain_hash()
        assert h1 != h2

    def test_chain_hash_deterministic(self) -> None:
        rec = FileRecord(
            id="fr1", file_name="x.csv", file_hash="abc",
            file_size_bytes=10, instrument_id="i1", lab_id="l1",
            prev_hash="prev123",
        )
        assert rec.compute_chain_hash() == rec.compute_chain_hash()

    def test_repr(self) -> None:
        rec = FileRecord(
            id="fr1", file_name="sample.csv", file_hash="h",
            file_size_bytes=100, instrument_id="i1", lab_id="l1",
            status="uploaded",
        )
        r = repr(rec)
        assert "sample.csv" in r
        assert "uploaded" in r

    def test_tablename(self) -> None:
        assert FileRecord.__tablename__ == "file_records"


class TestParseResult:
    def test_construct(self) -> None:
        pr = ParseResult(
            id="pr1", file_record_id="fr1",
            parser_name="spectrophotometer",
            parser_version="1.0.0",
            parsed_data='{"measurements": []}',
            instrument_type="spectrophotometer",
        )
        assert pr.parser_name == "spectrophotometer"

    def test_column_defaults(self) -> None:
        tbl = ParseResult.__table__
        assert tbl.columns["sample_count"].default.arg == 0
        assert tbl.columns["measurement_count"].default.arg == 0
        assert tbl.columns["warning_count"].default.arg == 0
        assert tbl.columns["error_count"].default.arg == 0
        assert tbl.columns["is_valid"].default.arg is True

    def test_repr(self) -> None:
        pr = ParseResult(
            id="pr1", file_record_id="fr1",
            parser_name="hplc", parser_version="1.0",
            parsed_data="{}", instrument_type="hplc",
            measurement_count=42,
        )
        r = repr(pr)
        assert "hplc" in r
        assert "42" in r

    def test_tablename(self) -> None:
        assert ParseResult.__tablename__ == "parse_results"


# ===========================================================================
# Data Models
# ===========================================================================


class TestDataset:
    def test_construct(self) -> None:
        ds = Dataset(
            id="ds1", org_id="o1", name="UV Scan",
            instrument_type="spectrophotometer",
            parser_name="spectrophotometer", parser_version="1.0",
        )
        assert ds.name == "UV Scan"

    def test_column_defaults(self) -> None:
        tbl = Dataset.__table__
        assert tbl.columns["sample_count"].default.arg == 0
        assert tbl.columns["measurement_count"].default.arg == 0
        assert tbl.columns["warning_count"].default.arg == 0
        assert tbl.columns["error_count"].default.arg == 0

    def test_soft_delete(self) -> None:
        ds = Dataset(
            id="ds1", org_id="o1", name="X",
            instrument_type="hplc", parser_name="hplc", parser_version="1.0",
        )
        assert ds.is_deleted is False

    def test_repr(self) -> None:
        ds = Dataset(
            id="ds1", org_id="o1", name="My Data",
            instrument_type="pcr", parser_name="pcr", parser_version="1.0",
        )
        r = repr(ds)
        assert "My Data" in r
        assert "pcr" in r

    def test_tablename(self) -> None:
        assert Dataset.__tablename__ == "datasets"


class TestDataPoint:
    def test_construct(self) -> None:
        dp = DataPoint(
            id="dp1", dataset_id="ds1",
            name="absorbance", value=0.543, unit="AU",
        )
        assert dp.wavelength_nm is None
        assert dp.sample_id is None

    def test_column_default_quality(self) -> None:
        col = DataPoint.__table__.columns["quality"]
        assert col.default.arg == "good"

    def test_repr(self) -> None:
        dp = DataPoint(
            id="dp1", dataset_id="ds1",
            name="mass", value=12.5, unit="mg",
        )
        r = repr(dp)
        assert "mass" in r
        assert "12.5" in r

    def test_tablename(self) -> None:
        assert DataPoint.__tablename__ == "data_points"


class TestTag:
    def test_construct(self) -> None:
        tag = Tag(id="t1", org_id="o1", name="Quality Check", slug="quality-check")
        assert tag.color is None
        assert tag.description is None

    def test_repr(self) -> None:
        tag = Tag(id="t1", org_id="o1", name="QC", slug="qc")
        assert "QC" in repr(tag)

    def test_tablename(self) -> None:
        assert Tag.__tablename__ == "tags"


class TestTagAssociation:
    def test_construct(self) -> None:
        ta = TagAssociation(
            id="ta1", tag_id="t1",
            resource_type="dataset", resource_id="ds1",
        )
        assert ta.resource_type == "dataset"

    def test_repr(self) -> None:
        ta = TagAssociation(
            id="ta1", tag_id="t1",
            resource_type="experiment", resource_id="exp1",
        )
        r = repr(ta)
        assert "experiment" in r

    def test_tablename(self) -> None:
        assert TagAssociation.__tablename__ == "tag_associations"


# ===========================================================================
# System / Audit Models
# ===========================================================================


class TestAuditAction:
    def test_all_actions(self) -> None:
        expected = {
            "CREATE", "UPDATE", "DELETE", "RESTORE",
            "LOGIN", "LOGOUT", "UPLOAD", "PARSE",
            "EXPORT", "CONFIG_CHANGE", "STATE_CHANGE",
        }
        assert {a.name for a in AuditAction} == expected


class TestNotificationLevel:
    def test_all_levels(self) -> None:
        assert set(NotificationLevel) == {
            NotificationLevel.INFO, NotificationLevel.WARNING,
            NotificationLevel.ERROR, NotificationLevel.SUCCESS,
        }


class TestNotificationStatus:
    def test_all_statuses(self) -> None:
        assert set(NotificationStatus) == {
            NotificationStatus.UNREAD, NotificationStatus.READ,
            NotificationStatus.DISMISSED,
        }


class TestAuditLog:
    def test_construct(self) -> None:
        log = AuditLog(
            id="al1", sequence=1,
            action=AuditAction.CREATE.value,
            resource_type="experiment",
            actor_type="user",
            summary="Created experiment",
            entry_hash="abc",
        )
        assert log.previous_hash is None

    def test_compute_hash_deterministic(self) -> None:
        log = AuditLog(
            id="al1", sequence=1,
            action=AuditAction.CREATE.value,
            resource_type="experiment",
            resource_id="exp-1",
            actor_id="u1",
            summary="Created experiment",
            detail=None,
            previous_hash=None,
            entry_hash="placeholder",
        )
        h = log.compute_hash()
        assert len(h) == 64
        assert h == log.compute_hash()

    def test_compute_hash_changes_with_content(self) -> None:
        log1 = AuditLog(
            id="al1", sequence=1, action="CREATE",
            resource_type="experiment", actor_id="u1",
            summary="Created", previous_hash=None, entry_hash="x",
        )
        log2 = AuditLog(
            id="al1", sequence=1, action="UPDATE",
            resource_type="experiment", actor_id="u1",
            summary="Created", previous_hash=None, entry_hash="x",
        )
        assert log1.compute_hash() != log2.compute_hash()

    def test_extra_metadata_property(self) -> None:
        log = AuditLog(
            id="al1", sequence=1, action="CREATE",
            resource_type="test", summary="test", entry_hash="h",
        )
        assert log.extra_metadata is None

        log.extra_metadata = {"key": "value"}
        assert log.metadata_json == '{"key": "value"}'
        assert log.extra_metadata == {"key": "value"}

        log.extra_metadata = None
        assert log.metadata_json is None

    def test_tablename(self) -> None:
        assert AuditLog.__tablename__ == "audit_logs"


class TestAuditEvent:
    def test_construct(self) -> None:
        event = AuditEvent(
            id="ae1", sequence=1,
            actor="user@lab.com", actor_type="user",
            action=AuditAction.CREATE.value,
            resource_type="experiment",
            event_hash="abc",
        )
        assert event.previous_hash is None
        assert event.detail is None

    def test_compute_hash_deterministic(self) -> None:
        event = AuditEvent(
            id="ae1", sequence=1,
            actor="user@lab.com",
            action=AuditAction.CREATE.value,
            resource_type="experiment",
            resource_id="exp-1",
            detail=None,
            previous_hash=None,
            event_hash="placeholder",
        )
        h = event.compute_hash()
        assert len(h) == 64
        assert h == event.compute_hash()

    def test_detail_dict_property(self) -> None:
        event = AuditEvent(
            id="ae1", sequence=1, actor="sys", action="CREATE",
            resource_type="test", event_hash="h",
        )
        assert event.detail_dict is None

        event.detail_dict = {"changes": ["a", "b"]}
        assert event.detail == '{"changes": ["a", "b"]}'
        result = event.detail_dict
        assert result == {"changes": ["a", "b"]}

        event.detail_dict = None
        assert event.detail is None

    def test_repr(self) -> None:
        event = AuditEvent(
            id="ae1", sequence=1, actor="user@lab.com",
            action="CREATE", resource_type="experiment",
            event_hash="h",
        )
        r = repr(event)
        assert "AuditEvent" in r
        assert "CREATE" in r
        assert "experiment" in r

    def test_tablename(self) -> None:
        assert AuditEvent.__tablename__ == "audit_events"


class TestNotification:
    def test_construct(self) -> None:
        n = Notification(
            id="n1", title="Parse complete",
            message="File data.csv parsed successfully",
        )
        assert n.read_at is None

    def test_column_defaults(self) -> None:
        tbl = Notification.__table__
        assert tbl.columns["level"].default.arg == NotificationLevel.INFO.value
        assert tbl.columns["status"].default.arg == NotificationStatus.UNREAD.value

    def test_tablename(self) -> None:
        assert Notification.__tablename__ == "notifications"


class TestSystemConfig:
    def test_construct(self) -> None:
        cfg = SystemConfig(
            id="sc1", key="parsers.balance.tolerance",
            value="0.001", value_type="float",
        )
        assert cfg.key == "parsers.balance.tolerance"

    def test_column_defaults(self) -> None:
        tbl = SystemConfig.__table__
        assert tbl.columns["value_type"].default.arg == "string"
        assert tbl.columns["category"].default.arg == "general"

    def test_typed_value_string(self) -> None:
        cfg = SystemConfig(id="1", key="k", value="hello", value_type="string")
        assert cfg.typed_value == "hello"

    def test_typed_value_int(self) -> None:
        cfg = SystemConfig(id="1", key="k", value="42", value_type="int")
        assert cfg.typed_value == 42

    def test_typed_value_float(self) -> None:
        cfg = SystemConfig(id="1", key="k", value="3.14", value_type="float")
        assert cfg.typed_value == pytest.approx(3.14)

    def test_typed_value_bool_true(self) -> None:
        for val in ("true", "True", "1", "yes"):
            cfg = SystemConfig(id="1", key="k", value=val, value_type="bool")
            assert cfg.typed_value is True

    def test_typed_value_bool_false(self) -> None:
        cfg = SystemConfig(id="1", key="k", value="false", value_type="bool")
        assert cfg.typed_value is False

    def test_typed_value_json(self) -> None:
        cfg = SystemConfig(
            id="1", key="k",
            value='{"a": [1, 2, 3]}', value_type="json",
        )
        assert cfg.typed_value == {"a": [1, 2, 3]}

    def test_tablename(self) -> None:
        assert SystemConfig.__tablename__ == "system_configs"


# ===========================================================================
# Table count: verify all expected tables are in metadata
# ===========================================================================


class TestAllTablesRegistered:
    def test_all_tables_in_metadata(self) -> None:
        """All domain tables must be registered in Base.metadata."""
        expected_tables = {
            "organizations", "users", "roles", "api_keys",
            "instrument_drivers", "instruments", "watched_folders",
            "file_records", "parse_results",
            "datasets", "data_points", "tags", "tag_associations",
            "audit_logs", "audit_events", "notifications",
            "system_configs", "experiments", "experiment_files",
        }
        actual_tables = set(Base.metadata.tables.keys())
        missing = expected_tables - actual_tables
        assert not missing, f"Missing tables: {missing}"
