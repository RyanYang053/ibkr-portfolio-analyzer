from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.schemas.domain import FundamentalSnapshot

SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

QUARTERLY_MIN_DAYS = 70
QUARTERLY_MAX_DAYS = 110
ANNUAL_MIN_DAYS = 330
ANNUAL_MAX_DAYS = 390
YTD_H1_MIN_DAYS = 170
YTD_H1_MAX_DAYS = 220
YTD_9M_MIN_DAYS = 260
YTD_9M_MAX_DAYS = 300

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

_TTL_TICKER_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_TTL_FACTS_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_LAST_REQUEST_AT: float | None = None


def _sec_headers() -> dict[str, str]:
    from app.core.config import settings

    user_agent = settings.sec_edgar_user_agent or "PortfolioIntelligence/1.0 contact@example.com"
    return {"User-Agent": user_agent, "Accept": "application/json"}


def _cache_expiry() -> datetime:
    from app.core.config import settings

    return datetime.now(timezone.utc) + timedelta(hours=settings.sec_edgar_cache_hours)


def _throttle() -> None:
    global _LAST_REQUEST_AT
    from app.core.config import settings

    min_interval = 1.0 / max(settings.sec_edgar_requests_per_second, 0.1)
    now = time.monotonic()
    if _LAST_REQUEST_AT is not None:
        elapsed = now - _LAST_REQUEST_AT
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    _LAST_REQUEST_AT = time.monotonic()


def _request_json(url: str, *, attempts: int = 4) -> dict[str, Any] | None:
    delay = 0.5
    for attempt in range(attempts):
        _throttle()
        try:
            response = httpx.get(url, headers=_sec_headers(), timeout=30.0)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == attempts - 1:
                return None
            time.sleep(delay)
            delay *= 2
    return None


def _normalize_row(concept: str, unit: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept": concept,
        "unit": unit,
        "value": float(Decimal(str(row["val"]))),
        "start": row.get("start"),
        "end": row.get("end"),
        "filed": row.get("filed"),
        "accepted": row.get("accepted"),
        "accn": row.get("accn"),
        "form": row.get("form"),
        "fy": row.get("fy"),
        "fp": row.get("fp"),
        "frame": row.get("frame"),
    }


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
            rows.append(_normalize_row(concept, unit, row))
    return rows


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dedupe_restatements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("concept"),
            row.get("unit"),
            row.get("start"),
            row.get("end"),
            row.get("form"),
            row.get("fp"),
            row.get("frame"),
        )
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
    eligible: list[dict[str, Any]] = []
    for row in rows:
        filed = _parse_iso_date(row.get("filed"))
        end = _parse_iso_date(row.get("end"))
        if as_of is not None:
            if filed is None or filed > as_of:
                continue
            if end is not None and end > as_of:
                continue
        eligible.append(row)
    return _dedupe_restatements(eligible)


def _duration_days(row: dict[str, Any]) -> int | None:
    start = _parse_iso_date(row.get("start"))
    end = _parse_iso_date(row.get("end"))
    if start is None or end is None:
        return None
    return (end - start).days


def _duration_kind(row: dict[str, Any]) -> str:
    days = _duration_days(row)
    if days is not None:
        if QUARTERLY_MIN_DAYS <= days <= QUARTERLY_MAX_DAYS:
            return "quarterly"
        if ANNUAL_MIN_DAYS <= days <= ANNUAL_MAX_DAYS:
            return "annual"
        if YTD_H1_MIN_DAYS <= days <= YTD_H1_MAX_DAYS:
            return "ytd_h1"
        if YTD_9M_MIN_DAYS <= days <= YTD_9M_MAX_DAYS:
            return "ytd_9m"
        return "other"
    fp = str(row.get("fp", "")).upper()
    if fp == "FY":
        return "annual"
    if fp in {"Q1", "Q2", "Q3", "Q4"}:
        return "quarterly"
    return "instant"


def _same_unit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    preferred = "USD"
    usd_rows = [row for row in rows if str(row.get("unit", "")).upper() == preferred]
    if usd_rows:
        return usd_rows
    unit = rows[0].get("unit")
    return [row for row in rows if row.get("unit") == unit]


