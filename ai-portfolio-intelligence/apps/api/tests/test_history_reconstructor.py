from datetime import date, datetime, timezone
from app.schemas.domain import AccountSummary, Position, utc_now
from app.services.risk.history_reconstructor import (
    get_underlying_symbol,
    reconstruct_portfolio_history,
    calculate_covariance,
    calculate_variance,
    calculate_correlation
)

def _make_test_summary(net_liq=100000.0, cash=20000.0) -> AccountSummary:
    return AccountSummary(
        account_id="MOCK-001",
        net_liquidation=net_liq,
        cash=cash,
        buying_power=80000.0,
        margin_requirement=15000.0,
        excess_liquidity=65000.0,
        total_unrealized_pnl=5000.0,
        total_realized_pnl=1000.0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )

def _make_test_position(symbol, qty, mkt_val, unrealized=0.0) -> Position:
    return Position(
        account_id="MOCK-001",
        symbol=symbol,
        company_name=f"{symbol} Inc.",
        asset_class="STK",
        quantity=qty,
        avg_cost=100.0,
        market_price=mkt_val / qty if qty > 0 else 0.0,
        market_value=mkt_val,
        unrealized_pnl=unrealized,
        realized_pnl=0.0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Misc",
        portfolio_weight=50.0,
        stock_type="core",
        is_etf=False,
        is_speculative=False,
        updated_at=utc_now(),
    )

def test_get_underlying_symbol():
    assert get_underlying_symbol("AAPL") == "AAPL"
    assert get_underlying_symbol("AAPL260619C00150000") == "AAPL"
    assert get_underlying_symbol("AAPL  260619C00150000") == "AAPL"
    assert get_underlying_symbol("MSFT240119P00200000") == "MSFT"

def test_math_functions():
    x = [0.01, 0.02, -0.01, 0.03, 0.00]
    y = [0.02, 0.04, -0.02, 0.06, 0.00] # y is exactly 2x
    
    assert round(calculate_correlation(x, y), 5) == 1.0
    assert round(calculate_covariance(x, y), 5) == round(2.0 * calculate_variance(x), 5)

def test_reconstruct_portfolio_history_mock_data():
    # MSFT is in MOCK_LOTS
    positions = [
        _make_test_position("MSFT", qty=10, mkt_val=4250.0, unrealized=500.0)
    ]
    summary = _make_test_summary(net_liq=34250.0, cash=30000.0)
    
    recon = reconstruct_portfolio_history(positions, summary, allow_mock=True)
    
    assert recon is not None
    assert "trading_dates" in recon
    assert len(recon["trading_dates"]) >= 220
    assert "portfolio_nav" in recon
    assert len(recon["portfolio_nav"]) == len(recon["trading_dates"])
    assert "spy_returns" in recon
    assert len(recon["spy_returns"]) == len(recon["trading_dates"]) - 1
    assert "methodology" in recon
    assert "ex-ante" in recon["methodology"].lower()

    # Portfolio NAV on the last day should match the current value
    assert round(recon["portfolio_nav"][-1], 2) == round(summary.cash + positions[0].market_value, 2)
