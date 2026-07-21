from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.options.market_inputs import option_market_inputs, reprice_option_scenario


def test_option_market_inputs_fail_closed_without_underlying_con_id(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.broker_mode", "ibkr_readonly")
    result = option_market_inputs(
        underlying_con_id=999001,
        expiration=date.today() + timedelta(days=30),
        currency="USD",
        underlying_symbol=None,
        allow_demo_defaults=False,
        positions=[],
    )
    assert result.inputs is None
    assert result.status == "withheld"
    assert "underlying_con_id_unresolved" in result.exclusions


def test_option_market_inputs_require_fx_for_dual_currency(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.broker_mode", "ibkr_readonly")
    positions = [
        SimpleNamespace(
            con_id=42,
            symbol="AAPL",
            asset_class="STK",
            market_price=100.0,
            quantity=100,
        )
    ]
    result = option_market_inputs(
        underlying_con_id=42,
        expiration=date.today() + timedelta(days=30),
        currency="CAD",
        underlying_symbol="AAPL",
        allow_demo_defaults=False,
        positions=positions,
        reporting_currency="USD",
        fx_rate=None,
    )
    assert result.inputs is None
    assert "fx_observation_required" in result.exclusions


def test_reprice_american_exercise_when_approved():
    from app.db.option_contract_repo import OptionContractMaster

    master = OptionContractMaster(
        con_id=1,
        symbol="AAPL",
        local_symbol="AAPL  250815C00100000",
        currency="USD",
        exchange="SMART",
        trading_class="AAPL",
        multiplier=100.0,
        strike=100.0,
        right="C",
        expiration=date.today() + timedelta(days=30),
        underlying_con_id=42,
        underlying_symbol="AAPL",
    )
    result = reprice_option_scenario(
        contract=master,
        current_option_mark=5.0,
        underlying_spot=100.0,
        implied_volatility=0.25,
        risk_free_curve=0.04,
        dividend_curve=0.0,
        spot_shock_pct=-10.0,
        volatility_shock_points=0.05,
        days_forward=0,
        quantity=-1,
        exercise_style="american",
    )
    assert result.status == "available"
    assert result.loss is not None
    assert result.repriced_mark is not None
    assert result.methodology_status == "approved_for_personal_use"


def test_reprice_withholds_american_when_not_approved(monkeypatch):
    from app.db.option_contract_repo import OptionContractMaster
    from app.services.model_governance import MethodologyNotApproved

    def _deny(methodology_id, **_kwargs):
        if methodology_id == "options_american_pricer":
            raise MethodologyNotApproved("options_american_pricer: withheld")
        raise MethodologyNotApproved(f"{methodology_id}: withheld")

    monkeypatch.setattr("app.services.model_governance.require_methodology_status", _deny)

    master = OptionContractMaster(
        con_id=1,
        symbol="AAPL",
        local_symbol="AAPL  250815C00100000",
        currency="USD",
        exchange="SMART",
        trading_class="AAPL",
        multiplier=100.0,
        strike=100.0,
        right="C",
        expiration=date.today() + timedelta(days=30),
        underlying_con_id=42,
        underlying_symbol="AAPL",
    )
    result = reprice_option_scenario(
        contract=master,
        current_option_mark=5.0,
        underlying_spot=100.0,
        implied_volatility=0.25,
        risk_free_curve=0.04,
        dividend_curve=0.0,
        spot_shock_pct=-10.0,
        volatility_shock_points=0.05,
        days_forward=0,
        quantity=-1,
        exercise_style="american",
    )
    assert result.status == "withheld"
    assert "american_exercise_not_supported" in result.exclusions
    assert result.loss is None
