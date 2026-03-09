"""E2E tests: Agents page."""

import pytest
from playwright.sync_api import Page

from tests.e2e.pages.agents_page import AgentsPage

pytestmark = pytest.mark.e2e


def test_agents_page_renders(auth_page: Page) -> None:
    """Agents page loads successfully."""
    ap = AgentsPage(auth_page)
    ap.navigate()
    assert ap.is_loaded()


def test_agents_page_heading(auth_page: Page) -> None:
    """Agents heading says 'Agents'."""
    ap = AgentsPage(auth_page)
    ap.navigate()
    assert auth_page.locator("h2").filter(has_text="Agents").count() >= 1


def test_agents_empty_state_or_grid(auth_page: Page) -> None:
    """Either the empty state or the agent grid is visible."""
    ap = AgentsPage(auth_page)
    ap.navigate()
    empty_state = auth_page.locator("text=No agents connected")
    grid = ap.agent_grid
    empty_state.or_(grid).wait_for(state="visible", timeout=5_000)
    assert empty_state.count() > 0 or grid.count() > 0


def test_agents_sse_indicator_visible(auth_page: Page) -> None:
    """SSE connection status indicator is rendered."""
    ap = AgentsPage(auth_page)
    ap.navigate()
    # The SSE indicator shows "Live" or "Connecting..."
    indicator = auth_page.locator("text=Live").or_(
        auth_page.locator("text=Connecting...")
    )
    assert indicator.count() >= 1
