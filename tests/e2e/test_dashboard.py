"""E2E tests: Dashboard page."""

import pytest
from playwright.sync_api import Page

from tests.e2e.pages.dashboard_page import DashboardPage

pytestmark = pytest.mark.e2e


def test_dashboard_renders(auth_page: Page) -> None:
    """Dashboard page loads with stats row and heading."""
    dp = DashboardPage(auth_page)
    assert dp.is_loaded()
    assert dp.stats_row.is_visible()


def test_dashboard_heading(auth_page: Page) -> None:
    """Dashboard heading says 'Dashboard'."""
    dp = DashboardPage(auth_page)
    assert "Dashboard" in dp.heading_text()


def test_dashboard_stat_cards_visible(auth_page: Page) -> None:
    """Four stat cards are rendered in the stats row."""
    dp = DashboardPage(auth_page)
    assert dp.stats_row.is_visible()
    assert auth_page.locator("text=Total Uploads").count() >= 1


def test_dashboard_recent_uploads_section(auth_page: Page) -> None:
    """Recent Uploads card is present on the dashboard."""
    assert auth_page.locator("text=Recent Uploads").count() >= 1


def test_dashboard_agent_status_section(auth_page: Page) -> None:
    """Agent Status card is present on the dashboard."""
    assert auth_page.locator("text=Agent Status").count() >= 1
