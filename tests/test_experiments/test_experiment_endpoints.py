"""Tests for Experiment API endpoints.

Validates:
- Envelope structure on all responses
- CRUD endpoints (create, list, get, update, delete)
- State transition endpoint with valid/invalid transitions
- Error responses include suggestion field
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Endpoint: Create Experiment
# ---------------------------------------------------------------------------


class TestCreateEndpoint:
    """POST /api/v1/experiments."""

    @pytest.mark.asyncio
    async def test_create_experiment(self, client: AsyncClient):
        """Create returns 201 with envelope."""
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "My Experiment"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert body["errors"] == []
        assert body["data"]["name"] == "My Experiment"
        assert body["data"]["status"] == "draft"
        assert body["data"]["valid_transitions"] is not None

    @pytest.mark.asyncio
    async def test_create_with_fields(self, client: AsyncClient):
        """Create with all optional fields."""
        resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "Full Experiment",
                "description": "Test description",
                "hypothesis": "If A then B",
                "intent": "Measure C",
                "protocol": "Standard protocol",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["description"] == "Test description"
        assert data["hypothesis"] == "If A then B"

    @pytest.mark.asyncio
    async def test_create_missing_name(self, client: AsyncClient):
        """Create without name returns 422 with suggestion."""
        resp = await client.post(
            "/api/v1/experiments",
            json={},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0
        assert body["errors"][0]["suggestion"] is not None


# ---------------------------------------------------------------------------
# Endpoint: List Experiments
# ---------------------------------------------------------------------------


class TestListEndpoint:
    """GET /api/v1/experiments."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient):
        """Empty list returns envelope with empty data."""
        resp = await client.get("/api/v1/experiments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["items"] == []
        assert body["data"]["total"] == 0
        assert body["errors"] == []

    @pytest.mark.asyncio
    async def test_list_with_experiments(self, client: AsyncClient):
        """List returns created experiments."""
        for i in range(3):
            await client.post(
                "/api/v1/experiments",
                json={"name": f"Exp {i}"},
            )

        resp = await client.get("/api/v1/experiments")
        body = resp.json()
        assert body["data"]["total"] == 3
        assert len(body["data"]["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_pagination(self, client: AsyncClient):
        """Pagination params work correctly."""
        for i in range(5):
            await client.post(
                "/api/v1/experiments",
                json={"name": f"Exp {i}"},
            )

        resp = await client.get(
            "/api/v1/experiments",
            params={"page": 1, "page_size": 2},
        )
        body = resp.json()
        assert len(body["data"]["items"]) == 2
        assert body["data"]["total"] == 5
        assert body["meta"]["page"] == 1
        assert body["meta"]["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, client: AsyncClient):
        """Filter by status works."""
        # Create and transition one to running
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "To Run"},
        )
        exp_id = resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Starting run"},
        )
        # Create another that stays draft
        await client.post(
            "/api/v1/experiments",
            json={"name": "Stay Planned"},
        )

        resp = await client.get(
            "/api/v1/experiments",
            params={"status": "running"},
        )
        body = resp.json()
        assert body["data"]["total"] == 1
        assert body["data"]["items"][0]["status"] == "running"


# ---------------------------------------------------------------------------
# Endpoint: Get Experiment
# ---------------------------------------------------------------------------


class TestGetEndpoint:
    """GET /api/v1/experiments/{id}."""

    @pytest.mark.asyncio
    async def test_get_experiment(self, client: AsyncClient):
        """Get by ID returns correct experiment."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Fetchable"},
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/experiments/{exp_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == exp_id
        assert body["data"]["name"] == "Fetchable"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient):
        """Non-existent ID returns 404 with suggestion."""
        resp = await client.get(f"/api/v1/experiments/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["errors"][0]["code"] == "not_found"
        assert body["errors"][0]["suggestion"] is not None


# ---------------------------------------------------------------------------
# Endpoint: Update Experiment
# ---------------------------------------------------------------------------


class TestUpdateEndpoint:
    """PATCH /api/v1/experiments/{id}."""

    @pytest.mark.asyncio
    async def test_update_fields(self, client: AsyncClient):
        """Partial update works."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Original"},
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/experiments/{exp_id}",
            json={"name": "Updated", "description": "New desc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["name"] == "Updated"
        assert body["data"]["description"] == "New desc"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient):
        """Update non-existent returns 404."""
        resp = await client.patch(
            f"/api/v1/experiments/{uuid.uuid4()}",
            json={"name": "Nope"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint: Delete Experiment
# ---------------------------------------------------------------------------


class TestDeleteEndpoint:
    """DELETE /api/v1/experiments/{id}."""

    @pytest.mark.asyncio
    async def test_soft_delete(self, client: AsyncClient):
        """Soft delete returns 200 and experiment becomes inaccessible."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "To Delete"},
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/experiments/{exp_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == exp_id
        assert body["errors"] == []

        # Verify experiment is no longer accessible
        get_resp = await client.get(f"/api/v1/experiments/{exp_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_experiment_not_listed(self, client: AsyncClient):
        """Deleted experiment doesn't appear in list."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Will Delete"},
        )
        exp_id = create_resp.json()["data"]["id"]
        await client.delete(f"/api/v1/experiments/{exp_id}")

        resp = await client.get("/api/v1/experiments")
        body = resp.json()
        assert body["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_deleted_experiment_not_gettable(self, client: AsyncClient):
        """Deleted experiment returns 404 on GET."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Will Delete"},
        )
        exp_id = create_resp.json()["data"]["id"]
        await client.delete(f"/api/v1/experiments/{exp_id}")

        resp = await client.get(f"/api/v1/experiments/{exp_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint: State Transitions
# ---------------------------------------------------------------------------


class TestTransitionEndpoint:
    """POST /api/v1/experiments/{id}/transition."""

    @pytest.mark.asyncio
    async def test_valid_transition(self, client: AsyncClient):
        """Valid transition returns updated experiment."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Transition Test"},
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Starting experiment"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "running"
        assert body["data"]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_409(self, client: AsyncClient):
        """Invalid transition returns 409 with suggestion."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Bad Transition"},
        )
        exp_id = create_resp.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "completed", "reason": "Trying to skip"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["errors"][0]["code"] == "invalid_state_transition"
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_terminal_state_transition_rejected(self, client: AsyncClient):
        """Terminal state experiments cannot be transitioned."""
        # Create -> run -> complete
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Terminal Test"},
        )
        exp_id = create_resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Starting"},
        )
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "completed", "reason": "Finished", "success": True},
        )

        # Try to transition completed experiment
        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Trying to restart"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert "terminal" in body["errors"][0]["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_transition_with_outcome(self, client: AsyncClient):
        """Transition to completed with outcome data."""
        create_resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Outcome Test"},
        )
        exp_id = create_resp.json()["data"]["id"]
        await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Starting"},
        )

        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={
                "target_status": "completed",
                "reason": "Experiment finished",
                "outcome_summary": "IC50 = 3.2nM",
                "success": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["outcome_summary"] == "IC50 = 3.2nM"
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_full_lifecycle_via_api(self, client: AsyncClient):
        """Full lifecycle via API: create -> run -> complete."""
        # Create
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Lifecycle Test", "hypothesis": "A causes B"},
        )
        assert resp.status_code == 201
        exp_id = resp.json()["data"]["id"]
        assert resp.json()["data"]["status"] == "draft"

        # Start
        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Beginning experiment"},
        )
        assert resp.json()["data"]["status"] == "running"

        # Complete
        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "completed", "reason": "Experiment done", "success": True},
        )
        assert resp.json()["data"]["status"] == "completed"

        # Verify final state
        resp = await client.get(f"/api/v1/experiments/{exp_id}")
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["started_at"] is not None
        assert data["completed_at"] is not None
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_envelope_structure_consistency(self, client: AsyncClient):
        """All experiment endpoints return proper Envelope structure."""
        # POST create
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Envelope Test"},
        )
        body = resp.json()
        assert set(body.keys()) >= {"data", "meta", "errors"}
        assert "timestamp" in body["meta"]
        exp_id = body["data"]["id"]

        # GET list
        resp = await client.get("/api/v1/experiments")
        body = resp.json()
        assert set(body.keys()) >= {"data", "meta", "errors"}

        # GET single
        resp = await client.get(f"/api/v1/experiments/{exp_id}")
        body = resp.json()
        assert set(body.keys()) >= {"data", "meta", "errors"}

        # PATCH update
        resp = await client.patch(
            f"/api/v1/experiments/{exp_id}",
            json={"name": "Updated"},
        )
        body = resp.json()
        assert set(body.keys()) >= {"data", "meta", "errors"}

        # POST transition
        resp = await client.post(
            f"/api/v1/experiments/{exp_id}/transition",
            json={"target_status": "running", "reason": "Starting"},
        )
        body = resp.json()
        assert set(body.keys()) >= {"data", "meta", "errors"}

        # DELETE
        resp = await client.delete(f"/api/v1/experiments/{exp_id}")
        body = resp.json()
        assert set(body.keys()) >= {"data", "meta", "errors"}

    @pytest.mark.asyncio
    async def test_valid_transitions_field_in_response(self, client: AsyncClient):
        """Response includes valid_transitions for agent consumption."""
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Transitions Field"},
        )
        data = resp.json()["data"]
        transitions = data["valid_transitions"]
        assert "running" in transitions
        assert "cancelled" in transitions
        assert len(transitions) == 2
