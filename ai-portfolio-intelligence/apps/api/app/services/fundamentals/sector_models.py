from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.schemas.domain import FundamentalSnapshot


@dataclass(frozen=True)
class SectorValuationNorms:
    pe_low: float
    pe_high: float
    ev_sales_low: float
    ev_sales_high: float
    gross_margin_low: float
    gross_margin_high: float
    operating_margin_low: float
    operating_margin_high: float
    growth_low: float
    growth_high: float
    fcf_yield_low: float
    fcf_yield_high: float
    model_name: str


SECTOR_MODEL_NAMES = frozenset(
    {
        "technology_growth",
        "financials_pb_rotce",
        "reit_affo_nav",
        "dividend_utility",
        "consumer_cyclical",
        "stable_consumer",
        "communication_services",
        "healthcare_innovation",
        "energy_cyclical",
        "industrials",
        "materials_cyclical",
        "diversified_index",
    }
)
SECTOR_VALUATION_NORMS: dict[str, SectorValuationNorms] = {
    "Technology": SectorValuationNorms(
        pe_low=12.0, pe_high=45.0,
        ev_sales_low=2.0, ev_sales_high=18.0,
        gross_margin_low=0.35, gross_margin_high=0.85,
        operating_margin_low=0.05, operating_margin_high=0.40,
        growth_low=-0.05, growth_high=0.40,
        fcf_yield_low=-0.01, fcf_yield_high=0.06,
        model_name="technology_growth",
    ),
    "Financials": SectorValuationNorms(
        pe_low=6.0, pe_high=18.0,
        ev_sales_low=0.5, ev_sales_high=6.0,
        gross_margin_low=0.20, gross_margin_high=0.70,
        operating_margin_low=0.10, operating_margin_high=0.45,
        growth_low=-0.05, growth_high=0.15,
        fcf_yield_low=0.01, fcf_yield_high=0.08,
        model_name="financials_pb_rotce",
    ),
    "Consumer Cyclical": SectorValuationNorms(
        pe_low=8.0, pe_high=30.0,
        ev_sales_low=0.5, ev_sales_high=8.0,
        gross_margin_low=0.20, gross_margin_high=0.65,
        operating_margin_low=0.03, operating_margin_high=0.22,
        growth_low=-0.10, growth_high=0.25,
        fcf_yield_low=0.0, fcf_yield_high=0.07,
        model_name="consumer_cyclical",
    ),
    "Consumer Defensive": SectorValuationNorms(
        pe_low=10.0, pe_high=28.0,
        ev_sales_low=0.8, ev_sales_high=6.0,
        gross_margin_low=0.25, gross_margin_high=0.60,
        operating_margin_low=0.08, operating_margin_high=0.25,
        growth_low=-0.03, growth_high=0.12,
        fcf_yield_low=0.01, fcf_yield_high=0.06,
        model_name="stable_consumer",
    ),
    "Communication Services": SectorValuationNorms(
        pe_low=10.0, pe_high=35.0,
        ev_sales_low=1.0, ev_sales_high=12.0,
        gross_margin_low=0.30, gross_margin_high=0.80,
        operating_margin_low=0.05, operating_margin_high=0.35,
        growth_low=-0.05, growth_high=0.30,
        fcf_yield_low=0.0, fcf_yield_high=0.06,
        model_name="communication_services",
    ),
    "Healthcare": SectorValuationNorms(
        pe_low=10.0, pe_high=35.0,
        ev_sales_low=1.0, ev_sales_high=15.0,
        gross_margin_low=0.35, gross_margin_high=0.85,
        operating_margin_low=0.05, operating_margin_high=0.30,
        growth_low=-0.05, growth_high=0.25,
        fcf_yield_low=-0.02, fcf_yield_high=0.05,
        model_name="healthcare_innovation",
    ),
    "Real Estate": SectorValuationNorms(
        pe_low=8.0, pe_high=25.0,
        ev_sales_low=2.0, ev_sales_high=20.0,
        gross_margin_low=0.30, gross_margin_high=0.75,
        operating_margin_low=0.10, operating_margin_high=0.45,
        growth_low=-0.05, growth_high=0.12,
        fcf_yield_low=0.02, fcf_yield_high=0.08,
        model_name="reit_affo_nav",
    ),
    "Energy": SectorValuationNorms(
        pe_low=5.0, pe_high=20.0,
        ev_sales_low=0.3, ev_sales_high=4.0,
        gross_margin_low=0.10, gross_margin_high=0.45,
        operating_margin_low=0.02, operating_margin_high=0.25,
        growth_low=-0.20, growth_high=0.20,
        fcf_yield_low=0.0, fcf_yield_high=0.10,
        model_name="energy_cyclical",
    ),
    "Industrials": SectorValuationNorms(
        pe_low=8.0, pe_high=28.0,
        ev_sales_low=0.5, ev_sales_high=6.0,
        gross_margin_low=0.15, gross_margin_high=0.45,
        operating_margin_low=0.04, operating_margin_high=0.20,
        growth_low=-0.10, growth_high=0.18,
        fcf_yield_low=0.0, fcf_yield_high=0.06,
        model_name="industrials",
    ),
    "Utilities": SectorValuationNorms(
        pe_low=10.0, pe_high=22.0,
        ev_sales_low=1.0, ev_sales_high=6.0,
        gross_margin_low=0.20, gross_margin_high=0.55,
        operating_margin_low=0.10, operating_margin_high=0.28,
        growth_low=-0.02, growth_high=0.08,
        fcf_yield_low=0.02, fcf_yield_high=0.07,
        model_name="dividend_utility",
    ),
    "Materials": SectorValuationNorms(
        pe_low=6.0, pe_high=22.0,
        ev_sales_low=0.4, ev_sales_high=5.0,
        gross_margin_low=0.10, gross_margin_high=0.40,
        operating_margin_low=0.02, operating_margin_high=0.18,
        growth_low=-0.15, growth_high=0.15,
        fcf_yield_low=0.0, fcf_yield_high=0.08,
        model_name="materials_cyclical",
    ),
    "Diversified": SectorValuationNorms(
        pe_low=10.0, pe_high=30.0,
        ev_sales_low=0.5, ev_sales_high=8.0,
        gross_margin_low=0.15, gross_margin_high=0.65,
        operating_margin_low=0.05, operating_margin_high=0.25,
        growth_low=-0.05, growth_high=0.15,
        fcf_yield_low=0.0, fcf_yield_high=0.05,
        model_name="diversified_index",
    ),
}

