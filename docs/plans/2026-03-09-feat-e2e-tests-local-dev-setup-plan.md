---
title: "feat: E2E Test Suite + Local-First Development Setup"
type: feat
status: active
date: 2026-03-09
deepened: 2026-03-09
---

# feat: E2E Test Suite + Local-First Development Setup

## Enhancement Summary

**Deepened on:** 2026-03-09
**Research agents used:** architecture-strategist, kieran-python-reviewer, best-practices-researcher (×2), framework-docs-researcher (×2), security-sentinel, ouroboros-qa-judge

### Key Improvements Over Original Plan

1. **Switch from CDP to Playwright** — critical blocker discovered: auth token lives in Zustand in-memory state, never `localStorage`. CDP page navigation clears the JS heap, losing the token on every URL change. Playwright's `browser.new_context()` model avoids this entirely.
2. **honcho over concurrently/overmind** — Python package, `uv add --dev honcho`, zero extra system deps.
3. **`.env.example` not `.env.local`** — `.env.local` is already gitignored; committed reference must be `.env.example`.
4. **SSE endpoint prerequisite** — `/api/v1/sse/updates` has no backend implementation yet; must be scoped out of E2E or flagged as a prerequisite task.
5. **Measurable acceptance criteria** — original criteria were unverifiable boolean checkboxes; replaced with DOM-observable specifics.
6. **Seed data gaps fixed** — add 1 failed upload (for parse-success-rate stat), call search indexing after parse, use deterministic storage keys.
7. **Process management hardened** — `os.killpg`, `start_new_session=True`, delete WAL files on reset, use `create_app --factory`.
8. **CI hardening** — `browser-actions/setup-chrome@v2`, static Vite build in CI, path-filtered PR E2E, security-hardened env block.

---

## Overview

Add a browser-based end-to-end test suite covering all user-facing functionality built through Week 7, and harden the local development experience so that anyone can run the full stack (API + frontend) without any AWS credentials, Docker services, or external infrastructure.

Scope excludes MCP/agent-native E2E (planned for a later week).

---

## Problem Statement

1. **No E2E coverage.** The 1,423 existing tests are unit/integration tests via httpx with `ASGITransport`. They validate the API contract but miss the real browser experience: auth redirects, upload file-picker, chart rendering, Vite proxy routing, CORS preflight, and SSE-driven live updates. Specifically, these failure modes are invisible to `ASGITransport` tests:
   - CORS preflight rejection when Vite runs on a different port
   - Router silently not registered (`_register_routers()` catches `ImportError` at DEBUG level)
   - Vite proxy misconfiguration (`/api` → `:8000` in `vite.config.ts`)

2. **Local setup is undocumented.** The config already supports fully local operation (SQLite, local filesystem, in-memory search, sync tasks), but there is no `make dev-local` target, no `.env.example` reference file, and no seed script producing realistic demo data.

---

## What Already Exists (Don't Rebuild)

`config.py` already provides everything needed for zero-infrastructure local dev:

| Setting | Default | What it replaces |
|---|---|---|
| `database_url` | `sqlite+aiosqlite:///./lablink.db` | PostgreSQL / RDS |
| `storage_backend` | `"local"` | S3 / AWS S3 |
| `use_celery` | `False` | Redis + Celery |
| `use_elasticsearch` | `False` | Elasticsearch / OpenSearch |
| `use_redis` | `False` | Redis |

The app boots today with no services at all. The gap is tooling, documentation, and the E2E layer on top.

---

## Critical Prerequisite: SSE Endpoint Missing

> **Blocking prerequisite for E2E.** `DashboardPage.tsx` and `AgentsPage.tsx` both call `useSSE('/api/v1/sse/updates')`. There is no SSE route defined in any router file (`grep -r "sse" src/lablink/routers/` returns nothing). The frontend hook silently errors via `EventSource.onerror` and falls back to polling. Any E2E assertion on SSE-driven state (agent heartbeats, live queue depth) will fail unconditionally, not flakily.
>
> **Resolution options:** (a) implement the SSE router endpoint before E2E Week, or (b) explicitly exclude SSE-dependent assertions from the initial E2E suite with `pytest.skip("SSE endpoint not implemented")` and a conftest smoke-test.

