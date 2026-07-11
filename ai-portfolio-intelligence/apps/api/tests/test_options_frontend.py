import os

import pytest

playwright = pytest.importorskip("playwright")

@pytest.mark.skipif(os.getenv("SKIP_FRONTEND_TESTS") == "true", reason="Skip frontend tests")
def test_options_tab_lazy_loading_and_mock_warning():
    from playwright.sync_api import sync_playwright
    # 1. Start playwright and browser
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright chromium browser not installed: {exc}")
            return
            
        context = browser.new_context()
        page = context.new_page()

        # Track requests to /options-strategy
        options_strategy_requested = []

        def handle_request(route):
            request = route.request
            if "options-strategy" in request.url:
                options_strategy_requested.append(request.url)
                # Mock a successful mock options response
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body="""{
                        "symbol": "MSFT",
                        "stock_price": 420.50,
                        "implied_volatility": 0.28,
                        "iv_percentile": 42,
                        "implied_move_percent": 6.2,
                        "strategies": [
                            {
                                "name": "Covered Call (Educational Candidate)",
                                "type": "income",
                                "expiration": "2026-07-16",
                                "strikes": "Sell $430.00 Call",
                                "net_credit_debit": 5.40,
                                "max_profit": "$1,490.00",
                                "max_loss": "$41,510.00",
                                "breakeven": 415.10,
                                "probability_of_profit": 62,
                                "rationale": "Moderate upside potential with attractive premium income.",
                                "eligible": true,
                                "eligibility_reason": "Eligible (holding at least 100 shares)."
                            }
                        ],
                        "market_sentiment": "Moderate volatility with slightly bullish bias.",
                        "human_review_required": true,
                        "disclaimer": "This options strategy is for educational purposes only.",
                        "provider": "gemini:gemini-2.5-flash",
                        "asOf": "2026-06-16T10:32:00Z",
                        "dataSource": "Mock",
                        "isMock": true,
                        "quoteDelaySeconds": 15,
                        "warnings": ["Simulated data — not suitable for trading decisions."]
                    }"""
                )
            else:
                route.continue_()

        # Set up route intercept
        page.route("**/*", handle_request)

        # 2. Load the main stock detail page (Research tab is default)
        try:
            page.goto("http://localhost:3000/holdings/MSFT")
            page.wait_for_load_state("networkidle")
        except Exception as exc:
            # If server is not running or slow in pytest test run environment, skip
            browser.close()
            pytest.skip(f"Frontend server not reachable at http://localhost:3000/holdings/MSFT: {exc}")
            return

        # Check that the /options-strategy request was NOT sent yet (lazy loading)
        assert len(options_strategy_requested) == 0, "Options API should not be fetched on initial page load"

        # Check that the compliance disclaimer for options is not visible yet
        assert not page.locator("text=Options Risk Disclosure & Disclaimer").is_visible()

        # 3. Click the Options Strategy tab
        options_tab = page.locator("a:has-text('Options Strategy')")
        assert options_tab.is_visible()
        options_tab.click()

        # Wait for the option strategy dashboard to load and verify the API call was made
        page.wait_for_selector("text=Educational Options Strategy Candidates")
        assert len(options_strategy_requested) > 0, "Options API should be fetched when tab is clicked"

        # 4. Verify mock warning banner appears (since isMock is true)
        mock_banner = page.locator("text=Simulated Data — Not Suitable for Trading Decisions")
        assert mock_banner.is_visible(), "Mock banner should be visible when isMock is true"

        # 5. Verify strategy card details are rendered correctly
        assert page.locator("text=Covered Call (Educational Candidate)").is_visible()
        assert page.locator("text=Sell $430.00 Call").is_visible()
        assert page.locator("text=$1,490.00").is_visible()  # Max profit
        assert page.locator("text=$41,510.00").is_visible() # Max loss
        assert page.locator("text=415.10").is_visible()    # Breakeven

        # Verify eligibility is displayed
        assert page.locator("text=Account Eligibility Check").is_visible()
        assert page.locator("text=Eligible (holding at least 100 shares)").is_visible()

        # 6. Verify compliance disclosure is always visible on options view
        assert page.locator("text=Options Risk Disclosure & Disclaimer").is_visible()
        assert page.locator("text=total premium loss").is_visible()
        assert page.locator("text=Assignment risk").is_visible()

        # 7. Check non-mock condition: mock isMock=false and ensure warning banner is hidden
        options_strategy_requested.clear()
        def handle_real_request(route):
            if "options-strategy" in route.request.url:
                options_strategy_requested.append(route.request.url)
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body="""{
                        "symbol": "MSFT",
                        "stock_price": 420.50,
                        "implied_volatility": 0.28,
                        "iv_percentile": 42,
                        "implied_move_percent": 6.2,
                        "strategies": [
                            {
                                "name": "Covered Call (Educational Candidate)",
                                "type": "income",
                                "expiration": "2026-07-16",
                                "strikes": "Sell $430.00 Call",
                                "net_credit_debit": 5.40,
                                "max_profit": "$1,490.00",
                                "max_loss": "$41,510.00",
                                "breakeven": 415.10,
                                "probability_of_profit": 62,
                                "rationale": "Moderate upside potential with attractive premium income.",
                                "eligible": true,
                                "eligibility_reason": "Eligible (holding at least 100 shares)."
                            }
                        ],
                        "market_sentiment": "Moderate volatility.",
                        "human_review_required": true,
                        "disclaimer": "This options strategy is for educational purposes only.",
                        "provider": "gemini:gemini-2.5-flash",
                        "asOf": "2026-06-16T10:32:00Z",
                        "dataSource": "IBKR",
                        "isMock": false,
                        "warnings": []
                    }"""
                )
            else:
                route.continue_()

        # Re-route and reload page
        page.unroute("**/*")
        page.route("**/*", handle_real_request)

        # Reload options tab or page
        page.goto("http://localhost:3000/holdings/MSFT?tab=options")
        page.wait_for_load_state("networkidle")

        # Verify mock warning banner is NOT visible (since isMock is false)
        assert not page.locator("text=Simulated Data — Not Suitable for Trading Decisions").is_visible(), "Mock banner should be hidden when isMock is false"
        # Verify metadata shows source as IBKR
        assert page.locator("text=Source:").is_visible()
        assert page.locator("text=IBKR").first.is_visible()

        # 8. Test error state handling on frontend
        page.unroute("**/*")
        def handle_error_request(route):
            if "options-strategy" in route.request.url:
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"detail": "Options strategy generation is unavailable."}'
                )
            else:
                route.continue_()
        page.route("**/*", handle_error_request)

        # Reload page with error state
        page.goto("http://localhost:3000/holdings/MSFT?tab=options")
        page.wait_for_load_state("networkidle")
        # Ensure it renders fallback elements or shows error gracefully
        assert page.locator("text=No option strategies generated").is_visible()

        browser.close()
