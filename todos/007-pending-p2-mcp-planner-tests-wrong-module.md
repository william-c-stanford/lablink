---
status: pending
priority: p2
issue_id: "007"
tags: [code-review, agent-native, testing, mcp]
dependencies: []
---

# MCP Planner Tests Exercise Wrong Module (backend/app, Not lablink.mcp)

## Problem Statement

`tests/test_mcp/test_planner.py` imports from `app.mcp_server.tools.planner` (the legacy `backend/app/` scaffold) and tests a `create_pipeline` / `validate_pipeline` / `estimate_duration` domain that doesn't exist in `src/lablink/`. The actual `lablink.mcp.server` planner toolset exposes: `create_experiment`, `update_experiment`, `record_outcome`, `link_upload_to_experiment`, `create_campaign`, `get_campaign_progress`, `list_campaigns`.

None of these lablink-package tools are tested by the existing planner test file. `test_mcp_tools.py` only verifies metadata (name, description, count) — it doesn't call the tools.

## Findings

- `tests/test_mcp/test_planner.py` — imports `from app.mcp_server.tools.planner import ...` (wrong module)
- `src/lablink/mcp/server.py` — actual planner tools have zero functional test coverage
- `test_mcp_tools.py` — only checks tool count and metadata, doesn't call tools
- The E2E test `test_create_experiment_success` tests the UI path but not the MCP tool directly

## Proposed Solutions

### Option 1: Replace test_planner.py with lablink MCP tests (Recommended)

Write tests that call the actual `lablink.mcp.server` async tool functions:

```python
# tests/test_mcp/test_lablink_planner.py
import pytest
from lablink.mcp.server import mcp  # FastMCP instance

@pytest.mark.asyncio
async def test_create_experiment_tool(db_session, test_org):
    """MCP create_experiment tool creates an experiment."""
    # Call the tool function directly
    result = await mcp.call_tool("create_experiment", {
        "organization_id": str(test_org.id),
        "intent": "Test experiment via MCP"
    })
    assert result["data"]["status"] == "planned"
```

**Effort:** Medium — requires understanding the FastMCP test pattern
**Risk:** Low

### Option 2: Keep existing test_planner.py, add lablink tests

Rename the existing file to `test_legacy_planner.py` and add a new `test_lablink_planner.py` for the lablink tools.

**Effort:** Medium
**Risk:** Low

### Option 3: Improve test_mcp_tools.py to call tools

Extend the existing metadata test to also call each tool with a minimal valid payload and verify the response envelope.

**Effort:** Small per tool, large total
**Risk:** Low

## Recommended Action

Option 1 — replace the wrong-module planner tests with tests for the actual `lablink.mcp.server` planner tools. At minimum test: `create_experiment`, `update_experiment`, `record_outcome`. Use the existing `db` fixture from `tests/conftest.py`.

## Technical Details

- File to replace/supplement: `tests/test_mcp/test_planner.py`
- New file: `tests/test_mcp/test_lablink_planner.py`
- Ref: `src/lablink/mcp/server.py` planner toolset definition

## Acceptance Criteria

- [ ] At least `create_experiment`, `update_experiment`, `record_outcome`, `link_upload_to_experiment` have functional MCP tool tests
- [ ] Tests use `lablink.mcp.server` (not `app.mcp_server`)
- [ ] Tests pass with `make test`

## Work Log

- 2026-03-09: Created during code review — agent-native reviewer surfaced this gap
