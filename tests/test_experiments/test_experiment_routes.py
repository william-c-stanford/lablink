"""Tests for Experiment API routes (router layer).

Covers:
- POST /api/v1/experiments (create)
- GET /api/v1/experiments (list with pagination and filtering)
- GET /api/v1/experiments/{id} (get single)
- PATCH /api/v1/experiments/{id} (update)
- DELETE /api/v1/experiments/{id} (soft-delete)
- POST /api/v1/experiments/{id}/transition (state transitions)
- Error responses for invalid state transitions with suggestion field
- Envelope structure on all responses
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _create_experiment(client: AsyncClient, **overrides) -> dict:
    """Helper to create an experiment and return the response data."""
    payload = {
        "name": "Test Experiment",
        "description": "A test experiment",
        "hypothesis": "It works",
        **overrides,
    }
    resp = await client.post("/api/v1/experiments", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["errors"] == []
    return body["data"]


async def _transition(client: AsyncClient, exp_id: str, target: str, **kwargs) -> dict:
    """Helper to transition an experiment."""
    payload = {"target_status": target, "reason": f"Transition to {target}", **kwargs}
    resp = await client.post(f"/api/v1/experiments/{exp_id}/transition", json=payload)
    return resp


# ---------------------------------------------------------------------------
# POST /experiments — Create
# ---------------------------------------------------------------------------


class TestCreateRoutes:
    @pytest.mark.asyncio
    async def test_create_success(self, client: AsyncClient):
        data = await _create_experiment(client)
        assert data["name"] == "Test Experiment"
        assert data["status"] == "draft"
        assert data["description"] == "A test experiment"
        assert data["hypothesis"] == "It works"
        assert data["id"] is not None
        assert data["is_terminal"] is False

    @pytest.mark.asyncio
    async def test_create_minimal(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "Minimal"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Minimal"
        assert data["status"] == "draft"
        assert data["description"] is None

    @pytest.mark.asyncio
    async def test_create_with_parameters(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/experiments",
            json={
                "name": "With Params",
                "parameters": {"temp": 37, "ph": 7.4},
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["parameters"] == {"temp": 37, "ph": 7.4}

    @pytest.mark.asyncio
    async def test_create_missing_name_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/experiments", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert len(body["errors"]) > 0
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_create_empty_name_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/experiments", json={"name": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_blank_name_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/experiments", json={"name": "   "})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /experiments — List
# ---------------------------------------------------------------------------


class TestListRoutes:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/experiments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["items"] == []
        assert body["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_items(self, client: AsyncClient):
        await _create_experiment(client, name="Exp 1")
        await _create_experiment(client, name="Exp 2")
        resp = await client.get("/api/v1/experiments")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, client: AsyncClient):
        exp = await _create_experiment(client, name="Running Exp")
        await _transition(client, exp["id"], "running")
        await _create_experiment(client, name="Planned Exp")

        resp = await client.get("/api/v1/experiments?status=running")
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_list_pagination(self, client: AsyncClient):
        for i in range(5):
            await _create_experiment(client, name=f"Exp {i}")

        resp = await client.get("/api/v1/experiments?page=1&page_size=2")
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2

        # Meta also has pagination info
        meta = resp.json()["meta"]
        assert meta["total"] == 5
        assert meta["page"] == 1

    @pytest.mark.asyncio
    async def test_list_pagination_page2(self, client: AsyncClient):
        for i in range(5):
            await _create_experiment(client, name=f"Exp {i}")

        resp = await client.get("/api/v1/experiments?page=2&page_size=2")
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 5


# ---------------------------------------------------------------------------
# GET /experiments/{id} — Get single
# ---------------------------------------------------------------------------


class TestGetRoutes:
    @pytest.mark.asyncio
    async def test_get_success(self, client: AsyncClient):
        created = await _create_experiment(client, name="Get Me")
        resp = await client.get(f"/api/v1/experiments/{created['id']}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Get Me"
        assert data["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/experiments/nonexistent-id")
        assert resp.status_code == 404
        body = resp.json()
        assert len(body["errors"]) == 1
        assert body["errors"][0]["code"] == "not_found"
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_get_includes_valid_transitions(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await client.get(f"/api/v1/experiments/{created['id']}")
        data = resp.json()["data"]
        transitions = set(data["valid_transitions"])
        assert "running" in transitions
        assert "cancelled" in transitions

    @pytest.mark.asyncio
    async def test_get_includes_is_terminal(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await client.get(f"/api/v1/experiments/{created['id']}")
        data = resp.json()["data"]
        assert data["is_terminal"] is False


# ---------------------------------------------------------------------------
# PATCH /experiments/{id} — Update
# ---------------------------------------------------------------------------


class TestUpdateRoutes:
    @pytest.mark.asyncio
    async def test_update_name(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await client.patch(
            f"/api/v1/experiments/{created['id']}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await client.patch(
            f"/api/v1/experiments/{created['id']}",
            json={
                "name": "New Name",
                "hypothesis": "New hypothesis",
                "protocol": "Updated protocol",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "New Name"
        assert data["hypothesis"] == "New hypothesis"
        assert data["protocol"] == "Updated protocol"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient):
        resp = await client.patch(
            "/api/v1/experiments/nonexistent",
            json={"name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_terminal_state_rejected(self, client: AsyncClient):
        """Cannot update an experiment in a terminal state."""
        created = await _create_experiment(client)
        await _transition(client, created["id"], "running")
        await _transition(
            client,
            created["id"],
            "completed",
            success=True,
            outcome_summary="Done",
        )
        resp = await client.patch(
            f"/api/v1/experiments/{created['id']}",
            json={"name": "Should Fail"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_update_no_fields_returns_422(self, client: AsyncClient):
        """PATCH with empty body should be rejected."""
        created = await _create_experiment(client)
        resp = await client.patch(
            f"/api/v1/experiments/{created['id']}",
            json={},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /experiments/{id} — Soft delete
# ---------------------------------------------------------------------------


class TestDeleteRoutes:
    @pytest.mark.asyncio
    async def test_soft_delete(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await client.delete(f"/api/v1/experiments/{created['id']}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_soft_deleted_not_in_list(self, client: AsyncClient):
        created = await _create_experiment(client)
        await client.delete(f"/api/v1/experiments/{created['id']}")
        resp = await client.get("/api/v1/experiments")
        data = resp.json()["data"]
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_soft_deleted_not_gettable(self, client: AsyncClient):
        created = await _create_experiment(client)
        await client.delete(f"/api/v1/experiments/{created['id']}")
        resp = await client.get(f"/api/v1/experiments/{created['id']}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_double_delete_returns_error(self, client: AsyncClient):
        created = await _create_experiment(client)
        await client.delete(f"/api/v1/experiments/{created['id']}")
        resp = await client.delete(f"/api/v1/experiments/{created['id']}")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/api/v1/experiments/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /experiments/{id}/transition — State transitions
# ---------------------------------------------------------------------------


class TestTransitionRoutes:
    @pytest.mark.asyncio
    async def test_planned_to_running(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await _transition(client, created["id"], "running")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "running"
        assert data["started_at"] is not None
        assert set(data["valid_transitions"]) == {"completed", "failed"}
        assert data["is_terminal"] is False

    @pytest.mark.asyncio
    async def test_planned_to_cancelled(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await _transition(client, created["id"], "cancelled")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "cancelled"
        assert data["completed_at"] is not None
        assert data["valid_transitions"] == []
        assert data["is_terminal"] is True

    @pytest.mark.asyncio
    async def test_running_to_completed_with_outcome(self, client: AsyncClient):
        created = await _create_experiment(client)
        await _transition(client, created["id"], "running")
        resp = await _transition(
            client,
            created["id"],
            "completed",
            outcome_summary="All measurements within tolerance",
            outcome={"yield": 95.0},
            success=True,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["outcome_summary"] == "All measurements within tolerance"
        assert data["outcome"] == {"yield": 95.0}
        assert data["success"] is True
        assert data["valid_transitions"] == []
        assert data["is_terminal"] is True

    @pytest.mark.asyncio
    async def test_running_to_failed(self, client: AsyncClient):
        created = await _create_experiment(client)
        await _transition(client, created["id"], "running")
        resp = await _transition(
            client,
            created["id"],
            "failed",
            outcome_summary="Contamination detected",
            success=False,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "failed"
        assert data["success"] is False
        assert data["is_terminal"] is True

    @pytest.mark.asyncio
    async def test_invalid_transition_planned_to_completed(self, client: AsyncClient):
        """planned -> completed is not valid — must go through running."""
        created = await _create_experiment(client)
        resp = await client.post(
            f"/api/v1/experiments/{created['id']}/transition",
            json={
                "target_status": "completed",
                "reason": "Skip ahead",
                "success": True,
            },
        )
        assert resp.status_code == 409
        body = resp.json()
        error = body["errors"][0]
        assert error["code"] == "invalid_state_transition"
        assert "draft" in error["message"]
        assert "completed" in error["message"]
        assert error["suggestion"] is not None
        assert "running" in error["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_invalid_transition_planned_to_failed(self, client: AsyncClient):
        """planned -> failed is not valid."""
        created = await _create_experiment(client)
        resp = await client.post(
            f"/api/v1/experiments/{created['id']}/transition",
            json={"target_status": "failed", "reason": "Not ready", "success": False},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_running(self, client: AsyncClient):
        """completed -> running is not valid (terminal state)."""
        created = await _create_experiment(client)
        await _transition(client, created["id"], "running")
        await _transition(client, created["id"], "completed", success=True)
        resp = await client.post(
            f"/api/v1/experiments/{created['id']}/transition",
            json={"target_status": "running", "reason": "Retry"},
        )
        assert resp.status_code == 409
        error = resp.json()["errors"][0]
        assert "terminal" in error["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_invalid_transition_running_to_cancelled(self, client: AsyncClient):
        """running -> cancelled is not valid."""
        created = await _create_experiment(client)
        await _transition(client, created["id"], "running")
        resp = await client.post(
            f"/api/v1/experiments/{created['id']}/transition",
            json={"target_status": "cancelled", "reason": "Cancel it"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_transition_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/experiments/nonexistent/transition",
            json={"target_status": "running", "reason": "Go"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_transition_missing_reason_returns_422(self, client: AsyncClient):
        """Reason is required for audit trail."""
        created = await _create_experiment(client)
        resp = await client.post(
            f"/api/v1/experiments/{created['id']}/transition",
            json={"target_status": "running"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Envelope structure tests
# ---------------------------------------------------------------------------


class TestEnvelopeStructure:
    @pytest.mark.asyncio
    async def test_success_envelope_structure(self, client: AsyncClient):
        created = await _create_experiment(client)
        resp = await client.get(f"/api/v1/experiments/{created['id']}")
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "errors" in body
        assert body["errors"] == []
        assert body["meta"]["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_error_envelope_has_suggestion(self, client: AsyncClient):
        resp = await client.get("/api/v1/experiments/nonexistent")
        body = resp.json()
        assert body["data"] is None
        assert len(body["errors"]) == 1
        assert body["errors"][0]["suggestion"] is not None

    @pytest.mark.asyncio
    async def test_list_envelope_has_pagination_meta(self, client: AsyncClient):
        await _create_experiment(client)
        resp = await client.get("/api/v1/experiments?page=1&page_size=10")
        meta = resp.json()["meta"]
        assert meta["page"] == 1
        assert meta["page_size"] == 10
        assert meta["total"] == 1

    @pytest.mark.asyncio
    async def test_create_envelope_status_201(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/experiments",
            json={"name": "New Exp"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["status"] == "draft"
        assert body["errors"] == []