---

## Proposed Solution

### Part 1 — Local-First Hardening

#### 1.1 `.env.example`

Commit a root-level `.env.example` (note: not `.env.local` — that filename is already in `.gitignore` and would be silently ignored by git). The frontend already has this pattern at `frontend/.env.development.local.example`.

```bash
# =============================================================================
# LabLink local development environment
# Copy to .env and fill in. .env is git-ignored.
# =============================================================================

# --- Database ---
# SQLite default for local dev. No change needed.
# For PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/lablink
LABLINK_DATABASE_URL=sqlite+aiosqlite:///./lablink.db

# --- Auth ---
# Generate a real secret: python -c "import secrets; print(secrets.token_hex(32))"
# NEVER use the default in staging or production.
LABLINK_SECRET_KEY=dev-secret-key-change-in-production

# --- Storage ---
# "local" writes to ./storage/. For S3: set to "s3" and fill S3_* vars.
LABLINK_STORAGE_BACKEND=local
# LABLINK_S3_BUCKET=
# LABLINK_S3_REGION=us-east-1

# --- Tasks ---
# sync runs inline (no Redis/Celery needed)
# LABLINK_USE_CELERY=false

# --- Search ---
# false = in-memory search (no Elasticsearch needed)
# LABLINK_USE_ELASTICSEARCH=false
```

#### 1.2 `make dev-local` via honcho

Use **honcho** (Python package), not `concurrently` or `overmind`:

```
| Tool       | Language | tmux required | uv installable |
|------------|----------|---------------|----------------|
| honcho     | Python   | No            | Yes            |
| overmind   | Go       | YES           | No             |
| concurrently | Node   | No            | Fragile path   |
```

`uv add --dev honcho` makes it available automatically to all contributors via `uv sync`.

**`Procfile`** (project root):
```
api: uv run uvicorn lablink.main:create_app --factory --reload --host 127.0.0.1 --port 8000
web: npm --prefix frontend run dev
```

Note: use `create_app --factory`, not the module-level `app` singleton. This ensures a fresh `Settings` instance per process, preventing stale `lru_cache` from a prior test run.

**Makefile additions:**
```makefile
API_PORT  ?= 8000
WEB_PORT  ?= 5173

dev-local: check-prereqs check-ports ## Start API + frontend dev servers (Ctrl+C stops both)
	@$(UV) run honcho start

check-prereqs: ## Check node, python, uv are installed at required versions
	@command -v uv >/dev/null 2>&1 || \
	  { echo "ERROR: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	@command -v node >/dev/null 2>&1 || \
	  { echo "ERROR: node not found. Install: https://nodejs.org"; exit 1; }
	@node_ver=$$(node -e "process.stdout.write(String(process.versions.node.split('.')[0]))"); \
	  [ "$$node_ver" -ge 20 ] || \
	  { echo "ERROR: Node.js >=20 required (found $$node_ver)"; exit 1; }

check-ports: ## Check API and web ports are not in use
	$(call check-port-free,$(API_PORT),API server)
	$(call check-port-free,$(WEB_PORT),Vite dev server)

define check-port-free
  @if lsof -iTCP:$(1) -sTCP:LISTEN -t >/dev/null 2>&1; then \
    pid=$$(lsof -iTCP:$(1) -sTCP:LISTEN -t | head -1); \
    proc=$$(ps -p $$pid -o comm= 2>/dev/null || echo "unknown"); \
    echo "ERROR: Port $(1) is already in use by '$$proc' (PID $$pid). Stop it: kill $$pid"; \
    exit 1; \
  fi
endef

e2e: check-prereqs ## Run E2E test suite (starts services, runs tests, tears down)
	$(UV) run pytest tests/e2e/ -v -m e2e --timeout=60
```

