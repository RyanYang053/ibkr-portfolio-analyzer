from __future__ import annotations

from app.services.investor_lenses import ensemble_synthesis, evaluate_all_lenses
from app.services.investor_lenses.base import LensInputs
from app.services.investor_lenses.buffett_quality import evaluate as buffett


def test_lenses_are_deterministic_and_do_not_average_gurus():
    inputs = LensInputs(
        symbol="AAA",
        fundamentals={
            "return_on_equity": 0.22,
            "fcf_yield": 0.05,
            "operating_margin": 0.28,
            "total_debt": 10,
            "average_common_equity": 100,
            "net_income_common": 50,
            "operating_cash_flow": 60,
            "cash": 20,
            "pe_forward": 18,
            "price_to_tangible_book": 1.2,
            "revenue_growth_yoy": 0.12,
            "gross_margin": 0.45,
        },
        risk_metrics={"volatility": 18.0, "max_drawdown": 12.0, "conditional_var_95": 8.0},
        factor_exposures={"market": 0.1, "value": 0.2, "momentum": -0.1, "quality": 0.3},
        liquidity={"participation_rate": 0.05},
        position={"portfolio_weight": 4.0, "asset_class": "STK"},
        tax_flags={"methodology_status": "available"},
    )
    first = evaluate_all_lenses(inputs)
    second = evaluate_all_lenses(inputs)
    assert [r.as_dict() for r in first] == [r.as_dict() for r in second]
    assert len(first) >= 8
    assert all(r.score is None or isinstance(r.score, float) for r in first)
    ensemble = ensemble_synthesis(first)
    assert "ordered_lenses" in ensemble
    assert "does not average" in str(ensemble.get("note", "")).lower() or "disagreements" in ensemble


def test_buffett_withheld_without_fundamentals():
    result = buffett(LensInputs(symbol="ZZZ"))
    assert result.status == "withheld"
    assert result.score is None


def test_buffett_includes_roic_and_owner_earnings_proxies():
    result = buffett(
        LensInputs(
            symbol="AAA",
            fundamentals={
                "return_on_equity": 0.22,
                "fcf_yield": 0.05,
                "operating_margin": 0.28,
                "gross_margin": 0.45,
                "total_debt": 10,
                "average_common_equity": 100,
                "net_income_common": 20,
                "free_cash_flow": 15,
                "cash": 5,
            },
        )
    )
    assert result.display_name == "Quality and Leverage Heuristic"
    names = {c.name for c in result.components}
    assert "roic_proxy" in names
    assert "owner_earnings_proxy" in names
    assert "moat_durability_score_not_implemented" in result.exclusions
    assert result.score is not None
