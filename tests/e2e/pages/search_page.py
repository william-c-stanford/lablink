"""Page Object Model for /search."""

from __future__ import annotations

from playwright.sync_api import Page


class SearchPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self) -> None:
        """Navigate via sidebar link (preserves Zustand auth token)."""
        self.page.locator("nav a", has_text="Search").first.click()
        self.page.wait_for_selector('[data-testid="search-page"]', timeout=10_000)

    @property
    def root(self):
        return self.page.get_by_test_id("search-page")

    @property
    def search_input(self):
        return self.page.get_by_test_id("search-input")

    @property
    def results(self):
        return self.page.get_by_test_id("search-results")

    def is_loaded(self) -> bool:
        return self.root.is_visible()

    def search(self, query: str) -> None:
        self.search_input.fill(query)
