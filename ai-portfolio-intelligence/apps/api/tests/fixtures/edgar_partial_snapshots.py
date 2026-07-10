from __future__ import annotations

from datetime import date

from app.schemas.domain import FundamentalSnapshot


def _base_snapshot(**overrides) -> FundamentalSnapshot:
    payload = dict(
        symbol="TEST",
        period="TTM",
        report_date=date(2025, 12, 31),
        revenue_growth_yoy=None,
        gross_margin=None,
        operating_margin=None,
        free_cash_flow=None,
        cash=None,
        total_debt=None,
        pe_forward=None,
        ev_sales=None,
        fcf_yield=None,
        source="edgar_partial",
        price_to_tangible_book=None,
        return_on_equity=None,
        net_interest_margin=None,
        ffo_per_share=None,
        affo_per_share=None,
        occupancy_rate=None,
        rate_base_growth=None,
        allowed_roe=None,
    )
    payload.update(overrides)
    return FundamentalSnapshot(**payload)


REVENUE_ONLY = _base_snapshot(revenue_growth_yoy=0.12)

REVENUE_AND_GROSS_MARGIN = _base_snapshot(revenue_growth_yoy=0.12, gross_margin=0.45)

OPERATING_INCOME_ONLY = _base_snapshot(operating_margin=0.18)

CASH_NO_DEBT = _base_snapshot(cash=5_000_000.0, total_debt=None)

DEBT_NO_CASH = _base_snapshot(cash=None, total_debt=5_000_000.0)

NEGATIVE_FCF = _base_snapshot(free_cash_flow=-1_000_000.0, operating_margin=0.10)

BANK_MISSING_NIM = _base_snapshot(
    price_to_tangible_book=1.1,
    return_on_equity=0.12,
    net_interest_margin=None,
)

REIT_MISSING_AFFO = _base_snapshot(ffo_per_share=3.5, occupancy_rate=0.94, affo_per_share=None)

UTILITY_MISSING_ALLOWED_ROE = _base_snapshot(rate_base_growth=0.03, allowed_roe=None)

ALL_SPECIALIST_INPUTS_FINANCIALS = _base_snapshot(
    price_to_tangible_book=1.1,
    return_on_equity=0.12,
    net_interest_margin=0.03,
    revenue_growth_yoy=0.04,
    cash=1_000_000.0,
    total_debt=500_000.0,
)

LEGITIMATE_ZERO_FCF_YIELD = _base_snapshot(
    revenue_growth_yoy=0.05,
    gross_margin=0.40,
    operating_margin=0.20,
    fcf_yield=0.0,
    cash=1_000_000.0,
    total_debt=500_000.0,
)

STALE_FILING = _base_snapshot(
    report_date=date(2020, 1, 1),
    revenue_growth_yoy=0.05,
    gross_margin=0.40,
    operating_margin=0.20,
    cash=1_000_000.0,
    total_debt=500_000.0,
)

PARTIAL_FIXTURES = {
    "revenue_only": REVENUE_ONLY,
    "revenue_and_gross_margin": REVENUE_AND_GROSS_MARGIN,
    "operating_income_only": OPERATING_INCOME_ONLY,
    "cash_no_debt": CASH_NO_DEBT,
    "debt_no_cash": DEBT_NO_CASH,
    "negative_fcf": NEGATIVE_FCF,
    "bank_missing_nim": BANK_MISSING_NIM,
    "reit_missing_affo": REIT_MISSING_AFFO,
    "utility_missing_allowed_roe": UTILITY_MISSING_ALLOWED_ROE,
    "all_specialist_inputs_financials": ALL_SPECIALIST_INPUTS_FINANCIALS,
    "legitimate_zero_fcf_yield": LEGITIMATE_ZERO_FCF_YIELD,
    "stale_filing": STALE_FILING,
}
