from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

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


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _append_linear(output: list[float], value: object, low: float, high: float) -> None:
    parsed = _number(value)
    if parsed is not None:
        output.append(_linear(parsed, low, high))


def _pe_score(pe: float, norms: SectorValuationNorms) -> float:
    if pe <= 0:
        return 20.0
    return max(0.0, min(100.0, 110.0 - _linear(pe, norms.pe_low, norms.pe_high)))


def _balance_sheet_score(fundamentals: FundamentalSnapshot) -> float | None:
    cash = _number(fundamentals.cash)
    debt = _number(fundamentals.total_debt)
    if cash is None or debt is None:
        return None
    capital = abs(cash) + abs(debt)
    if capital <= 0:
        return None
    net_cash_ratio = (cash - debt) / capital
    return max(0.0, min(100.0, 50.0 + 50.0 * net_cash_ratio))


def _debt_normalized_balance_sheet(fundamentals: FundamentalSnapshot, low: float, high: float) -> float | None:
    cash = _number(fundamentals.cash)
    debt = _number(fundamentals.total_debt)
    if cash is None or debt is None:
        return None
    denominator = max(abs(debt), 1.0)
    return _linear((cash - debt) / denominator, low, high)


def _score_universal_heuristic(fundamentals: FundamentalSnapshot, sector: str) -> dict[str, float]:
    norms = get_sector_norms(sector)
    scores: dict[str, float] = {}

    quality_parts: list[float] = []
    _append_linear(quality_parts, fundamentals.gross_margin, norms.gross_margin_low, norms.gross_margin_high)
    _append_linear(
        quality_parts,
        fundamentals.operating_margin,
        norms.operating_margin_low,
        norms.operating_margin_high,
    )
    if quality_parts:
        scores["business_quality"] = fmean(quality_parts)

    growth = _number(fundamentals.revenue_growth_yoy)
    if growth is not None:
        scores["growth"] = _linear(growth, norms.growth_low, norms.growth_high)

    profitability_parts: list[float] = []
    _append_linear(
        profitability_parts,
        fundamentals.operating_margin,
        norms.operating_margin_low,
        norms.operating_margin_high,
    )
    if fundamentals.fcf_yield is not None:
        _append_linear(profitability_parts, fundamentals.fcf_yield, norms.fcf_yield_low, norms.fcf_yield_high)
    elif fundamentals.free_cash_flow is not None and fundamentals.free_cash_flow != 0:
        profitability_parts.append(75.0 if fundamentals.free_cash_flow > 0 else 15.0)
    if profitability_parts:
        scores["profitability"] = fmean(profitability_parts)

    balance_sheet = _balance_sheet_score(fundamentals)
    if balance_sheet is not None:
        scores["balance_sheet"] = balance_sheet

    valuation_parts: list[float] = []
    pe_forward = _number(fundamentals.pe_forward)
    if pe_forward is not None and pe_forward > 0:
        valuation_parts.append(_pe_score(pe_forward, norms))
    ev_sales = _number(fundamentals.ev_sales)
    if ev_sales is not None and ev_sales >= 0:
        valuation_parts.append(max(0.0, min(100.0, 105.0 - _linear(ev_sales, norms.ev_sales_low, norms.ev_sales_high))))
    if fundamentals.fcf_yield is not None:
        _append_linear(valuation_parts, fundamentals.fcf_yield, norms.fcf_yield_low, norms.fcf_yield_high)
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
    return all(getattr(fundamentals, field, None) is not None for field in fields)


