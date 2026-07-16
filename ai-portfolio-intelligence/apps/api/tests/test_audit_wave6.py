from datetime import date

import pytest

from app.schemas.domain import Transaction
from app.services.ai.structured_outputs import build_structured_stock_context
from app.services.portfolio.performance_returns import _flow_weight, _modified_dietz_interval_return
from app.services.portfolio_construction.advanced_optimizer import (
    hierarchical_risk_parity_weights,
    solve_cvar_weights,
    verify_weight_constraints,
)


def test_modified_dietz_early_deposit_has_higher_weight_than_late_deposit():
    early = _flow_weight(date(2026, 1, 2), date(2026, 1, 1), date(2026, 1, 15))
    late = _flow_weight(date(2026, 1, 14), date(2026, 1, 1), date(2026, 1, 15))
    assert early > late
    assert early == pytest.approx(13 / 14, rel=1e-6)
    assert late == pytest.approx(1 / 14, rel=1e-6)


def test_modified_dietz_early_and_late_deposits_produce_different_returns():
    base_kwargs = dict(
        beginning_nav=100_000.0,
        ending_nav=106_000.0,
        interval_start=date(2026, 1, 1),
        interval_end=date(2026, 1, 15),
        base_currency="USD",
        fx_resolver=lambda _a, _b, _c=None: 1.0,
    )
    early_txn = [
        Transaction(
            account_id="TEST-001",
            symbol="CASH",
            trade_date=date(2026, 1, 2),
            action="deposit",
            quantity=1,
            price=5000,
            commission=0,
            currency="USD",
            amount=5000,
        )
    ]
    late_txn = [
        Transaction(
            account_id="TEST-001",
            symbol="CASH",
            trade_date=date(2026, 1, 14),
            action="deposit",
            quantity=1,
            price=5000,
            commission=0,
            currency="USD",
            amount=5000,
        )
    ]
    early_return = _modified_dietz_interval_return(**base_kwargs, transactions=early_txn)
    late_return = _modified_dietz_interval_return(**base_kwargs, transactions=late_txn)
    assert early_return is not None
    assert late_return is not None
    assert early_return != pytest.approx(late_return, rel=1e-4)


def test_hrp_matches_independent_reference_vector():
    covariance = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.02],
        [0.005, 0.02, 0.16],
    ]
    expected = [0.5770653514180025, 0.25647348951911225, 0.16646115906288528]
    actual = hierarchical_risk_parity_weights(covariance)
    assert actual == pytest.approx(expected, abs=1e-8)


def test_cvar_solver_reports_post_solve_feasibility():
    returns_by_symbol = {
        "AAA": [0.01, -0.02, 0.015, -0.01, 0.005] * 8,
        "BBB": [-0.005, 0.02, -0.01, 0.01, 0.0] * 8,
        "CCC": [0.0, 0.01, -0.015, 0.02, -0.005] * 8,
    }
    symbols = ["AAA", "BBB", "CCC"]
    weights, metadata = solve_cvar_weights(
        returns_by_symbol,
        symbols,
        target_budget=1.0,
        current_full_weights=[1 / 3, 1 / 3, 1 / 3],
        turnover_budget=0.5,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        sector_labels=["Tech", "Tech", "Energy"],
        sector_cap=0.8,
        fixed_sector_exposure={"Financials": 0.05},
    )
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is not None
    feasibility = metadata.get("feasibility", {})
    assert feasibility.get("feasible") is True
    slack = verify_weight_constraints(
        weights,
        target_budget=1.0,
        current_full_weights=[1 / 3, 1 / 3, 1 / 3],
        turnover_budget=0.5,
        liquidity_caps=None,
        sector_labels=["Tech", "Tech", "Energy"],
        sector_cap=0.8,
        fixed_sector_exposure={"Financials": 0.05},
    )
    assert slack["feasible"] is True


def test_stock_structured_context_uses_real_user_id_for_thesis(monkeypatch, tmp_path):
    from app.schemas.domain import Position, utc_now

    captured: dict[str, str] = {}

    def _capture_thesis(*_args, **kwargs):
        captured["user_id"] = kwargs.get("user_id", "")
        return {"status": "intact", "invalidation_triggers": []}

    monkeypatch.setattr("app.services.ai.structured_outputs.evaluate_thesis", _capture_thesis)
    position = Position(
        account_id="LIVE-001",
        symbol="MSFT",
        company_name="Microsoft",
        asset_class="STK",
        quantity=10,
        avg_cost=100,
        market_price=120,
        market_value=1200,
        unrealized_pnl=200,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=5,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )
    build_structured_stock_context(
        position=position,
        score=type("Score", (), {"final_score": 70, "model_dump": lambda self, mode="json": {}})(),
        recommendation=type(
            "Rec",
            (),
            {"action": "Hold", "model_dump": lambda self, mode="json": {}},
        )(),
        technicals=None,
        fundamentals=None,
        valuation=None,
        catalysts=None,
        portfolio_timestamp=position.updated_at,
        user_id="tenant-user-42",
    )
    assert captured["user_id"] == "tenant-user-42"
