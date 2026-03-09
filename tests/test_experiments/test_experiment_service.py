"""Tests for Experiment service layer — CRUD and state machine enforcement.

Covers:
- Create, read, list, update, soft-delete
- All valid state transitions (planned->running, planned->cancelled,
  running->completed, running->failed)
- Invalid transition rejection with suggestion field
- Terminal state enforcement (no transitions from completed/failed/cancelled)
- Edge cases: double delete, update terminal, not found, etc.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError, StateTransitionError, ValidationError
from app.models.experiment import ExperimentStatus, EXPERIMENT_TRANSITIONS
from app.services.experiment import (
    create_experiment,
    get_experiment,
    list_experiments,
    soft_delete_experiment,
    transition_experiment,
    update_experiment,
)


# ---------------------------------------------------------------------------
# CRUD: Create
# ---------------------------------------------------------------------------


class TestCreateExperiment:
    """Tests for experiment creation."""

    @pytest.mark.asyncio
    async def test_create_minimal(self, session: AsyncSession, organization):
        """Create with only required fields."""
        exp = await create_experiment(
            session,
            org_id=organization.id,
            name="Minimal Experiment",
        )
        await session.commit()

        assert exp.id is not None
        assert exp.name == "Minimal Experiment"
        assert exp.org_id == organization.id
        assert exp.status == ExperimentStatus.DRAFT.value
        assert exp.description is None
        assert exp.hypothesis is None
        assert exp.started_at is None
        assert exp.completed_at is None

    @pytest.mark.asyncio
    async def test_create_full(self, session: AsyncSession, organization):
        """Create with all optional fields."""
        exp = await create_experiment(
            session,
            org_id=organization.id,
            name="Full Experiment",
            description="Detailed description",
            hypothesis="If X then Y",
            intent="Measure Z",
            project_id="proj-123",
            campaign_id="camp-456",
            parameters_json='{"temp": 37}',
            protocol="Standard protocol v1",
            created_by="user-789",
        )
        await session.commit()

        assert exp.name == "Full Experiment"
        assert exp.description == "Detailed description"
        assert exp.hypothesis == "If X then Y"
        assert exp.intent == "Measure Z"
        assert exp.project_id == "proj-123"
        assert exp.campaign_id == "camp-456"
        assert exp.parameters_json == '{"temp": 37}'
        assert exp.protocol == "Standard protocol v1"
        assert exp.created_by == "user-789"
        assert exp.status == ExperimentStatus.DRAFT.value

    @pytest.mark.asyncio
    async def test_create_always_starts_planned(self, session: AsyncSession, organization):
        """New experiments always start in PLANNED state regardless of input."""
        exp = await create_experiment(
            session,
            org_id=organization.id,
            name="Should Be Planned",
        )
        assert exp.status == ExperimentStatus.DRAFT.value

    @pytest.mark.asyncio
    async def test_create_generates_uuid(self, session: AsyncSession, organization):
        """Each experiment gets a unique UUID."""
        exp1 = await create_experiment(session, org_id=organization.id, name="Exp 1")
        exp2 = await create_experiment(session, org_id=organization.id, name="Exp 2")
        assert exp1.id != exp2.id
        # Validate UUID format
        uuid.UUID(exp1.id)
        uuid.UUID(exp2.id)


# ---------------------------------------------------------------------------
# CRUD: Read (Get)
# ---------------------------------------------------------------------------


class TestGetExperiment:
    """Tests for getting a single experiment."""

    @pytest.mark.asyncio
    async def test_get_existing(self, session: AsyncSession, draft_experiment):
        """Get an experiment by its ID."""
        exp = await get_experiment(session, draft_experiment.id)
        assert exp.id == draft_experiment.id
        assert exp.name == draft_experiment.name

    @pytest.mark.asyncio
    async def test_get_not_found(self, session: AsyncSession):
        """Getting a non-existent experiment raises NotFoundError."""
        fake_id = str(uuid.uuid4())
        with pytest.raises(NotFoundError) as exc_info:
            await get_experiment(session, fake_id)
        assert fake_id in exc_info.value.message
        assert exc_info.value.suggestion is not None

    @pytest.mark.asyncio
    async def test_get_soft_deleted_excluded(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Soft-deleted experiments are excluded by default."""
        await soft_delete_experiment(session, draft_experiment.id)
        await session.commit()

        with pytest.raises(NotFoundError):
            await get_experiment(session, draft_experiment.id)

    @pytest.mark.asyncio
    async def test_get_soft_deleted_included(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Soft-deleted experiments can be fetched with include_deleted=True."""
        await soft_delete_experiment(session, draft_experiment.id)
        await session.commit()

        exp = await get_experiment(
            session,
            draft_experiment.id,
            include_deleted=True,
        )
        assert exp.id == draft_experiment.id
        assert exp.deleted_at is not None


# ---------------------------------------------------------------------------
# CRUD: List
# ---------------------------------------------------------------------------


class TestListExperiments:
    """Tests for listing experiments."""

    @pytest.mark.asyncio
    async def test_list_empty(self, session: AsyncSession):
        """Empty list when no experiments exist."""
        experiments, total = await list_experiments(session)
        assert experiments == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_all(self, session: AsyncSession, organization):
        """List returns all non-deleted experiments."""
        for i in range(3):
            await create_experiment(
                session,
                org_id=organization.id,
                name=f"Exp {i}",
            )
        await session.commit()

        experiments, total = await list_experiments(session)
        assert total == 3
        assert len(experiments) == 3

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, session: AsyncSession, organization):
        """Filter experiments by status."""
        exp = await create_experiment(
            session,
            org_id=organization.id,
            name="Planned",
        )
        await session.flush()
        await transition_experiment(
            session,
            exp.id,
            ExperimentStatus.RUNNING,
        )
        await create_experiment(
            session,
            org_id=organization.id,
            name="Still Planned",
        )
        await session.commit()

        running, total = await list_experiments(
            session,
            status=ExperimentStatus.RUNNING,
        )
        assert total == 1
        assert running[0].status == ExperimentStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_list_pagination(self, session: AsyncSession, organization):
        """Pagination works correctly."""
        for i in range(5):
            await create_experiment(
                session,
                org_id=organization.id,
                name=f"Exp {i}",
            )
        await session.commit()

        page1, total = await list_experiments(session, page=1, page_size=2)
        assert total == 5
        assert len(page1) == 2

        page3, _ = await list_experiments(session, page=3, page_size=2)
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_list_excludes_soft_deleted(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Soft-deleted experiments are excluded from listing."""
        await soft_delete_experiment(session, draft_experiment.id)
        await session.commit()

        experiments, total = await list_experiments(session)
        assert total == 0


# ---------------------------------------------------------------------------
# CRUD: Update
# ---------------------------------------------------------------------------


class TestUpdateExperiment:
    """Tests for updating experiment fields."""

    @pytest.mark.asyncio
    async def test_update_name(self, session: AsyncSession, draft_experiment):
        """Update the experiment name."""
        exp = await update_experiment(
            session,
            draft_experiment.id,
            name="Updated Name",
        )
        assert exp.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_multiple_fields(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Update multiple fields at once."""
        exp = await update_experiment(
            session,
            draft_experiment.id,
            description="New description",
            hypothesis="New hypothesis",
            protocol="New protocol",
        )
        assert exp.description == "New description"
        assert exp.hypothesis == "New hypothesis"
        assert exp.protocol == "New protocol"

    @pytest.mark.asyncio
    async def test_update_not_found(self, session: AsyncSession):
        """Updating a non-existent experiment raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await update_experiment(
                session,
                str(uuid.uuid4()),
                name="Nope",
            )

    @pytest.mark.asyncio
    async def test_update_terminal_state_rejected(
        self,
        session: AsyncSession,
        completed_experiment,
    ):
        """Cannot update experiments in terminal states."""
        with pytest.raises(ValidationError) as exc_info:
            await update_experiment(
                session,
                completed_experiment.id,
                name="Can't Change",
            )
        assert (
            "terminal" in exc_info.value.suggestion.lower()
            or "terminal" in exc_info.value.message.lower()
        )


# ---------------------------------------------------------------------------
# CRUD: Soft Delete
# ---------------------------------------------------------------------------


class TestSoftDeleteExperiment:
    """Tests for soft-deleting experiments."""

    @pytest.mark.asyncio
    async def test_soft_delete(self, session: AsyncSession, draft_experiment):
        """Soft delete sets deleted_at timestamp."""
        exp = await soft_delete_experiment(session, draft_experiment.id)
        assert exp.deleted_at is not None
        assert exp.is_deleted is True

    @pytest.mark.asyncio
    async def test_double_delete_rejected(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Cannot soft-delete an already deleted experiment."""
        await soft_delete_experiment(session, draft_experiment.id)
        await session.commit()

        with pytest.raises(ValidationError) as exc_info:
            await soft_delete_experiment(session, draft_experiment.id)
        assert "already deleted" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, session: AsyncSession):
        """Deleting a non-existent experiment raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await soft_delete_experiment(session, str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# State Machine: Valid Transitions
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """Tests for all valid state machine transitions."""

    @pytest.mark.asyncio
    async def test_planned_to_running(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """PLANNED -> RUNNING is valid and sets started_at."""
        exp = await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.RUNNING,
        )
        assert exp.status == ExperimentStatus.RUNNING.value
        assert exp.started_at is not None
        assert exp.completed_at is None

    @pytest.mark.asyncio
    async def test_planned_to_cancelled(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """PLANNED -> CANCELLED is valid and sets completed_at."""
        exp = await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.CANCELLED,
        )
        assert exp.status == ExperimentStatus.CANCELLED.value
        assert exp.completed_at is not None

    @pytest.mark.asyncio
    async def test_running_to_completed(
        self,
        session: AsyncSession,
        running_experiment,
    ):
        """RUNNING -> COMPLETED is valid and sets completed_at."""
        exp = await transition_experiment(
            session,
            running_experiment.id,
            ExperimentStatus.COMPLETED,
            outcome_summary="Great results",
            success=True,
        )
        assert exp.status == ExperimentStatus.COMPLETED.value
        assert exp.completed_at is not None
        assert exp.outcome_summary == "Great results"
        assert exp.success is True

    @pytest.mark.asyncio
    async def test_running_to_failed(
        self,
        session: AsyncSession,
        running_experiment,
    ):
        """RUNNING -> FAILED is valid and sets completed_at."""
        exp = await transition_experiment(
            session,
            running_experiment.id,
            ExperimentStatus.FAILED,
            outcome_summary="Contamination detected",
            success=False,
        )
        assert exp.status == ExperimentStatus.FAILED.value
        assert exp.completed_at is not None
        assert exp.outcome_summary == "Contamination detected"
        assert exp.success is False

    @pytest.mark.asyncio
    async def test_full_lifecycle_planned_running_completed(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Full happy path: PLANNED -> RUNNING -> COMPLETED."""
        exp = await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.RUNNING,
        )
        assert exp.status == ExperimentStatus.RUNNING.value

        exp = await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.COMPLETED,
            success=True,
        )
        assert exp.status == ExperimentStatus.COMPLETED.value
        assert exp.started_at is not None
        assert exp.completed_at is not None

    @pytest.mark.asyncio
    async def test_full_lifecycle_planned_running_failed(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Full failure path: PLANNED -> RUNNING -> FAILED."""
        await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.RUNNING,
        )
        exp = await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.FAILED,
        )
        assert exp.status == ExperimentStatus.FAILED.value
        assert exp.started_at is not None
        assert exp.completed_at is not None


# ---------------------------------------------------------------------------
# State Machine: Invalid Transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    """Tests for rejected state machine transitions with suggestions."""

    @pytest.mark.asyncio
    async def test_planned_to_completed_rejected(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """PLANNED -> COMPLETED is not valid (must go through RUNNING)."""
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(
                session,
                draft_experiment.id,
                ExperimentStatus.COMPLETED,
            )
        assert "draft" in exc_info.value.message.lower()
        assert "completed" in exc_info.value.message.lower()
        assert exc_info.value.suggestion is not None
        assert (
            "running" in exc_info.value.suggestion.lower()
            or "cancelled" in exc_info.value.suggestion.lower()
        )

    @pytest.mark.asyncio
    async def test_planned_to_failed_rejected(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """PLANNED -> FAILED is not valid."""
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(
                session,
                draft_experiment.id,
                ExperimentStatus.FAILED,
            )
        assert exc_info.value.suggestion is not None

    @pytest.mark.asyncio
    async def test_running_to_planned_rejected(
        self,
        session: AsyncSession,
        running_experiment,
    ):
        """RUNNING -> PLANNED is not valid (no going back)."""
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(
                session,
                running_experiment.id,
                ExperimentStatus.DRAFT,
            )
        assert exc_info.value.suggestion is not None

    @pytest.mark.asyncio
    async def test_running_to_cancelled_rejected(
        self,
        session: AsyncSession,
        running_experiment,
    ):
        """RUNNING -> CANCELLED is not valid."""
        with pytest.raises(StateTransitionError):
            await transition_experiment(
                session,
                running_experiment.id,
                ExperimentStatus.CANCELLED,
            )

    @pytest.mark.asyncio
    async def test_same_state_transition_rejected(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Transitioning to the same state is not valid."""
        with pytest.raises(StateTransitionError):
            await transition_experiment(
                session,
                draft_experiment.id,
                ExperimentStatus.DRAFT,
            )

    @pytest.mark.asyncio
    async def test_transition_not_found(self, session: AsyncSession):
        """Transitioning a non-existent experiment raises NotFoundError."""
        with pytest.raises(NotFoundError):
            await transition_experiment(
                session,
                str(uuid.uuid4()),
                ExperimentStatus.RUNNING,
            )


# ---------------------------------------------------------------------------
# State Machine: Terminal State Enforcement
# ---------------------------------------------------------------------------


class TestTerminalStates:
    """Tests that terminal states (completed, failed, cancelled) cannot transition."""

    @pytest.mark.asyncio
    async def test_completed_is_terminal(
        self,
        session: AsyncSession,
        completed_experiment,
    ):
        """COMPLETED experiment cannot transition to any state."""
        for target in ExperimentStatus:
            with pytest.raises(StateTransitionError) as exc_info:
                await transition_experiment(
                    session,
                    completed_experiment.id,
                    target,
                )
            assert "terminal" in exc_info.value.suggestion.lower()

    @pytest.mark.asyncio
    async def test_failed_is_terminal(
        self,
        session: AsyncSession,
        running_experiment,
    ):
        """FAILED experiment cannot transition to any state."""
        await transition_experiment(
            session,
            running_experiment.id,
            ExperimentStatus.FAILED,
        )
        await session.commit()

        for target in ExperimentStatus:
            with pytest.raises(StateTransitionError):
                await transition_experiment(
                    session,
                    running_experiment.id,
                    target,
                )

    @pytest.mark.asyncio
    async def test_cancelled_is_terminal(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """CANCELLED experiment cannot transition to any state."""
        await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.CANCELLED,
        )
        await session.commit()

        for target in ExperimentStatus:
            with pytest.raises(StateTransitionError):
                await transition_experiment(
                    session,
                    draft_experiment.id,
                    target,
                )

    @pytest.mark.asyncio
    async def test_terminal_suggestion_mentions_new_experiment(
        self,
        session: AsyncSession,
        completed_experiment,
    ):
        """Suggestion for terminal state transitions says to create a new experiment."""
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(
                session,
                completed_experiment.id,
                ExperimentStatus.RUNNING,
            )
        assert "new experiment" in exc_info.value.suggestion.lower()


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_transition_preserves_other_fields(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """State transitions should not clear other fields."""
        original_name = draft_experiment.name
        original_hypothesis = draft_experiment.hypothesis

        exp = await transition_experiment(
            session,
            draft_experiment.id,
            ExperimentStatus.RUNNING,
        )
        assert exp.name == original_name
        assert exp.hypothesis == original_hypothesis

    @pytest.mark.asyncio
    async def test_transition_with_outcome_data(
        self,
        session: AsyncSession,
        running_experiment,
    ):
        """Transition to completed with outcome data."""
        exp = await transition_experiment(
            session,
            running_experiment.id,
            ExperimentStatus.COMPLETED,
            outcome_summary="Binding affinity measured at 42nM",
            outcome_json='{"kd": 42, "unit": "nM"}',
            success=True,
        )
        assert exp.outcome_summary == "Binding affinity measured at 42nM"
        assert exp.outcome_json == '{"kd": 42, "unit": "nM"}'
        assert exp.success is True

    @pytest.mark.asyncio
    async def test_model_can_transition_to_method(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Test the ORM model's can_transition_to helper."""
        assert draft_experiment.can_transition_to(ExperimentStatus.RUNNING) is True
        assert draft_experiment.can_transition_to(ExperimentStatus.CANCELLED) is True
        assert draft_experiment.can_transition_to(ExperimentStatus.COMPLETED) is False
        assert draft_experiment.can_transition_to(ExperimentStatus.FAILED) is False

    @pytest.mark.asyncio
    async def test_model_valid_transitions_property(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Test the ORM model's valid_transitions property."""
        valid = draft_experiment.valid_transitions
        assert ExperimentStatus.RUNNING in valid
        assert ExperimentStatus.CANCELLED in valid
        assert len(valid) == 2

    @pytest.mark.asyncio
    async def test_model_is_terminal_property(
        self,
        session: AsyncSession,
        draft_experiment,
        running_experiment,
        completed_experiment,
    ):
        """Test is_terminal on different states."""
        assert draft_experiment.is_terminal is False
        assert running_experiment.is_terminal is False
        assert completed_experiment.is_terminal is True

    @pytest.mark.asyncio
    async def test_transitions_dict_completeness(self):
        """Every ExperimentStatus has an entry in EXPERIMENT_TRANSITIONS."""
        for status in ExperimentStatus:
            assert status in EXPERIMENT_TRANSITIONS

    @pytest.mark.asyncio
    async def test_terminal_states_have_no_transitions(self):
        """Terminal states map to empty sets in EXPERIMENT_TRANSITIONS."""
        for status in (
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
        ):
            assert EXPERIMENT_TRANSITIONS[status] == set()

    @pytest.mark.asyncio
    async def test_soft_deleted_cannot_transition(
        self,
        session: AsyncSession,
        draft_experiment,
    ):
        """Soft-deleted experiments cannot be transitioned."""
        await soft_delete_experiment(session, draft_experiment.id)
        await session.commit()

        with pytest.raises(NotFoundError):
            await transition_experiment(
                session,
                draft_experiment.id,
                ExperimentStatus.RUNNING,
            )

    @pytest.mark.asyncio
    async def test_experiment_repr(self, session: AsyncSession, draft_experiment):
        """Test the __repr__ output."""
        r = repr(draft_experiment)
        assert "Experiment" in r
        assert draft_experiment.name in r
        assert "draft" in r
