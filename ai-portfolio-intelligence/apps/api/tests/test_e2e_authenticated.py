import os

import pytest

playwright = pytest.importorskip("playwright")


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

        page = browser.new_page()
        try:
            page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=30_000)
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            page.get_by_role("button", name="Sign in").click()
            page.wait_for_url(lambda url: "/login" not in url, timeout=30_000)

            page.goto(f"{base_url}/portfolio", wait_until="domcontentloaded", timeout=30_000)
            assert "/login" not in page.url
            assert page.get_by_role("heading", name="Sign in").count() == 0
        except Exception as exc:
            pytest.fail(f"Authenticated E2E failed: {exc}")
        finally:
            browser.close()
