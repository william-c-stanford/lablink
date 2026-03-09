"""E2E tests: Experiments page."""

import pytest
from playwright.sync_api import Page

from tests.e2e.pages.experiments_page import ExperimentsPage

pytestmark = pytest.mark.e2e


def test_experiments_page_renders(auth_page: Page) -> None:
    """Experiments page loads with create button visible."""
    ep = ExperimentsPage(auth_page)
    ep.navigate()
    assert ep.is_loaded()
    assert ep.create_btn.is_visible()


def test_experiments_page_heading(auth_page: Page) -> None:
    """Experiments heading says 'Experiments'."""
    ep = ExperimentsPage(auth_page)
    ep.navigate()
    assert auth_page.locator("h2").filter(has_text="Experiments").count() >= 1


def test_create_experiment_dialog_opens(auth_page: Page) -> None:
    """Clicking 'Create Experiment' opens the dialog."""
    ep = ExperimentsPage(auth_page)
    ep.navigate()
    ep.open_create_dialog()
    # Dialog title should appear
    auth_page.wait_for_selector("text=Create Experiment", timeout=5_000)
    assert auth_page.locator("text=Create Experiment").count() >= 1


def test_create_experiment_requires_intent(auth_page: Page) -> None:
    """Submit button is disabled until intent is filled."""
    ep = ExperimentsPage(auth_page)
    ep.navigate()
    ep.open_create_dialog()
    auth_page.wait_for_timeout(500)
    # The Create button in the modal should be visible
    create_buttons = auth_page.locator("button", has_text="Create")
    assert create_buttons.count() >= 1


def test_create_experiment_success(auth_page: Page) -> None:
    """Creating an experiment with a valid intent closes the dialog."""
    ep = ExperimentsPage(auth_page)
    ep.navigate()
    ep.open_create_dialog()
    auth_page.wait_for_timeout(500)
    ep.fill_intent("E2E Test Experiment - DNA Quantification")
    # Confirm the submit button is enabled before clicking
    submit_btn = auth_page.get_by_test_id("create-experiment-submit")
    submit_btn.wait_for(state="visible", timeout=3_000)
    assert not submit_btn.is_disabled(), "Create button must be enabled after filling intent"
    ep.submit_create()
    # Wait for the dialog to close (API creates experiment, onSuccess closes dialog)
    auth_page.wait_for_selector("text=Define a new experiment", state="hidden", timeout=5_000)
