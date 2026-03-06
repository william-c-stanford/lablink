"""Tests for Admin toolset (4 tools): manage_users, get_audit_log, update_settings, get_system_health.

Admin tools are async functions called directly (not via FastMCP dispatch).
"""

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


@pytest.fixture(autouse=True)
def reset_admin_stores(sample_audit_entries):
    """Reset in-memory admin stores between tests."""
    _mock_users.clear()
    # Save default settings before test
    saved_settings = {k: dict(v) for k, v in _mock_settings.items()}
    _mock_audit_entries.clear()
    _mock_audit_entries.extend(sample_audit_entries)
    yield
    _mock_users.clear()
    _mock_settings.clear()
    _mock_settings.update(saved_settings)
    _mock_audit_entries.clear()


class TestManageUsers:
    """Tests for manage_users admin tool."""

    @pytest.mark.asyncio
    async def test_list_empty_users(self):
        """Listing users when none exist returns empty list."""
        result = await manage_users(action="list")
        assert result["status"] == "ok"
        assert result["users"] == []
        assert result["total"] == 0
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_list_with_org_filter(self):
        """Can filter users by org_id."""
        _mock_users["u1"] = {"id": "u1", "org_id": "org-1", "is_active": True}
        _mock_users["u2"] = {"id": "u2", "org_id": "org-2", "is_active": True}

        result = await manage_users(action="list", org_id="org-1")
        assert result["total"] == 1
        assert result["users"][0]["id"] == "u1"

    @pytest.mark.asyncio
    async def test_activate_user(self):
        """Can activate a deactivated user."""
        _mock_users["u1"] = {"id": "u1", "is_active": False}
        result = await manage_users(action="activate", user_id="u1")
        assert result["status"] == "ok"
        assert result["is_active"] is True
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_deactivate_user(self):
        """Can deactivate an active user."""
        _mock_users["u1"] = {"id": "u1", "is_active": True}
        result = await manage_users(action="deactivate", user_id="u1")
        assert result["status"] == "ok"
        assert result["is_active"] is False
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_activate_without_user_id_returns_error(self):
        """Activate without user_id returns error."""
        result = await manage_users(action="activate")
        assert result["status"] == "error"
        assert "user_id" in result["error"]
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_activate_nonexistent_user_returns_error(self):
        """Activating a missing user returns not_found."""
        result = await manage_users(action="activate", user_id="fake")
        assert result["status"] == "not_found"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_invalid_action_returns_error(self):
        """Invalid action returns error with valid options."""
        result = await manage_users(action="promote")
        assert result["status"] == "error"
        assert "suggestion" in result
        assert "Valid actions" in result["suggestion"]


class TestGetAuditLog:
    """Tests for get_audit_log admin tool."""

    @pytest.mark.asyncio
    async def test_returns_all_entries(self, sample_audit_entries):
        """Returns all audit entries when no filter applied."""
        result = await get_audit_log()
        assert result["status"] == "ok"
        assert result["total"] == len(sample_audit_entries)
        assert "entries" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self):
        """Can filter entries by resource_type."""
        result = await get_audit_log(resource_type="experiment")
        assert result["total"] == 2  # CREATE + STATE_CHANGE
        for entry in result["entries"]:
            assert entry["resource_type"] == "experiment"

    @pytest.mark.asyncio
    async def test_filter_by_action(self):
        """Can filter entries by action."""
        result = await get_audit_log(action="UPLOAD")
        assert result["total"] == 1
        assert result["entries"][0]["action"] == "UPLOAD"

    @pytest.mark.asyncio
    async def test_filter_by_actor_id(self):
        """Can filter entries by actor_id."""
        result = await get_audit_log(actor_id="agent-auto")
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_pagination(self):
        """Pagination works correctly."""
        result = await get_audit_log(page=1, page_size=2)
        assert len(result["entries"]) == 2
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_empty_result_includes_suggestion(self):
        """Empty result includes helpful suggestion."""
        result = await get_audit_log(resource_type="nonexistent")
        assert result["total"] == 0
        assert "suggestion" in result
        assert "broaden" in result["suggestion"].lower()

    @pytest.mark.asyncio
    async def test_chain_integrity_field(self):
        """Result includes chain_integrity status."""
        result = await get_audit_log()
        assert "chain_integrity" in result


