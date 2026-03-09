"""Unit tests for all Pydantic schemas: envelope, auth, audit, experiment, file_upload, parsed_result.

Tests validation rules, serialisation, computed fields, and error cases.
No database required — pure Pydantic model tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.experiment import ExperimentStatus
from app.models.system import AuditAction
from app.schemas.envelope import Envelope, ErrorDetail, ResponseMeta
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.audit import (
    AuditChainVerification,
    AuditEventCreate,
    AuditEventRead,
)
from app.schemas.experiment import (
    ExperimentCreate,
    ExperimentListResponse,
    ExperimentRead,
    ExperimentStateTransition,
    ExperimentUpdate,
)
from app.schemas.file_upload import FileUploadResponse
from app.schemas.parsed_result import (
    InstrumentSettings,
    MeasurementValue,
    ParsedResult,
    QualityFlag,
)


# ===========================================================================
# Envelope Schemas
# ===========================================================================


class TestResponseMeta:
    def test_defaults(self) -> None:
        meta = ResponseMeta()
        assert meta.timestamp is not None
        assert meta.request_id is None
        assert meta.page is None
        assert meta.total is None

    def test_with_pagination(self) -> None:
        meta = ResponseMeta(page=1, page_size=20, total=100)
        assert meta.page == 1
        assert meta.page_size == 20
        assert meta.total == 100


class TestErrorDetail:
    def test_required_fields(self) -> None:
        err = ErrorDetail(code="not_found", message="Resource not found")
        assert err.code == "not_found"
        assert err.suggestion is None
        assert err.field is None

    def test_with_suggestion(self) -> None:
        err = ErrorDetail(
            code="validation_error",
            message="Invalid email",
            suggestion="Use a valid email address",
            field="email",
        )
        assert err.suggestion == "Use a valid email address"
        assert err.field == "email"

    def test_missing_code_raises(self) -> None:
        with pytest.raises(ValidationError):
            ErrorDetail(message="oops")  # type: ignore

    def test_missing_message_raises(self) -> None:
        with pytest.raises(ValidationError):
            ErrorDetail(code="err")  # type: ignore


class TestEnvelope:
    def test_ok_factory(self) -> None:
        env = Envelope.ok({"key": "value"})
        assert env.data == {"key": "value"}
        assert env.errors == []
        assert env.meta.timestamp is not None

    def test_ok_with_pagination(self) -> None:
        env = Envelope.ok([1, 2, 3], page=1, page_size=10, total=3)
        assert env.meta.page == 1
        assert env.meta.total == 3

    def test_error_factory(self) -> None:
        err = ErrorDetail(code="err", message="msg")
        env = Envelope.error([err])
        assert env.data is None
        assert len(env.errors) == 1
        assert env.errors[0].code == "err"

    def test_single_error_factory(self) -> None:
        env = Envelope.single_error(
            "not_found", "Not found",
            suggestion="Check ID", field="id",
        )
        assert env.data is None
        assert len(env.errors) == 1
        assert env.errors[0].suggestion == "Check ID"
        assert env.errors[0].field == "id"

    def test_ok_with_request_id(self) -> None:
        env = Envelope.ok("data", request_id="req-123")
        assert env.meta.request_id == "req-123"

    def test_generic_type_annotation(self) -> None:
        """Envelope[str] wraps a string."""
        env: Envelope[str] = Envelope.ok("hello")
        assert env.data == "hello"

    def test_serialization_roundtrip(self) -> None:
        env = Envelope.ok({"x": 1}, request_id="r1")
        d = env.model_dump()
        assert d["data"] == {"x": 1}
        assert d["meta"]["request_id"] == "r1"
        assert d["errors"] == []


# ===========================================================================
# Auth Schemas
# ===========================================================================


class TestUserRegisterRequest:
    def test_valid(self) -> None:
        req = UserRegisterRequest(
            email="user@lab.com",
            password="securepass123",
            display_name="Lab User",
            org_name="Research Lab",
            org_slug="research-lab",
        )
        assert req.email == "user@lab.com"

    def test_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="not-an-email",
                password="securepass",
                display_name="X",
                org_name="Lab",
                org_slug="lab",
            )

    def test_password_too_short(self) -> None:
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="a@b.com", password="short",
                display_name="X", org_name="Lab", org_slug="lab",
            )

    def test_org_slug_pattern(self) -> None:
        # Valid slugs
        UserRegisterRequest(
            email="a@b.com", password="12345678",
            display_name="X", org_name="Lab", org_slug="my-lab-123",
        )
        # Invalid slug (uppercase)
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="a@b.com", password="12345678",
                display_name="X", org_name="Lab", org_slug="MyLab",
            )


class TestUserLoginRequest:
    def test_valid(self) -> None:
        req = UserLoginRequest(email="user@lab.com", password="pass123")
        assert req.email == "user@lab.com"


class TestTokenResponse:
    def test_defaults(self) -> None:
        resp = TokenResponse(access_token="jwt.token.here", expires_in=3600)
        assert resp.token_type == "bearer"
        assert resp.expires_in == 3600


class TestUserResponse:
    def test_from_dict(self) -> None:
        now = datetime.now(timezone.utc)
        resp = UserResponse(
            id="u1", email="a@b.com", display_name="A",
            org_id="o1", is_active=True, is_service_account=False,
            created_at=now,
        )
        assert resp.last_login_at is None

    def test_from_attributes_mode(self) -> None:
        """model_config from_attributes should be True."""
        assert UserResponse.model_config.get("from_attributes") is True


# ===========================================================================
# Audit Schemas
# ===========================================================================


class TestAuditEventCreate:
    def test_valid(self) -> None:
        event = AuditEventCreate(
            action=AuditAction.CREATE,
            resource_type="experiment",
            summary="Created experiment X",
        )
        assert event.actor_type == "user"
        assert event.resource_id is None
        assert event.metadata is None

    def test_with_all_fields(self) -> None:
        event = AuditEventCreate(
            action=AuditAction.UPDATE,
            resource_type="dataset",
            resource_id="ds-1",
            actor_id="u-1",
            actor_type="agent",
            summary="Updated dataset",
            detail="Changed name from X to Y",
            metadata={"old_name": "X", "new_name": "Y"},
        )
        assert event.metadata == {"old_name": "X", "new_name": "Y"}


class TestAuditEventRead:
    def test_from_dict(self) -> None:
        now = datetime.now(timezone.utc)
        read = AuditEventRead(
            id="ae1", sequence=1, action="CREATE",
            resource_type="experiment",
            actor_id="u1", actor_type="user",
            summary="Created",
            entry_hash="abc123",
            timestamp=now,
        )
        assert read.previous_hash is None
        assert read.metadata_json is None

    def test_parsed_metadata(self) -> None:
        now = datetime.now(timezone.utc)
        read = AuditEventRead(
            id="ae1", sequence=1, action="CREATE",
            resource_type="test", actor_type="user",
            summary="test", entry_hash="h",
            metadata_json='{"key": "value"}',
            timestamp=now,
        )
        assert read.parsed_metadata == {"key": "value"}

    def test_parsed_metadata_none(self) -> None:
        now = datetime.now(timezone.utc)
        read = AuditEventRead(
            id="ae1", sequence=1, action="CREATE",
            resource_type="test", actor_type="user",
            summary="test", entry_hash="h", timestamp=now,
        )
        assert read.parsed_metadata is None


class TestAuditChainVerification:
    def test_valid_chain(self) -> None:
        v = AuditChainVerification(
            valid=True, total_entries=10, invalid_entries=0,
            checked_range=[1, 10],
        )
        assert v.suggestion is None
        assert v.details == []

    def test_broken_chain(self) -> None:
        v = AuditChainVerification(
            valid=False, total_entries=10, invalid_entries=1,
            first_invalid_sequence=5,
            checked_range=[1, 10],
            suggestion="Chain broken at seq 5",
        )
        assert v.first_invalid_sequence == 5


# ===========================================================================
# Experiment Schemas
# ===========================================================================


class TestExperimentCreate:
    def test_valid_minimal(self) -> None:
        ec = ExperimentCreate(name="Test Experiment")
        assert ec.name == "Test Experiment"
        assert ec.description is None
        assert ec.parameters is None

    def test_name_stripped(self) -> None:
        ec = ExperimentCreate(name="  My Exp  ")
        assert ec.name == "My Exp"

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentCreate(name="   ")

    def test_to_orm_dict_without_params(self) -> None:
        ec = ExperimentCreate(name="Exp 1")
        d = ec.to_orm_dict()
        assert "name" in d
        assert "parameters_json" not in d

    def test_to_orm_dict_with_params(self) -> None:
        ec = ExperimentCreate(
            name="Exp 1",
            parameters={"temp": 37, "ph": 7.4},
        )
        d = ec.to_orm_dict()
        assert "parameters_json" in d
        assert json.loads(d["parameters_json"]) == {"temp": 37, "ph": 7.4}
        assert "parameters" not in d

    def test_with_all_fields(self) -> None:
        ec = ExperimentCreate(
            name="Full Experiment",
            description="Detailed description",
            hypothesis="H1: Something works",
            intent="Test the thing",
            project_id="proj-1",
            campaign_id="camp-1",
            parameters={"x": 1},
            protocol="Step 1: do stuff",
        )
        assert ec.hypothesis == "H1: Something works"


class TestExperimentUpdate:
    def test_single_field(self) -> None:
        eu = ExperimentUpdate(name="New Name")
        assert eu.name == "New Name"

    def test_empty_update_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentUpdate()

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentUpdate(name="   ")

    def test_to_orm_dict_maps_parameters(self) -> None:
        eu = ExperimentUpdate(parameters={"k": "v"})
        d = eu.to_orm_dict()
        assert "parameters_json" in d
        assert "parameters" not in d

    def test_to_orm_dict_maps_outcome(self) -> None:
        eu = ExperimentUpdate(outcome={"result": 42})
        d = eu.to_orm_dict()
        assert "outcome_json" in d
        assert "outcome" not in d


class TestExperimentRead:
    def test_from_dict(self) -> None:
        now = datetime.now(timezone.utc)
        er = ExperimentRead(
            id="exp-1", org_id="o1", name="Exp",
            status=ExperimentStatus.DRAFT,
            created_at=now, updated_at=now,
        )
        assert er.status == ExperimentStatus.DRAFT
        assert er.is_terminal is False
        assert ExperimentStatus.RUNNING in [
            ExperimentStatus(v) for v in er.valid_transitions
        ]

    def test_terminal_state_no_transitions(self) -> None:
        now = datetime.now(timezone.utc)
        er = ExperimentRead(
            id="exp-1", org_id="o1", name="Exp",
            status=ExperimentStatus.COMPLETED,
            created_at=now, updated_at=now,
        )
        assert er.is_terminal is True
        assert er.valid_transitions == []

    def test_from_orm_with_json_columns(self) -> None:
        """Validate the model_validator handles parameters_json -> parameters."""
        now = datetime.now(timezone.utc)
        data = {
            "id": "exp-1", "org_id": "o1", "name": "Exp",
            "status": "draft", "created_at": now, "updated_at": now,
            "parameters_json": '{"temp": 37}',
            "outcome_json": '{"result": "pass"}',
        }
        er = ExperimentRead.model_validate(data)
        assert er.parameters == {"temp": 37}
        assert er.outcome == {"result": "pass"}


class TestExperimentStateTransition:
    def test_valid_transition(self) -> None:
        t = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="Starting experiment",
        )
        assert t.target_status == ExperimentStatus.RUNNING

    def test_blank_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentStateTransition(
                target_status=ExperimentStatus.RUNNING,
                reason="   ",
            )

    def test_outcome_on_non_terminal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentStateTransition(
                target_status=ExperimentStatus.RUNNING,
                reason="Starting",
                outcome={"x": 1},
            )

    def test_outcome_on_terminal_allowed(self) -> None:
        t = ExperimentStateTransition(
            target_status=ExperimentStatus.COMPLETED,
            reason="Done",
            outcome={"yield": 95},
            success=True,
        )
        assert t.outcome == {"yield": 95}

    def test_validate_transition_valid(self) -> None:
        t = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="Starting",
        )
        errors = t.validate_transition(ExperimentStatus.DRAFT)
        assert errors == []

    def test_validate_transition_invalid(self) -> None:
        t = ExperimentStateTransition(
            target_status=ExperimentStatus.COMPLETED,
            reason="Done",
            outcome_summary="Worked",
        )
        errors = t.validate_transition(ExperimentStatus.DRAFT)
        assert len(errors) == 1
        assert "Cannot transition" in errors[0]

    def test_reason_stripped(self) -> None:
        t = ExperimentStateTransition(
            target_status=ExperimentStatus.RUNNING,
            reason="  Starting now  ",
        )
        assert t.reason == "Starting now"


class TestExperimentListResponse:
    def test_construct(self) -> None:
        now = datetime.now(timezone.utc)
        items = [
            ExperimentRead(
                id=f"exp-{i}", org_id="o1", name=f"Exp {i}",
                status=ExperimentStatus.DRAFT,
                created_at=now, updated_at=now,
            )
            for i in range(3)
        ]
        resp = ExperimentListResponse(
            items=items, total=100, page=1, page_size=20,
        )
        assert len(resp.items) == 3
        assert resp.total == 100


# ===========================================================================
# File Upload Schema
# ===========================================================================


class TestFileUploadResponse:
    def test_valid(self) -> None:
        now = datetime.now(timezone.utc)
        resp = FileUploadResponse(
            file_record_id="fr1",
            file_name="data.csv",
            file_hash="a" * 64,
            file_size_bytes=1024,
            status="uploaded",
            is_duplicate=False,
            created_at=now,
        )
        assert resp.is_duplicate is False
        assert resp.suggestion is None

    def test_with_suggestion(self) -> None:
        now = datetime.now(timezone.utc)
        resp = FileUploadResponse(
            file_record_id="fr1",
            file_name="data.csv",
            file_hash="b" * 64,
            file_size_bytes=512,
            status="uploaded",
            is_duplicate=True,
            created_at=now,
            suggestion="File already exists. Use the existing record.",
        )
        assert resp.is_duplicate is True
        assert resp.suggestion is not None


# ===========================================================================
# Parsed Result Schemas
# ===========================================================================


class TestQualityFlag:
    def test_all_values(self) -> None:
        assert set(QualityFlag) == {
            QualityFlag.GOOD, QualityFlag.SUSPECT,
            QualityFlag.BAD, QualityFlag.MISSING,
        }

    def test_is_str(self) -> None:
        assert isinstance(QualityFlag.GOOD, str)
        assert QualityFlag.GOOD == "good"


class TestMeasurementValue:
    def test_minimal(self) -> None:
        mv = MeasurementValue(name="absorbance", value=0.5, unit="AU")
        assert mv.quality == QualityFlag.GOOD
        assert mv.metadata == {}
        assert mv.sample_id is None

    def test_with_all_fields(self) -> None:
        mv = MeasurementValue(
            name="ct_value", value=25.3, unit="cycles",
            sample_id="S001", well_position="A1",
            cycle_number=35,
            quality=QualityFlag.SUSPECT,
            metadata={"threshold": 0.1},
        )
        assert mv.cycle_number == 35
        assert mv.quality == QualityFlag.SUSPECT

    def test_null_value(self) -> None:
        """Value can be None (below LOD or missing)."""
        mv = MeasurementValue(name="mass", value=None, unit="mg")
        assert mv.value is None


class TestInstrumentSettings:
    def test_defaults(self) -> None:
        settings = InstrumentSettings()
        assert settings.instrument_model is None
        assert settings.parameters == {}

    def test_with_fields(self) -> None:
        settings = InstrumentSettings(
            instrument_model="Cary 60",
            serial_number="SN-123",
            temperature_celsius=25.0,
            parameters={"pathlength_cm": 1.0},
        )
        assert settings.instrument_model == "Cary 60"


class TestParsedResult:
    def test_minimal(self) -> None:
        pr = ParsedResult(
            parser_name="spectrophotometer",
            parser_version="1.0.0",
            instrument_type="spectrophotometer",
            file_name="scan.csv",
        )
        assert pr.measurements == []
        assert pr.sample_count == 0
        assert pr.warnings == []
        assert pr.has_warnings is False
        assert pr.sample_ids == []

    def test_with_measurements(self) -> None:
        measurements = [
            MeasurementValue(
                name="absorbance", value=0.5, unit="AU",
                sample_id="S1", wavelength_nm=280.0,
            ),
            MeasurementValue(
                name="absorbance", value=0.7, unit="AU",
                sample_id="S2", wavelength_nm=280.0,
            ),
        ]
        pr = ParsedResult(
            parser_name="spectrophotometer",
            parser_version="1.0.0",
            instrument_type="spectrophotometer",
            file_name="scan.csv",
            measurements=measurements,
            sample_count=2,
            measurement_count=2,
        )
        assert len(pr.measurements) == 2
        assert set(pr.sample_ids) == {"S1", "S2"}

    def test_has_warnings(self) -> None:
        pr = ParsedResult(
            parser_name="balance",
            parser_version="1.0.0",
            instrument_type="balance",
            file_name="weight.csv",
            warnings=["Calibration date expired"],
        )
        assert pr.has_warnings is True

    def test_summary(self) -> None:
        pr = ParsedResult(
            parser_name="hplc",
            parser_version="1.0.0",
            instrument_type="hplc",
            file_name="run.csv",
            sample_count=5,
            measurement_count=100,
            warnings=["Peak overlap detected"],
            errors=["Missing reference peak"],
        )
        s = pr.summary()
        assert s["parser_name"] == "hplc"
        assert s["sample_count"] == 5
        assert s["measurement_count"] == 100
        assert s["warning_count"] == 1
        assert s["error_count"] == 1

    def test_serialization_roundtrip(self) -> None:
        pr = ParsedResult(
            parser_name="pcr",
            parser_version="1.0.0",
            instrument_type="pcr",
            file_name="amplification.csv",
            measurements=[
                MeasurementValue(
                    name="ct_value", value=25.0, unit="cycles",
                    sample_id="S1",
                ),
            ],
            sample_count=1,
            measurement_count=1,
        )
        json_str = pr.model_dump_json()
        loaded = ParsedResult.model_validate_json(json_str)
        assert loaded.parser_name == "pcr"
        assert len(loaded.measurements) == 1
        assert loaded.measurements[0].value == 25.0


# ===========================================================================
# Schema exports
# ===========================================================================


class TestSchemaExports:
    """Verify that app.schemas.__init__ exports all expected types."""

    def test_all_exports_importable(self) -> None:
        from app.schemas import __all__
        import app.schemas as schemas_mod

        for name in __all__:
            assert hasattr(schemas_mod, name), f"Missing export: {name}"
