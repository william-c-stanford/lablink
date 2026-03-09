"""E2E test configuration and fixtures.

Session-scoped fixture starts the API + frontend servers, seeds the database,
waits for both to be healthy, then yields. Each test gets its own Playwright
BrowserContext so tests are isolated (no shared cookies or in-memory state).

Run via::

    make e2e
    # or
    uv run pytest tests/e2e/ -v -m e2e
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

# Skip this entire module if Playwright is not installed
playwright = pytest.importorskip("playwright", reason="playwright not installed — run: uv run playwright install chromium")
from playwright.sync_api import BrowserContext, Page, sync_playwright  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "lablink.db"
API_BASE_URL = "http://localhost:8000"
E2E_BASE_URL = "http://localhost:5173"

# Credentials inserted by seed.py
E2E_EMAIL = "demo@example.com"
E2E_PASSWORD = "demodemo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_url(url: str, timeout: int = 60) -> None:
    """Poll url until it returns HTTP 2xx, or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code < 500:
                return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(0.5)
    raise TimeoutError(
        f"Service at {url} did not become healthy within {timeout}s. "
        f"Last error: {last_exc}"
    )


def _kill(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()


# ---------------------------------------------------------------------------
# Session fixture — starts services once for the whole test run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_services() -> Generator[None, None, None]:
    """Start API + frontend, seed DB. Teardown on exit."""

    # Kill any stale processes on our ports before starting fresh
    import subprocess as _sub
    for port in (8000, 5173):
        _sub.run(
            f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true",
            shell=True,
        )

    # Clean slate — remove WAL files or SQLite gets confused
    for suffix in ("", "-shm", "-wal"):
        p = DB_PATH.with_suffix(f".db{suffix}")
        p.unlink(missing_ok=True)

    env = {**os.environ, "LABLINK_DATABASE_URL": f"sqlite+aiosqlite:///{DB_PATH}"}

    # Run migrations
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=PROJECT_ROOT,
        env=env,
    )

    # Seed demo data
    subprocess.run(
        ["uv", "run", "python", "-m", "lablink.scripts.seed"],
        check=True,
        cwd=PROJECT_ROOT,
        env=env,
    )

    # Start API server — use DEVNULL so the pipe buffer never fills and blocks uvicorn
    api_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "lablink.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Start frontend dev server
    fe_env = {**os.environ, "VITE_API_BASE_URL": API_BASE_URL}
    fe_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", "5173"],
        cwd=PROJECT_ROOT / "frontend",
        env=fe_env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_url(f"{API_BASE_URL}/health")
        _wait_for_url(E2E_BASE_URL)
        yield
    finally:
        _kill(api_proc)
        _kill(fe_proc)


# ---------------------------------------------------------------------------
# Per-test browser context + page
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_type_launch_args() -> dict[str, Any]:
    return {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance, browser_type_launch_args):
    b = playwright_instance.chromium.launch(**browser_type_launch_args)
    yield b
    b.close()


@pytest.fixture()
def context(browser, e2e_services) -> Generator[BrowserContext, None, None]:
    """Fresh browser context per test — isolates in-memory Zustand state."""
    ctx = browser.new_context(base_url=E2E_BASE_URL)
    yield ctx
    ctx.close()


@pytest.fixture()
def page(context: BrowserContext) -> Page:
    return context.new_page()


# ---------------------------------------------------------------------------
# Authenticated page fixture — already logged in
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_page(page: Page) -> Page:
    """Return a Page that has already completed the login flow."""
    page.goto(f"{E2E_BASE_URL}/login")
    page.get_by_test_id("login-email").fill(E2E_EMAIL)
    page.get_by_test_id("login-password").fill(E2E_PASSWORD)
    page.get_by_test_id("login-submit").click()
    # TanStack Router uses client-side navigation; wait for dashboard element
    # Use 30s timeout to account for API latency on first requests
    try:
        page.wait_for_selector('[data-testid="dashboard-page"]', timeout=30_000)
    except Exception:
        # Capture screenshot and current URL for debugging
        try:
            page.screenshot(path="/tmp/e2e-auth-failure.png")
        except Exception:
            pass
        raise
    return page