#### 1.3 `src/lablink/scripts/seed.py`

The `make seed` Makefile target already references this path but the script doesn't exist yet.

**Key design decisions from research:**

- Create a fresh engine (not `get_engine()` singleton) with WAL + FK pragmas for SQLite
- Select-then-skip idempotency pattern using natural keys
- Direct ORM inserts, NOT service layer calls (services generate random keys, raise `ConflictError`, expect router-managed transactions)
- Reuse from service layer: `hash_password()`, `LocalStorageBackend.put()`, `compute_hash()`, `create_audit_event()`
- Use `uuid.uuid5(uuid.NAMESPACE_DNS, f"seed:{org_id}:{filename}")` for deterministic storage keys
- Guard: `assert settings.is_dev, f"Seed refused: environment={settings.environment}"`
- Include 1 upload with forced `status=failed` (use `tests/fixtures/spectrophotometer/corrupted.csv`) so parse-success-rate stat is meaningful
- Call in-memory search indexing explicitly after each upload parse

**FK insertion order (strictly required due to `PRAGMA foreign_keys=ON`):**

```
1. Organization       (no FKs)
2. User               (no org FK)
3. Membership         → user_id, organization_id
4. Project            → organization_id
5. Instrument         → organization_id
6. Agent              → organization_id
7. Upload             → org, project, instrument, user  [write file bytes first]
8. ParsedData         → upload_id
9. Experiment         → org, project
10. ExperimentUpload  → experiment_id, upload_id
11. Campaign          → org, project
12. AuditEvent        → organization_id  [use create_audit_event() only]
```

`await session.flush()` after each entity group before inserting dependents.

**Seed data contract (document at top of seed.py):**

| Entity | Count | Notes |
|---|---|---|
| Organization | 1 | slug=`e2e-lab` |
| User | 1 | `admin@lablink.local` / `lablink`, role=admin |
| Instrument | 3 | NanoDrop, Plate Reader, HPLC |
| Upload | 6 | 5 parsed + 1 failed (corrupted.csv) |
| ParsedData | 5 | linked to parsed uploads |
| Experiment | 2 | one with linked uploads, one empty |
| Campaign | 1 | baseline for campaign E2E |
| ApiToken | 1 | for API-auth testing |

---

### Part 2 — E2E Test Infrastructure

#### 2.1 Switch to Playwright (not CDP)

> **Why Playwright, not the web-browser CDP skill:**
>
> The `authStore.ts` comment states explicitly: *"On a hard refresh the token is lost and the app redirects to `/login`."* The auth token lives in Zustand **in-memory state only** — never `localStorage` or cookies. Any CDP `cdp_nav()` call that changes the page URL resets the JavaScript heap, clearing the Zustand store. Every test that navigates after login would immediately lose auth and redirect to `/login`. The only workaround would be injecting the token via `cdp_eval("window.__useAuthStore.setState({accessToken: '...'})")` — which defeats the purpose of testing the real auth flow.
>
> Playwright's `browser.new_context()` maintains JS heap state across navigations within the same context. Its Python API also meshes with `asyncio_mode=auto` used throughout the existing test suite.
>
> The web-browser CDP skill remains useful for **manual debugging and exploration** during development, just not as the E2E test driver.

**Install:**
```bash
uv add --dev playwright
uv run playwright install chromium
```

#### 2.2 Test Directory Structure

```
tests/e2e/
  __init__.py
  conftest.py          # Session-scoped services, function-scoped browser contexts
  helpers.py           # login_as(), wait_for_text(), API client fixture
  pages/
    __init__.py
    login_page.py      # LoginPage POM
    dashboard_page.py  # DashboardPage POM
    uploads_page.py    # UploadsPage POM
    experiments_page.py
    search_page.py
    agents_page.py
  test_auth.py
  test_dashboard.py
  test_uploads.py
  test_experiments.py
  test_search.py
  test_agents.py
```

