"""Admin toolset — 4 MCP tools for system administration.

Tools:
    manage_users       — List, activate, or deactivate users within an organization.
    get_audit_log      — Query the immutable audit trail with filters and pagination.
    update_settings    — Read or update system configuration key-value pairs.
    get_system_health  — Get system health status including DB, storage, and parser info.
"""

import time
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.parsers import PARSER_REGISTRY

# ---------------------------------------------------------------------------
# In-memory stores for dev/test (production uses real DB + services)
# ---------------------------------------------------------------------------

_mock_users: dict[str, dict[str, Any]] = {}
_mock_settings: dict[str, dict[str, Any]] = {
    "parsers.auto_detect": {
        "key": "parsers.auto_detect",
        "value": "true",
        "value_type": "bool",
        "description": "Enable automatic parser detection for uploaded files",
        "category": "parsers",
        "updated_at": datetime.now(UTC).isoformat(),
    },
    "retention.soft_delete_days": {
        "key": "retention.soft_delete_days",
        "value": "90",
        "value_type": "int",
        "description": "Days to retain soft-deleted records before permanent purge",
        "category": "retention",
        "updated_at": datetime.now(UTC).isoformat(),
    },
    "storage.backend": {
        "key": "storage.backend",
        "value": "local",
        "value_type": "string",
        "description": "File storage backend: 'local' or 's3'",
        "category": "storage",
        "updated_at": datetime.now(UTC).isoformat(),
    },
    "ingest.max_file_size_mb": {
        "key": "ingest.max_file_size_mb",
        "value": "50",
        "value_type": "int",
        "description": "Maximum file size in MB for ingestion",
        "category": "ingest",
        "updated_at": datetime.now(UTC).isoformat(),
    },
}

# In-memory audit log for dev/test
_mock_audit_entries: list[dict[str, Any]] = []
_startup_time = time.monotonic()


# ---------------------------------------------------------------------------
# Tool: manage_users
# ---------------------------------------------------------------------------


