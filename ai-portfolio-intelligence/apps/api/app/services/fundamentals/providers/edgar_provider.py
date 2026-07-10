from datetime import date
from typing import Any

import httpx

from app.schemas.domain import FundamentalSnapshot


SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

COMPANY_TYPE_CONCEPTS: dict[str, list[str]] = {
    "general_operating": [
        "Revenues",
        "SalesRevenueNet",
        "OperatingIncomeLoss",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "GrossProfit",
    ],
    "bank": [
        "InterestIncomeExpenseNet",
        "NetIncomeLoss",
        "StockholdersEquity",
        "Assets",
    ],
    "reit": [
        "NetIncomeLoss",
        "RealEstateInvestmentPropertyNet",
        "PaymentsOfDividends",
    ],
    "utility": [
        "RegulatedAndUnregulatedOperatingRevenue",
        "OperatingIncomeLoss",
        "PropertyPlantAndEquipmentNet",
    ],
}


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


def _point_in_time_values(facts: dict[str, Any], concept: str) -> list[dict[str, Any]]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    concept_data = us_gaap.get(concept)
    if not concept_data:
        return []
    rows: list[dict[str, Any]] = []
    for unit, unit_values in (concept_data.get("units") or {}).items():
        for row in unit_values:
            if row.get("val") is None:
                continue
            rows.append(
                {
                    "concept": concept,
                    "unit": unit,
                    "value": float(row["val"]),
                    "end": row.get("end"),
                    "filed": row.get("filed"),
                    "form": row.get("form"),
                    "fy": row.get("fy"),
                    "fp": row.get("fp"),
                }
            )
    return sorted(
        rows,
        key=lambda item: (str(item.get("filed", "")), str(item.get("end", ""))),
        reverse=True,
    )


def _latest_filed_value(facts: dict[str, Any], concept: str) -> tuple[float | None, str | None]:
    rows = _point_in_time_values(facts, concept)
    if not rows:
        return None, None
    latest = rows[0]
    filed = latest.get("filed")
    report_date = date.fromisoformat(filed) if filed else None
    return float(latest["value"]), report_date.isoformat() if report_date else None


def fetch_company_facts_payload(symbol: str) -> dict[str, Any] | None:
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
        return response.json()
    except Exception:
        return None


def extract_xbrl_facts(symbol: str, company_type: str = "general_operating") -> list[dict[str, Any]]:
    payload = fetch_company_facts_payload(symbol)
    if not payload:
        return []
    concepts = COMPANY_TYPE_CONCEPTS.get(company_type, COMPANY_TYPE_CONCEPTS["general_operating"])
    extracted: list[dict[str, Any]] = []
    for concept in concepts:
        extracted.extend(_point_in_time_values(payload, concept)[:3])
    return extracted


def fetch_edgar_fundamental_snapshot(symbol: str, *, company_type: str = "general_operating") -> FundamentalSnapshot | None:
    """Fetch a point-in-time fundamental snapshot from SEC EDGAR company facts."""
    payload = fetch_company_facts_payload(symbol)
    if not payload:
        return None

    revenue, revenue_filed = _latest_filed_value(payload, "Revenues")
    if revenue is None:
        revenue, revenue_filed = _latest_filed_value(payload, "SalesRevenueNet")
    operating_income, _ = _latest_filed_value(payload, "OperatingIncomeLoss")
    cash, _ = _latest_filed_value(payload, "CashAndCashEquivalentsAtCarryingValue")
    debt, _ = _latest_filed_value(payload, "LongTermDebtNoncurrent")
    operating_cash_flow, _ = _latest_filed_value(payload, "NetCashProvidedByUsedInOperatingActivities")
    capex, _ = _latest_filed_value(payload, "PaymentsToAcquirePropertyPlantAndEquipment")
    gross_profit, _ = _latest_filed_value(payload, "GrossProfit")
    equity, _ = _latest_filed_value(payload, "StockholdersEquity")
    if revenue is None or revenue <= 0:
        return None

    report_date = date.fromisoformat(revenue_filed) if revenue_filed else date.today()
    gross_margin = (gross_profit / revenue) if gross_profit is not None and revenue > 0 else None
    operating_margin = (operating_income / revenue) if operating_income is not None else None
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - abs(capex)
    elif operating_cash_flow is not None:
        free_cash_flow = operating_cash_flow

    return FundamentalSnapshot(
        symbol=symbol.upper(),
        period="TTM",
        report_date=report_date,
        revenue_growth_yoy=0.0,
        gross_margin=round(gross_margin, 4) if gross_margin is not None else 0.0,
        operating_margin=round(operating_margin, 4) if operating_margin is not None else 0.0,
        free_cash_flow=free_cash_flow if free_cash_flow is not None else 0.0,
        cash=cash if cash is not None else 0.0,
        total_debt=debt if debt is not None else 0.0,
        pe_forward=None,
        ev_sales=None,
        fcf_yield=None,
        return_on_equity=round((operating_income / equity), 4) if operating_income is not None and equity else None,
        source="sec_edgar_companyfacts",
    )