DEFAULT_NORMS = SECTOR_VALUATION_NORMS["Technology"]


def get_sector_norms(sector: str) -> SectorValuationNorms:
    return SECTOR_VALUATION_NORMS.get(sector, DEFAULT_NORMS)


def score_fundamentals_for_sector(fundamentals: FundamentalSnapshot, sector: str) -> dict[str, float]:
    from statistics import fmean

    norms = get_sector_norms(sector)

    def linear(value: float, low: float, high: float) -> float:
        if high <= low:
            return 50.0
        return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))

    def pe_score(pe: float) -> float:
        if pe <= 0:
            return 20.0
        return max(0.0, min(100.0, 110.0 - linear(pe, norms.pe_low, norms.pe_high)))

    scores: dict[str, float] = {}
    scores["business_quality"] = fmean(
        [
            linear(fundamentals.gross_margin, norms.gross_margin_low, norms.gross_margin_high),
            linear(fundamentals.operating_margin, norms.operating_margin_low, norms.operating_margin_high),
        ]
    )
    scores["growth"] = linear(fundamentals.revenue_growth_yoy, norms.growth_low, norms.growth_high)

    profitability_parts = [linear(fundamentals.operating_margin, norms.operating_margin_low, norms.operating_margin_high)]
    if fundamentals.fcf_yield is not None:
        profitability_parts.append(linear(fundamentals.fcf_yield, norms.fcf_yield_low, norms.fcf_yield_high))
    elif fundamentals.free_cash_flow != 0:
        profitability_parts.append(75.0 if fundamentals.free_cash_flow > 0 else 15.0)
    scores["profitability"] = fmean(profitability_parts)

    capital = abs(fundamentals.cash) + abs(fundamentals.total_debt)
    if capital > 0:
        net_cash_ratio = (fundamentals.cash - fundamentals.total_debt) / capital
        scores["balance_sheet"] = max(0.0, min(100.0, 50.0 + 50.0 * net_cash_ratio))

    valuation_parts: list[float] = []
    if fundamentals.pe_forward is not None and fundamentals.pe_forward > 0:
        valuation_parts.append(pe_score(fundamentals.pe_forward))
    if fundamentals.ev_sales is not None and fundamentals.ev_sales >= 0:
        valuation_parts.append(max(0.0, min(100.0, 105.0 - linear(fundamentals.ev_sales, norms.ev_sales_low, norms.ev_sales_high))))
    if fundamentals.fcf_yield is not None:
        valuation_parts.append(linear(fundamentals.fcf_yield, norms.fcf_yield_low, norms.fcf_yield_high))
    if valuation_parts:
        scores["valuation"] = fmean(valuation_parts)

    return scores


def resolve_scoring_model(position) -> str:
    if position.is_etf:
        return "etf"
    if position.is_speculative:
        return "speculative_growth"
    norms = get_sector_norms(position.sector or "Unknown")
    if norms.model_name in SECTOR_MODEL_NAMES:
        return norms.model_name
    if position.stock_type in {"mega_cap_quality", "speculative_growth", "universal"}:
        return position.stock_type
    return "universal"
