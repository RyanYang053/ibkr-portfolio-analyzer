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
    return rows


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dedupe_restatements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the latest filed observation for each (end, form, fp) key."""
    latest_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("end", "")), str(row.get("form", "")), str(row.get("fp", "")))
        filed = _parse_iso_date(row.get("filed"))
        existing = latest_by_key.get(key)
        if existing is None:
            latest_by_key[key] = row
            continue
        existing_filed = _parse_iso_date(existing.get("filed"))
        if filed and (existing_filed is None or filed >= existing_filed):
            latest_by_key[key] = row
    return sorted(
        latest_by_key.values(),
        key=lambda item: (str(item.get("filed", "")), str(item.get("end", ""))),
        reverse=True,
    )


def _rows_as_of(rows: list[dict[str, Any]], as_of: date | None) -> list[dict[str, Any]]:
    deduped = _dedupe_restatements(rows)
    if as_of is None:
        return deduped
    filtered: list[dict[str, Any]] = []
    for row in deduped:
        filed = _parse_iso_date(row.get("filed"))
        end = _parse_iso_date(row.get("end"))
        if filed and filed <= as_of and (end is None or end <= as_of):
            filtered.append(row)
    return filtered


def _latest_filed_value(
    facts: dict[str, Any],
    concept: str,
    *,
    as_of: date | None = None,
) -> tuple[float | None, str | None]:
    rows = _rows_as_of(_point_in_time_values(facts, concept), as_of)
    if not rows:
        return None, None
    latest = rows[0]
    filed = latest.get("filed")
    report_date = _parse_iso_date(filed)
    return float(latest["value"]), report_date.isoformat() if report_date else None


def _ttm_value(
    facts: dict[str, Any],
    concept: str,
    *,
    as_of: date | None = None,
) -> float | None:
    rows = _rows_as_of(_point_in_time_values(facts, concept), as_of)
    quarterly = [
        row
        for row in rows
        if str(row.get("fp", "")).upper() in {"Q1", "Q2", "Q3", "Q4"}
        and str(row.get("unit", "")).upper() == "USD"
    ]
    if len(quarterly) < 4:
        annual = next((row for row in rows if str(row.get("fp", "")).upper() == "FY"), None)
        return float(annual["value"]) if annual else None
    return sum(float(row["value"]) for row in quarterly[:4])


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


def extract_xbrl_facts(
    symbol: str,
    company_type: str = "general_operating",
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    payload = fetch_company_facts_payload(symbol)
    if not payload:
        return []
    concepts = COMPANY_TYPE_CONCEPTS.get(company_type, COMPANY_TYPE_CONCEPTS["general_operating"])
    extracted: list[dict[str, Any]] = []
    for concept in concepts:
        extracted.extend(_rows_as_of(_point_in_time_values(payload, concept), as_of)[:3])
    return extracted


def fetch_edgar_fundamental_snapshot(
    symbol: str,
    *,
    company_type: str = "general_operating",
    as_of: date | None = None,
) -> FundamentalSnapshot | None:
    """Fetch a point-in-time fundamental snapshot from SEC EDGAR company facts."""
    payload = fetch_company_facts_payload(symbol)
    if not payload:
        return None

    revenue, revenue_filed = _latest_filed_value(payload, "Revenues", as_of=as_of)
    if revenue is None:
        revenue, revenue_filed = _latest_filed_value(payload, "SalesRevenueNet", as_of=as_of)
    if revenue is None:
        revenue = _ttm_value(payload, "Revenues", as_of=as_of) or _ttm_value(payload, "SalesRevenueNet", as_of=as_of)

    operating_income, _ = _latest_filed_value(payload, "OperatingIncomeLoss", as_of=as_of)
    if operating_income is None:
        operating_income = _ttm_value(payload, "OperatingIncomeLoss", as_of=as_of)

    cash, _ = _latest_filed_value(payload, "CashAndCashEquivalentsAtCarryingValue", as_of=as_of)
    debt, _ = _latest_filed_value(payload, "LongTermDebtNoncurrent", as_of=as_of)
    operating_cash_flow, _ = _latest_filed_value(payload, "NetCashProvidedByUsedInOperatingActivities", as_of=as_of)
    if operating_cash_flow is None:
        operating_cash_flow = _ttm_value(payload, "NetCashProvidedByUsedInOperatingActivities", as_of=as_of)
    capex, _ = _latest_filed_value(payload, "PaymentsToAcquirePropertyPlantAndEquipment", as_of=as_of)
    if capex is None:
        capex = _ttm_value(payload, "PaymentsToAcquirePropertyPlantAndEquipment", as_of=as_of)
    gross_profit, _ = _latest_filed_value(payload, "GrossProfit", as_of=as_of)
    if gross_profit is None:
        gross_profit = _ttm_value(payload, "GrossProfit", as_of=as_of)
    equity, _ = _latest_filed_value(payload, "StockholdersEquity", as_of=as_of)

    if revenue is None or revenue <= 0:
        return None

    report_date = date.fromisoformat(revenue_filed) if revenue_filed else (as_of or date.today())
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
        revenue_growth_yoy=None,
        gross_margin=round(gross_margin, 4) if gross_margin is not None else None,
        operating_margin=round(operating_margin, 4) if operating_margin is not None else None,
        free_cash_flow=round(free_cash_flow, 2) if free_cash_flow is not None else None,
        cash=round(cash, 2) if cash is not None else None,
        total_debt=round(debt, 2) if debt is not None else None,
        pe_forward=None,
        ev_sales=None,
        fcf_yield=None,
        return_on_equity=round((operating_income / equity), 4) if operating_income is not None and equity else None,
        source="sec_edgar_companyfacts",
    )
