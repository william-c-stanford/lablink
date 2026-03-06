"""Tests for MCP admin toolset (4 tools).

Covers:
- manage_users: list, activate, deactivate, invalid action, missing user_id
- get_audit_log: empty log, with filters, pagination
- update_settings: list, get, set (existing + new), invalid action, missing key
- get_system_health: returns all subsystem checks, suggestion field present
"""

from __future__ import annotations

import pytest

from app.mcp_server.tools.admin import (
    _mock_audit_entries,
    _mock_settings,
    _mock_users,
    get_audit_log,
    get_system_health,
    manage_users,
    update_settings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_mock_state():
    """Reset mock state between tests."""
    saved_users = dict(_mock_users)
    saved_entries = list(_mock_audit_entries)
    saved_settings = dict(_mock_settings)

    _mock_users.clear()
    _mock_audit_entries.clear()

    yield

    _mock_users.clear()
    _mock_users.update(saved_users)
    _mock_audit_entries.clear()
    _mock_audit_entries.extend(saved_entries)
    _mock_settings.clear()
    _mock_settings.update(saved_settings)


def _add_mock_user(user_id: str, **kwargs) -> dict:
    """Helper to add a mock user."""
    user = {
        "user_id": user_id,
        "email": kwargs.get("email", f"{user_id}@example.com"),
        "display_name": kwargs.get("display_name", f"User {user_id}"),
        "org_id": kwargs.get("org_id", "org-1"),
        "role": kwargs.get("role", "member"),
        "is_active": kwargs.get("is_active", True),
    }
    _mock_users[user_id] = user
    return user


# ---------------------------------------------------------------------------
# manage_users tests
# ---------------------------------------------------------------------------


class TestManageUsers:
    """Tests for the manage_users tool."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """List users when none exist returns empty list with suggestion."""
        result = await manage_users(action="list")
        assert result["status"] == "ok"
        assert result["users"] == []
        assert result["total"] == 0
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_list_with_users(self):
        """List users returns populated list."""
        _add_mock_user("u1", org_id="org-1")
        _add_mock_user("u2", org_id="org-1")

        result = await manage_users(action="list")
        assert result["status"] == "ok"
        assert result["total"] == 2
        assert len(result["users"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_org(self):
        """List users filtered by org_id."""
        _add_mock_user("u1", org_id="org-1")
        _add_mock_user("u2", org_id="org-2")

        result = await manage_users(action="list", org_id="org-1")
        assert result["total"] == 1
        assert result["users"][0]["org_id"] == "org-1"

    @pytest.mark.asyncio
    async def test_list_filter_by_role(self):
        """List users filtered by role."""
        _add_mock_user("u1", role="admin")
        _add_mock_user("u2", role="member")

        result = await manage_users(action="list", role="admin")
        assert result["total"] == 1
        assert result["users"][0]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_list_pagination(self):
        """List users respects page and page_size."""
        for i in range(5):
            _add_mock_user(f"u{i}")

        result = await manage_users(action="list", page=1, page_size=2)
        assert result["total"] == 5
        assert len(result["users"]) == 2
        assert result["page"] == 1
        assert result["page_size"] == 2

    @pytest.mark.asyncio
    async def test_activate_user(self):
        """Activate a deactivated user."""
        _add_mock_user("u1", is_active=False)

        result = await manage_users(action="activate", user_id="u1")
        assert result["status"] == "ok"
        assert result["is_active"] is True
        assert _mock_users["u1"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_deactivate_user(self):
        """Deactivate an active user."""
        _add_mock_user("u1", is_active=True)

        result = await manage_users(action="deactivate", user_id="u1")
        assert result["status"] == "ok"
        assert result["is_active"] is False
        assert _mock_users["u1"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_activate_missing_user_id(self):
        """Activate without user_id returns error."""
        result = await manage_users(action="activate")
        assert result["status"] == "error"
        assert "user_id" in result["error"]
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_activate_unknown_user(self):
        """Activate unknown user returns not_found."""
        result = await manage_users(action="activate", user_id="ghost")
        assert result["status"] == "not_found"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        """Invalid action returns error with valid options."""
        result = await manage_users(action="delete")
        assert result["status"] == "error"
        assert "suggestion" in result


# ---------------------------------------------------------------------------
# get_audit_log tests
# ---------------------------------------------------------------------------


class TestGetAuditLog:
    """Tests for the get_audit_log tool."""

    @pytest.mark.asyncio
    async def test_empty_audit_log(self):
        """Empty audit log returns ok with zero entries."""
        result = await get_audit_log()
        assert result["status"] == "ok"
        assert result["total"] == 0
        assert result["entries"] == []
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_audit_log_with_entries(self):
        """Audit log returns entries in reverse chronological order."""
        _mock_audit_entries.extend([
            {"action": "CREATE", "resource_type": "experiment", "timestamp": "2024-01-01T10:00:00Z"},
            {"action": "UPDATE", "resource_type": "experiment", "timestamp": "2024-01-02T10:00:00Z"},
        ])

        result = await get_audit_log()
        assert result["total"] == 2
        assert len(result["entries"]) == 2
        # Reverse chronological
        assert result["entries"][0]["timestamp"] >= result["entries"][1]["timestamp"]

    @pytest.mark.asyncio
    async def test_audit_log_filter_by_resource_type(self):
        """Filter audit entries by resource_type."""
        _mock_audit_entries.extend([
            {"action": "CREATE", "resource_type": "experiment", "timestamp": "2024-01-01T10:00:00Z"},
            {"action": "UPLOAD", "resource_type": "file", "timestamp": "2024-01-02T10:00:00Z"},
        ])

        result = await get_audit_log(resource_type="experiment")
        assert result["total"] == 1
        assert result["entries"][0]["resource_type"] == "experiment"

    @pytest.mark.asyncio
    async def test_audit_log_filter_by_action(self):
        """Filter audit entries by action."""
        _mock_audit_entries.extend([
            {"action": "CREATE", "resource_type": "experiment", "timestamp": "2024-01-01T10:00:00Z"},
            {"action": "DELETE", "resource_type": "experiment", "timestamp": "2024-01-02T10:00:00Z"},
        ])

        result = await get_audit_log(action="CREATE")
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_audit_log_pagination(self):
        """Audit log respects pagination parameters."""
        for i in range(10):
            _mock_audit_entries.append({
                "action": "CREATE",
                "resource_type": "experiment",
                "timestamp": f"2024-01-{i+1:02d}T10:00:00Z",
            })

        result = await get_audit_log(page=2, page_size=3)
        assert result["total"] == 10
        assert len(result["entries"]) == 3
        assert result["page"] == 2

    @pytest.mark.asyncio
    async def test_audit_log_max_page_size(self):
        """Page size is capped at 200."""
        result = await get_audit_log(page_size=500)
        assert result["page_size"] == 200


# ---------------------------------------------------------------------------
# update_settings tests
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    """Tests for the update_settings tool."""

    @pytest.mark.asyncio
    async def test_list_settings(self):
        """List all settings returns default entries."""
        result = await update_settings(action="list")
        assert result["status"] == "ok"
        assert result["total"] >= 4  # at least the 4 defaults
        assert "categories" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_list_settings_by_category(self):
        """List settings filtered by category."""
        result = await update_settings(action="list", category="parsers")
        assert result["status"] == "ok"
        assert all(s["category"] == "parsers" for s in result["settings"])

    @pytest.mark.asyncio
    async def test_get_setting(self):
        """Get a specific setting by key."""
        result = await update_settings(action="get", key="parsers.auto_detect")
        assert result["status"] == "ok"
        assert result["setting"]["key"] == "parsers.auto_detect"
        assert result["setting"]["value"] == "true"

    @pytest.mark.asyncio
    async def test_get_setting_not_found(self):
        """Get unknown key returns not_found."""
        result = await update_settings(action="get", key="nonexistent.key")
        assert result["status"] == "not_found"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_set_existing_setting(self):
        """Update an existing setting."""
        result = await update_settings(
            action="set",
            key="parsers.auto_detect",
            value="false",
        )
        assert result["status"] == "ok"
        assert result["old_value"] == "true"
        assert result["new_value"] == "false"
        assert "suggestion" in result

        # Verify audit entry was created
        assert any(
            e.get("resource_id") == "parsers.auto_detect"
            for e in _mock_audit_entries
        )

    @pytest.mark.asyncio
    async def test_set_new_setting(self):
        """Create a new setting via set action."""
        result = await update_settings(
            action="set",
            key="custom.new_setting",
            value="hello",
        )
        assert result["status"] == "ok"
        assert result["created"] is True
        assert result["new_value"] == "hello"

        # Verify it's now retrievable
        get_result = await update_settings(action="get", key="custom.new_setting")
        assert get_result["setting"]["value"] == "hello"
        assert get_result["setting"]["category"] == "custom"

    @pytest.mark.asyncio
    async def test_set_missing_value(self):
        """Set without value returns error."""
        result = await update_settings(action="set", key="some.key")
        assert result["status"] == "error"
        assert "value" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_missing_key(self):
        """Get without key returns error."""
        result = await update_settings(action="get")
        assert result["status"] == "error"
        assert "key" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        """Invalid action returns error with valid options."""
        result = await update_settings(action="delete")
        assert result["status"] == "error"
        assert "suggestion" in result


# ---------------------------------------------------------------------------
# get_system_health tests
# ---------------------------------------------------------------------------


class TestGetSystemHealth:
    """Tests for the get_system_health tool."""

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self):
        """System health in dev mode returns healthy."""
        result = await get_system_health()
        assert result["status"] == "healthy"
        assert "version" in result
        assert "environment" in result
        assert "uptime_seconds" in result
        assert "timestamp" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_health_has_all_checks(self):
        """Health response includes all expected subsystem checks."""
        result = await get_system_health()
        checks = result["checks"]
        expected_keys = {"database", "storage", "task_queue", "elasticsearch", "redis", "parsers"}
        assert set(checks.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_health_database_check(self):
        """Database check reports sqlite in dev."""
        result = await get_system_health()
        db = result["checks"]["database"]
        assert db["status"] == "ok"
        assert db["backend"] == "sqlite"

    @pytest.mark.asyncio
    async def test_health_storage_check(self):
        """Storage check reports local backend."""
        result = await get_system_health()
        storage = result["checks"]["storage"]
        assert storage["status"] == "ok"
        assert storage["backend"] == "local"

    @pytest.mark.asyncio
    async def test_health_task_queue_sync_fallback(self):
        """Task queue reports sync_fallback in dev mode."""
        result = await get_system_health()
        tq = result["checks"]["task_queue"]
        assert tq["mode"] == "sync_fallback"

    @pytest.mark.asyncio
    async def test_health_parsers_all_ok(self):
        """All 5 parsers report ok status."""
        result = await get_system_health()
        parsers = result["checks"]["parsers"]
        assert parsers["status"] == "ok"
        assert parsers["total"] == 5
        for p in parsers["details"]:
            assert p["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_uptime_positive(self):
        """Uptime is a positive number."""
        result = await get_system_health()
        assert result["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


class TestAdminToolRegistration:
    """Tests for the admin toolset registration helper."""

    def test_get_admin_tools_returns_four(self):
        """get_admin_tools returns exactly 4 tool metadata entries."""
        from app.mcp_server.tools.admin import get_admin_tools

        tools = get_admin_tools()
        assert len(tools) == 4
        names = {t["name"] for t in tools}
        assert names == {"manage_users", "get_audit_log", "update_settings", "get_system_health"}

    def test_admin_tools_have_required_fields(self):
        """Each tool entry has name, description, toolset, parameters."""
        from app.mcp_server.tools.admin import get_admin_tools

        for tool in get_admin_tools():
            assert "name" in tool
            assert "description" in tool
            assert tool["toolset"] == "admin"
            assert "parameters" in tool


class TestIngestorToolRegistration:
    """Tests for the ingestor toolset registration helper."""

    def test_get_ingestor_tools_returns_four(self):
        """get_ingestor_tools returns exactly 4 tool metadata entries."""
        from app.mcp_server.tools.ingestor import get_ingestor_tools

        tools = get_ingestor_tools()
        assert len(tools) == 4
        names = {t["name"] for t in tools}
        assert names == {"ingest_file", "check_ingest_status", "retry_ingest", "list_parsers"}

    def test_ingestor_tools_have_required_fields(self):
        """Each tool entry has name, description, toolset, parameters."""
        from app.mcp_server.tools.ingestor import get_ingestor_tools

        for tool in get_ingestor_tools():
            assert "name" in tool
            assert "description" in tool
            assert tool["toolset"] == "ingestor"
            assert "parameters" in tool
