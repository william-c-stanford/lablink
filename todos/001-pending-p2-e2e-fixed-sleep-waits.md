---
status: pending
priority: p2
issue_id: "001"
tags: [code-review, e2e, reliability, performance]
dependencies: []
---

# E2E Tests Use Fixed `wait_for_timeout` Sleeps Instead of Proper Wait Conditions

## Problem Statement

Seven places in the E2E test suite use `auth_page.wait_for_timeout(N)` (arbitrary fixed sleeps) instead of Playwright's event-driven wait APIs. Fixed sleeps cause two failure modes: too short on a loaded CI runner (flaky failures), and always too long locally (slow test suite).

## Findings

Affected locations:
- `tests/e2e/test_agents.py:29` — `wait_for_timeout(2_000)` after navigation, before asserting agent list
- `tests/e2e/test_auth.py:38` — `wait_for_timeout(2_000)` after login mutation to check URL/error
- `tests/e2e/test_experiments.py:41` — `wait_for_timeout(500)` after opening dialog
- `tests/e2e/test_experiments.py:52` — `wait_for_timeout(500)` after opening dialog
- `tests/e2e/test_search.py:47` — `wait_for_timeout(1_500)` after search, waiting for results
- `tests/e2e/test_uploads.py:37` — `wait_for_timeout(2_000)` after navigation for seed data
- `tests/e2e/test_uploads.py:51` — `wait_for_timeout(3_000)` after file upload

## Proposed Solutions

### Option 1: Replace with `wait_for_selector` / `wait_for_response` (Recommended)
Use Playwright's proper event-driven waits that resolve as soon as the condition is true.

```python
# Instead of: auth_page.wait_for_timeout(2_000)
# For API response wait:
auth_page.wait_for_response(lambda r: "/api/v1/agents" in r.url and r.status == 200)

# For element appearance:
auth_page.wait_for_selector('[data-testid="agent-list"]', state="visible")

# For auth error message:
auth_page.wait_for_selector("text=Invalid credentials", state="visible", timeout=5_000)

# For upload completion:
auth_page.wait_for_selector('[data-testid="upload-status-completed"]', state="visible", timeout=10_000)
```

**Pros:** Deterministic, fast, no artificial delays
**Effort:** Small — 7 targeted replacements
**Risk:** Low — pure swap with no logic change

### Option 2: Use `expect(locator).to_be_visible()` assertions
Playwright's `expect` API has built-in retry/wait behavior with configurable timeout.

```python
from playwright.sync_api import expect
expect(auth_page.get_by_test_id("agent-list")).to_be_visible(timeout=5_000)
```

**Pros:** More idiomatic Playwright, better error messages on failure
**Effort:** Small
**Risk:** Low

### Option 3: Keep fixed sleeps, document intent
Leave as-is with a comment explaining why. Acceptable for the 500ms dialog waits (animation timing).

**Pros:** Zero effort
**Cons:** Flaky in CI, wastes ~16 seconds per full run
**Risk:** Low but accrues technical debt

## Recommended Action

Option 1 for the API/data waits (agents list, uploads seed data, upload progress, search results). Option 3 acceptable only for the 500ms dialog animation waits in `test_experiments.py`.

## Technical Details

- Affected files: `tests/e2e/test_*.py` (7 locations)
- No backend changes needed
- Playwright docs: `page.wait_for_response()`, `page.wait_for_selector()`

## Acceptance Criteria

- [ ] No `wait_for_timeout` calls > 500ms in E2E tests
- [ ] Any remaining `wait_for_timeout` calls have a comment explaining why event-driven wait is not applicable
- [ ] E2E suite still passes in < 45 seconds locally

## Work Log

- 2026-03-09: Created during code review of feat/week7-docs-and-infrastructure
