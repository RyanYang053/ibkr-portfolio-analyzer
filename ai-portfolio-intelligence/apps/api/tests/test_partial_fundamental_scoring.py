from __future__ import annotations

import pytest

from app.schemas.domain import Position, utc_now
from app.services.fundamentals.sector_models import score_fundamentals_for_sector
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from tests.fixtures.edgar_partial_snapshots import PARTIAL_FIXTURES


def _position(sector: str = "Technology") -> Position:
    return Position(
        account_id="MOCK-001",
        symbol="TEST",
        company_name="Test Corp",
        asset_class="STK",
        quantity=100,
        avg_cost=100,
        market_price=120,
        market_value=12_000,
        unrealized_pnl=2_000,
        currency="USD",
        exchange="SMART",
        sector=sector,
        industry="Software",
        portfolio_weight=5.0,
        stock_type="core",
        updated_at=utc_now(),
    )


@pytest.mark.parametrize("fixture_name", sorted(PARTIAL_FIXTURES))
def test_partial_fundamental_fixtures_do_not_raise(fixture_name: str):
    snapshot = PARTIAL_FIXTURES[fixture_name]
    scores = score_fundamentals_for_sector(snapshot, "Technology")
    assert isinstance(scores, dict)


def test_revenue_only_fixture_limits_coverage():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["revenue_only"], "Technology")
    assert "growth" in scores
    assert "business_quality" not in scores
    assert "balance_sheet" not in scores


def test_cash_without_debt_omits_balance_sheet_factor():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["cash_no_debt"], "Technology")
    assert "balance_sheet" not in scores


def test_debt_without_cash_omits_balance_sheet_factor():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["debt_no_cash"], "Technology")
    assert "balance_sheet" not in scores


def test_bank_missing_nim_falls_back_to_universal_heuristic():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["bank_missing_nim"], "Financials")
    assert "valuation" not in scores or "business_quality" in scores


def test_reit_missing_affo_still_scores_with_ffo():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["reit_missing_affo"], "Real Estate")
    assert "profitability" in scores


def test_utility_missing_allowed_roe_falls_back():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["utility_missing_allowed_roe"], "Utilities")
    assert isinstance(scores, dict)


def test_zero_fcf_yield_is_not_treated_as_missing():
    scores = score_fundamentals_for_sector(PARTIAL_FIXTURES["legitimate_zero_fcf_yield"], "Technology")
    assert "profitability" in scores


def test_partial_fundamentals_reduce_stock_score_coverage(monkeypatch):
    snapshot = PARTIAL_FIXTURES["revenue_only"]

    class _Provider:
        def get_fundamentals(self, symbol: str):
            return snapshot

    monkeypatch.setattr(
        "app.services.fundamentals.providers.get_fundamental_provider",
        lambda allow_mock=True: _Provider(),
    )
    monkeypatch.setattr(
        "app.services.market_data.news_service.fetch_scoring_news",
        lambda *args, **kwargs: [],
    )

    result = score_stock(_position(), allow_mock=True)
    assert result.factor_coverage["growth"] is True
    assert result.factor_coverage["business_quality"] is False
    assert result.final_score is None or result.confidence in {"Low", "Medium", "Medium-High", "High"}


def test_low_coverage_withholds_decision_grade_recommendation(monkeypatch):
    snapshot = PARTIAL_FIXTURES["operating_income_only"]

    class _Provider:
        def get_fundamentals(self, symbol: str):
            return snapshot

    monkeypatch.setattr(
        "app.services.fundamentals.providers.get_fundamental_provider",
        lambda allow_mock=True: _Provider(),
    )
    monkeypatch.setattr(
        "app.services.market_data.news_service.fetch_scoring_news",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.scoring.decision_engine.score_stock",
        lambda position: score_stock(position, allow_mock=True),
    )

    recommendation = build_recommendation(_position())
    assert recommendation.action == "Data Insufficient"
