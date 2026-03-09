"""Tests for ExperimentService — CRUD operations and state machine enforcement.

Covers:
- Create experiment (default DRAFT state)
- Get experiment by ID (with org scoping, soft-delete filtering)
- List experiments (pagination, filtering by status/org)
- Update experiment (field updates, terminal state restrictions)
- Soft delete
- State machine transitions (all valid paths, all invalid paths)
- Transition timestamps (started_at, completed_at)
- Error handling (NotFoundError, StateTransitionError, ValidationError)
- Agent-friendly suggestion fields on errors
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.exceptions import NotFoundError, StateTransitionError, ValidationError
from app.models.base import Base
from app.models.experiment import ExperimentStatus, EXPERIMENT_TRANSITIONS
from app.models.identity import Organization
from app.services.experiment import (
    create_experiment,
    get_experiment,
    list_experiments,
    soft_delete_experiment,
    transition_experiment,
    update_experiment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """In-memory SQLite engine with all tables created."""
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
async def session_factory(engine):
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def org(session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Lab",
        slug="test-lab",
    )
    session.add(org)
    await session.flush()
    return org


@pytest_asyncio.fixture
async def org_id(org: Organization) -> str:
    return org.id


# ---------------------------------------------------------------------------
# CREATE tests
# ---------------------------------------------------------------------------


class TestCreateExperiment:
    @pytest.mark.asyncio
    async def test_create_basic(self, session, org_id):
        """Created experiment starts in DRAFT state with correct fields."""
        exp = await create_experiment(
            session,
            org_id=org_id,
            name="Dose-response curve",
        )
        assert exp.id is not None
        assert exp.name == "Dose-response curve"
        assert exp.org_id == org_id
        assert exp.status == ExperimentStatus.DRAFT.value
        assert exp.started_at is None
        assert exp.completed_at is None
        assert exp.deleted_at is None

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, session, org_id):
        """All optional fields are persisted."""
        exp = await create_experiment(
            session,
            org_id=org_id,
            name="HPLC method validation",
            description="Validate HPLC method for compound X",
            hypothesis="Method will be linear in 1-100 ug/mL range",
            intent="Method validation",
            project_id="proj-123",
            campaign_id="camp-456",
            parameters_json='{"column": "C18", "flow_rate": 1.0}',
            protocol="USP method 621",
            created_by="user-789",
        )
        assert exp.description == "Validate HPLC method for compound X"
        assert exp.hypothesis == "Method will be linear in 1-100 ug/mL range"
        assert exp.intent == "Method validation"
        assert exp.project_id == "proj-123"
        assert exp.campaign_id == "camp-456"
        assert exp.parameters_json == '{"column": "C18", "flow_rate": 1.0}'
        assert exp.protocol == "USP method 621"
        assert exp.created_by == "user-789"

    @pytest.mark.asyncio
    async def test_create_generates_uuid(self, session, org_id):
        """Each experiment gets a unique UUID."""
        exp1 = await create_experiment(session, org_id=org_id, name="Exp 1")
        exp2 = await create_experiment(session, org_id=org_id, name="Exp 2")
        assert exp1.id != exp2.id
        assert len(exp1.id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_create_sets_timestamps(self, session, org_id):
        """created_at and updated_at are automatically set."""
        exp = await create_experiment(session, org_id=org_id, name="Timestamped")
        assert exp.created_at is not None
        assert exp.updated_at is not None


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------


class TestGetExperiment:
    @pytest.mark.asyncio
    async def test_get_existing(self, session, org_id):
        """Can retrieve a created experiment."""
        created = await create_experiment(session, org_id=org_id, name="Findable")
        found = await get_experiment(session, created.id)
        assert found.id == created.id
        assert found.name == "Findable"

    @pytest.mark.asyncio
    async def test_get_not_found(self, session):
        """NotFoundError raised for nonexistent ID."""
        fake_id = str(uuid.uuid4())
        with pytest.raises(NotFoundError) as exc_info:
            await get_experiment(session, fake_id)
        assert fake_id in str(exc_info.value.message)
        assert exc_info.value.suggestion is not None

    @pytest.mark.asyncio
    async def test_get_with_org_scope(self, session, org_id):
        """Org scoping filters experiments from other orgs."""
        exp = await create_experiment(session, org_id=org_id, name="Scoped")
        # Same org works
        found = await get_experiment(session, exp.id, org_id=org_id)
        assert found.id == exp.id
        # Different org raises NotFound
        with pytest.raises(NotFoundError):
            await get_experiment(session, exp.id, org_id="other-org-id")

    @pytest.mark.asyncio
    async def test_get_excludes_deleted_by_default(self, session, org_id):
        """Soft-deleted experiments are not returned by default."""
        exp = await create_experiment(session, org_id=org_id, name="To Delete")
        await soft_delete_experiment(session, exp.id)
        with pytest.raises(NotFoundError):
            await get_experiment(session, exp.id)

    @pytest.mark.asyncio
    async def test_get_includes_deleted_when_requested(self, session, org_id):
        """include_deleted=True returns soft-deleted experiments."""
        exp = await create_experiment(session, org_id=org_id, name="Deleted but findable")
        await soft_delete_experiment(session, exp.id)
        found = await get_experiment(session, exp.id, include_deleted=True)
        assert found.id == exp.id
        assert found.deleted_at is not None


# ---------------------------------------------------------------------------
# LIST tests
# ---------------------------------------------------------------------------


class TestListExperiments:
    @pytest.mark.asyncio
    async def test_list_empty(self, session, org_id):
        """Empty org returns empty list with zero total."""
        exps, total = await list_experiments(session, org_id=org_id)
        assert exps == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_returns_all(self, session, org_id):
        """All experiments in an org are returned."""
        for i in range(3):
            await create_experiment(session, org_id=org_id, name=f"Exp {i}")
        exps, total = await list_experiments(session, org_id=org_id)
        assert len(exps) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, session, org_id):
        """Status filter narrows results."""
        await create_experiment(session, org_id=org_id, name="Planned")
        exp2 = await create_experiment(session, org_id=org_id, name="Running")
        await transition_experiment(session, exp2.id, ExperimentStatus.RUNNING)

        planned, total_planned = await list_experiments(
            session, org_id=org_id, status=ExperimentStatus.DRAFT
        )
        assert len(planned) == 1
        assert total_planned == 1
        assert planned[0].name == "Planned"

        running, total_running = await list_experiments(
            session, org_id=org_id, status=ExperimentStatus.RUNNING
        )
        assert len(running) == 1
        assert total_running == 1

    @pytest.mark.asyncio
    async def test_list_pagination(self, session, org_id):
        """Pagination returns correct slices."""
        for i in range(5):
            await create_experiment(session, org_id=org_id, name=f"Exp {i}")

        page1, total = await list_experiments(session, org_id=org_id, page=1, page_size=2)
        assert len(page1) == 2
        assert total == 5

        page3, _ = await list_experiments(session, org_id=org_id, page=3, page_size=2)
        assert len(page3) == 1  # 5th item

    @pytest.mark.asyncio
    async def test_list_excludes_deleted(self, session, org_id):
        """Deleted experiments are excluded from listing by default."""
        await create_experiment(session, org_id=org_id, name="Active")
        exp2 = await create_experiment(session, org_id=org_id, name="Deleted")
        await soft_delete_experiment(session, exp2.id)

        exps, total = await list_experiments(session, org_id=org_id)
        assert len(exps) == 1
        assert total == 1
        assert exps[0].name == "Active"

    @pytest.mark.asyncio
    async def test_list_org_isolation(self, session, org_id):
        """Experiments from other orgs are not visible."""
        await create_experiment(session, org_id=org_id, name="My Exp")
        # Create another org's experiment
        other_org = Organization(id=str(uuid.uuid4()), name="Other Lab", slug="other-lab")
        session.add(other_org)
        await session.flush()
        await create_experiment(session, org_id=other_org.id, name="Their Exp")

        exps, total = await list_experiments(session, org_id=org_id)
        assert len(exps) == 1
        assert total == 1
        assert exps[0].name == "My Exp"


# ---------------------------------------------------------------------------
# UPDATE tests
# ---------------------------------------------------------------------------


class TestUpdateExperiment:
    @pytest.mark.asyncio
    async def test_update_name(self, session, org_id):
        """Can update experiment name."""
        exp = await create_experiment(session, org_id=org_id, name="Old Name")
        updated = await update_experiment(session, exp.id, name="New Name")
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, session, org_id):
        """Multiple fields can be updated at once."""
        exp = await create_experiment(session, org_id=org_id, name="Original")
        updated = await update_experiment(
            session,
            exp.id,
            name="Updated",
            description="New description",
            hypothesis="New hypothesis",
        )
        assert updated.name == "Updated"
        assert updated.description == "New description"
        assert updated.hypothesis == "New hypothesis"

    @pytest.mark.asyncio
    async def test_update_ignores_unknown_fields(self, session, org_id):
        """Unknown fields are silently ignored."""
        exp = await create_experiment(session, org_id=org_id, name="Test")
        updated = await update_experiment(session, exp.id, name="Updated", bogus_field="ignored")
        assert updated.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_terminal_raises(self, session, org_id):
        """Cannot update a completed experiment."""
        exp = await create_experiment(session, org_id=org_id, name="To Complete")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)

        with pytest.raises(ValidationError) as exc_info:
            await update_experiment(session, exp.id, name="Nope")
        assert (
            "terminal" in exc_info.value.suggestion.lower()
            or "completed" in exc_info.value.suggestion.lower()
        )

    @pytest.mark.asyncio
    async def test_update_failed_raises(self, session, org_id):
        """Cannot update a failed experiment."""
        exp = await create_experiment(session, org_id=org_id, name="To Fail")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.FAILED)

        with pytest.raises(ValidationError):
            await update_experiment(session, exp.id, name="Nope")

    @pytest.mark.asyncio
    async def test_update_cancelled_raises(self, session, org_id):
        """Cannot update a cancelled experiment."""
        exp = await create_experiment(session, org_id=org_id, name="To Cancel")
        await transition_experiment(session, exp.id, ExperimentStatus.CANCELLED)

        with pytest.raises(ValidationError):
            await update_experiment(session, exp.id, name="Nope")

    @pytest.mark.asyncio
    async def test_update_not_found(self, session):
        """Updating nonexistent experiment raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await update_experiment(session, str(uuid.uuid4()), name="Ghost")


