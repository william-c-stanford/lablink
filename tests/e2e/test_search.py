"""E2E tests: Search page."""

import pytest
from playwright.sync_api import Page

from tests.e2e.pages.search_page import SearchPage

pytestmark = pytest.mark.e2e


def test_search_page_renders(auth_page: Page) -> None:
    """Search page loads with the search input visible."""
    sp = SearchPage(auth_page)
    sp.navigate()
    assert sp.is_loaded()
    assert sp.search_input.is_visible()


def test_search_page_heading(auth_page: Page) -> None:
    """Search heading says 'Search'."""
    sp = SearchPage(auth_page)
    sp.navigate()
    assert auth_page.locator("h2").filter(has_text="Search").count() >= 1


def test_search_empty_state(auth_page: Page) -> None:
    """Empty state is shown when no query is entered."""
    sp = SearchPage(auth_page)
    sp.navigate()
    assert auth_page.locator("text=Start typing to search").count() >= 1


def test_search_query_updates_input(auth_page: Page) -> None:
    """Typing in the search input updates the value."""
    sp = SearchPage(auth_page)
    sp.navigate()
    sp.search("nanodrop")
    assert sp.search_input.input_value() == "nanodrop"


def test_search_shows_results_or_no_results(auth_page: Page) -> None:
    """After typing a query, results or a no-results message appears."""
    sp = SearchPage(auth_page)
    sp.navigate()
    sp.search("DNA")
    # Wait for debounce + API response
    auth_page.wait_for_timeout(1_500)
    has_results = sp.results.count() > 0
    has_no_results = auth_page.locator("text=No results found").count() > 0
    assert has_results or has_no_results