def _score_financials_sector(fundamentals: FundamentalSnapshot) -> dict[str, float]:
    required = ["price_to_tangible_book", "return_on_equity", "net_interest_margin"]
    if not _has_sector_inputs(fundamentals, required):
        return _score_universal_heuristic(fundamentals, "Financials")

    scores: dict[str, float] = {}
    quality_parts: list[float] = []
    _append_linear(quality_parts, fundamentals.return_on_equity, 0.08, 0.18)
    _append_linear(quality_parts, fundamentals.net_interest_margin, 0.02, 0.04)
    if quality_parts:
        scores["business_quality"] = fmean(quality_parts)

    growth = _number(fundamentals.revenue_growth_yoy)
    if growth is not None:
        scores["growth"] = _linear(growth, -0.03, 0.10)

    roe = _number(fundamentals.return_on_equity)
    if roe is not None:
        scores["profitability"] = _linear(roe, 0.08, 0.18)

    balance_sheet = _debt_normalized_balance_sheet(fundamentals, -0.5, 0.5)
    if balance_sheet is not None:
        scores["balance_sheet"] = balance_sheet

    ptb = _number(fundamentals.price_to_tangible_book)
    if ptb is not None:
        scores["valuation"] = max(0.0, min(100.0, 110.0 - _linear(ptb, 0.8, 2.5)))
    return scores


def _score_reit_sector(fundamentals: FundamentalSnapshot) -> dict[str, float]:
    required = ["ffo_per_share", "occupancy_rate"]
    if not _has_sector_inputs(fundamentals, required):
        return _score_universal_heuristic(fundamentals, "Real Estate")

    scores: dict[str, float] = {}
    occupancy = _number(fundamentals.occupancy_rate)
    if occupancy is not None:
        scores["business_quality"] = _linear(occupancy, 0.88, 0.98)

    growth = _number(fundamentals.revenue_growth_yoy)
    if growth is not None:
        scores["growth"] = _linear(growth, -0.02, 0.08)

    ffo_metric = (
        fundamentals.affo_per_share
        if fundamentals.affo_per_share is not None
        else fundamentals.ffo_per_share
    )
    if ffo_metric is not None:
        scores["profitability"] = _linear(float(ffo_metric), 1.0, 6.0)

    balance_sheet = _debt_normalized_balance_sheet(fundamentals, -0.3, 0.3)
    if balance_sheet is not None:
        scores["balance_sheet"] = balance_sheet

    valuation_parts: list[float] = []
    if fundamentals.fcf_yield is not None:
        _append_linear(valuation_parts, fundamentals.fcf_yield, 0.03, 0.08)
    pe_forward = _number(fundamentals.pe_forward)
    if pe_forward is not None and pe_forward > 0:
        valuation_parts.append(max(0.0, min(100.0, 110.0 - _linear(pe_forward, 10.0, 25.0))))
    if valuation_parts:
        scores["valuation"] = fmean(valuation_parts)
    return scores


def _score_utilities_sector(fundamentals: FundamentalSnapshot) -> dict[str, float]:
    required = ["rate_base_growth", "allowed_roe"]
    if not _has_sector_inputs(fundamentals, required):
        return _score_universal_heuristic(fundamentals, "Utilities")

    scores: dict[str, float] = {}
    allowed_roe = _number(fundamentals.allowed_roe)
    if allowed_roe is not None:
        scores["business_quality"] = _linear(allowed_roe, 0.08, 0.12)

    rate_base_growth = _number(fundamentals.rate_base_growth)
    if rate_base_growth is not None:
        scores["growth"] = _linear(rate_base_growth, 0.01, 0.05)

    if fundamentals.operating_margin is not None:
        scores["profitability"] = _linear(fundamentals.operating_margin, 0.12, 0.28)

    balance_sheet = _debt_normalized_balance_sheet(fundamentals, -0.2, 0.2)
    if balance_sheet is not None:
        scores["balance_sheet"] = balance_sheet

    valuation_parts: list[float] = []
    pe_forward = _number(fundamentals.pe_forward)
    if pe_forward is not None and pe_forward > 0:
        valuation_parts.append(max(0.0, min(100.0, 110.0 - _linear(pe_forward, 12.0, 22.0))))
    if fundamentals.fcf_yield is not None:
        _append_linear(valuation_parts, fundamentals.fcf_yield, 0.02, 0.06)
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
