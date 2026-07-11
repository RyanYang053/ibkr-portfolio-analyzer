from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.schemas.domain import Position, utc_now
from app.services.options.contract_filters import OptionLiquidityPolicy, is_liquid, is_otm_call, is_otm_put, spread_percent
from app.services.options.engine import OptionContract, calculate_bs_price
from app.services.risk.advanced_risk import OptionStressResult, _option_stress_loss


def test_invalid_black_scholes_inputs_raise():
    with pytest.raises(ValueError, match="Spot must be positive"):
        calculate_bs_price(0, 100, 0.25, 0.05, 0.2, "C")
    with pytest.raises(ValueError, match="Strike must be positive"):
        calculate_bs_price(100, 0, 0.25, 0.05, 0.2, "C")
    with pytest.raises(ValueError, match="Time to expiry must be positive"):
        calculate_bs_price(100, 100, 0, 0.05, 0.2, "C")
    with pytest.raises(ValueError, match="Volatility must be positive"):
        calculate_bs_price(100, 100, 0.25, 0.05, 0, "C")
    with pytest.raises(ValueError, match="Option right must be C or P"):
        calculate_bs_price(100, 100, 0.25, 0.05, 0.2, "X")


def test_stale_quotes_fail_liquidity_policy():
    contract = OptionContract(
        symbol="TEST",
        strike=100,
        right="C",
        expiration=date.today() + timedelta(days=30),
        bid=1.0,
        ask=1.1,
        mid=1.05,
        implied_volatility=0.25,
        quote_timestamp=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        open_interest=100,
        volume=10,
    )
    policy = OptionLiquidityPolicy(max_quote_age_seconds=120)
    assert is_liquid(contract, policy) is False


def test_wide_spread_fails_liquidity_policy():
    contract = OptionContract(
        symbol="TEST",
        strike=100,
        right="C",
        expiration=date.today() + timedelta(days=30),
        bid=1.0,
        ask=2.0,
        mid=1.5,
        implied_volatility=0.25,
        quote_timestamp=datetime.now(timezone.utc).isoformat(),
        quote_age_seconds=1.0,
        open_interest=100,
        volume=10,
    )
    assert spread_percent(contract) == pytest.approx(66.666, rel=1e-2)
    assert is_liquid(contract, OptionLiquidityPolicy()) is False


def test_moneyness_filters():
    call = OptionContract(
        symbol="C",
        strike=105,
        right="C",
        expiration=date.today() + timedelta(days=30),
        bid=1,
        ask=1.1,
        mid=1.05,
        implied_volatility=0.2,
    )
    put = OptionContract(
        symbol="P",
        strike=95,
        right="P",
        expiration=date.today() + timedelta(days=30),
        bid=1,
        ask=1.1,
        mid=1.05,
        implied_volatility=0.2,
    )
    assert is_otm_call(call, 100) is True
    assert is_otm_put(put, 100) is True


def test_option_stress_withholds_without_underlying_spot():
    option = Position(
        account_id="MOCK-001",
        symbol="MSFT",
        company_name="MSFT Call",
        asset_class="OPT",
        quantity=1,
        avg_cost=5,
        market_price=6,
        market_value=600,
        unrealized_pnl=100,
        realized_pnl=0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=1,
        stock_type="universal",
        con_id=424242,
        local_symbol="MSFT  260116C00400000",
        multiplier=100,
        updated_at=utc_now(),
    )
    result = _option_stress_loss(
        option,
        underlying_spot=None,
        underlying_spot_source="withheld",
        implied_volatility=0.30,
        risk_free_rate=0.045,
        dividend_yield=0.0,
        spot_shock_pct=-30,
        volatility_shock_points=0.0,
        days_forward=0,
        positions=[option],
    )
    assert isinstance(result, OptionStressResult)
    assert result.status == "withheld"
    assert "option_contract_metadata_unavailable" in result.exclusions or "underlying_spot_unavailable" in result.exclusions


def test_option_stress_uses_contract_master(monkeypatch):
    from datetime import date

    from app.core.config import settings
    from app.db.option_contract_repo import upsert_contract
    from app.services.options.engine import OptionContract

    monkeypatch.setattr(settings, "persistence_backend", "json")
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
            con_id=424242,
            underlying_symbol="MSFT",
            multiplier=100.0,
            currency="USD",
            provider="IBKR",
        )
    )

    stock = Position(
        account_id="MOCK-001",
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
            "quantity": 1,
            "market_price": 6,
            "market_value": 600,
            "con_id": 424242,
            "local_symbol": "MSFT  260116C00400000",
            "multiplier": 100,
        }
    )
    result = _option_stress_loss(
        option,
        underlying_spot=None,
        underlying_spot_source="withheld",
        implied_volatility=0.30,
        risk_free_rate=0.045,
        dividend_yield=0.0,
        spot_shock_pct=-30,
        volatility_shock_points=0.0,
        days_forward=0,
        positions=[stock, option],
    )
    assert result.status == "available"
    assert result.loss is not None
