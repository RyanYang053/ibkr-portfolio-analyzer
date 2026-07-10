from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.domain import FundamentalSnapshot


class ScenarioValuationResult(BaseModel):
    symbol: str
    company_type: str
    fair_value_low: float | None = None
    fair_value_mid: float | None = None
    fair_value_high: float | None = None
    methodology: str
    assumptions: dict[str, float | str] = Field(default_factory=dict)
    data_quality: dict[str, str] = Field(default_factory=dict)


def _company_type_from_sector(sector: str, stock_type: str) -> str:
    if stock_type == "reit_heuristic" or sector == "Real Estate":
        return "reit"
    if stock_type == "financials_heuristic" or sector == "Financials":
        return "bank"
    if stock_type == "utilities_heuristic" or sector == "Utilities":
        return "utility"
    return "general_operating"


def run_scenario_valuation(
    snapshot: FundamentalSnapshot,
    *,
    sector: str = "Unknown",
    stock_type: str = "universal",
    market_price: float | None = None,
) -> ScenarioValuationResult:
    company_type = _company_type_from_sector(sector, stock_type)
    price = market_price or max(snapshot.pe_forward or 0.0, 1.0)
    assumptions: dict[str, float | str] = {"report_date": snapshot.report_date.isoformat(), "source": snapshot.source}

    if company_type == "bank":
        book_proxy = max(snapshot.cash - snapshot.total_debt, snapshot.cash * 0.2, 1.0)
        roe = snapshot.return_on_equity or snapshot.operating_margin or 0.1
        ptbv = snapshot.price_to_tangible_book or (price / book_proxy if book_proxy > 0 else 1.0)
        fair_mid = book_proxy * ptbv * (1.0 + (roe - 0.1))
        assumptions.update({"roe": round(roe, 4), "book_proxy": round(book_proxy, 2)})
        methodology = "Bank residual-income style scenario using book proxy, ROE, and P/TBV heuristics."
    elif company_type == "reit":
        ffo = snapshot.ffo_per_share or (snapshot.free_cash_flow / max(price, 1.0))
        affo = snapshot.affo_per_share or ffo * 0.9
        cap_rate = 0.06
        fair_mid = affo / cap_rate if affo > 0 else price
        assumptions.update({"affo_per_share": round(affo, 4), "cap_rate": cap_rate})
        methodology = "REIT AFFO capitalization scenario with configurable cap-rate band."
    elif company_type == "utility":
        rate_base_growth = snapshot.rate_base_growth or snapshot.revenue_growth_yoy or 0.03
        allowed_roe = snapshot.allowed_roe or 0.09
        fair_mid = price * (1.0 + rate_base_growth) * (1.0 + (allowed_roe - 0.09))
        assumptions.update({"rate_base_growth": round(rate_base_growth, 4), "allowed_roe": round(allowed_roe, 4)})
        methodology = "Utility rate-base growth scenario with allowed ROE normalization."
    else:
        fcf_yield = snapshot.fcf_yield or (snapshot.free_cash_flow / max(price, 1.0) if price > 0 else 0.04)
        growth = snapshot.revenue_growth_yoy or 0.05
        base_multiple = 1.0 / max(fcf_yield, 0.01)
        fair_mid = price * (1.0 + growth) * min(base_multiple / 20.0, 1.5)
        assumptions.update({"fcf_yield": round(fcf_yield, 4), "revenue_growth_yoy": round(growth, 4)})
        methodology = "General operating company FCF-yield and growth scenario valuation."

    return ScenarioValuationResult(
        symbol=snapshot.symbol,
        company_type=company_type,
        fair_value_low=round(fair_mid * 0.85, 2),
        fair_value_mid=round(fair_mid, 2),
        fair_value_high=round(fair_mid * 1.15, 2),
        methodology=methodology,
        assumptions=assumptions,
        data_quality={"inputs": snapshot.source, "scenario_date": date.today().isoformat()},
    )
