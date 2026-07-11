from __future__ import annotations

from datetime import date

from app.db.option_contract_repo import upsert_contract
from app.schemas.domain import Position, utc_now
from app.services.options.engine import OptionContract
from app.services.options.portfolio_greeks import compute_portfolio_greeks


def _seed_contract(con_id: int = 1001) -> None:
    upsert_contract(
        OptionContract(
            symbol="MSFT260116C00400000",
            strike=400.0,
            right="C",
            expiration=date(2026, 1, 16),
            bid=5.0,
            ask=5.2,
            mid=5.1,
            implied_volatility=0.25,
            delta=0.5,
            gamma=0.02,
            vega=0.15,
            theta=-0.04,
            con_id=con_id,
            underlying_symbol="MSFT",
            multiplier=100.0,
            currency="USD",
            provider="IBKR",
        )
    )


def test_compute_portfolio_greeks_aggregates_option_exposures(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    _seed_contract()

    stock = Position(
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
        portfolio_weight=80,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )
    option = stock.model_copy(
        update={
            "asset_class": "OPT",
            "quantity": 2,
            "market_price": 5.1,
            "market_value": 1020,
            "con_id": 1001,
            "multiplier": 100,
        }
    )

    summary, exclusions = compute_portfolio_greeks([stock, option], base_currency="USD")
    assert summary is not None
    assert summary.delta != 0
    assert summary.vega != 0
    assert "2026-01-16" in summary.expiry_concentration
    assert exclusions == []
