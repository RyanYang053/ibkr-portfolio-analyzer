from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.domain import FundamentalSnapshot


class ScenarioValuationResult(BaseModel):
    symbol: str
    company_type: str
    valuation_status: str = "unavailable"
    fair_value_low: float | None = None
    fair_value_mid: float | None = None
    fair_value_high: float | None = None
    methodology: str
    assumptions: dict[str, float | str] = Field(default_factory=dict)
    data_quality: dict[str, str] = Field(default_factory=dict)
    unavailable_reasons: list[str] = Field(default_factory=list)


def _company_type_from_sector(sector: str, stock_type: str) -> str:
    if stock_type == "reit_heuristic" or sector == "Real Estate":
        return "reit"
    if stock_type == "financials_heuristic" or sector == "Financials":
        return "bank"
    if stock_type == "utilities_heuristic" or sector == "Utilities":
        return "utility"
    return "general_operating"


def _unavailable(
    snapshot: FundamentalSnapshot,
    company_type: str,
    reasons: list[str],
) -> ScenarioValuationResult:
    return ScenarioValuationResult(
        symbol=snapshot.symbol,
        company_type=company_type,
        valuation_status="unavailable",
        methodology="Scenario valuation withheld until unit-consistent inputs are available.",
        assumptions={"report_date": snapshot.report_date.isoformat(), "source": snapshot.source},
        data_quality={"inputs": snapshot.source},
        unavailable_reasons=reasons,
    )


def run_scenario_valuation(
    snapshot: FundamentalSnapshot,
    *,
    sector: str = "Unknown",
    stock_type: str = "universal",
    market_price: float | None = None,
) -> ScenarioValuationResult:
    company_type = _company_type_from_sector(sector, stock_type)
    if market_price is None or market_price <= 0:
        return _unavailable(snapshot, company_type, ["market_price_unavailable"])

    assumptions: dict[str, float | str] = {
        "report_date": snapshot.report_date.isoformat(),
        "source": snapshot.source,
        "market_price": round(market_price, 4),
    }

    if company_type == "bank":
        if snapshot.price_to_tangible_book is None or snapshot.return_on_equity is None:
            return _unavailable(snapshot, company_type, ["tangible_book_or_roe_unavailable"])
        fair_mid = market_price * (1.0 + (snapshot.return_on_equity - 0.10))
        assumptions.update(
            {
                "price_to_tangible_book": round(snapshot.price_to_tangible_book, 4),
                "return_on_equity": round(snapshot.return_on_equity, 4),
            }
        )
        methodology = "Bank scenario uses tangible book and ROE only when per-share inputs are available."
    elif company_type == "reit":
        affo = snapshot.affo_per_share
        if affo is None or affo <= 0:
            return _unavailable(snapshot, company_type, ["affo_per_share_unavailable"])
        cap_rate = 0.06
        fair_mid = affo / cap_rate
        assumptions.update({"affo_per_share": round(affo, 4), "cap_rate": cap_rate})
        methodology = "REIT AFFO capitalization using per-share AFFO."
    elif company_type == "utility":
        if snapshot.rate_base_growth is None or snapshot.allowed_roe is None:
            return _unavailable(snapshot, company_type, ["rate_base_growth_or_allowed_roe_unavailable"])
        fair_mid = market_price * (1.0 + snapshot.rate_base_growth) * (1.0 + (snapshot.allowed_roe - 0.09))
        assumptions.update(
            {
                "rate_base_growth": round(snapshot.rate_base_growth, 4),
                "allowed_roe": round(snapshot.allowed_roe, 4),
            }
        )
        methodology = "Utility rate-base growth scenario with allowed ROE inputs."
    else:
        if snapshot.fcf_yield is None or snapshot.revenue_growth_yoy is None:
            return _unavailable(snapshot, company_type, ["fcf_yield_or_growth_unavailable"])
        fair_mid = market_price * (1.0 + snapshot.revenue_growth_yoy) / max(snapshot.fcf_yield, 0.01)
        assumptions.update(
            {
                "fcf_yield": round(snapshot.fcf_yield, 4),
                "revenue_growth_yoy": round(snapshot.revenue_growth_yoy, 4),
            }
        )
        methodology = "General operating scenario uses verified FCF yield and revenue growth only."

    return ScenarioValuationResult(
        symbol=snapshot.symbol,
        company_type=company_type,
        valuation_status="available",
        fair_value_low=round(fair_mid * 0.90, 2),
        fair_value_mid=round(fair_mid, 2),
        fair_value_high=round(fair_mid * 1.10, 2),
        methodology=methodology,
        assumptions=assumptions,
        data_quality={"inputs": snapshot.source, "scenario_date": date.today().isoformat()},
    )