**Page Object Model** — one class per page, methods mirror user actions:

```python
# tests/e2e/pages/uploads_page.py
from playwright.async_api import Page

class UploadsPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self._page = page
        self._base_url = base_url

    async def goto(self) -> None:
        await self._page.goto(f"{self._base_url}/uploads")
        await self._page.wait_for_selector("[data-testid='uploads-table']")

    async def upload_file(self, file_path: str) -> None:
        await self._page.set_input_files("[data-testid='file-input']", file_path)
        await self._page.click("[data-testid='upload-submit']")

    async def first_upload_status(self) -> str:
        badge = self._page.locator("[data-testid='upload-status-badge']").first
        return await badge.inner_text()
```

#### 2.3 `conftest.py` — Process Management

**Critical patterns from review:**

```python
# tests/e2e/conftest.py
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "lablink.db"
E2E_BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:5173")
API_BASE_URL = os.getenv("E2E_API_URL", "http://localhost:8000")


def _wait_for_url(url: str, timeout_s: float = 30.0) -> None:
    """Poll url until HTTP 200 or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(url)
                if resp.status_code < 500:
                    return
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(0.5)
    raise TimeoutError(f"Service at {url} did not become ready within {timeout_s}s")


def _check_port_free(port: int) -> None:
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(
                f"Port {port} is already in use. Stop the conflicting process before running E2E."
            )


@pytest.fixture(scope="session")
def e2e_services() -> Generator[None, None, None]:
    """Start API + frontend, seed DB, yield, teardown."""
    # 1. Check ports
    _check_port_free(8000)
    _check_port_free(5173)

    # 2. Reset SQLite (delete db + WAL files)
    for path in [DB_PATH, DB_PATH.with_suffix(".db-shm"), DB_PATH.with_suffix(".db-wal")]:
        path.unlink(missing_ok=True)

    # 3. Run migrations
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=PROJECT_ROOT,
    )

    # 4. Seed
    subprocess.run(
        ["uv", "run", "python", "-m", "lablink.scripts.seed"],
        check=True,
        cwd=PROJECT_ROOT,
        env={**os.environ, "LABLINK_ENVIRONMENT": "test"},
    )

    # 5. Start API (factory form to avoid lru_cache stale settings)
    api_proc = subprocess.Popen(
        [
            "uv", "run", "uvicorn", "lablink.main:create_app",
            "--factory", "--host", "127.0.0.1", "--port", "8000",
        ],
        cwd=PROJECT_ROOT,
        start_new_session=True,  # enables os.killpg for full process group cleanup
        env={**os.environ, "LABLINK_ENVIRONMENT": "test"},
    )

    # 6. Start frontend
    fe_proc = subprocess.Popen(
        ["npm", "--prefix", "frontend", "run", "dev"],
        cwd=PROJECT_ROOT,
        start_new_session=True,
    )

    # 7. Wait for readiness
    _wait_for_url(f"{API_BASE_URL}/health")
    _wait_for_url(E2E_BASE_URL)

    try:
        yield
    finally:
        for proc in (api_proc, fe_proc):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()


@pytest.fixture
async def browser_context(e2e_services: None) -> Generator[BrowserContext, None, None]:
    """Function-scoped browser context — fresh JS heap per test."""
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(base_url=E2E_BASE_URL)
        yield context
        await context.close()
        await browser.close()


@pytest.fixture
async def page(browser_context: BrowserContext) -> Page:
    return await browser_context.new_page()


@pytest.fixture
async def authed_page(browser_context: BrowserContext) -> Page:
    """Page pre-authenticated via real API login call."""
    page = await browser_context.new_page()
    admin_email = os.getenv("E2E_ADMIN_EMAIL", "admin@lablink.local")
    admin_password = os.getenv("E2E_ADMIN_PASSWORD", "lablink")

    await page.goto("/login")
    await page.fill("[data-testid='email-input']", admin_email)
    await page.fill("[data-testid='password-input']", admin_password)
    await page.click("[data-testid='login-submit']")
    await page.wait_for_url("**/dashboard")
    return page
```

