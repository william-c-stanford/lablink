"""Shared helpers for E2E tests."""

from __future__ import annotations

from playwright.sync_api import Page


def screenshot_on_failure(page: Page, name: str) -> None:
    """Save a screenshot to /tmp for CI artifact upload."""
    path = f"/tmp/e2e-failure-{name}.png"
    try:
        page.screenshot(path=path)
        print(f"Screenshot saved: {path}")
    except Exception:  # noqa: BLE001
        pass


def wait_for_no_spinner(page: Page, timeout: int = 15_000) -> None:
    """Wait until no Spinner components are visible."""
    # Spinners have role="status" or a known class; fall back to a short wait
    try:
        page.wait_for_selector("[data-testid='spinner']", state="detached", timeout=timeout)
    except Exception:  # noqa: BLE001
        pass
