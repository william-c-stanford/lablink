---
title: "chore: MCP Planner Test Coverage"
type: chore
status: active
date: 2026-03-09
source: code-review
---

# chore: MCP Planner Test Coverage

Code-review finding from the agent-native reviewer (week 7). The existing MCP planner test file exercises the wrong module; the actual `lablink.mcp.server` planner tools have zero functional test coverage.

---

## Issue 007 — MCP Planner Tests Exercise Wrong Module (p2)

**Tags:** agent-native, testing, mcp

### Problem

`tests/test_mcp/test_planner.py` imports from `app.mcp_server.tools.planner` (the legacy `backend/app/` scaffold) and tests a `create_pipeline` / `validate_pipeline` / `estimate_duration` domain that doesn't exist in `src/lablink/`.

The actual `lablink.mcp.server` planner toolset exposes:
- `create_experiment`
- `update_experiment`
- `record_outcome`
- `link_upload_to_experiment`
- `create_campaign`
- `get_campaign_progress`
- `list_campaigns`

None of these are tested by the existing planner test file. `test_mcp_tools.py` only verifies metadata (name, description, count) — it doesn't call the tools.

### Recommended Fix

Replace `tests/test_mcp/test_planner.py` with tests that call the actual `lablink.mcp.server` async tool functions:

```python
# tests/test_mcp/test_lablink_planner.py
import pytest
from lablink.mcp.server import mcp  # FastMCP instance

@pytest.mark.asyncio
async def test_create_experiment_tool(db_session, test_org):
    """MCP create_experiment tool creates an experiment."""
    result = await mcp.call_tool("create_experiment", {
        "organization_id": str(test_org.id),
        "intent": "Test experiment via MCP"
    })
    assert result["data"]["status"] == "planned"
```

Use the existing `db` fixture from `tests/conftest.py` for database setup.

### Files to Change

| File | Action |
|---|---|
| `tests/test_mcp/test_planner.py` | Delete or rename to `test_legacy_planner.py` |
| `tests/test_mcp/test_lablink_planner.py` | Create — tests for `lablink.mcp.server` planner tools |

### Minimum Coverage Required

- [ ] `create_experiment` — happy path, missing org returns error with suggestion
- [ ] `update_experiment` — status transition, invalid transition returns error
- [ ] `record_outcome` — links outcome to experiment
- [ ] `link_upload_to_experiment` — links upload, verifies relationship
- [ ] Tests use `lablink.mcp.server` (not `app.mcp_server`)
- [ ] Tests pass with `make test`