**Why function-scoped context, not session-scoped:**
- Auth token lives in Zustand memory → test A's `clearAuth()` contaminates test B
- With function scope, each test gets a fresh JS heap and performs its own login
- Login overhead: ~200ms per test (API round-trip + React re-render) — acceptable

#### 2.4 `data-testid` Attributes Required

Phase 1 must add `data-testid` attributes to key components before E2E tests can use stable selectors:

| Component | `data-testid` needed |
|---|---|
| `StatCard` | `stat-{label}` (e.g., `stat-total-uploads`) |
| `UploadStatusBadge` | `upload-status-badge` |
| `LoginPage` | `email-input`, `password-input`, `login-submit` |
| `UploadsPage` | `file-input`, `upload-submit`, `uploads-table` |
| `ExperimentsPage` | `create-experiment-btn`, `experiments-table` |
| `SearchPage` | `search-input`, `search-results` |

---

### Part 3 — E2E Coverage Map (Measurable)

| Test | Flow | Observable Assertion |
|---|---|---|
| `test_auth::test_register` | Fill register form → submit | URL becomes `/dashboard`, `[data-testid=stat-total-uploads]` visible within 5s |
| `test_auth::test_login_bad_password` | Login with wrong password | Error message containing "Invalid" visible, URL stays `/login` |
| `test_auth::test_logout` | Click logout button | URL becomes `/login` within 3s |
| `test_dashboard::test_stats_load` | Navigate to `/dashboard` | All 4 stat cards show numeric values ≥ 0 within 5s |
| `test_dashboard::test_uploads_list_populated` | Navigate to `/dashboard` | Recent uploads list contains ≥ 5 rows (matching seed data) |
| `test_dashboard::test_parse_success_stat` | Navigate to `/dashboard` | Parse success rate stat shows value < 100% (seed has 1 failed upload) |
| `test_uploads::test_upload_file` | Upload `tests/fixtures/spectrophotometer/nanodrop_sample.csv` | Upload row appears with `data-testid=upload-status-badge` text "parsed" within 10s |
| `test_uploads::test_failed_badge` | Navigate to uploads | At least one badge shows "failed" (from seed failed upload) |
| `test_experiments::test_create` | Click create, fill form | New row appears in experiments table |
| `test_experiments::test_link_upload` | Open experiment → link upload | Upload appears in experiment's uploads list |
| `test_search::test_query_returns_results` | Type "nanodrop" in search | At least 1 result row appears within 5s |
| `test_search::test_empty_state` | Type "zzznomatch" | "No results" text visible |
| `test_agents::test_empty_state` | Navigate to `/agents` | "No agents connected" text visible |

**SSE assertions** (skip until endpoint exists):
```python
@pytest.mark.skip(reason="SSE endpoint /api/v1/sse/updates not yet implemented")
async def test_dashboard_sse_heartbeat(...): ...
```

---

### Part 4 — CI Integration

#### 4.1 GitHub Actions Job

