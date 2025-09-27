import pytest
from playwright.sync_api import sync_playwright, Page, expect
import time

def run_verification(page: Page):
    """
    This script verifies the UI enhancements by registering a new user,
    logging in, and taking screenshots of the key redesigned pages.
    """
    base_url = "http://127.0.0.1:5000"

    # 1. Register a new user
    page.goto(f"{base_url}/auth/register")
    expect(page).to_have_title("Register - SlipTrack")
    page.get_by_placeholder("Email address").fill("testuser@example.com")
    page.get_by_placeholder("Password (min. 8 characters)").fill("password123")
    page.get_by_role("button", name="Create account").click()

    # After registration, we should be on the login page
    expect(page).to_have_title("Login - SlipTrack")

    # 2. Log in with the new user
    page.get_by_placeholder("Email address").fill("testuser@example.com")
    page.get_by_placeholder("Password").fill("password123")
    page.get_by_role("button", name="Sign in").click()

    # 3. Verify the dashboard and take a screenshot
    expect(page).to_have_title("Dashboard - SlipTrack")
    expect(page.get_by_role("heading", name="Welcome back!")).to_be_visible()
    page.screenshot(path="jules-scratch/verification/dashboard.png")

    # 4. Navigate to the journal page and take a screenshot
    page.get_by_role("link", name="Journal").click()
    expect(page).to_have_title("Journal - SlipTrack")
    expect(page.get_by_role("heading", name="Journal")).to_be_visible()
    page.screenshot(path="jules-scratch/verification/journal_list.png")

    # 5. Navigate to the upload page and take a screenshot
    page.get_by_role("link", name="Upload").click()
    expect(page).to_have_title("Upload - SlipTrack")
    expect(page.get_by_role("heading", name="Upload a new document")).to_be_visible()
    page.screenshot(path="jules-scratch/verification/upload_page.png")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        run_verification(page)
        browser.close()

if __name__ == "__main__":
    main()