class TestUpdateSettings:
    """Tests for update_settings admin tool."""

    @pytest.mark.asyncio
    async def test_list_all_settings(self):
        """list action returns all settings."""
        result = await update_settings(action="list")
        assert result["status"] == "ok"
        assert result["total"] >= 4  # at least the 4 default settings
        assert "categories" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_list_by_category(self):
        """Can filter settings by category."""
        result = await update_settings(action="list", category="parsers")
        assert result["status"] == "ok"
        for setting in result["settings"]:
            assert setting["category"] == "parsers"

    @pytest.mark.asyncio
    async def test_get_existing_setting(self):
        """Can retrieve a specific setting by key."""
        result = await update_settings(action="get", key="parsers.auto_detect")
        assert result["status"] == "ok"
        assert result["setting"]["value"] == "true"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_get_nonexistent_setting(self):
        """Getting unknown key returns not_found with suggestion."""
        result = await update_settings(action="get", key="nonexistent.key")
        assert result["status"] == "not_found"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_set_updates_existing(self):
        """Can update an existing setting value."""
        result = await update_settings(
            action="set",
            key="retention.soft_delete_days",
            value="180",
        )
        assert result["status"] == "ok"
        assert result["old_value"] == "90"
        assert result["new_value"] == "180"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_set_creates_new(self):
        """Setting a new key creates it."""
        result = await update_settings(
            action="set",
            key="custom.new_setting",
            value="hello",
        )
        assert result["status"] == "ok"
        assert result.get("created") is True
        assert result["new_value"] == "hello"

    @pytest.mark.asyncio
    async def test_set_without_value_returns_error(self):
        """Setting without value returns error."""
        result = await update_settings(action="set", key="some.key")
        assert result["status"] == "error"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_set_creates_audit_entry(self):
        """Setting a value creates an audit entry."""
        initial_count = len(_mock_audit_entries)
        await update_settings(
            action="set",
            key="retention.soft_delete_days",
            value="365",
        )
        assert len(_mock_audit_entries) > initial_count

    @pytest.mark.asyncio
    async def test_invalid_action_returns_error(self):
        """Invalid action returns error."""
        result = await update_settings(action="delete")
        assert result["status"] == "error"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_get_without_key_returns_error(self):
        """get action without key returns error."""
        result = await update_settings(action="get")
        assert result["status"] == "error"
        assert "key" in result["error"].lower()


class TestGetSystemHealth:
    """Tests for get_system_health admin tool."""

    @pytest.mark.asyncio
    async def test_returns_healthy_status(self):
        """System health reports healthy in dev mode."""
        result = await get_system_health()
        assert result["status"] == "healthy"
        assert "version" in result
        assert "environment" in result

    @pytest.mark.asyncio
    async def test_has_all_subsystem_checks(self):
        """Health check covers all subsystems."""
        result = await get_system_health()
        checks = result["checks"]
        expected_systems = {"database", "storage", "task_queue", "elasticsearch", "redis", "parsers"}
        assert set(checks.keys()) == expected_systems

    @pytest.mark.asyncio
    async def test_parser_check_lists_all_five(self):
        """Parser health check lists all 5 parsers."""
        result = await get_system_health()
        parser_check = result["checks"]["parsers"]
        assert parser_check["total"] == 5
        for p in parser_check["details"]:
            assert p["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dev_mode_task_queue(self):
        """In dev mode, task queue shows sync_fallback."""
        result = await get_system_health()
        tq = result["checks"]["task_queue"]
        assert tq["mode"] == "sync_fallback"

    @pytest.mark.asyncio
    async def test_uptime_is_positive(self):
        """Uptime should be a positive number."""
        result = await get_system_health()
        assert result["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_includes_suggestion(self):
        """Health check includes suggestion."""
        result = await get_system_health()
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_includes_timestamp(self):
        """Health check includes ISO timestamp."""
        result = await get_system_health()
        assert "timestamp" in result
        assert "T" in result["timestamp"]  # ISO format