```yaml
# In .github/workflows/ci.yml

e2e:
  name: E2E Tests
  runs-on: ubuntu-latest
  needs: [lint, test]  # Only run if fast checks pass
  timeout-minutes: 20

  # Run on main merges + path-filtered PRs + manual trigger
  if: |
    github.ref == 'refs/heads/main' ||
    github.event_name == 'workflow_dispatch' ||
    (github.event_name == 'pull_request' && ...)
  # Note: path filter for PRs requires separate workflow or
  # use `paths` under the top-level `on.pull_request` block

  env:
    LABLINK_ENVIRONMENT: test
    LABLINK_SECRET_KEY: ${{ secrets.E2E_SECRET_KEY }}
    LABLINK_DEBUG: "false"
    LABLINK_DATABASE_URL: sqlite+aiosqlite:///./e2e.db
    E2E_ADMIN_EMAIL: admin@e2e.local
    E2E_ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}

  steps:
    - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683

    - name: Install Chrome
      id: setup-chrome
      uses: browser-actions/setup-chrome@v2
      with:
        chrome-version: stable

    - uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
        cache-dependency-glob: "uv.lock"

    - run: uv sync --locked --all-extras --dev

    - run: uv run playwright install chromium

    - uses: actions/setup-node@v4
      with:
        node-version: "20"
        cache: "npm"
        cache-dependency-path: frontend/package-lock.json

    - run: npm ci
      working-directory: frontend

    - name: Build frontend (static, more reliable than vite dev in CI)
      run: npm run build
      working-directory: frontend

    - name: Seed database
      run: |
        uv run alembic upgrade head
        uv run python -m lablink.scripts.seed

    - name: Start API
      run: |
        uv run uvicorn lablink.main:create_app \
          --factory --host 0.0.0.0 --port 8000 \
          --log-level warning > /tmp/uvicorn-e2e.log 2>&1 &

    - name: Start frontend (serve static build)
      run: npx serve -s dist -l 5173 &
      working-directory: frontend

    - name: Wait for services
      run: |
        for i in $(seq 1 30); do
          curl -sf http://localhost:8000/health && \
          curl -sf http://localhost:5173 && \
          echo "Services ready" && break
          echo "Waiting... $i/30"; sleep 2
        done

    - name: Run E2E tests
      timeout-minutes: 12
      run: uv run pytest tests/e2e/ -v -m e2e --timeout=60

    - name: Upload failure artifacts
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: e2e-failures-${{ github.run_id }}
        path: |
          tests/e2e/screenshots/
          /tmp/uvicorn-e2e.log
        retention-days: 3
        if-no-files-found: warn
```

#### 4.2 Path-Filtered PR E2E

Add to the top-level `on:` block to run E2E on PRs that touch browser-relevant files:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
    paths:
      - "frontend/**"
      - "src/lablink/routers/**"
      - "src/lablink/services/**"
      - "src/lablink/main.py"
      - "tests/e2e/**"
```

This avoids running E2E on every parser or schema change (expensive) while still catching CORS, proxy, and router registration regressions.

---

## Technical Considerations

### Auth Token Architecture

The Zustand `authStore.ts` stores the access token only in memory:
```typescript
// "On a hard refresh the token is lost and the app redirects to /login"
accessToken: string | null  // never localStorage, never sessionStorage
```

This means:
1. **Each E2E test must perform its own login** (via the `authed_page` fixture above)
2. **No shared browser session between test functions** — function-scoped `BrowserContext`
3. The `authed_page` fixture (~200ms) is the E2E equivalent of the unit test `auth_headers` fixture

### SQLite WAL File Cleanup

Must delete all three files on reset:
```python
for ext in [".db", ".db-shm", ".db-wal"]:
    (PROJECT_ROOT / f"lablink{ext}").unlink(missing_ok=True)
