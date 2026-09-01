"""Demo mode must resolve every provider call locally.

Demo Mode is an explicit user choice to run against the bundled mock portfolio.
Any code path that consults a live provider anyway both contradicts that choice
(mixing live market data into mock figures) and, on a machine that cannot reach
the provider, spends seconds in retry backoff before withholding the result.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.config import settings
from app.schemas.domain import AccountSummary, Position, utc_now
from app.services.attribution.engine import calculate_performance_attribution
from app.services.market_data import fx_store


@pytest.fixture()
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")


@pytest.fixture(autouse=True)
def clear_fx_failures():
    fx_store.reset_fx_fetch_failures()
    yield
    fx_store.reset_fx_fetch_failures()


def _position(symbol: str = "MSFT", currency: str = "USD") -> Position:
    return Position(
        account_id="MOCK-001",
        symbol=symbol,
        company_name=f"{symbol} Inc.",
        asset_class="STK",
        quantity=50,
        avg_cost=300,
        market_price=380,
        market_value=19_000,
        unrealized_pnl=4_000,
        currency=currency,
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=12,
        stock_type="mega cap quality",
        updated_at=utc_now(),
    )


def _summary() -> AccountSummary:
    return AccountSummary(
        account_id="MOCK-001",
        net_liquidation=160_000,
        cash=32_500,
        buying_power=125_000,
        margin_requirement=18_500,
        excess_liquidity=94_000,
        total_unrealized_pnl=4_000,
        total_realized_pnl=0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )


def test_attribution_makes_no_provider_requests_in_demo_mode(demo_mode, monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("demo mode must not reach the market-data provider")

    monkeypatch.setattr("app.services.market_data.http_client.request_with_retry", _forbidden)
    monkeypatch.setattr("app.services.market_data.fx_store.request_with_retry", _forbidden)

    result = calculate_performance_attribution(
        [_position()], [], base_currency="USD", account_id="MOCK-001"
    )

    assert result is not None


def test_dated_fx_resolves_locally_in_demo_mode(demo_mode, monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("demo mode must not reach the FX provider")

    monkeypatch.setattr("app.services.market_data.fx_store.request_with_retry", _forbidden)

    quote = fx_store.get_historical_fx_quote("CAD", "USD", date(2026, 6, 1))

    assert quote.rate > 0
    assert quote.source == "mock_fx"


def test_dated_and_spot_demo_rates_agree(demo_mode):
    from app.services.broker.ibkr_readonly import get_exchange_rate

    dated = fx_store.get_historical_exchange_rate("CAD", "USD", date(2026, 6, 1))
    spot = get_exchange_rate("CAD", "USD")
    assert dated == pytest.approx(spot, rel=1e-9)


def test_live_mode_dated_fx_still_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")

    def _unreachable(*args, **kwargs):
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr("app.services.market_data.fx_store.request_with_retry", _unreachable)
    monkeypatch.setattr("app.services.market_data.fx_store.lookup_rate_with_metadata", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="Historical FX unavailable"):
        fx_store.get_historical_fx_quote("CAD", "USD", date(2026, 6, 1))


def test_failed_fx_fetch_is_not_retried_in_a_tight_loop(monkeypatch):
    """A provider that is down must not cost retry backoff on every conversion."""
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")

    calls = {"count": 0}

    def _unreachable(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr("app.services.market_data.fx_store._fetch_yahoo_fx_series", _unreachable)

    for _ in range(5):
        fx_store.fetch_and_persist_rate_series("CAD", "USD", date(2026, 6, 1))

    assert calls["count"] == 1, "subsequent attempts should be served by the negative cache"

    fx_store.reset_fx_fetch_failures()
    fx_store.fetch_and_persist_rate_series("CAD", "USD", date(2026, 6, 1))
    assert calls["count"] == 2, "clearing the negative cache must allow a retry"
