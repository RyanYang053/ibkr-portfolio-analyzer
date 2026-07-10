from datetime import date, timedelta
import pytest
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.risk.history_reconstructor import reconstruct_portfolio_history
from app.schemas.domain import Position, AccountSummary, utc_now

def test_live_yahoo_finance_connectivity():
    # 1. Test market price fetching
    market_provider = MockMarketDataProvider(allow_mock=False)
    price = market_provider.get_latest_price("AAPL")
    assert price > 0.0, f"Latest price for AAPL should be positive, got {price}"

    # 2. Test fundamentals fetching
    fundamental_provider = MockFundamentalProvider(allow_mock=False)
    fundamentals = fundamental_provider.get_fundamentals("AAPL")
    assert fundamentals.symbol == "AAPL"
    assert fundamentals.revenue_growth_yoy is not None
    assert fundamentals.gross_margin > 0.0
    assert fundamentals.source == "live_yahoo_finance"

    # 3. Test news fetching
    news = market_provider.get_recent_news("AAPL")
    assert len(news) > 0, "Should fetch at least one news item from Yahoo Finance"
    assert all(item["symbol"] == "AAPL" for item in news)
    assert news[0]["title"] != ""

    # 4. Test chart data fetching
    chart = market_provider.get_chart_data("AAPL", range_str="1mo", interval_str="1d")
    assert len(chart) > 0, "Should fetch chart price history for AAPL"
    assert chart[0]["close"] > 0.0
    assert chart[0]["source"] == "live_yahoo_finance"


def test_live_history_reconstruction_and_alignment():
    # Construct a real position payload for AAPL
    pos_aapl = Position(
        account_id="TEST-AC-001",
        symbol="AAPL",
        company_name="Apple Inc.",
        asset_class="STK",
        quantity=50.0,
        avg_cost=150.0,
        market_price=220.0,
        market_value=11000.0,
        unrealized_pnl=3500.0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        portfolio_weight=100.0,
        stock_type="core",
        updated_at=utc_now()
    )

    summary = AccountSummary(
        account_id="TEST-AC-001",
        net_liquidation=11000.0,
        cash=0.0,
        buying_power=0.0,
        margin_requirement=0.0,
        excess_liquidity=0.0,
        total_unrealized_pnl=3500.0,
        total_realized_pnl=0.0,
        base_currency="USD",
        data_timestamp=utc_now()
    )

    # Perform portfolio history reconstruction explicitly using live data providers (allow_mock=False)
    recon = reconstruct_portfolio_history([pos_aapl], summary, allow_mock=False)
    
    assert recon is not None, "Live portfolio history reconstruction should succeed"
    assert "trading_dates" in recon
    assert len(recon["trading_dates"]) > 10, "Should reconstruct at least some aligned trading days"
    assert "portfolio_nav" in recon
    assert "spy_returns" in recon
    assert "qqq_returns" in recon
    assert "port_returns" in recon
    assert "asset_returns" in recon
    assert "AAPL" in recon["asset_returns"]

    # Aligned lengths verify index mapping works
    n_days = len(recon["trading_dates"])
    assert len(recon["portfolio_nav"]) == n_days
    # Returns lists are n-1 in size
    assert len(recon["port_returns"]) == n_days - 1
    assert len(recon["spy_returns"]) == n_days - 1
    assert len(recon["asset_returns"]["AAPL"]) == n_days - 1

    # Verify return calculations are within sensible numeric boundaries
    assert all(-1.0 <= r <= 1.0 for r in recon["port_returns"])
    assert all(-1.0 <= r <= 1.0 for r in recon["spy_returns"])


def test_live_advanced_risk_metrics_calculation(monkeypatch):
    import sys
    from app.services.risk.advanced_risk import calculate_advanced_risk_metrics
    # Force MockMarketDataProvider to not use mock
    monkeypatch.setattr(MockMarketDataProvider, "__init__", lambda self, allow_mock=None: setattr(self, "allow_mock", False))
    monkeypatch.setattr(MockFundamentalProvider, "__init__", lambda self, allow_mock=None: setattr(self, "allow_mock", False))
    
    # Construct position and summary
    pos_aapl = Position(
        account_id="TEST-AC-001",
        symbol="AAPL",
        company_name="Apple Inc.",
        asset_class="STK",
        quantity=50.0,
        avg_cost=150.0,
        market_price=220.0,
        market_value=11000.0,
        unrealized_pnl=3500.0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        portfolio_weight=100.0,
        stock_type="core",
        updated_at=utc_now()
    )
    summary = AccountSummary(
        account_id="TEST-AC-001",
        net_liquidation=11000.0,
        cash=0.0,
        buying_power=0.0,
        margin_requirement=0.0,
        excess_liquidity=0.0,
        total_unrealized_pnl=3500.0,
        total_realized_pnl=0.0,
        base_currency="USD",
        data_timestamp=utc_now()
    )
    
    # Temporarily remove pytest from sys.modules to bypass pytest guard in calculate_advanced_risk_metrics
    pytest_module = sys.modules.pop("pytest", None)
    try:
        metrics = calculate_advanced_risk_metrics([pos_aapl], summary, [])
    finally:
        if pytest_module is not None:
            sys.modules["pytest"] = pytest_module
            
    assert metrics is not None
    # Current-holdings reconstruction is an ex-ante covariance model, not realized
    # account performance. Historical ratios are withheld without actual snapshots
    # and full activity-ledger coverage.
    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None
    assert metrics.jensens_alpha is None
    assert metrics.tracking_error is None
    assert metrics.information_ratio is None
    assert metrics.data_quality["historical_metrics"] == "insufficient"
    assert metrics.data_quality["cash_flow_ledger"] == "insufficient_history"
    assert metrics.data_quality["security_return_series"] in {
        "sufficient_modeled_current_holdings",
        "partial_modeled_current_holdings",
    }

