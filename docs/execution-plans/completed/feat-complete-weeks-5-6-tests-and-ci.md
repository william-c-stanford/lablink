# feat: Complete Week 5 & 6 — Missing Tests + CI Cross-Compile

## Overview

Weeks 5 and 6 of the Month 2 roadmap are **structurally complete**: all implementation files exist and pass spec requirements. However, **3 test files** required by Week 5 are absent, and **Week 6 has no GitHub Actions CI** for cross-platform builds. This plan closes those gaps so both weeks can be marked done.

---

## Audit Results

### Week 5 — MCP Server + Webhooks

| File | Status | Notes |
|---|---|---|
| `src/lablink/mcp/server.py` | COMPLETE | 25 tools: 2 discovery + 8 explorer + 7 planner + 4 ingestor + 4 admin |
| `src/lablink/routers/webhooks.py` | COMPLETE | 5 endpoints, Envelope pattern, pagination |
| `src/lablink/services/webhook_service.py` | COMPLETE | HMAC-SHA256 signing, `hmac.compare_digest`, fan-out dispatch |
| `src/lablink/tasks/webhook_task.py` | COMPLETE | `2**attempt` backoff, 3 max attempts, sync/async bridge |
| `tests/test_mcp_tools.py` | **MISSING** | No file; existing `test_mcp_server.py` targets legacy `app.mcp_server` |
| `tests/test_tool_descriptions.py` | **MISSING** | No file; partial coverage in wrong module |
| `tests/test_webhooks.py` | **MISSING** | No file anywhere |

> Note: `tests/test_mcp_server.py` (970 lines), `test_mcp_admin.py`, and `test_mcp_ingestor.py` exist but target `backend/app/` — the legacy module. They do not cover `src/lablink/mcp/server.py`.

### Week 6 — Go Agent

| File | Status | Notes |
|---|---|---|
| `agent/go.mod` | COMPLETE | Go 1.23, fsnotify v1.9.0, bbolt v1.4.0, cobra v1.8.1 |
| `agent/main.go` | COMPLETE | 19-line entry point |
| `agent/cmd/root.go` | COMPLETE | Has `start` + `register` (≡ `configure`) + bonus `status`, `version` |
| `agent/internal/config/config.go` | COMPLETE | YAML load/save, `IsRegistered()` |
| `agent/internal/watcher/watcher.go` | COMPLETE | 5-second stability check (5x 1s polls), extension filter |
| `agent/internal/queue/queue.go` | COMPLETE | BBolt, `MaxRetries=3`, dead-letter bucket |
| `agent/internal/uploader/uploader.go` | COMPLETE | Backoff: 1s/5s/25s, 3 retries |
| `agent/internal/heartbeat/heartbeat.go` | COMPLETE | 60s ticker, `/api/v1/agents/{id}/heartbeat` |
| `agent/configs/lablink-agent.example.yaml` | COMPLETE | All config fields documented |
| Cross-compile (Windows amd64 + macOS arm64/amd64) | **PARTIAL** | `agent/Makefile` has `build-all` for Linux/Darwin arm64/Windows but macOS amd64 is absent; no `.github/workflows/` directory exists |

---

## Problem Statement / Motivation

The test gap means:
- Zero coverage on `src/lablink/mcp/server.py` — the critical agent interface. If a tool is accidentally removed or renamed, nothing catches it.
- Zero coverage on `webhook_service.py` / `webhook_task.py` — HMAC signing, fan-out, and retry logic are all untested.
- The roadmap cannot be marked "Week 5: done" until the test files exist.

The CI gap means:
- Cross-platform binaries can only be built manually via `agent/Makefile`. No automated release artifact generation.
- macOS amd64 is missing from the `build-all` target (only arm64 is present).

---

## Proposed Solution

Write the 3 missing test files and add a GitHub Actions release workflow with a fixed Makefile. No implementation changes needed — the code is correct.

---

## Technical Considerations

### `tests/test_mcp_tools.py`

Tests agent tool-selection behavior. Imports `lablink.mcp.server` directly (not via HTTP). Uses `FastMCP`'s tool registry to verify tool names exist and are callable. Covers the narrative: "an agent looking for chromatography data should find `get_instrument_data`, not need to know the parser internals."

Key test scenarios:
- `list_toolsets()` returns 4 toolsets with correct names
- `get_toolset("explorer")` returns all 8 explorer tools
- Each expected tool name exists in the registered tool list
- Tools return dict-shaped results (not raw exceptions) when called with valid mocked DB context

### `tests/test_tool_descriptions.py`

Static quality checks against the tool registry — no DB or HTTP needed.

Key assertions:
- All 25 tool names match `verb_noun` snake_case pattern (`^[a-z]+_[a-z_]+$`)
- Tool count is exactly 25 (regression guard)
- Each tool description is non-empty and contains a return type hint (e.g. "Returns", "List of", etc.)
- No tool name starts with `get_` without also having a corresponding `list_` or vice versa (symmetry check)
- `list_toolsets` and `get_toolset` are present (discovery tools)

