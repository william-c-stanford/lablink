"""Page Object Model for / (Dashboard)."""

from __future__ import annotations

from playwright.sync_api import Page


class DashboardPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self) -> None:
        """Navigate to dashboard via sidebar link (preserves Zustand auth token)."""
        self.page.locator("nav a", has_text="Dashboard").first.click()
        self.page.wait_for_selector('[data-testid="dashboard-page"]', timeout=10_000)

    @property
    def root(self):
        return self.page.get_by_test_id("dashboard-page")

    @property
    def stats_row(self):
        return self.page.get_by_test_id("stats-row")

    def is_loaded(self) -> bool:
        return self.root.is_visible()

    def heading_text(self) -> str:
        return self.page.locator("h2").first.inner_text()
