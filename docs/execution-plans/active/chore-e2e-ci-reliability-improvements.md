---
title: "chore: E2E + CI Reliability Improvements"
type: chore
status: active
date: 2026-03-09
source: code-review
---

# chore: E2E + CI Reliability Improvements

Code-review findings from the E2E plan (`feat-e2e-tests-local-dev-setup-plan.md`). Seven issues across E2E test reliability, subprocess security, port management, CI coverage, and CI performance.

---

## Issue 001 — Fixed Sleep Waits in E2E Tests (p2)

**Tags:** e2e, reliability, performance

### Problem

Seven places in the E2E suite use `wait_for_timeout(N)` (fixed sleeps) instead of Playwright's event-driven wait APIs. Fixed sleeps are flaky on loaded CI runners and always too slow locally.

### Affected Locations

- `tests/e2e/test_agents.py:29` — `wait_for_timeout(2_000)` before asserting agent list
- `tests/e2e/test_auth.py:38` — `wait_for_timeout(2_000)` after login
- `tests/e2e/test_experiments.py:41,52` — `wait_for_timeout(500)` after dialog open
- `tests/e2e/test_search.py:47` — `wait_for_timeout(1_500)` after search
- `tests/e2e/test_uploads.py:37,51` — `wait_for_timeout(2_000/3_000)` after navigation/upload

### Recommended Fix

Replace API/data waits with `page.wait_for_response()` or `page.wait_for_selector()`. The 500ms dialog waits in `test_experiments.py` may remain with a comment explaining animation timing.

```python
# Instead of: page.wait_for_timeout(2_000)
# For API responses:
page.wait_for_response(lambda r: "/api/v1/agents" in r.url and r.status == 200)
# For DOM elements:
page.wait_for_selector('[data-testid="agent-list"]', state="visible")
```

### Acceptance Criteria

- [ ] No `wait_for_timeout` calls > 500ms in E2E tests
- [ ] Any remaining `wait_for_timeout` calls have a comment explaining why event-driven wait is not applicable
- [ ] E2E suite still passes in < 45 seconds locally

---

## Issue 002 — E2E conftest Passes Full `os.environ` to API Subprocess (p2)

**Tags:** security, e2e, subprocess

### Problem

`tests/e2e/conftest.py` starts the API subprocess with `env={**os.environ, ...}`, inheriting every env var from the developer's shell — including real `LABLINK_SECRET_KEY`, `AWS_*` credentials, and database passwords. Tests run against non-isolated configuration; real cloud calls possible.

### Recommended Fix

Pass a minimal, explicit env dict:

```python
MINIMAL_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "USER": os.environ.get("USER", ""),
    "UV_PROJECT_ENVIRONMENT": os.environ.get("UV_PROJECT_ENVIRONMENT", ""),
    "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
    "LABLINK_DATABASE_URL": f"sqlite+aiosqlite:///{DB_PATH}",
    "LABLINK_SECRET_KEY": "e2e-test-secret-not-for-production",
    "LABLINK_CORS_ORIGINS": '["http://localhost:5173"]',
    "LABLINK_TASK_BACKEND": "sync",
    "LABLINK_STORAGE_BACKEND": "local",
    "LABLINK_SEARCH_BACKEND": "memory",
    "LABLINK_ENVIRONMENT": "test",
}
```

### Acceptance Criteria

- [ ] API subprocess does not inherit real cloud credentials from shell
- [ ] E2E suite still passes with explicit env dict
- [ ] CI E2E job passes

---

## Issue 003 — Hardcoded Ports 8000/5173 Kill Running Dev Server (p2)

**Tags:** e2e, reliability, infrastructure

### Problem

E2E conftest hardcodes ports 8000/5173. When a developer runs `make e2e` while `make dev-local` is running, the conftest `kill -9` loop silently kills their dev server.

### Recommended Fix

Use non-conflicting ports for E2E (8765/5174), controlled by env vars, and remove the `kill -9` loop. Replace with a clear error if ports are occupied:

```python
API_BASE_URL = os.environ.get("E2E_API_URL", "http://localhost:8765")
E2E_BASE_URL = os.environ.get("E2E_FE_URL", "http://localhost:5174")
```

