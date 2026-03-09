"""Tests for the experiment service: CRUD, soft delete, state transitions.

Uses in-memory SQLite via the session fixture from conftest.py.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError, StateTransitionError, ValidationError
from app.models.experiment import ExperimentStatus
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
# Helper to seed an org (required FK for experiments)
# ---------------------------------------------------------------------------

async def _seed_org(session: AsyncSession, org_id: str = "org-1") -> Organization:
    org = Organization(id=org_id, name="Test Lab", slug=f"test-lab-{org_id}")
    session.add(org)
    await session.flush()
    return org


# ===========================================================================
# CREATE
# ===========================================================================


class TestCreateExperiment:
    async def test_creates_in_draft(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(
            session, org_id="org-1", name="My Experiment",
        )
        assert exp.id is not None
        assert exp.status == ExperimentStatus.DRAFT.value
        assert exp.name == "My Experiment"

    async def test_creates_with_all_fields(self, session: AsyncSession) -> None:
        await _seed_org(session)
        params = json.dumps({"temp": 37})
        exp = await create_experiment(
            session,
            org_id="org-1",
            name="Full Experiment",
            description="Testing everything",
            hypothesis="H1: It works",
            intent="Verify hypothesis",
            project_id="proj-1",
            campaign_id="camp-1",
            parameters_json=params,
            protocol="Step 1: mix. Step 2: heat.",
            created_by="user-1",
        )
        assert exp.description == "Testing everything"
        assert exp.hypothesis == "H1: It works"
        assert json.loads(exp.parameters_json) == {"temp": 37}
        assert exp.created_by == "user-1"

    async def test_creates_multiple_experiments(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp1 = await create_experiment(session, org_id="org-1", name="Exp 1")
        exp2 = await create_experiment(session, org_id="org-1", name="Exp 2")
        assert exp1.id != exp2.id


# ===========================================================================
# READ / GET
# ===========================================================================


class TestGetExperiment:
    async def test_get_by_id(self, session: AsyncSession) -> None:
        await _seed_org(session)
        created = await create_experiment(session, org_id="org-1", name="Find Me")
        found = await get_experiment(session, created.id)
        assert found.id == created.id
        assert found.name == "Find Me"

    async def test_get_nonexistent_raises(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            await get_experiment(session, "nonexistent-id")
        assert "not found" in exc_info.value.message.lower()
        assert exc_info.value.suggestion is not None

    async def test_get_scoped_to_org(self, session: AsyncSession) -> None:
        await _seed_org(session, "org-1")
        await _seed_org(session, "org-2")
        exp = await create_experiment(session, org_id="org-1", name="Org1 Exp")

        # Same org
        found = await get_experiment(session, exp.id, org_id="org-1")
        assert found.id == exp.id

        # Different org
        with pytest.raises(NotFoundError):
            await get_experiment(session, exp.id, org_id="org-2")

    async def test_get_soft_deleted_excluded(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Deleted")
        await soft_delete_experiment(session, exp.id)

        with pytest.raises(NotFoundError):
            await get_experiment(session, exp.id)

    async def test_get_soft_deleted_included(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Deleted")
        await soft_delete_experiment(session, exp.id)

        found = await get_experiment(session, exp.id, include_deleted=True)
        assert found.id == exp.id
        assert found.deleted_at is not None


# ===========================================================================
# LIST
# ===========================================================================


class TestListExperiments:
    async def test_list_empty(self, session: AsyncSession) -> None:
        experiments, total = await list_experiments(session)
        assert experiments == []
        assert total == 0

    async def test_list_returns_all(self, session: AsyncSession) -> None:
        await _seed_org(session)
        for i in range(5):
            await create_experiment(session, org_id="org-1", name=f"Exp {i}")
        experiments, total = await list_experiments(session)
        assert total == 5
        assert len(experiments) == 5

    async def test_list_filter_by_status(self, session: AsyncSession) -> None:
        await _seed_org(session)
        await create_experiment(session, org_id="org-1", name="Draft")
        exp2 = await create_experiment(session, org_id="org-1", name="Running")
        await transition_experiment(session, exp2.id, ExperimentStatus.RUNNING)

        drafts, total = await list_experiments(
            session, status=ExperimentStatus.DRAFT,
        )
        assert total == 1
        assert drafts[0].name == "Draft"

    async def test_list_pagination(self, session: AsyncSession) -> None:
        await _seed_org(session)
        for i in range(10):
            await create_experiment(session, org_id="org-1", name=f"Exp {i}")

        page1, total = await list_experiments(session, page=1, page_size=3)
        assert total == 10
        assert len(page1) == 3

        page2, _ = await list_experiments(session, page=2, page_size=3)
        assert len(page2) == 3

        # Ensure different pages have different items
        page1_ids = {e.id for e in page1}
        page2_ids = {e.id for e in page2}
        assert page1_ids.isdisjoint(page2_ids)

    async def test_list_excludes_soft_deleted(self, session: AsyncSession) -> None:
        await _seed_org(session)
        await create_experiment(session, org_id="org-1", name="Active")
        exp2 = await create_experiment(session, org_id="org-1", name="Deleted")
        await soft_delete_experiment(session, exp2.id)

        experiments, total = await list_experiments(session)
        assert total == 1
        assert experiments[0].name == "Active"

    async def test_list_includes_soft_deleted(self, session: AsyncSession) -> None:
        await _seed_org(session)
        await create_experiment(session, org_id="org-1", name="Active")
        exp2 = await create_experiment(session, org_id="org-1", name="Deleted")
        await soft_delete_experiment(session, exp2.id)

        experiments, total = await list_experiments(session, include_deleted=True)
        assert total == 2

    async def test_list_filter_by_org(self, session: AsyncSession) -> None:
        await _seed_org(session, "org-1")
        await _seed_org(session, "org-2")
        await create_experiment(session, org_id="org-1", name="Org1")
        await create_experiment(session, org_id="org-2", name="Org2")

        results, total = await list_experiments(session, org_id="org-1")
        assert total == 1
        assert results[0].name == "Org1"


# ===========================================================================
# UPDATE
# ===========================================================================


class TestUpdateExperiment:
    async def test_update_name(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Old Name")
        updated = await update_experiment(session, exp.id, name="New Name")
        assert updated.name == "New Name"

    async def test_update_multiple_fields(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        updated = await update_experiment(
            session, exp.id,
            name="Updated",
            description="New description",
            hypothesis="New hypothesis",
        )
        assert updated.name == "Updated"
        assert updated.description == "New description"
        assert updated.hypothesis == "New hypothesis"

    async def test_update_nonexistent_raises(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await update_experiment(session, "nonexistent", name="X")

    async def test_update_terminal_state_raises(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)

        with pytest.raises(ValidationError) as exc_info:
            await update_experiment(session, exp.id, name="Can't change")
        assert "terminal" in exc_info.value.message.lower() or "completed" in exc_info.value.message.lower()
        assert exc_info.value.suggestion is not None

    async def test_update_ignores_non_updatable_fields(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        original_id = exp.id
        await update_experiment(session, exp.id, name="New", id="hacked-id")
        refreshed = await get_experiment(session, original_id)
        assert refreshed.id == original_id  # id not changed


# ===========================================================================
# SOFT DELETE
# ===========================================================================


class TestSoftDeleteExperiment:
    async def test_soft_delete_sets_timestamp(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="To Delete")
        assert exp.deleted_at is None

        deleted = await soft_delete_experiment(session, exp.id)
        assert deleted.deleted_at is not None
        assert deleted.is_deleted is True

    async def test_soft_delete_nonexistent_raises(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await soft_delete_experiment(session, "nonexistent")

    async def test_soft_delete_already_deleted_raises(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Deleted")
        await soft_delete_experiment(session, exp.id)

        with pytest.raises(ValidationError) as exc_info:
            await soft_delete_experiment(session, exp.id)
        assert "already deleted" in exc_info.value.message.lower()

    async def test_soft_delete_preserves_data(self, session: AsyncSession) -> None:
        """Soft delete should NOT erase the record's data."""
        await _seed_org(session)
        exp = await create_experiment(
            session, org_id="org-1", name="Preserved",
            description="Important data",
        )
        await soft_delete_experiment(session, exp.id)

        found = await get_experiment(session, exp.id, include_deleted=True)
        assert found.name == "Preserved"
        assert found.description == "Important data"