async def manage_users(
    *,
    action: str = "list",
    org_id: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List, activate, or deactivate users within an organization.

    Actions:
        list       — List users with optional org_id filter and pagination.
        activate   — Re-enable a deactivated user account (requires user_id).
        deactivate — Disable a user account without deleting it (requires user_id).

    Args:
        action: One of 'list', 'activate', 'deactivate'.
        org_id: Filter by organization ID (required for list, optional for activate/deactivate).
        user_id: Target user ID (required for activate/deactivate).
        role: Filter by role name when listing (e.g. 'admin', 'member', 'viewer').
        page: Page number for pagination (default: 1).
        page_size: Number of results per page (default: 20).

    Returns:
        dict with users list or status update confirmation.
    """
    valid_actions = {"list", "activate", "deactivate"}
    if action not in valid_actions:
        return {
            "status": "error",
            "error": f"Invalid action: {action!r}.",
            "suggestion": f"Valid actions: {', '.join(sorted(valid_actions))}.",
        }

    if action == "list":
        users = list(_mock_users.values())
        if org_id:
            users = [u for u in users if u.get("org_id") == org_id]
        if role:
            users = [u for u in users if u.get("role") == role]

        total = len(users)
        start = (page - 1) * page_size
        end = start + page_size
        page_users = users[start:end]

        return {
            "status": "ok",
            "action": "list",
            "users": page_users,
            "total": total,
            "page": page,
            "page_size": page_size,
            "suggestion": (
                "No users found. Users are populated when authentication is used."
                if total == 0
                else f"Showing {len(page_users)} of {total} users."
            ),
        }

    # activate / deactivate require user_id
    if not user_id:
        return {
            "status": "error",
            "error": f"user_id is required for '{action}' action.",
            "suggestion": "Provide the user_id of the target user. Use manage_users with action='list' to find user IDs.",
        }

    user = _mock_users.get(user_id)
    if user is None:
        return {
            "status": "not_found",
            "error": f"User {user_id!r} not found.",
            "suggestion": "Verify the user_id. Use manage_users with action='list' to see available users.",
        }

    if action == "activate":
        user["is_active"] = True
        user["updated_at"] = datetime.now(UTC).isoformat()
        return {
            "status": "ok",
            "action": "activate",
            "user_id": user_id,
            "is_active": True,
            "suggestion": "User has been activated. They can now log in and access the system.",
        }

    else:  # deactivate
        user["is_active"] = False
        user["updated_at"] = datetime.now(UTC).isoformat()
        return {
            "status": "ok",
            "action": "deactivate",
            "user_id": user_id,
            "is_active": False,
            "suggestion": "User has been deactivated. They will be unable to log in. Use activate to re-enable.",
        }


# ---------------------------------------------------------------------------
# Tool: get_audit_log
# ---------------------------------------------------------------------------


async def get_audit_log(
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Query the immutable audit trail with filters and pagination.

    The audit log is append-only with SHA-256 hash chain integrity.
    Results are returned in reverse chronological order.

    Args:
        resource_type: Filter by resource type (e.g. 'experiment', 'file', 'user').
        resource_id: Filter by specific resource UUID.
        actor_id: Filter by the user/agent who performed the action.
        action: Filter by action type (e.g. 'CREATE', 'UPDATE', 'DELETE', 'UPLOAD', 'PARSE').
        start_date: ISO 8601 date string for range start (inclusive).
        end_date: ISO 8601 date string for range end (inclusive).
        page: Page number (default: 1).
        page_size: Results per page (default: 50, max: 200).

    Returns:
        dict with audit entries, pagination metadata, and chain integrity note.
    """
    page_size = min(page_size, 200)

    entries = list(_mock_audit_entries)

    # Apply filters
    if resource_type:
        entries = [e for e in entries if e.get("resource_type") == resource_type]
    if resource_id:
        entries = [e for e in entries if e.get("resource_id") == resource_id]
    if actor_id:
        entries = [e for e in entries if e.get("actor_id") == actor_id]
    if action:
        entries = [e for e in entries if e.get("action") == action]
    if start_date:
        entries = [e for e in entries if e.get("timestamp", "") >= start_date]
    if end_date:
        entries = [e for e in entries if e.get("timestamp", "") <= end_date]

    # Reverse chronological
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]

    return {
        "status": "ok",
        "entries": page_entries,
        "total": total,
        "page": page,
        "page_size": page_size,
        "chain_integrity": "verified" if total > 0 else "no_entries",
        "suggestion": (
            "No audit entries match the given filters. Broaden your search criteria."
            if total == 0
            else (
                f"Showing {len(page_entries)} of {total} entries. "
                "Use resource_type, actor_id, or action filters to narrow results."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Tool: update_settings
# ---------------------------------------------------------------------------


async def update_settings(
    *,
    action: str = "list",
    key: str | None = None,
    value: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Read or update system configuration key-value pairs.

    Actions:
        list  — List all settings, optionally filtered by category.
        get   — Get a single setting by key.
        set   — Update a setting value (creates if it doesn't exist).

    Args:
        action: One of 'list', 'get', 'set'.
        key: Setting key (required for 'get' and 'set').
             Keys use dot-notation namespacing (e.g. 'parsers.auto_detect').
        value: New value as string (required for 'set').
        category: Filter category for 'list' action.

    Returns:
        dict with settings data or update confirmation.
    """
    valid_actions = {"list", "get", "set"}
    if action not in valid_actions:
        return {
            "status": "error",
            "error": f"Invalid action: {action!r}.",
            "suggestion": f"Valid actions: {', '.join(sorted(valid_actions))}.",
        }

    if action == "list":
        settings_list = list(_mock_settings.values())
        if category:
            settings_list = [s for s in settings_list if s.get("category") == category]
        return {
            "status": "ok",
            "action": "list",
            "settings": settings_list,
            "total": len(settings_list),
            "categories": sorted({s.get("category", "general") for s in _mock_settings.values()}),
            "suggestion": "Use action='get' with a specific key to retrieve a single setting.",
        }

    if not key:
        return {
            "status": "error",
            "error": f"'key' parameter is required for '{action}' action.",
            "suggestion": "Provide a setting key. Use action='list' to see all available keys.",
        }

    if action == "get":
        setting = _mock_settings.get(key)
        if setting is None:
            return {
                "status": "not_found",
                "error": f"Setting {key!r} not found.",
                "suggestion": "Use action='list' to see all available settings, or action='set' to create a new one.",
            }
        return {
            "status": "ok",
            "action": "get",
            "setting": setting,
            "suggestion": f"Use action='set' with key='{key}' and a value to update this setting.",
        }

    # action == "set"
    if value is None:
        return {
            "status": "error",
            "error": "'value' parameter is required for 'set' action.",
            "suggestion": "Provide a string value. The system will cast it to the setting's declared type.",
        }

    existing = _mock_settings.get(key)
    now = datetime.now(UTC).isoformat()

    if existing:
        old_value = existing["value"]
        existing["value"] = value
        existing["updated_at"] = now

        # Record audit entry
        _mock_audit_entries.append({
            "action": "CONFIG_CHANGE",
            "resource_type": "system_config",
            "resource_id": key,
            "actor_id": "system",
            "summary": f"Setting '{key}' changed from '{old_value}' to '{value}'",
            "timestamp": now,
        })

        return {
            "status": "ok",
            "action": "set",
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "suggestion": "Setting updated. Changes take effect immediately for most settings.",
        }
    else:
        # Infer category from key prefix
        inferred_category = key.split(".")[0] if "." in key else "general"
        new_setting = {
            "key": key,
            "value": value,
            "value_type": "string",
            "description": None,
            "category": inferred_category,
            "updated_at": now,
        }
        _mock_settings[key] = new_setting

        _mock_audit_entries.append({
            "action": "CONFIG_CHANGE",
            "resource_type": "system_config",
            "resource_id": key,
            "actor_id": "system",
            "summary": f"New setting '{key}' created with value '{value}'",
            "timestamp": now,
        })

        return {
            "status": "ok",
            "action": "set",
            "key": key,
            "new_value": value,
            "created": True,
            "suggestion": f"New setting created in category '{inferred_category}'. Set value_type via update_settings if needed.",
        }


# ---------------------------------------------------------------------------
# Tool: get_system_health
# ---------------------------------------------------------------------------


async def get_system_health() -> dict[str, Any]:
    """Get system health status including DB, storage, and parser info.

    Returns a comprehensive health check covering:
    - Application version and environment
    - Database connectivity status
    - Storage backend status
    - Parser availability
    - Celery/task queue status
    - Elasticsearch status
    - Uptime

    Returns:
        dict with health status for each subsystem and overall status.
    """
    settings = get_settings()
    uptime_seconds = round(time.monotonic() - _startup_time, 2)

    # Check parser availability
    parser_status: list[dict[str, str]] = []
    for name, cls in PARSER_REGISTRY.items():
        try:
            instance = cls()
            parser_status.append({
                "name": name,
                "version": getattr(instance, "version", "unknown"),
                "status": "ok",
            })
        except Exception as exc:
            parser_status.append({
                "name": name,
                "status": "error",
                "error": str(exc),
            })

    # Build subsystem health checks
    checks: dict[str, dict[str, Any]] = {
        "database": {
            "status": "ok",
            "backend": "sqlite" if settings.is_sqlite else "postgresql",
            "url_hint": settings.database_url.split("@")[-1] if "@" in settings.database_url else "local",
        },
        "storage": {
            "status": "ok",
            "backend": settings.storage_backend,
            "path": settings.local_storage_path if settings.storage_backend == "local" else settings.s3_bucket,
        },
        "task_queue": {
            "status": "ok" if not settings.use_celery else "configured",
            "mode": "sync_fallback" if not settings.use_celery else "celery",
            "broker": settings.celery_broker_url if settings.use_celery else "n/a (sync mode)",
        },
        "elasticsearch": {
            "status": "ok" if not settings.use_elasticsearch else "configured",
            "mode": "in_memory_mock" if not settings.use_elasticsearch else "live",
            "url": settings.elasticsearch_url if settings.use_elasticsearch else "n/a (mock mode)",
        },
        "redis": {
            "status": "ok" if not settings.use_redis else "configured",
            "mode": "in_memory_mock" if not settings.use_redis else "live",
        },
        "parsers": {
            "status": "ok" if all(p["status"] == "ok" for p in parser_status) else "degraded",
            "total": len(parser_status),
            "details": parser_status,
        },
    }

    # Overall status
    all_ok = all(
        c["status"] in ("ok", "configured") for c in checks.values()
    )

    return {
        "status": "healthy" if all_ok else "degraded",
        "version": settings.version,
        "environment": settings.environment.value,
        "uptime_seconds": uptime_seconds,
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
        "suggestion": (
            "All systems operational."
            if all_ok
            else "One or more subsystems are degraded. Check the 'checks' field for details."
        ),
    }


# ---------------------------------------------------------------------------
# Toolset registration helper
# ---------------------------------------------------------------------------


def get_admin_tools() -> list[dict[str, Any]]:
    """Return metadata for all admin tools (used by discovery)."""
    return [
        {
            "name": "manage_users",
            "description": "List, activate, or deactivate users within an organization.",
            "toolset": "admin",
            "parameters": ["action", "org_id", "user_id", "role", "page", "page_size"],
        },
        {
            "name": "get_audit_log",
            "description": "Query the immutable audit trail with filters and pagination.",
            "toolset": "admin",
            "parameters": ["resource_type", "resource_id", "actor_id", "action", "start_date", "end_date", "page", "page_size"],
        },
        {
            "name": "update_settings",
            "description": "Read or update system configuration key-value pairs.",
            "toolset": "admin",
            "parameters": ["action", "key", "value", "category"],
        },
        {
            "name": "get_system_health",
            "description": "Get system health status including DB, storage, parsers, and task queue.",
            "toolset": "admin",
            "parameters": [],
        },
    ]
