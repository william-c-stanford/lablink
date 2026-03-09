"""Page Object Model for /agents."""

from __future__ import annotations

from playwright.sync_api import Page


class AgentsPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self) -> None:
        """Navigate via sidebar link (preserves Zustand auth token)."""
        self.page.locator("nav a", has_text="Agents").first.click()
        self.page.wait_for_selector('[data-testid="agents-page"]', timeout=10_000)

    @property
    def root(self):
        return self.page.get_by_test_id("agents-page")

    @property
    def agent_grid(self):
        return self.page.get_by_test_id("agent-grid")

    def is_loaded(self) -> bool:
        return self.root.is_visible()