```

Leftover WAL files cause `"database disk image is malformed"` on the next open.

### pyproject.toml Marker Registration

```toml
[tool.pytest.ini_options]
addopts = "-m 'not e2e'"  # exclude E2E from make test
markers = [
    "e2e: browser-based end-to-end tests (requires running services)",
]
```

### No AWS Required

The E2E suite uses:
- `storage_backend=local` → files written to `./storage/`
- `use_celery=False` → parse runs synchronously (status is `parsed` immediately after upload)
- `use_elasticsearch=False` → in-memory search
- `use_redis=False` → no Redis
- SQLite → `lablink.db` deleted and recreated before each session

---

## Security Considerations

| Risk | Severity | Mitigation |
|---|---|---|
| CI screenshots expose JWT/API tokens | High | `retention-days: 3`; `--disable-dev-tools` flag; `echo "::add-mask::$token"` for generated tokens |
| Default `LABLINK_SECRET_KEY` in CI | High | Set via `secrets.E2E_SECRET_KEY` in GitHub Secrets, never use default |
| `debug=True` leaks exceptions | Medium | Set `LABLINK_DEBUG=false` in E2E CI job |
| Seed creates admin-role user | Medium | Guard `assert settings.is_dev` in seed.py before any writes |
| `.env.local` gitignore conflict | Medium | Use `.env.example` (committed) not `.env.local` |

---

## System-Wide Impact

- **New test directory** (`tests/e2e/`) excluded from `make test` via `addopts = "-m 'not e2e'"` in `pyproject.toml`
- **`data-testid` attributes** required on 6 component files before E2E selectors work
- **`Procfile`** added at project root (no impact on existing tooling)
- **`honcho`** added as dev dependency (`uv add --dev honcho`)
- **Playwright** added as dev dependency (`uv add --dev playwright`)
- **No changes to existing 1,423 tests** — fully backward compatible

---

## Acceptance Criteria

### Local-First Hardening
- [ ] `.env.example` committed with all `LABLINK_` vars documented, secret generation instructions inline
- [ ] `Procfile` committed, `honcho` in dev dependencies
- [ ] `make dev-local` starts API + frontend via honcho, `check-prereqs` + `check-ports` run first
- [ ] `make seed` creates demo data per the seed contract table above
- [ ] `make e2e` runs full suite from cold start (wipe → migrate → seed → start → test → teardown)

### E2E Infrastructure
- [ ] `tests/e2e/conftest.py` uses function-scoped `BrowserContext`, process group cleanup via `os.killpg`
- [ ] All 3 SQLite files cleaned on reset (`.db`, `.db-shm`, `.db-wal`)
- [ ] `authed_page` fixture performs real login via UI before each test
- [ ] Page Object Model classes for all 6 pages
- [ ] `data-testid` attributes added to StatCard, UploadStatusBadge, LoginPage, UploadsPage, ExperimentsPage, SearchPage

### E2E Test Coverage
- [ ] `test_auth.py`: register, bad-password error, login, logout — all with URL and DOM assertions
- [ ] `test_dashboard.py`: 4 stat cards load, uploads list ≥5 rows, parse rate <100%
- [ ] `test_uploads.py`: file upload → status badge "parsed" within 10s; failed badge visible from seed
- [ ] `test_experiments.py`: create + list + link upload
- [ ] `test_search.py`: query returns results, no-results state
- [ ] `test_agents.py`: empty state copy visible
- [ ] All SSE assertions marked `pytest.mark.skip` with explanation

### CI
- [ ] E2E job in `ci.yml` using `browser-actions/setup-chrome@v2`
- [ ] Static Vite build served with `npx serve` (not `vite dev`)
- [ ] `uvicorn` bound to `0.0.0.0`, uses `--factory`
- [ ] Artifacts uploaded on failure, `retention-days: 3`
- [ ] `secrets.E2E_SECRET_KEY` used, not default
- [ ] Path filter on `pull_request` event for relevant paths

---

## Dependencies & Risks

| Item | Note |
|---|---|
| Playwright Python | `uv add --dev playwright && uv run playwright install chromium` |
| honcho | `uv add --dev honcho` |
| `data-testid` attrs | Must be added to 6 components before E2E selectors work (Phase 1) |
| SSE endpoint missing | Scope SSE assertions out until endpoint is built |
| `npx serve` in CI | `npm ci` installs it; or add `serve` to `package.json` devDependencies |
| `E2E_SECRET_KEY` in GitHub Secrets | Must be created before CI job runs |

---

## Implementation Phases

### Phase 1: Local-First Hardening + Component Data-testids
1. Create `.env.example`
2. Create `Procfile`, add `honcho` + `playwright` to dev deps
3. Add `make dev-local`, `check-prereqs`, `check-ports`, `e2e` to Makefile
4. Create `src/lablink/scripts/__init__.py` + `seed.py`
5. Add `data-testid` attrs to 6 component files

### Phase 2: E2E Infrastructure
1. Create `tests/e2e/conftest.py` (process management, fixtures)
2. Create `tests/e2e/helpers.py`
3. Create `tests/e2e/pages/` POM classes (6 files)
4. Update `pyproject.toml` with `e2e` marker + `addopts`

### Phase 3: E2E Test Suites
1. `test_auth.py`
2. `test_dashboard.py`
3. `test_uploads.py`
4. `test_experiments.py`
5. `test_search.py`
6. `test_agents.py`

### Phase 4: CI Integration
1. Add E2E job to `.github/workflows/ci.yml`
2. Add path filters to `on.pull_request`
3. Create `secrets.E2E_SECRET_KEY` and `secrets.E2E_ADMIN_PASSWORD` in GitHub

---

## Files To Create / Modify

| File | Action |
|---|---|
| `.env.example` | Create — committed reference for all `LABLINK_` vars |
| `Procfile` | Create — `api` + `web` processes for honcho |
| `src/lablink/scripts/__init__.py` | Create (empty) |
| `src/lablink/scripts/seed.py` | Create — idempotent seeder with is_dev guard |
| `frontend/src/components/ui/card.tsx` | Modify — add `data-testid` to StatCard |
| `frontend/src/components/ui/badge.tsx` | Modify — add `data-testid` to UploadStatusBadge |
| `frontend/src/pages/LoginPage.tsx` | Modify — add `data-testid` to form fields |
| `frontend/src/pages/UploadsPage.tsx` | Modify — add `data-testid` to table + inputs |
| `frontend/src/pages/ExperimentsPage.tsx` | Modify — add `data-testid` to table + create btn |
| `frontend/src/pages/SearchPage.tsx` | Modify — add `data-testid` to search input + results |
| `tests/e2e/__init__.py` | Create |
| `tests/e2e/conftest.py` | Create — session services, function-scoped browser context |
| `tests/e2e/helpers.py` | Create |
| `tests/e2e/pages/*.py` | Create × 6 — Page Object Model classes |
| `tests/e2e/test_auth.py` | Create |
| `tests/e2e/test_dashboard.py` | Create |
| `tests/e2e/test_uploads.py` | Create |
| `tests/e2e/test_experiments.py` | Create |
| `tests/e2e/test_search.py` | Create |
| `tests/e2e/test_agents.py` | Create |
| `Makefile` | Modify — add `dev-local`, `e2e`, `check-prereqs`, `check-ports` |
| `pyproject.toml` | Modify — `e2e` marker, `addopts = "-m 'not e2e'"` |
| `.github/workflows/ci.yml` | Modify — add E2E job, path filters |
| `README.md` | Modify — local quickstart, E2E instructions |

---

## Sources & References

- Architecture review: auth token in Zustand memory (`frontend/src/store/authStore.ts:7`)
- SSE endpoint missing: `grep -r "sse" src/lablink/routers/` returns nothing
- Config local defaults: `src/lablink/config.py:59-91`
- FK ordering: `src/lablink/models/` (all 16 model files)
- seed script patterns: `src/lablink/services/auth_service.py:47`, `upload_service.py:57-83,197`
- Process manager: honcho v2.0.0 (Oct 2024), `uv add --dev honcho`
- CI Chrome: `browser-actions/setup-chrome@v2`
- Playwright Python: `uv add --dev playwright && uv run playwright install chromium`
- Existing test patterns: `tests/test_integration/conftest.py`
- Web-browser CDP skill: `~/.claude/skills/web-browser/SKILL.md` (retained for manual debugging)
