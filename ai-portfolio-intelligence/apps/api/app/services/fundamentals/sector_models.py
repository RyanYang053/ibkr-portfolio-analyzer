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
        "technology_heuristic",
        "financials_heuristic",
        "reit_heuristic",
        "utilities_heuristic",
        "consumer_cyclical_heuristic",
        "consumer_defensive_heuristic",
        "communication_services_heuristic",
        "healthcare_heuristic",
        "energy_heuristic",
        "industrials_heuristic",
        "materials_heuristic",
        "diversified_heuristic",
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
        model_name="technology_heuristic",
    ),
    "Financials": SectorValuationNorms(
        pe_low=6.0, pe_high=18.0,
        ev_sales_low=0.5, ev_sales_high=6.0,
        gross_margin_low=0.20, gross_margin_high=0.70,
        operating_margin_low=0.10, operating_margin_high=0.45,
        growth_low=-0.05, growth_high=0.15,
        fcf_yield_low=0.01, fcf_yield_high=0.08,
        model_name="financials_heuristic",
    ),
    "Consumer Cyclical": SectorValuationNorms(
        pe_low=8.0, pe_high=30.0,
        ev_sales_low=0.5, ev_sales_high=8.0,
        gross_margin_low=0.20, gross_margin_high=0.65,
        operating_margin_low=0.03, operating_margin_high=0.22,
        growth_low=-0.10, growth_high=0.25,
        fcf_yield_low=0.0, fcf_yield_high=0.07,
        model_name="consumer_cyclical_heuristic",
    ),
    "Consumer Defensive": SectorValuationNorms(
        pe_low=10.0, pe_high=28.0,
        ev_sales_low=0.8, ev_sales_high=6.0,
        gross_margin_low=0.25, gross_margin_high=0.60,
        operating_margin_low=0.08, operating_margin_high=0.25,
        growth_low=-0.03, growth_high=0.12,
        fcf_yield_low=0.01, fcf_yield_high=0.06,
        model_name="consumer_defensive_heuristic",
    ),
    "Communication Services": SectorValuationNorms(
        pe_low=10.0, pe_high=35.0,
        ev_sales_low=1.0, ev_sales_high=12.0,
        gross_margin_low=0.30, gross_margin_high=0.80,
        operating_margin_low=0.05, operating_margin_high=0.35,
        growth_low=-0.05, growth_high=0.30,
        fcf_yield_low=0.0, fcf_yield_high=0.06,
        model_name="communication_services_heuristic",
    ),
    "Healthcare": SectorValuationNorms(
        pe_low=10.0, pe_high=35.0,
        ev_sales_low=1.0, ev_sales_high=15.0,
        gross_margin_low=0.35, gross_margin_high=0.85,
        operating_margin_low=0.05, operating_margin_high=0.30,
        growth_low=-0.05, growth_high=0.25,
        fcf_yield_low=-0.02, fcf_yield_high=0.05,
        model_name="healthcare_heuristic",
    ),
    "Real Estate": SectorValuationNorms(
        pe_low=8.0, pe_high=25.0,
        ev_sales_low=2.0, ev_sales_high=20.0,
        gross_margin_low=0.30, gross_margin_high=0.75,
        operating_margin_low=0.10, operating_margin_high=0.45,
        growth_low=-0.05, growth_high=0.12,
        fcf_yield_low=0.02, fcf_yield_high=0.08,
        model_name="reit_heuristic",
    ),
    "Energy": SectorValuationNorms(
        pe_low=5.0, pe_high=20.0,
        ev_sales_low=0.3, ev_sales_high=4.0,
        gross_margin_low=0.10, gross_margin_high=0.45,
        operating_margin_low=0.02, operating_margin_high=0.25,
        growth_low=-0.20, growth_high=0.20,
        fcf_yield_low=0.0, fcf_yield_high=0.10,
        model_name="energy_heuristic",
    ),
    "Industrials": SectorValuationNorms(
        pe_low=8.0, pe_high=28.0,
        ev_sales_low=0.5, ev_sales_high=6.0,
        gross_margin_low=0.15, gross_margin_high=0.45,
        operating_margin_low=0.04, operating_margin_high=0.20,
        growth_low=-0.10, growth_high=0.18,
        fcf_yield_low=0.0, fcf_yield_high=0.06,
        model_name="industrials_heuristic",
    ),
    "Utilities": SectorValuationNorms(
        pe_low=10.0, pe_high=22.0,
        ev_sales_low=1.0, ev_sales_high=6.0,
        gross_margin_low=0.20, gross_margin_high=0.55,
        operating_margin_low=0.10, operating_margin_high=0.28,
        growth_low=-0.02, growth_high=0.08,
        fcf_yield_low=0.02, fcf_yield_high=0.07,
        model_name="utilities_heuristic",
    ),
    "Materials": SectorValuationNorms(
        pe_low=6.0, pe_high=22.0,
        ev_sales_low=0.4, ev_sales_high=5.0,
        gross_margin_low=0.10, gross_margin_high=0.40,
        operating_margin_low=0.02, operating_margin_high=0.18,
        growth_low=-0.15, growth_high=0.15,
        fcf_yield_low=0.0, fcf_yield_high=0.08,
        model_name="materials_heuristic",
    ),
    "Diversified": SectorValuationNorms(
        pe_low=10.0, pe_high=30.0,
        ev_sales_low=0.5, ev_sales_high=8.0,
        gross_margin_low=0.15, gross_margin_high=0.65,
        operating_margin_low=0.05, operating_margin_high=0.25,
        growth_low=-0.05, growth_high=0.15,
        fcf_yield_low=0.0, fcf_yield_high=0.05,
        model_name="diversified_heuristic",
    ),
}

