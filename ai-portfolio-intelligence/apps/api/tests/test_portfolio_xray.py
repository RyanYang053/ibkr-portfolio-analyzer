"""Unit tests for the portfolio X-Ray diagnostic rules."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.analytics.portfolio_xray import portfolio_xray


def _holding(symbol, market_value, currency="USD", asset_class="STK"):
    return SimpleNamespace(symbol=symbol, market_value=market_value, currency=currency, asset_class=asset_class)


def test_concentrated_three_name_portfolio_warns():
    holdings = [
        _holding("A", 6000, "USD"),
        _holding("B", 2000, "USD"),
        _holding("C", 2000, "CAD", "ETF"),
    ]
    findings = {f.key: f for f in portfolio_xray(holdings)}

    assert findings["currency_concentration"].value == 80.0
    assert findings["currency_concentration"].status == "warn"  # USD 80% > 70%
    assert findings["top5_concentration"].status == "warn"  # 100% > 60%
    assert findings["holdings_count"].value == 3.0
    assert findings["holdings_count"].status == "warn"  # 3 < 10
    # HHI = 0.6^2 + 0.2^2 + 0.2^2 = 0.44 -> effective 2.27
    assert findings["effective_holdings"].value == 2.27
    assert findings["effective_holdings"].status == "warn"


def test_diversified_portfolio_passes():
    holdings = [_holding(f"S{i}", 1000, "USD") for i in range(20)]
    findings = {f.key: f for f in portfolio_xray(holdings)}
    assert findings["holdings_count"].status == "pass"  # 20 >= 10
    assert findings["effective_holdings"].value == 20.0  # equal weights -> 1/HHI = N
    assert findings["effective_holdings"].status == "pass"
    assert findings["top5_concentration"].status == "pass"  # 5*5% = 25% < 60%


def test_custom_thresholds_and_empty():
    holdings = [_holding("A", 100), _holding("B", 100)]
    findings = {f.key: f for f in portfolio_xray(holdings, thresholds={"min_holdings": 2.0})}
    assert findings["holdings_count"].status == "pass"  # threshold lowered to 2

    empty = portfolio_xray([_holding("Z", 0.0)])
    assert all(f.status == "insufficient" for f in empty)