# ---------------------------------------------------------------------------
# SOFT DELETE tests
# ---------------------------------------------------------------------------


class TestSoftDeleteExperiment:
    @pytest.mark.asyncio
    async def test_soft_delete(self, session, org_id):
        """Soft delete sets deleted_at timestamp."""
        exp = await create_experiment(session, org_id=org_id, name="Deletable")
        deleted = await soft_delete_experiment(session, exp.id)
        assert deleted.deleted_at is not None
        assert deleted.is_deleted

    @pytest.mark.asyncio
    async def test_soft_delete_already_deleted(self, session, org_id):
        """Deleting an already-deleted experiment raises ValidationError."""
        exp = await create_experiment(session, org_id=org_id, name="Double Delete")
        await soft_delete_experiment(session, exp.id)
        with pytest.raises(ValidationError) as exc_info:
            await soft_delete_experiment(session, exp.id)
        assert "already deleted" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_soft_delete_not_found(self, session):
        """Deleting nonexistent experiment raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await soft_delete_experiment(session, str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_soft_delete_with_org_scope(self, session, org_id):
        """Org scoping applies to soft delete."""
        exp = await create_experiment(session, org_id=org_id, name="Scoped Delete")
        with pytest.raises(NotFoundError):
            await soft_delete_experiment(session, exp.id, org_id="wrong-org")


# ---------------------------------------------------------------------------
# STATE MACHINE tests — valid transitions
# ---------------------------------------------------------------------------


class TestValidTransitions:
    @pytest.mark.asyncio
    async def test_planned_to_running(self, session, org_id):
        """DRAFT -> RUNNING sets started_at."""
        exp = await create_experiment(session, org_id=org_id, name="Start me")
        result = await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert result.status == ExperimentStatus.RUNNING.value
        assert result.started_at is not None
        assert result.completed_at is None

    @pytest.mark.asyncio
    async def test_planned_to_cancelled(self, session, org_id):
        """DRAFT -> CANCELLED sets completed_at."""
        exp = await create_experiment(session, org_id=org_id, name="Cancel me")
        result = await transition_experiment(session, exp.id, ExperimentStatus.CANCELLED)
        assert result.status == ExperimentStatus.CANCELLED.value
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_running_to_completed(self, session, org_id):
        """RUNNING -> COMPLETED sets completed_at."""
        exp = await create_experiment(session, org_id=org_id, name="Complete me")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        result = await transition_experiment(
            session,
            exp.id,
            ExperimentStatus.COMPLETED,
            outcome_summary="All endpoints validated",
            success=True,
        )
        assert result.status == ExperimentStatus.COMPLETED.value
        assert result.completed_at is not None
        assert result.outcome_summary == "All endpoints validated"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_running_to_failed(self, session, org_id):
        """RUNNING -> FAILED sets completed_at and outcome."""
        exp = await create_experiment(session, org_id=org_id, name="Fail me")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        result = await transition_experiment(
            session,
            exp.id,
            ExperimentStatus.FAILED,
            outcome_summary="Reagent contaminated",
            outcome_json='{"error": "contamination"}',
            success=False,
        )
        assert result.status == ExperimentStatus.FAILED.value
        assert result.completed_at is not None
        assert result.outcome_summary == "Reagent contaminated"
        assert result.outcome_json == '{"error": "contamination"}'
        assert result.success is False

    @pytest.mark.asyncio
    async def test_full_happy_path(self, session, org_id):
        """DRAFT -> RUNNING -> COMPLETED is the happy path."""
        exp = await create_experiment(session, org_id=org_id, name="Happy Path")
        assert exp.status == ExperimentStatus.DRAFT.value

        running = await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert running.status == ExperimentStatus.RUNNING.value
        assert running.started_at is not None

        completed = await transition_experiment(
            session, exp.id, ExperimentStatus.COMPLETED, success=True
        )
        assert completed.status == ExperimentStatus.COMPLETED.value
        assert completed.completed_at is not None
        assert completed.success is True


# ---------------------------------------------------------------------------
# STATE MACHINE tests — invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    @pytest.mark.asyncio
    async def test_planned_to_completed(self, session, org_id):
        """DRAFT -> COMPLETED is invalid (must go through RUNNING)."""
        exp = await create_experiment(session, org_id=org_id, name="Skip step")
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        assert "draft" in exc_info.value.message.lower()
        assert "completed" in exc_info.value.message.lower()
        assert exc_info.value.suggestion is not None
        assert (
            "running" in exc_info.value.suggestion.lower()
            or "cancelled" in exc_info.value.suggestion.lower()
        )

    @pytest.mark.asyncio
    async def test_planned_to_failed(self, session, org_id):
        """DRAFT -> FAILED is invalid."""
        exp = await create_experiment(session, org_id=org_id, name="Premature fail")
        with pytest.raises(StateTransitionError):
            await transition_experiment(session, exp.id, ExperimentStatus.FAILED)

    @pytest.mark.asyncio
    async def test_running_to_planned(self, session, org_id):
        """RUNNING -> DRAFT is invalid (no going back)."""
        exp = await create_experiment(session, org_id=org_id, name="No rewind")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        with pytest.raises(StateTransitionError):
            await transition_experiment(session, exp.id, ExperimentStatus.DRAFT)

    @pytest.mark.asyncio
    async def test_running_to_cancelled(self, session, org_id):
        """RUNNING -> CANCELLED is invalid."""
        exp = await create_experiment(session, org_id=org_id, name="No cancel running")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        with pytest.raises(StateTransitionError):
            await transition_experiment(session, exp.id, ExperimentStatus.CANCELLED)

    @pytest.mark.asyncio
    async def test_completed_to_anything(self, session, org_id):
        """COMPLETED is terminal — no transitions allowed."""
        exp = await create_experiment(session, org_id=org_id, name="Terminal completed")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)

        for target in ExperimentStatus:
            with pytest.raises(StateTransitionError) as exc_info:
                await transition_experiment(session, exp.id, target)
            assert "terminal" in exc_info.value.suggestion.lower()

    @pytest.mark.asyncio
    async def test_failed_to_anything(self, session, org_id):
        """FAILED is terminal — no transitions allowed."""
        exp = await create_experiment(session, org_id=org_id, name="Terminal failed")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.FAILED)

        for target in ExperimentStatus:
            with pytest.raises(StateTransitionError):
                await transition_experiment(session, exp.id, target)

    @pytest.mark.asyncio
    async def test_cancelled_to_anything(self, session, org_id):
        """CANCELLED is terminal — no transitions allowed."""
        exp = await create_experiment(session, org_id=org_id, name="Terminal cancelled")
        await transition_experiment(session, exp.id, ExperimentStatus.CANCELLED)

        for target in ExperimentStatus:
            with pytest.raises(StateTransitionError):
                await transition_experiment(session, exp.id, target)

    @pytest.mark.asyncio
    async def test_same_state_transition(self, session, org_id):
        """Transitioning to the same state is invalid."""
        exp = await create_experiment(session, org_id=org_id, name="Same state")
        with pytest.raises(StateTransitionError):
            await transition_experiment(session, exp.id, ExperimentStatus.DRAFT)


# ---------------------------------------------------------------------------
# ERROR DETAIL tests — agent-friendly suggestions
# ---------------------------------------------------------------------------


class TestErrorSuggestions:
    @pytest.mark.asyncio
    async def test_not_found_has_suggestion(self, session):
        """NotFoundError includes a suggestion for agents."""
        with pytest.raises(NotFoundError) as exc_info:
            await get_experiment(session, str(uuid.uuid4()))
        err = exc_info.value
        assert err.suggestion is not None
        assert err.code == "not_found"
        assert err.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_transition_suggestion_lists_valid(self, session, org_id):
        """StateTransitionError suggestion lists valid transitions."""
        exp = await create_experiment(session, org_id=org_id, name="Test suggestion")
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        suggestion = exc_info.value.suggestion
        # planned can go to running or cancelled
        assert "running" in suggestion.lower()
        assert "cancelled" in suggestion.lower()

    @pytest.mark.asyncio
    async def test_terminal_suggestion_says_create_new(self, session, org_id):
        """Terminal state suggestion tells agent to create a new experiment."""
        exp = await create_experiment(session, org_id=org_id, name="Done")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert "create a new experiment" in exc_info.value.suggestion.lower()

    @pytest.mark.asyncio
    async def test_validation_error_on_terminal_update(self, session, org_id):
        """ValidationError on terminal update includes suggestion."""
        exp = await create_experiment(session, org_id=org_id, name="Terminal")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        with pytest.raises(ValidationError) as exc_info:
            await update_experiment(session, exp.id, name="Nope")
        err = exc_info.value
        assert err.suggestion is not None
        assert err.status_code == 422


# ---------------------------------------------------------------------------
# TRANSITION TIMESTAMPS tests
# ---------------------------------------------------------------------------


class TestTransitionTimestamps:
    @pytest.mark.asyncio
    async def test_started_at_only_set_on_running(self, session, org_id):
        """started_at is set when transitioning to RUNNING, not before."""
        exp = await create_experiment(session, org_id=org_id, name="Timing test")
        assert exp.started_at is None

        running = await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert running.started_at is not None
        started = running.started_at

        completed = await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        # started_at should not change when completing
        assert completed.started_at == started

    @pytest.mark.asyncio
    async def test_completed_at_set_on_completed(self, session, org_id):
        """completed_at is set when transitioning to COMPLETED."""
        exp = await create_experiment(session, org_id=org_id, name="Complete timing")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        completed = await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        assert completed.completed_at is not None

    @pytest.mark.asyncio
    async def test_completed_at_set_on_failed(self, session, org_id):
        """completed_at is set when transitioning to FAILED."""
        exp = await create_experiment(session, org_id=org_id, name="Fail timing")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        failed = await transition_experiment(session, exp.id, ExperimentStatus.FAILED)
        assert failed.completed_at is not None

    @pytest.mark.asyncio
    async def test_completed_at_set_on_cancelled(self, session, org_id):
        """completed_at is set when transitioning to CANCELLED."""
        exp = await create_experiment(session, org_id=org_id, name="Cancel timing")
        cancelled = await transition_experiment(session, exp.id, ExperimentStatus.CANCELLED)
        assert cancelled.completed_at is not None


# ---------------------------------------------------------------------------
# STATE MACHINE COMPLETENESS test
# ---------------------------------------------------------------------------


class TestStateMachineCompleteness:
    def test_all_states_in_transitions_map(self):
        """Every ExperimentStatus has an entry in EXPERIMENT_TRANSITIONS."""
        for status in ExperimentStatus:
            assert status in EXPERIMENT_TRANSITIONS

    def test_terminal_states_have_no_transitions(self):
        """Terminal states (completed, failed, cancelled) have empty transition sets."""
        for terminal in (
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
        ):
            assert EXPERIMENT_TRANSITIONS[terminal] == set()

    def test_planned_transitions(self):
        """DRAFT can go to RUNNING or CANCELLED."""
        assert EXPERIMENT_TRANSITIONS[ExperimentStatus.DRAFT] == {
            ExperimentStatus.RUNNING,
            ExperimentStatus.CANCELLED,
        }

    def test_running_transitions(self):
        """RUNNING can go to COMPLETED or FAILED."""
        assert EXPERIMENT_TRANSITIONS[ExperimentStatus.RUNNING] == {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
        }

    @pytest.mark.asyncio
    async def test_model_can_transition_to_agrees(self, session, org_id):
        """Experiment.can_transition_to matches EXPERIMENT_TRANSITIONS."""
        exp = await create_experiment(session, org_id=org_id, name="Consistency check")
        for target in ExperimentStatus:
            expected = target in EXPERIMENT_TRANSITIONS[ExperimentStatus.DRAFT]
            assert exp.can_transition_to(target) == expected

    @pytest.mark.asyncio
    async def test_model_valid_transitions_property(self, session, org_id):
        """Experiment.valid_transitions returns the correct set."""
        exp = await create_experiment(session, org_id=org_id, name="Valid set check")
        assert exp.valid_transitions == {ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED}

    @pytest.mark.asyncio
    async def test_model_is_terminal_property(self, session, org_id):
        """is_terminal is True only for terminal states."""
        exp = await create_experiment(session, org_id=org_id, name="Terminal check")
        assert not exp.is_terminal

        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        refreshed = await get_experiment(session, exp.id)
        assert not refreshed.is_terminal

        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        refreshed = await get_experiment(session, exp.id)
        assert refreshed.is_terminal