DEFAULT_NORMS = SECTOR_VALUATION_NORMS["Technology"]


def get_sector_norms(sector: str) -> SectorValuationNorms:
    return SECTOR_VALUATION_NORMS.get(sector, DEFAULT_NORMS)


def _linear(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _score_universal_heuristic(fundamentals: FundamentalSnapshot, sector: str) -> dict[str, float]:
    from statistics import fmean

    norms = get_sector_norms(sector)

    def pe_score(pe: float) -> float:
        if pe <= 0:
            return 20.0
        return max(0.0, min(100.0, 110.0 - _linear(pe, norms.pe_low, norms.pe_high)))

    scores: dict[str, float] = {}
    scores["business_quality"] = fmean(
        [
            _linear(fundamentals.gross_margin, norms.gross_margin_low, norms.gross_margin_high),
            _linear(fundamentals.operating_margin, norms.operating_margin_low, norms.operating_margin_high),
        ]
    )
    scores["growth"] = _linear(fundamentals.revenue_growth_yoy, norms.growth_low, norms.growth_high)

    profitability_parts = [_linear(fundamentals.operating_margin, norms.operating_margin_low, norms.operating_margin_high)]
    if fundamentals.fcf_yield is not None:
        profitability_parts.append(_linear(fundamentals.fcf_yield, norms.fcf_yield_low, norms.fcf_yield_high))
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
        valuation_parts.append(max(0.0, min(100.0, 105.0 - _linear(fundamentals.ev_sales, norms.ev_sales_low, norms.ev_sales_high))))
    if fundamentals.fcf_yield is not None:
        valuation_parts.append(_linear(fundamentals.fcf_yield, norms.fcf_yield_low, norms.fcf_yield_high))
    if valuation_parts:
        scores["valuation"] = fmean(valuation_parts)
    return scores


def score_fundamentals_for_sector(fundamentals: FundamentalSnapshot, sector: str) -> dict[str, float]:
    sector_key = sector or "Unknown"
    if sector_key == "Financials":
        return _score_financials_sector(fundamentals)
    if sector_key == "Real Estate":
        return _score_reit_sector(fundamentals)
    if sector_key == "Utilities":
        return _score_utilities_sector(fundamentals)
    return _score_universal_heuristic(fundamentals, sector_key)


def _has_sector_inputs(fundamentals: FundamentalSnapshot, fields: list[str]) -> bool:
    return any(getattr(fundamentals, field, None) is not None for field in fields)


def _score_financials_sector(fundamentals: FundamentalSnapshot) -> dict[str, float]:
    from statistics import fmean

    required = ["price_to_tangible_book", "return_on_equity", "net_interest_margin"]
    if not _has_sector_inputs(fundamentals, required):
        return _score_universal_heuristic(fundamentals, "Financials")

    scores: dict[str, float] = {}
    scores["business_quality"] = fmean(
        [
            _linear(float(fundamentals.return_on_equity or 0.0), 0.08, 0.18),
            _linear(float(fundamentals.net_interest_margin or 0.0), 0.02, 0.04),
        ]
    )
    scores["growth"] = _linear(fundamentals.revenue_growth_yoy, -0.03, 0.10)
    scores["profitability"] = _linear(float(fundamentals.return_on_equity or 0.0), 0.08, 0.18)
    scores["balance_sheet"] = _linear((fundamentals.cash - fundamentals.total_debt) / max(abs(fundamentals.total_debt), 1.0), -0.5, 0.5)
    scores["valuation"] = max(
        0.0,
        min(100.0, 110.0 - _linear(float(fundamentals.price_to_tangible_book or 1.5), 0.8, 2.5)),
    )
    return scores


def _score_reit_sector(fundamentals: FundamentalSnapshot) -> dict[str, float]:
    from statistics import fmean

    required = ["ffo_per_share", "occupancy_rate"]
    if not _has_sector_inputs(fundamentals, required):
        return _score_universal_heuristic(fundamentals, "Real Estate")

    scores: dict[str, float] = {}
    scores["business_quality"] = _linear(float(fundamentals.occupancy_rate or 0.0), 0.88, 0.98)
    scores["growth"] = _linear(fundamentals.revenue_growth_yoy, -0.02, 0.08)
    ffo_metric = fundamentals.affo_per_share or fundamentals.ffo_per_share or 0.0
    scores["profitability"] = _linear(float(ffo_metric), 1.0, 6.0)
    scores["balance_sheet"] = _linear((fundamentals.cash - fundamentals.total_debt) / max(abs(fundamentals.total_debt), 1.0), -0.3, 0.3)
    if fundamentals.fcf_yield is not None:
        scores["valuation"] = _linear(fundamentals.fcf_yield, 0.03, 0.08)
    elif fundamentals.pe_forward is not None and fundamentals.pe_forward > 0:
        scores["valuation"] = max(0.0, min(100.0, 110.0 - _linear(fundamentals.pe_forward, 10.0, 25.0)))
    return scores


def _score_utilities_sector(fundamentals: FundamentalSnapshot) -> dict[str, float]:
    from statistics import fmean

    required = ["rate_base_growth", "allowed_roe"]
    if not _has_sector_inputs(fundamentals, required):
        return _score_universal_heuristic(fundamentals, "Utilities")
    scores["growth"] = _linear(float(fundamentals.rate_base_growth or 0.0), 0.01, 0.05)
    scores["profitability"] = _linear(fundamentals.operating_margin, 0.12, 0.28)
    scores["balance_sheet"] = _linear((fundamentals.cash - fundamentals.total_debt) / max(abs(fundamentals.total_debt), 1.0), -0.2, 0.2)
    scores["valuation"] = fmean(
        [
            max(0.0, min(100.0, 110.0 - _linear(float(fundamentals.pe_forward or 18.0), 12.0, 22.0))),
            _linear(fundamentals.fcf_yield or 0.03, 0.02, 0.06),
        ]
    )
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