def _latest_instant_value(
    facts: dict[str, Any],
    concept: str,
    *,
    as_of: date | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    rows = _same_unit(_rows_as_of(_point_in_time_values(facts, concept), as_of))
    instant_rows = [row for row in rows if _duration_kind(row) == "instant"]
    if not instant_rows:
        instant_rows = [row for row in rows if row.get("start") is None]
    if not instant_rows:
        return None, None
    latest = max(
        instant_rows,
        key=lambda row: (
            _parse_iso_date(row.get("end")) or date.min,
            _parse_iso_date(row.get("filed")) or date.min,
        ),
    )
    return float(latest["value"]), latest


def _standalone_quarters_for_fy(rows: list[dict[str, Any]], fy: int) -> dict[str, float] | None:
    fy_rows = [row for row in rows if row.get("fy") == fy]
    if not fy_rows:
        return None

    quarters: dict[str, float] = {}
    for row in fy_rows:
        fp = str(row.get("fp", "")).upper()
        kind = _duration_kind(row)
        if fp == "Q1" and kind == "quarterly":
            quarters["Q1"] = float(row["value"])
        elif fp == "Q2" and kind == "quarterly":
            quarters["Q2"] = float(row["value"])
        elif fp == "Q3" and kind == "quarterly":
            quarters["Q3"] = float(row["value"])
        elif fp == "Q4" and kind == "quarterly":
            quarters["Q4"] = float(row["value"])

    q1_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "Q1" and _duration_kind(row) == "quarterly"), None)
    h1_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "Q2" and _duration_kind(row) == "ytd_h1"), None)
    nine_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "Q3" and _duration_kind(row) == "ytd_9m"), None)
    fy_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "FY" and _duration_kind(row) == "annual"), None)

    if q1_row and h1_row and "Q2" not in quarters:
        quarters["Q2"] = float(h1_row["value"]) - float(q1_row["value"])
    if h1_row and nine_row and "Q3" not in quarters:
        quarters["Q3"] = float(nine_row["value"]) - float(h1_row["value"])
    if fy_row and nine_row and "Q4" not in quarters:
        quarters["Q4"] = float(fy_row["value"]) - float(nine_row["value"])

    if len(quarters) != 4:
        return None
    if any(value < 0 for value in quarters.values()):
        return None
    return quarters


