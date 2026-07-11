from __future__ import annotations

from datetime import date

from app.core.config import settings
from app.db.option_contract_repo import upsert_contract
from app.schemas.domain import Position, utc_now
from app.services.options.engine import OptionContract
from app.services.options.portfolio_greeks import compute_portfolio_greeks
from app.services.risk.advanced_risk import OptionStressResult, _option_stress_loss


def _seed_put_contract(con_id: int = 2002) -> None:
    upsert_contract(
        OptionContract(
            symbol="MSFT260116P00380000",
            strike=380.0,
            right="P",
            expiration=date(2026, 1, 16),
            bid=4.0,
            ask=4.2,
            mid=4.1,
            implied_volatility=0.28,
            delta=-0.35,
            con_id=con_id,
            underlying_symbol="MSFT",
            multiplier=100.0,
            currency="USD",
            provider="IBKR",
        )
    )


def test_short_put_reports_assignment_and_uncovered_exposure(monkeypatch):
    monkeypatch.setattr(settings, "persistence_backend", "json")
    _seed_put_contract()

    stock = Position(
        account_id="LIVE-001",
        symbol="MSFT",
        company_name="Microsoft",
        asset_class="STK",
        quantity=0,
        avg_cost=0,
        market_price=400,
        market_value=0,
        unrealized_pnl=0,
        realized_pnl=0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=0,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )
    short_put = stock.model_copy(
        update={
            "asset_class": "OPT",
            "quantity": -1,
            "market_price": 4.1,
            "market_value": -410,
            "con_id": 2002,
            "multiplier": 100,
        }
    )

    summary, _ = compute_portfolio_greeks([stock, short_put], base_currency="USD")
    assert summary is not None
    assert summary.assignment_exposure > 0
    assert summary.uncovered_notional > 0
    assert summary.margin_stress > 0


def test_option_stress_withholds_without_contract_master(monkeypatch):
    monkeypatch.setattr(settings, "persistence_backend", "json")
    option = Position(
        account_id="LIVE-001",
        symbol="MSFT",
        company_name="MSFT Put",
        asset_class="OPT",
        quantity=1,
        avg_cost=4,
        market_price=4.1,
        market_value=410,
        unrealized_pnl=10,
        realized_pnl=0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=1,
        stock_type="universal",
        con_id=999888,
        local_symbol="MSFT  260116P00380000",
        multiplier=100,
        updated_at=utc_now(),
    )
    result = _option_stress_loss(
        option,
        underlying_spot=400.0,
        underlying_spot_source="test",
        implied_volatility=0.30,
        risk_free_rate=0.045,
        dividend_yield=0.0,
        spot_shock_pct=-20,
        volatility_shock_points=0.0,
        days_forward=0,
        positions=[option],
    )
    assert isinstance(result, OptionStressResult)
    assert result.status == "withheld"
    assert "option_contract_metadata_unavailable" in result.exclusions
