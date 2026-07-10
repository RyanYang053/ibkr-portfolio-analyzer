from datetime import date

import pytest

from app.schemas.domain import FundamentalSnapshot
from app.services.fundamentals.company_valuation import run_scenario_valuation
from app.services.portfolio_construction.advanced_optimizer import (
    black_litterman_posterior_returns,
    hierarchical_risk_parity_weights,
    solve_cvar_weights,
)


def test_hrp_weights_sum_to_one():
    covariance = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.02],
        [0.005, 0.02, 0.16],
    ]
    weights = hierarchical_risk_parity_weights(covariance)
    assert weights is not None
    assert pytest.approx(sum(weights), rel=1e-6) == 1.0
    assert all(weight >= 0 for weight in weights)


def test_black_litterman_posterior_shape():
    covariance = [
        [0.04, 0.01],
        [0.01, 0.09],
    ]
    market_weights = [0.6, 0.4]
    posterior = black_litterman_posterior_returns(covariance, market_weights)
    assert len(posterior) == 2


def test_cvar_optimizer_returns_normalized_weights():
    returns_by_symbol = {
        "AAA": [0.01, -0.02, 0.015, -0.01, 0.005] * 8,
        "BBB": [-0.005, 0.02, -0.01, 0.01, 0.0] * 8,
        "CCC": [0.0, 0.01, -0.015, 0.02, -0.005] * 8,
    }
    symbols = ["AAA", "BBB", "CCC"]
    weights, metadata = solve_cvar_weights(
        returns_by_symbol,
        symbols,
        current_weights=[1 / 3, 1 / 3, 1 / 3],
        turnover_budget=0.5,
        liquidity_caps=[0.5, 0.5, 0.5],
    )
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is not None
    assert pytest.approx(sum(weights), rel=1e-4) == 1.0


def test_iv_percentile_from_history(monkeypatch):
    from app.core.config import settings
    from app.db import iv_observation_repo

    class MemoryStore:
        def __init__(self):
            self.records: dict[tuple[str, str], object] = {}

        def read_json(self, namespace: str, record_key: str, default=None):
            return self.records.get((namespace, record_key), default)

        def write_json(self, namespace: str, record_key: str, payload):
            self.records[(namespace, record_key)] = payload

        def delete(self, namespace: str, record_key: str):
            self.records.pop((namespace, record_key), None)

    store = MemoryStore()
    monkeypatch.setattr(settings, "persistence_backend", "json")
    monkeypatch.setattr(iv_observation_repo, "get_state_store", lambda: store)

    history = [
        {"iv": 0.20 + index * 0.01, "source": "test", "date": "2026-01-01"}
        for index in range(25)
    ]
    store.write_json("iv_observations", "MSFT", history)

    percentile = iv_observation_repo.iv_percentile("MSFT", 0.30)
    assert percentile is not None
    assert 0 <= percentile <= 100


def test_company_type_valuation_models():
    bank_snapshot = FundamentalSnapshot(
        symbol="JPM",
        period="TTM",
        report_date=date.today(),
        revenue_growth_yoy=0.05,
        gross_margin=0.4,
        operating_margin=0.3,
        free_cash_flow=1_000_000.0,
        cash=50_000_000.0,
        total_debt=10_000_000.0,
        pe_forward=12.0,
        ev_sales=3.0,
        fcf_yield=0.05,
        price_to_tangible_book=1.2,
        return_on_equity=0.14,
        source="test",
    )
    bank = run_scenario_valuation(
        bank_snapshot,
        sector="Financials",
        stock_type="financials_heuristic",
        market_price=150.0,
    )
    assert bank.company_type == "bank"
    assert bank.valuation_status == "available"
    assert bank.fair_value_mid is not None

    reit_snapshot = bank_snapshot.model_copy(update={"symbol": "O", "affo_per_share": 3.6})
    reit = run_scenario_valuation(reit_snapshot, sector="Real Estate", stock_type="reit_heuristic", market_price=60.0)
    assert reit.company_type == "reit"
    assert reit.valuation_status == "available"

    missing_price = run_scenario_valuation(bank_snapshot, sector="Financials", stock_type="financials_heuristic")
    assert missing_price.valuation_status == "unavailable"


def test_quantlib_benchmark_compare_or_skip():
    import os

    from app.services.options.quantlib_benchmark import compare_with_internal_bs, quantlib_available

    if not quantlib_available():
        if os.getenv("CI"):
            pytest.fail("QuantLib is required for institutional benchmark validation in CI")
        pytest.skip("QuantLib not installed on this machine")

    result = compare_with_internal_bs(
        spot=100.0,
        strike=105.0,
        days_to_expiry=30,
        risk_free_rate=0.045,
        volatility=0.28,
        right="C",
    )
    assert result["status"] in {"within_tolerance", "diverged"}


def test_extract_xbrl_facts_parses_companyfacts(monkeypatch):
    from app.services.fundamentals.providers import edgar_provider

    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"val": 100.0, "end": "2024-12-31", "filed": "2025-02-01", "form": "10-K", "fy": 2024, "fp": "FY"},
                            {"val": 90.0, "end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fy": 2023, "fp": "FY"},
                        ]
                    }
                }
            }
        }
    }

    monkeypatch.setattr(edgar_provider, "_lookup_cik", lambda _symbol: "0000320193")
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)

    facts = edgar_provider.extract_xbrl_facts("AAPL", company_type="general_operating")
    assert facts
    assert facts[0]["concept"] == "Revenues"
    assert facts[0]["value"] == 100.0
