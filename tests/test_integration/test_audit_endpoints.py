"""Integration tests for audit log endpoints.

Tests creation, listing, and chain verification of audit events
through the HTTP API with envelope format validation.
"""

from __future__ import annotations

import pytest


class TestAuditEventCreation:
    """POST /api/v1/audit/events"""

    @pytest.mark.asyncio
    async def test_create_audit_event_returns_201_envelope(self, client):
        resp = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "experiment",
                "resource_id": "test-exp-001",
                "actor_id": "test-user-001",
                "summary": "Created experiment 'Kinetics Study'",
            },
        )
        assert resp.status_code == 201
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []

        event = body["data"]
        assert event["action"] == "CREATE"
        assert event["resource_type"] == "experiment"
        assert event["entry_hash"] is not None
        assert event["sequence"] >= 1
        assert event["previous_hash"] is None  # first event has no predecessor

    @pytest.mark.asyncio
    async def test_second_event_has_previous_hash(self, client):
        """Second audit event should chain to the first."""
        await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "experiment",
                "summary": "First event",
            },
        )
        resp2 = await client.post(
            "/api/v1/audit/events",
            json={
                "action": "UPDATE",
                "resource_type": "experiment",
                "summary": "Second event",
            },
        )
        assert resp2.status_code == 201
        body = resp2.json()
        assert body["data"]["previous_hash"] is not None
        assert body["data"]["sequence"] > 1


class TestAuditEventQuery:
    """GET /api/v1/audit/events"""

    @pytest.mark.asyncio
    async def test_list_audit_events_returns_envelope(self, client):
        # Create some events
        for action in ["CREATE", "UPDATE", "DELETE"]:
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": action,
                    "resource_type": "file",
                    "summary": f"{action} action test",
                },
            )

        resp = await client.get("/api/v1/audit/events")
        assert resp.status_code == 200
        body = resp.json()

        assert body["data"] is not None
        assert body["errors"] == []
        assert body["meta"]["page"] == 1
        assert body["meta"]["total"] is not None

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self, client):
        await client.post(
            "/api/v1/audit/events",
            json={
                "action": "UPLOAD",
                "resource_type": "unique_resource_type",
                "summary": "Unique event",
            },
        )

        resp = await client.get(
            "/api/v1/audit/events",
            params={
                "resource_type": "unique_resource_type",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) >= 1
        for event in body["data"]:
            assert event["resource_type"] == "unique_resource_type"


class TestAuditChainVerification:
    """GET /api/v1/audit/verify"""

    @pytest.mark.asyncio
    async def test_verify_empty_chain_is_valid(self, client):
        """Empty audit log should still return valid=True."""
        resp = await client.get("/api/v1/audit/verify")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid"] is True
        assert body["data"]["total_entries"] >= 0

    @pytest.mark.asyncio
    async def test_verify_chain_after_events(self, client):
        """Chain with multiple events should verify successfully."""
        for i in range(3):
            await client.post(
                "/api/v1/audit/events",
                json={
                    "action": "CREATE",
                    "resource_type": "test",
                    "summary": f"Chain test event {i}",
                },
            )

        resp = await client.get("/api/v1/audit/verify")
        assert resp.status_code == 200
        body = resp.json()

        assert body["data"]["valid"] is True
        assert body["data"]["total_entries"] >= 3
        assert body["data"]["invalid_entries"] == 0
        assert body["data"]["suggestion"] is None

    @pytest.mark.asyncio
    async def test_verify_with_verbose_returns_details(self, client):
        await client.post(
            "/api/v1/audit/events",
            json={
                "action": "CREATE",
                "resource_type": "verbose_test",
                "summary": "Verbose detail event",
            },
        )

        resp = await client.get("/api/v1/audit/verify", params={"verbose": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid"] is True
        # Verbose mode should include details for all entries
        if body["data"]["total_entries"] > 0:
            assert len(body["data"]["details"]) > 0
