"""Page Object Model for /uploads."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page


class UploadsPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self) -> None:
        """Navigate to uploads via sidebar link (preserves Zustand auth token)."""
        self.page.locator("nav a", has_text="Uploads").first.click()
        self.page.wait_for_selector('[data-testid="uploads-page"]', timeout=10_000)

    @property
    def root(self):
        return self.page.get_by_test_id("uploads-page")

    @property
    def dropzone(self):
        return self.page.get_by_test_id("upload-dropzone")

    @property
    def upload_list(self):
        return self.page.get_by_test_id("upload-list")

    def is_loaded(self) -> bool:
        return self.root.is_visible()

    def upload_file(self, fixture_path: Path) -> None:
        """Trigger a file upload by setting the hidden file input."""
        file_input = self.page.locator('input[type="file"]')
        file_input.set_input_files(str(fixture_path))
