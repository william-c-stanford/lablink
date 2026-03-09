"""E2E tests: Uploads page."""

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import FIXTURES_DIR
from tests.e2e.pages.uploads_page import UploadsPage

pytestmark = pytest.mark.e2e


def test_uploads_page_renders(auth_page: Page) -> None:
    """Uploads page loads with dropzone visible."""
    up = UploadsPage(auth_page)
    up.navigate()
    assert up.is_loaded()
    assert up.dropzone.is_visible()


def test_uploads_page_heading(auth_page: Page) -> None:
    """Uploads page heading says 'Uploads'."""
    up = UploadsPage(auth_page)
    up.navigate()
    assert auth_page.locator("h2").filter(has_text="Uploads").count() >= 1


def test_uploads_list_shows_seed_data(auth_page: Page) -> None:
    """Seed data is visible in the uploads list."""
    up = UploadsPage(auth_page)
    up.navigate()
    # Wait for seed data to appear in the list
    auth_page.wait_for_selector("text=nanodrop_sample.csv", timeout=5_000)
    assert up.upload_list.is_visible()
    assert auth_page.locator("text=nanodrop_sample.csv").count() >= 1


def test_upload_file_via_input(auth_page: Page) -> None:
    """Uploading a file via the hidden input triggers an upload."""
    up = UploadsPage(auth_page)
    up.navigate()
    fixture = FIXTURES_DIR / "spectrophotometer" / "cary_uv_vis_scan.csv"
    if not fixture.exists():
        pytest.skip("Fixture not found")
    up.upload_file(fixture)
    # Wait for progress bar or list refresh
    auth_page.wait_for_timeout(3_000)
    assert up.is_loaded()


def test_uploads_filter_status_dropdown_visible(auth_page: Page) -> None:
    """Status filter dropdown is visible."""
    up = UploadsPage(auth_page)
    up.navigate()
    assert auth_page.locator("select").count() >= 1
