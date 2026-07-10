from app.schemas.domain import FundamentalSnapshot
from app.services.fundamentals.sector_models import score_fundamentals_for_sector
from datetime import date


def _fundamentals(**overrides):
    base = dict(
        symbol="JPM",
        period="TTM",
        report_date=date(2025, 12, 31),
        revenue_growth_yoy=0.05,
        gross_margin=0.4,
        operating_margin=0.3,
        free_cash_flow=1_000_000.0,
        cash=10_000_000.0,
        total_debt=5_000_000.0,
        pe_forward=12.0,
        ev_sales=3.0,
        fcf_yield=0.04,
        source="mock_fundamentals",
    )
    base.update(overrides)
    return FundamentalSnapshot(**base)


def test_financials_sector_uses_accounting_metrics_when_present():
    scores = score_fundamentals_for_sector(
        _fundamentals(
            price_to_tangible_book=1.2,
            return_on_equity=0.14,
            net_interest_margin=0.03,
        ),
        "Financials",
    )
    assert scores["valuation"] > 0
    assert scores["profitability"] > 0


def test_financials_sector_falls_back_without_sector_inputs():
    scores = score_fundamentals_for_sector(_fundamentals(), "Financials")
    assert "business_quality" in scores
    assert "valuation" in scores


def test_reit_sector_uses_ffo_and_occupancy_when_present():
    scores = score_fundamentals_for_sector(
        _fundamentals(ffo_per_share=4.0, occupancy_rate=0.95),
        "Real Estate",
    )
    assert scores["business_quality"] > 50


def test_financials_sector_falls_back_with_partial_sector_inputs():
    scores = score_fundamentals_for_sector(
        _fundamentals(price_to_tangible_book=1.2),
        "Financials",
    )
    assert "business_quality" in scores