# ===========================================================================
# STATE TRANSITIONS
# ===========================================================================


class TestTransitionExperiment:
    async def test_draft_to_running(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        updated = await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert updated.status == ExperimentStatus.RUNNING.value
        assert updated.started_at is not None

    async def test_running_to_completed(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        updated = await transition_experiment(
            session, exp.id, ExperimentStatus.COMPLETED,
            outcome_summary="Success",
            success=True,
        )
        assert updated.status == ExperimentStatus.COMPLETED.value
        assert updated.completed_at is not None
        assert updated.outcome_summary == "Success"
        assert updated.success is True

    async def test_running_to_failed(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        updated = await transition_experiment(
            session, exp.id, ExperimentStatus.FAILED,
            outcome_summary="Equipment malfunction",
            success=False,
        )
        assert updated.status == ExperimentStatus.FAILED.value
        assert updated.completed_at is not None

    async def test_draft_to_cancelled(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        updated = await transition_experiment(session, exp.id, ExperimentStatus.CANCELLED)
        assert updated.status == ExperimentStatus.CANCELLED.value
        assert updated.completed_at is not None

    async def test_invalid_transition_raises(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)
        assert exc_info.value.suggestion is not None
        assert "Valid transitions" in exc_info.value.suggestion

    async def test_terminal_to_any_raises(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        await transition_experiment(session, exp.id, ExperimentStatus.COMPLETED)

        with pytest.raises(StateTransitionError) as exc_info:
            await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert "terminal" in exc_info.value.suggestion.lower()

    async def test_nonexistent_raises(self, session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await transition_experiment(session, "nope", ExperimentStatus.RUNNING)

    async def test_started_at_set_on_running(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        assert exp.started_at is None
        updated = await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert updated.started_at is not None

    async def test_completed_at_not_set_on_running(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        updated = await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        assert updated.completed_at is None

    async def test_outcome_json_stored(self, session: AsyncSession) -> None:
        await _seed_org(session)
        exp = await create_experiment(session, org_id="org-1", name="Exp")
        await transition_experiment(session, exp.id, ExperimentStatus.RUNNING)
        outcome = json.dumps({"yield_pct": 95.2})
        updated = await transition_experiment(
            session, exp.id, ExperimentStatus.COMPLETED,
            outcome_json=outcome,
        )
        assert json.loads(updated.outcome_json) == {"yield_pct": 95.2}