def _ttm_duration_value(
    facts: dict[str, Any],
    concept: str,
    *,
    as_of: date | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    rows = _same_unit(_rows_as_of(_point_in_time_values(facts, concept), as_of))
    if not rows:
        return None, None

    annual_rows = [row for row in rows if _duration_kind(row) == "annual"]
    if annual_rows:
        latest_annual = max(
            annual_rows,
            key=lambda row: (
                _parse_iso_date(row.get("end")) or date.min,
                _parse_iso_date(row.get("filed")) or date.min,
            ),
        )
        return float(latest_annual["value"]), latest_annual

    fiscal_years = sorted({int(row["fy"]) for row in rows if row.get("fy") is not None}, reverse=True)
    for fy in fiscal_years:
        quarters = _standalone_quarters_for_fy(rows, fy)
        if quarters is None:
            continue
        source_rows = [row for row in rows if row.get("fy") == fy]
        source = max(
            source_rows,
            key=lambda row: (
                _parse_iso_date(row.get("end")) or date.min,
                _parse_iso_date(row.get("filed")) or date.min,
            ),
        )
        return sum(quarters.values()), source

    quarterly_rows = [
        row
        for row in rows
        if str(row.get("fp", "")).upper() in {"Q1", "Q2", "Q3", "Q4"} and _duration_kind(row) == "quarterly"
    ]
    if len(quarterly_rows) >= 4:
        latest_four = sorted(
            quarterly_rows,
            key=lambda row: (_parse_iso_date(row.get("end")) or date.min, str(row.get("fp", ""))),
            reverse=True,
        )[:4]
        ends = {_parse_iso_date(row.get("end")) for row in latest_four}
        if None not in ends and len(ends) == 4:
            return sum(float(row["value"]) for row in latest_four), latest_four[0]

    return None, None


def _lookup_cik(symbol: str) -> str | None:
    from app.db.sec_edgar_repo import cache_ticker_map, get_cached_ticker_map
    cached = get_cached_ticker_map()
    if cached is None:
        payload = _request_json(SEC_TICKER_MAP_URL)
        if payload is None:
            return None
        cache_ticker_map(payload)
        cached = payload
    target = symbol.upper().strip()
    for item in cached.values():
        if str(item.get("ticker", "")).upper() == target:
            cik = str(item.get("cik_str", ""))
            return cik.zfill(10)
    return None


def fetch_company_facts_payload(symbol: str) -> dict[str, Any] | None:
    from app.db.sec_edgar_repo import get_cached_company_facts, persist_company_facts

    symbol_key = symbol.upper().strip()
    cached = get_cached_company_facts(symbol_key)
    if cached is not None:
        return cached

    memory_cached = _TTL_FACTS_CACHE.get(symbol_key)
    if memory_cached and memory_cached[0] > datetime.now(timezone.utc):
        return memory_cached[1]

    cik = _lookup_cik(symbol_key)
    if not cik:
        return None
    payload = _request_json(SEC_COMPANY_FACTS_URL.format(cik=cik))
    if payload is None:
        return None
    observations: list[dict[str, Any]] = []
    for concept in (
        "Revenues",
        "SalesRevenueNet",
        "OperatingIncomeLoss",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "GrossProfit",
        "CashAndCashEquivalentsAtCarryingValue",
        "LongTermDebtNoncurrent",
        "StockholdersEquity",
    ):
        observations.extend(_point_in_time_values(payload, concept))
    persist_company_facts(symbol_key, cik, payload, observations)
    _TTL_FACTS_CACHE[symbol_key] = (_cache_expiry(), payload)
    return payload


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

    revenue, revenue_source = _ttm_duration_value(payload, "Revenues", as_of=as_of)
    if revenue is None:
        revenue, revenue_source = _ttm_duration_value(payload, "SalesRevenueNet", as_of=as_of)

    operating_income, _ = _ttm_duration_value(payload, "OperatingIncomeLoss", as_of=as_of)
    operating_cash_flow, _ = _ttm_duration_value(payload, "NetCashProvidedByUsedInOperatingActivities", as_of=as_of)
    capex, _ = _ttm_duration_value(payload, "PaymentsToAcquirePropertyPlantAndEquipment", as_of=as_of)
    gross_profit, _ = _ttm_duration_value(payload, "GrossProfit", as_of=as_of)

    cash, _ = _latest_instant_value(payload, "CashAndCashEquivalentsAtCarryingValue", as_of=as_of)
    debt, _ = _latest_instant_value(payload, "LongTermDebtNoncurrent", as_of=as_of)
    equity, _ = _latest_instant_value(payload, "StockholdersEquity", as_of=as_of)

    if revenue is None or revenue <= 0:
        return None

    filed = revenue_source.get("filed") if revenue_source else None
    report_date = _parse_iso_date(filed) or as_of or date.today()
    gross_margin = (gross_profit / revenue) if gross_profit is not None and revenue > 0 else None
    operating_margin = (operating_income / revenue) if operating_income is not None else None
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - abs(capex)

    return FundamentalSnapshot(
        symbol=symbol.upper(),
        period="TTM",
        report_date=report_date,
        revenue_growth_yoy=None,
        gross_margin=round(gross_margin, 4) if gross_margin is not None else None,
        operating_margin=round(operating_margin, 4) if operating_margin is not None else None,
        free_cash_flow=round(free_cash_flow, 2) if free_cash_flow is not None else None,
        operating_cash_flow=round(operating_cash_flow, 2) if operating_cash_flow is not None else None,
        cash=round(cash, 2) if cash is not None else None,
        total_debt=round(debt, 2) if debt is not None else None,
        pe_forward=None,
        ev_sales=None,
        fcf_yield=None,
        return_on_equity=round((operating_income / equity), 4) if operating_income is not None and equity else None,
        source="sec_edgar_companyfacts",
    )
