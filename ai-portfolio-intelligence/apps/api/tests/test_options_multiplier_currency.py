from __future__ import annotations

from app.services.options.engine import (
    calculate_cash_secured_put_metrics,
    calculate_covered_call_metrics,
    evaluate_strategy_eligibility,
)


def test_covered_call_metrics_use_multiplier():
    metrics = calculate_covered_call_metrics(100.0, 105.0, 2.0, multiplier=10.0)
    assert "70.00" in metrics["max_profit"]
    assert "980.00" in metrics["max_loss"]


def test_cash_secured_put_metrics_use_multiplier():
    metrics = calculate_cash_secured_put_metrics(150.0, 3.5, multiplier=10.0)
    assert "35.00" in metrics["max_profit"]
    assert "1465.00" in metrics["max_loss"]


def test_eligibility_uses_multiplier_and_fx_for_cash_secured_put(monkeypatch):
    monkeypatch.setattr(
        "app.services.broker.ibkr_readonly.get_exchange_rate",
        lambda _from, _to: 2.0,
    )
    eligible, reason = evaluate_strategy_eligibility(
        "Cash-Secured Put",
        strike=100.0,
        underlying_price=95.0,
        quantity_held=0,
        cash_available=15000.0,
        contract_multiplier=100.0,
        contract_currency="USD",
        account_currency="CAD",
        fx_rate_to_account=2.0,
    )
    assert eligible is False
    assert "Requires $20,000.00" in reason
