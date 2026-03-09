"""Integration tests for experiment CRUD endpoints and state machine.

Tests the full experiment lifecycle through HTTP endpoints with
proper envelope format validation.
"""

from __future__ import annotations

import pytest


class TestExperimentCreate:
    """POST /api/v1/experiments"""

    @pytest.mark.asyncio
    async def test_create_experiment_returns_201_envelope(self, client):
        resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Enzyme Activity Assay",
                "description": "Measure enzyme kinetics",
                "hypothesis": "Km will be approximately 5mM",
            },
        )
        assert resp.status_code == 201
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []
        assert "meta" in body

        exp = body["data"]
        assert exp["name"] == "Enzyme Activity Assay"
        assert exp["status"] == "draft"
        assert exp["is_terminal"] is False
        # Agent-native: valid_transitions should include running and cancelled
        assert "running" in exp["valid_transitions"]
        assert "cancelled" in exp["valid_transitions"]

    @pytest.mark.asyncio
    async def test_create_experiment_blank_name_returns_422(self, client):
        resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "   ",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0

    @pytest.mark.asyncio
    async def test_create_experiment_with_parameters(self, client):
        resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Dose Response Curve",
                "parameters": {"concentrations": [0.1, 1, 10, 100], "unit": "uM"},
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["parameters"] == {
            "concentrations": [0.1, 1, 10, 100],
            "unit": "uM",
        }


class TestExperimentRead:
    """GET /api/v1/experiments and GET /api/v1/experiments/{id}"""

    @pytest.mark.asyncio
    async def test_list_experiments_returns_envelope_with_pagination(self, client):
        # Create a few experiments
        for i in range(3):
            await client.post("/api/v1/experiments", json={"name": f"Exp {i}"})

        resp = await client.get("/api/v1/experiments")
        assert resp.status_code == 200
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []
        assert body["meta"]["page"] == 1
        assert body["meta"]["page_size"] is not None
        assert body["meta"]["total"] is not None
        assert body["meta"]["total"] >= 3

        # Each experiment in the list should have agent-native fields
        for exp in body["data"]["items"]:
            assert "valid_transitions" in exp
            assert "is_terminal" in exp

    @pytest.mark.asyncio
    async def test_get_experiment_by_id(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Specific Experiment",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/experiments/{exp_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == exp_id
        assert body["data"]["name"] == "Specific Experiment"

    @pytest.mark.asyncio
    async def test_get_nonexistent_experiment_returns_404(self, client):
        resp = await client.get("/api/v1/experiments/does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert body["errors"][0]["code"] == "not_found"
        assert body["errors"][0]["suggestion"] is not None


class TestExperimentUpdate:
    """PATCH /api/v1/experiments/{id}"""

    @pytest.mark.asyncio
    async def test_update_experiment_name(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Original Name",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/experiments/{exp_id}",
            json={
                "name": "Updated Name",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_terminal_experiment_returns_422(self, client):
        """Cannot update a completed experiment."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Terminal Test",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        # Transition: draft -> running -> completed
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "running",
                "reason": "Starting",
            },
        )
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "completed",
                "reason": "Done",
                "success": True,
            },
        )

        resp = await client.patch(
            f"/api/v1/experiments/{exp_id}",
            json={
                "name": "Should Fail",
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["errors"][0]["suggestion"] is not None


class TestExperimentStateTransitions:
    """POST /api/v1/experiments/{id}/transition"""

    @pytest.mark.asyncio
    async def test_valid_transition_draft_to_running(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Transition Test",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "running",
                "reason": "Starting experiment",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "running"
        assert body["data"]["started_at"] is not None
        # After running, valid transitions should be completed and failed
        assert "completed" in body["data"]["valid_transitions"]
        assert "failed" in body["data"]["valid_transitions"]

    @pytest.mark.asyncio
    async def test_full_lifecycle_draft_running_completed(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Full Lifecycle",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        # draft -> running
        resp1 = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "running",
                "reason": "Begin experiment",
            },
        )
        assert resp1.status_code == 200
        assert resp1.json()["data"]["status"] == "running"

        # running -> completed
        resp2 = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "completed",
                "reason": "Experiment finished",
                "outcome_summary": "All assays passed",
                "success": True,
                "outcome": {"yield": 0.95, "purity": 99.2},
            },
        )
        assert resp2.status_code == 200
        data = resp2.json()["data"]
        assert data["status"] == "completed"
        assert data["is_terminal"] is True
        assert data["valid_transitions"] == []
        assert data["success"] is True
        assert data["outcome"]["yield"] == 0.95

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_409_with_suggestion(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Invalid Transition",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        # draft -> failed (not allowed)
        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "failed",
                "reason": "This should not work",
            },
        )
        assert resp.status_code == 409
        body = resp.json()
        error = body["errors"][0]
        assert error["code"] == "invalid_state_transition"
        assert error["suggestion"] is not None
        # Suggestion should mention the valid options
        assert "running" in error["suggestion"] or "cancelled" in error["suggestion"]

    @pytest.mark.asyncio
    async def test_transition_from_terminal_returns_409(self, client):
        """Cannot transition from a terminal state."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Terminal Transition",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        # draft -> cancelled
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "cancelled",
                "reason": "Cancel it",
            },
        )

        # cancelled -> running (not allowed)
        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "running",
                "reason": "Try to restart",
            },
        )
        assert resp.status_code == 409
        body = resp.json()
        assert "terminal" in body["errors"][0]["suggestion"].lower()


class TestExperimentDelete:
    """DELETE /api/v1/experiments/{id}"""

    @pytest.mark.asyncio
    async def test_soft_delete_experiment(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Delete Me",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/experiments/{exp_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["deleted_at"] is not None

    @pytest.mark.asyncio
    async def test_deleted_experiment_not_in_list(self, client):
        create_resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Vanishing Experiment",
            },
        )
        exp_id = create_resp.json()["data"]["id"]

        await client.delete(f"/api/v1/experiments/{exp_id}")

        # Should not be findable via GET
        get_resp = await client.get(f"/api/v1/experiments/{exp_id}")
        assert get_resp.status_code == 404
