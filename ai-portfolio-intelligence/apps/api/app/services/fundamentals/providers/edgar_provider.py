from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx

from app.schemas.domain import FundamentalSnapshot


SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"


def _sec_headers() -> dict[str, str]:
    from app.core.config import settings

    user_agent = getattr(settings, "sec_edgar_user_agent", "PortfolioIntelligence/1.0 contact@example.com")
    return {"User-Agent": user_agent, "Accept": "application/json"}


def _lookup_cik(symbol: str) -> str | None:
    try:
        response = httpx.get(SEC_TICKER_MAP_URL, headers=_sec_headers(), timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None
    target = symbol.upper().strip()
    for item in payload.values():
        if str(item.get("ticker", "")).upper() == target:
            cik = str(item.get("cik_str", ""))
            return cik.zfill(10)
    return None


def _latest_us_gaap_value(facts: dict[str, Any], concept: str) -> float | None:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    concept_data = us_gaap.get(concept)
    if not concept_data:
        return None
    units = concept_data.get("units", {})
    for unit_values in units.values():
        if not unit_values:
            continue
        ordered = sorted(unit_values, key=lambda row: row.get("end", ""), reverse=True)
        for row in ordered:
            value = row.get("val")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def fetch_edgar_fundamental_snapshot(symbol: str) -> FundamentalSnapshot | None:
    """Fetch a point-in-time fundamental snapshot from SEC EDGAR company facts."""
    cik = _lookup_cik(symbol)
    if not cik:
        return None
    try:
        response = httpx.get(
            SEC_COMPANY_FACTS_URL.format(cik=cik),
            headers=_sec_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    revenue = _latest_us_gaap_value(payload, "Revenues")
    if revenue is None:
        revenue = _latest_us_gaap_value(payload, "SalesRevenueNet")
    operating_income = _latest_us_gaap_value(payload, "OperatingIncomeLoss")
    cash = _latest_us_gaap_value(payload, "CashAndCashEquivalentsAtCarryingValue") or 0.0
    debt = _latest_us_gaap_value(payload, "LongTermDebtNoncurrent") or 0.0
    if revenue is None or revenue <= 0:
        return None

    operating_margin = (operating_income / revenue) if operating_income is not None else 0.0
    return FundamentalSnapshot(
        symbol=symbol.upper(),
        period="TTM",
        report_date=date.today(),
        revenue_growth_yoy=0.0,
        gross_margin=0.0,
        operating_margin=round(operating_margin, 4),
        free_cash_flow=0.0,
        cash=cash,
        total_debt=debt,
        pe_forward=0.0,
        ev_sales=0.0,
        fcf_yield=0.0,
        source="sec_edgar_companyfacts",
    )
