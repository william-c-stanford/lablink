"""Page Object Model for /login."""

from __future__ import annotations

from playwright.sync_api import Page


class LoginPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def goto(self) -> None:
        from tests.e2e.conftest import E2E_BASE_URL
        self.page.goto(f"{E2E_BASE_URL}/login")

    def fill_credentials(self, email: str, password: str) -> None:
        self.page.get_by_test_id("login-email").fill(email)
        self.page.get_by_test_id("login-password").fill(password)

    def submit(self) -> None:
        self.page.get_by_test_id("login-submit").click()

    def login(self, email: str, password: str) -> None:
        self.fill_credentials(email, password)
        self.submit()

    @property
    def form(self):
        return self.page.get_by_test_id("login-form")

    @property
    def error_text(self) -> str | None:
        el = self.page.locator("[style*='color: #ef4444']").first
        if el.is_visible():
            return el.inner_text()
        return None
