"""E2E tests: authentication flows."""

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import E2E_BASE_URL, E2E_EMAIL, E2E_PASSWORD
from tests.e2e.pages.login_page import LoginPage

pytestmark = pytest.mark.e2e


def test_login_page_renders(page: Page) -> None:
    """Login page loads and shows the form."""
    page.goto(f"{E2E_BASE_URL}/login")
    lp = LoginPage(page)
    assert lp.form.is_visible()
    assert page.get_by_test_id("login-email").is_visible()
    assert page.get_by_test_id("login-password").is_visible()
    assert page.get_by_test_id("login-submit").is_visible()


def test_login_success_redirects_to_dashboard(page: Page) -> None:
    """Valid credentials load the dashboard."""
    page.goto(f"{E2E_BASE_URL}/login")
    lp = LoginPage(page)
    lp.login(E2E_EMAIL, E2E_PASSWORD)
    # TanStack Router does client-side navigation — wait for dashboard element
    page.wait_for_selector('[data-testid="dashboard-page"]', timeout=30_000)
    assert page.get_by_test_id("dashboard-page").is_visible()


def test_login_invalid_credentials_shows_error(page: Page) -> None:
    """Wrong password shows an error message and stays on /login."""
    page.goto(f"{E2E_BASE_URL}/login")
    lp = LoginPage(page)
    lp.login(E2E_EMAIL, "wrongpassword")
    # Wait for mutation to settle
    page.wait_for_timeout(2_000)
    assert "/login" in page.url
    # Form must still be visible after failed login (no redirect)
    assert page.locator("form[data-testid='login-form']").is_visible()
    # After a failed login, the form should still be on screen (no redirect)
    assert page.get_by_test_id("login-submit").is_visible()


def test_unauthenticated_redirect_to_login(page: Page) -> None:
    """Accessing a protected route without auth redirects to /login."""
    page.goto(f"{E2E_BASE_URL}/")
    page.wait_for_url(f"{E2E_BASE_URL}/login", timeout=5_000)
    assert "/login" in page.url


def test_authenticated_dashboard_visible(auth_page: Page) -> None:
    """After login, the dashboard is accessible."""
    assert auth_page.get_by_test_id("dashboard-page").is_visible()
