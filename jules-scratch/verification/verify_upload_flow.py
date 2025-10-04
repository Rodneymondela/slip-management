import re
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def run_verification(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Base URL for the running Flask application
        base_url = "http://127.0.0.1:5000"

        # --- 1. Register a new user ---
        print("Navigating to registration page...")
        page.goto(f"{base_url}/auth/register")

        # Fill out the registration form using placeholders
        page.get_by_placeholder("Email address").fill("test@example.com")
        page.get_by_placeholder("Password (min. 8 characters)").fill("password123")

        # Click the register button
        page.get_by_role("button", name="Create account").click()
        print("Registration submitted.")

        # --- 2. Log in ---
        print("Navigating to login page...")
        page.goto(f"{base_url}/auth/login")

        # Fill out the login form using placeholders
        page.get_by_placeholder("Email address").fill("test@example.com")
        page.get_by_placeholder("Password").fill("password123")

        # Click the login button
        page.get_by_role("button", name="Sign in").click()
        print("Login submitted.")

        # Wait for navigation to the dashboard and expect a welcome message
        expect(page.get_by_role("heading", name="Welcome back!")).to_be_visible()
        print("Successfully logged in.")

        # --- 3. Upload a document ---
        print("Navigating to upload page...")
        page.goto(f"{base_url}/uploads")

        # Use an absolute path to the fixture file
        file_path = "/app/tests/fixtures/receipt.png"

        print("Waiting for file chooser...")
        with page.expect_file_chooser() as fc_info:
            # Click the element that triggers the file chooser
            page.get_by_text("Upload a file").click()

        file_chooser = fc_info.value
        file_chooser.set_files(file_path)
        print(f"File chooser handled for: {file_path}")

        # Click the upload button
        page.get_by_role("button", name="Upload Document").click()
        print("Upload submitted.")

        # --- 4. Wait for processing and redirection ---
        print("Waiting for document processing...")
        # The processing page should poll and redirect automatically.
        # We expect to land on the "Confirm Details" page.
        expect(page.get_by_role("heading", name="Confirm Details")).to_be_visible(timeout=60000)
        print("Redirected to confirmation page.")

        # --- 5. Verify content on the confirmation page ---
        print("Verifying form fields...")

        # Check Supplier Name (should be something like "TAPINGO")
        expect(page.get_by_label("Supplier")).to_have_value(re.compile("TAPINGO", re.IGNORECASE))

        # Check Total Amount (should be 7.29)
        expect(page.get_by_label("Total (R)")).to_have_value("7.29")

        print("Form fields verified successfully.")

        # --- 6. Take a screenshot ---
        screenshot_path = "jules-scratch/verification/verification.png"
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")

    except Exception as e:
        print(f"An error occurred: {e}")
        # Save a screenshot on failure for debugging
        page.screenshot(path="jules-scratch/verification/error.png")
        raise
    finally:
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run_verification(playwright)