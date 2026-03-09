"""Page Object Model for /experiments."""

from __future__ import annotations

from playwright.sync_api import Page


class ExperimentsPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self) -> None:
        """Navigate via sidebar link (preserves Zustand auth token)."""
        self.page.locator("nav a", has_text="Experiments").first.click()
        self.page.wait_for_selector('[data-testid="experiments-page"]', timeout=10_000)

    @property
    def root(self):
        return self.page.get_by_test_id("experiments-page")

    @property
    def create_btn(self):
        return self.page.get_by_test_id("create-experiment-btn")

    @property
    def experiment_list(self):
        return self.page.get_by_test_id("experiment-list")

    def is_loaded(self) -> bool:
        return self.root.is_visible()

    def open_create_dialog(self) -> None:
        self.create_btn.click()

    def fill_intent(self, intent: str) -> None:
        el = self.page.locator("#exp-intent")
        el.click()
        # press_sequentially triggers real keystroke events React's onChange responds to
        el.press_sequentially(intent, delay=20)

    def submit_create(self) -> None:
        self.page.get_by_test_id("create-experiment-submit").click()