### `tests/test_webhooks.py`

Integration tests against `WebhookService` and `WebhookTask`. Uses SQLite in-memory DB (same pattern as other service tests). Mocks `httpx` for delivery calls.

Key test classes:
- `TestWebhookRegistration` — create, list, update, delete webhook subscriptions
- `TestWebhookSigning` — `sign_payload()` produces `sha256=...` prefix; `verify_signature()` passes/fails correctly
- `TestWebhookDelivery` — `dispatch()` fans out to all active org webhooks; skips paused webhooks
- `TestWebhookRetry` — `deliver_webhook` task retries up to 3 times with exponential backoff; marks delivery failed after max attempts
- `TestWebhookHMAC` — constant-time comparison via `hmac.compare_digest`; rejects tampered payloads

### `.github/workflows/release.yml`

Triggers on `push: tags: ['v*']`. Matrix strategy:
```yaml
matrix:
  include:
    - goos: linux,   goarch: amd64
    - goos: darwin,  goarch: arm64
    - goos: darwin,  goarch: amd64
    - goos: windows, goarch: amd64
```
Uploads binaries as GitHub Release artifacts using `softprops/action-gh-release`.

### `agent/Makefile` fix

Add missing `darwin-amd64` target to `build-all`:
```makefile
GOOS=darwin GOARCH=amd64 go build -o bin/lablink-agent-darwin-amd64 .
```

---

## Acceptance Criteria

### Week 5 Tests

- [ ] `tests/test_mcp_tools.py` exists and passes — verifies tool names match expected list for each toolset
- [ ] `tests/test_tool_descriptions.py` exists and passes — all 25 tools present, all names `verb_noun`, all descriptions non-empty
- [ ] `tests/test_webhooks.py` exists and passes — registration CRUD, HMAC signing, delivery fan-out, retry backoff
- [ ] `pytest tests/test_mcp_tools.py tests/test_tool_descriptions.py tests/test_webhooks.py` exits 0
- [ ] Total test count reaches ≥ 1,340 (adding ~44 new tests across 3 files)

### Week 6 CI

- [ ] `.github/workflows/release.yml` exists
- [ ] Workflow triggers on `v*` tags
- [ ] All 4 platform targets present: linux-amd64, darwin-arm64, darwin-amd64, windows-amd64
- [ ] `agent/Makefile` `build-all` target includes macOS amd64
- [ ] Workflow uses `actions/setup-go@v5`, `go build` matrix, `softprops/action-gh-release@v2`

---

## Dependencies & Risks

- **No new dependencies.** All test files use existing pytest + SQLAlchemy + unittest.mock patterns already in the test suite.
- **GitHub Actions secrets:** Release workflow needs `GITHUB_TOKEN` (auto-provided) — no manual secrets needed.
- **Existing `test_mcp_server.py`:** Targets the legacy module. It continues to pass — we are not touching it. New test files target `lablink.mcp.server` separately.
- **Risk:** `WebhookService` calls `httpx` for delivery — tests must mock this import (same pattern used in `test_security.py`).

---

## Implementation Order

1. **`tests/test_tool_descriptions.py`** — simplest, no DB needed, pure static inspection. Write first to establish the 25-tool contract.
2. **`tests/test_mcp_tools.py`** — builds on the tool list confirmed in step 1. Needs a mock `AsyncSession` for tools that query DB.
3. **`tests/test_webhooks.py`** — most complex, needs SQLite fixture and `httpx` mocking. Write last.
4. **`agent/Makefile`** — 1-line fix for macOS amd64 target.
5. **`.github/workflows/release.yml`** — new file, ~50 lines YAML.

---

## File List

```
tests/test_tool_descriptions.py     # new — static MCP tool quality checks
tests/test_mcp_tools.py             # new — tool selection + toolset routing
tests/test_webhooks.py              # new — registration, HMAC, delivery, retry
agent/Makefile                      # edit — add darwin/amd64 to build-all
.github/workflows/release.yml       # new — cross-compile + GitHub Release artifacts
```

---

## References

### Internal References

- MCP server implementation: `src/lablink/mcp/server.py:29` (FastMCP instance)
- Tool registration pattern: `src/lablink/mcp/server.py:85` (`list_toolsets`)
- Webhook service HMAC: `src/lablink/services/webhook_service.py:56` (`sign_payload`)
- Webhook task backoff: `src/lablink/tasks/webhook_task.py:74` (retry loop)
- Existing service test pattern: `tests/test_experiment_service.py` (SQLite + AsyncSession)
- Go Makefile cross-compile: `agent/Makefile:build-all`
- CLAUDE.md conventions: verb_noun operation_ids, Envelope pattern, suggestion fields
