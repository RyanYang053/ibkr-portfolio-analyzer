from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.schemas.domain import Position, utc_now
from app.services.options.contract_filters import OptionLiquidityPolicy, is_liquid
from app.services.options.deterministic_report import build_deterministic_options_report
from app.services.options.engine import OptionContract


def _fresh_contract(**overrides) -> OptionContract:
    base = {
        "symbol": "MSFT260116C00400000",
        "strike": 400.0,
        "right": "C",
        "expiration": date.today() + timedelta(days=30),
        "bid": 5.0,
        "ask": 5.2,
        "mid": 5.1,
        "implied_volatility": 0.25,
        "quote_timestamp": datetime.now(timezone.utc).isoformat(),
        "quote_age_seconds": 1.0,
        "open_interest": 100,
        "volume": 10,
        "multiplier": 100.0,
        "currency": "USD",
    }
    base.update(overrides)
    return OptionContract(**base)


def _position() -> Position:
    return Position(
        account_id="LIVE-001",
        symbol="MSFT",
        company_name="Microsoft",
        asset_class="STK",
        quantity=100,
        avg_cost=380,
        market_price=400,
        market_value=40000,
        unrealized_pnl=2000,
        realized_pnl=0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=100,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )


def test_missing_open_interest_fails_production_liquidity():
    contract = _fresh_contract(open_interest=None)
    assert is_liquid(contract, OptionLiquidityPolicy()) is False


def test_missing_volume_fails_production_liquidity():
    contract = _fresh_contract(volume=None)
    assert is_liquid(contract, OptionLiquidityPolicy()) is False


def test_deterministic_report_withholds_without_liquid_contracts():
    chain = [
        _fresh_contract(open_interest=None),
        _fresh_contract(
            right="P",
            strike=390.0,
            symbol="MSFT260116P00390000",
            open_interest=None,
        ),
    ]
    report = build_deterministic_options_report(
        _position(),
        chain,
        cash_available=50000,
        account_type="Margin",
        chain_source="IBKR",
        is_demo=False,
    )
    assert report["status"] == "withheld_no_liquid_contracts"
    assert report["strategies"] == []
    assert "No contracts passed production liquidity" in report["warnings"][0]
