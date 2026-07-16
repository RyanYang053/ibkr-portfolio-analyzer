import json
import os

import pytest

playwright = pytest.importorskip("playwright")


@pytest.mark.skipif(os.getenv("RUN_AUTHENTICATED_E2E") != "true", reason="Authenticated E2E runs in dedicated CI job")
def test_login_form_submits_and_reaches_portfolio():
    from playwright.sync_api import sync_playwright

    base_url = os.getenv("E2E_BASE_URL", "http://localhost:3000")
    email = os.getenv("E2E_EMAIL", "e2e@example.com")
    password = os.getenv("E2E_PASSWORD", "e2e-password")

    with sync_playwright() as playwright_context:
        try:
            browser = playwright_context.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright chromium browser not installed: {exc}")

        page = browser.new_page()
        try:
            page.goto(f"{base_url}/login", wait_until="networkidle", timeout=60_000)
            email_input = page.locator("#login-email")
            email_input.wait_for(state="visible", timeout=30_000)
            # Wait for client hydration so the controlled input is editable.
            page.wait_for_function(
                """() => {
                  const el = document.querySelector('#login-email');
                  return !!(el && !el.disabled && !el.readOnly);
                }""",
                timeout=30_000,
            )
            email_input.click()
            email_input.fill(email)
            page.locator("#login-password").fill(password)
            page.get_by_role("button", name="Sign in").click()
            page.wait_for_url("**/portfolio**", timeout=30_000)
            assert page.get_by_role("heading", name="Sign in").count() == 0
        except Exception as exc:
            pytest.fail(f"Login form E2E failed: {exc}")
        finally:
            browser.close()


@pytest.mark.skipif(os.getenv("RUN_AUTHENTICATED_E2E") != "true", reason="Authenticated E2E runs in dedicated CI job")
def test_login_redirects_to_protected_portfolio_view():
    from playwright.sync_api import sync_playwright

    base_url = os.getenv("E2E_BASE_URL", "http://localhost:3000")
    email = os.getenv("E2E_EMAIL", "e2e@example.com")
    password = os.getenv("E2E_PASSWORD", "e2e-password")

    with sync_playwright() as playwright_context:
        try:
            browser = playwright_context.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright chromium browser not installed: {exc}")

        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        try:
            login_response = page.request.post(
                f"{base_url}/api/auth/login",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"email": email, "password": password}),
            )
            assert login_response.ok, login_response.text()

            page.goto(f"{base_url}/portfolio", wait_until="domcontentloaded", timeout=30_000)
            assert "/login" not in page.url
            assert page.get_by_role("heading", name="Sign in").count() == 0
        except Exception as exc:
            pytest.fail(f"Authenticated E2E failed: {exc}")
        finally:
            browser.close()