Remove the `lsof | xargs kill -9` block. The existing `_check_port_free()` call already provides a clear error message.

### Acceptance Criteria

- [ ] `make dev-local` and `make e2e` can run simultaneously without killing each other
- [ ] E2E suite passes on non-conflicting ports
- [ ] Error message is clear if E2E ports are already in use

---

## Issue 004 — E2E Tests Only Run on Main Branch Push, Not on PRs (p2)

**Tags:** ci, e2e, devops

### Problem

CI E2E job has `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`. E2E failures are discovered only after merging to main — backwards from the purpose of CI.

### Recommended Fix

Run E2E on PRs but mark as non-blocking (allows visibility without blocking):

```yaml
e2e:
  name: E2E Tests
  runs-on: ubuntu-latest
  continue-on-error: ${{ github.event_name == 'pull_request' }}
```

Or opt-in via PR label `run-e2e`:

```yaml
if: |
  (github.event_name == 'push' && github.ref == 'refs/heads/main') ||
  (github.event_name == 'pull_request' &&
   contains(github.event.pull_request.labels.*.name, 'run-e2e'))
```

### Acceptance Criteria

- [ ] E2E failures are visible before (or at) merge time, not only after
- [ ] PR authors can determine E2E pass/fail status before requesting review

---

## Issue 005 — Duplicate `FIXTURES_DIR` in test_uploads.py vs conftest.py (p3)

**Tags:** quality, e2e

### Problem

`tests/e2e/test_uploads.py` defines its own `FIXTURES_DIR` path that duplicates logic from conftest. If the fixtures directory moves, both places need updating.

### Recommended Fix

Export `FIXTURES_DIR` from `tests/e2e/conftest.py` and import it in `test_uploads.py`:

```python
# conftest.py
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# test_uploads.py
from tests.e2e.conftest import FIXTURES_DIR
```

### Acceptance Criteria

- [ ] `FIXTURES_DIR` defined once and imported where needed
- [ ] E2E uploads tests still pass

---

## Issue 006 — E2E Failure Screenshot Uses Fixed Path — Overwritten by Multiple Failures (p3)

**Tags:** quality, e2e, ci

### Problem

`conftest.py` auth_page fixture saves failure screenshot to `/tmp/e2e-auth-failure.png` (fixed path). Multiple test failures overwrite each other. Also, this path does NOT match the CI artifact upload glob `e2e-failure-*.png` — CI misses it.

### Recommended Fix

Use `request.node.name` for a per-test, glob-compatible path:

```python
@pytest.fixture()
def auth_page(page: Page, request: pytest.FixtureRequest) -> Page:
    ...
    except Exception:
        test_name = request.node.name.replace("/", "_")
        page.screenshot(path=f"/tmp/e2e-failure-{test_name}.png")
        raise
```

### Acceptance Criteria

- [ ] Screenshot path matches CI artifact glob `e2e-failure-*.png`
- [ ] Multiple test failures produce separate screenshots
- [ ] Screenshot filename identifies which test failed

---

## Issue 008 — Playwright Chromium Not Cached in CI — 60-120s per Run (p3)

**Tags:** ci, performance

### Problem

CI E2E job downloads ~130MB of Chrome + dependencies on every run (`playwright install chromium --with-deps`) with no `actions/cache` step. Wastes 60-120s per run.

### Recommended Fix

```yaml
- name: Cache Playwright browsers
  uses: actions/cache@v4
  id: playwright-cache
  with:
    path: ~/.cache/ms-playwright
    key: playwright-chromium-${{ hashFiles('pyproject.toml') }}

- name: Install Playwright browsers
  run: playwright install chromium --with-deps
  if: steps.playwright-cache.outputs.cache-hit != 'true'
```

### Acceptance Criteria

- [ ] Playwright browsers cached between CI runs
- [ ] Cache key invalidates when `pyproject.toml` changes
- [ ] E2E CI job still passes

---

## Implementation Order

1. **001** — Fixed sleep waits (highest reliability impact, pure code change)
2. **003** — Hardcoded ports (prevents dev server destruction)
3. **002** — Env isolation (security hygiene)
4. **004** — PR E2E visibility (CI config change)
5. **008** — Playwright cache (CI performance)
6. **005, 006** — Minor quality cleanups (do alongside any E2E touch)
