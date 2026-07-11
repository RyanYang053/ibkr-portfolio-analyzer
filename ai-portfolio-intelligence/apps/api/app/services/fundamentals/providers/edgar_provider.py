from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.schemas.domain import FundamentalFieldLineage, FundamentalSnapshot
from app.services.fundamentals.concept_resolver import ALL_REGISTRY_CONCEPTS, resolve_nonduplicative_debt
from app.services.fundamentals.metric_lineage import lineage_from_rows, row_to_field_lineage

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
RECONCILIATION_TOLERANCE = 0.02

COMPANY_TYPE_CONCEPTS: dict[str, list[str]] = {
    "general_operating": list(ALL_REGISTRY_CONCEPTS),
    "bank": [
        "InterestIncomeExpenseNet",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "CommonStockholdersEquity",
        "StockholdersEquity",
        "Assets",
    ],
    "reit": [
        "NetIncomeLoss",
        "FundsFromOperations",
        "AdjustedFundsFromOperations",
        "RealEstateInvestmentPropertyNet",
        "PaymentsOfDividends",
        "OccupancyRate",
    ],
    "utility": [
        "RegulatedAndUnregulatedOperatingRevenue",
        "OperatingIncomeLoss",
        "PropertyPlantAndEquipmentNet",
        "RegulatoryAssets",
    ],
}

_TTL_TICKER_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_TTL_FACTS_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}


def _sec_headers() -> dict[str, str]:
    from app.core.config import settings

    user_agent = settings.sec_edgar_user_agent or "PortfolioIntelligence/1.0 contact@example.com"
    return {"User-Agent": user_agent, "Accept": "application/json"}


def _throttle() -> None:
    from app.core.sec_rate_limit import throttle_sec_edgar_request

    throttle_sec_edgar_request()


def _cache_expiry() -> datetime:
    from app.core.config import settings

    return datetime.now(timezone.utc) + timedelta(hours=settings.sec_edgar_cache_hours)


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


def _period_end_then_filed(row: dict[str, Any]) -> tuple[date, date]:
    end = _parse_iso_date(row.get("end")) or date.min
    filed = _parse_iso_date(row.get("filed")) or date.min
    return end, filed


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
    from collections import Counter

    unit_counts = Counter(str(row.get("unit", "")).strip() for row in rows if row.get("unit"))
    if not unit_counts:
        return rows
    dominant_unit = unit_counts.most_common(1)[0][0]
    matched = [row for row in rows if str(row.get("unit", "")).strip() == dominant_unit]
    return matched or rows


def arithmetic_reconciliation_within_tolerance(
    derived: float,
    reported: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE,
) -> bool:
    if reported == 0:
        return abs(derived) <= tolerance
    return abs(derived - reported) / abs(reported) <= tolerance


def _standalone_quarters_for_fy(rows: list[dict[str, Any]], fy: int) -> dict[str, float] | None:
    fy_rows = [row for row in rows if row.get("fy") == fy]
    if not fy_rows:
        return None

    quarters: dict[str, float] = {}
    for row in fy_rows:
        fp = str(row.get("fp", "")).upper()
        kind = _duration_kind(row)
        if fp in {"Q1", "Q2", "Q3", "Q4"} and kind == "quarterly":
            quarters[fp] = float(row["value"])

    q1_row = next(
        (row for row in fy_rows if str(row.get("fp", "")).upper() == "Q1" and _duration_kind(row) == "quarterly"),
        None,
    )
    h1_row = next(
        (row for row in fy_rows if str(row.get("fp", "")).upper() == "Q2" and _duration_kind(row) == "ytd_h1"),
        None,
    )
    nine_row = next(
        (row for row in fy_rows if str(row.get("fp", "")).upper() == "Q3" and _duration_kind(row) == "ytd_9m"),
        None,
    )
    fy_row = next(
        (row for row in fy_rows if str(row.get("fp", "")).upper() == "FY" and _duration_kind(row) == "annual"),
        None,
    )

    if q1_row and h1_row and "Q2" not in quarters:
        derived_q2 = float(h1_row["value"]) - float(q1_row["value"])
        if not arithmetic_reconciliation_within_tolerance(
            float(q1_row["value"]) + derived_q2,
            float(h1_row["value"]),
        ):
            return None
        quarters["Q2"] = derived_q2
    if h1_row and nine_row and "Q3" not in quarters:
        derived_q3 = float(nine_row["value"]) - float(h1_row["value"])
        if not arithmetic_reconciliation_within_tolerance(
            float(h1_row["value"]) + derived_q3,
            float(nine_row["value"]),
        ):
            return None
        quarters["Q3"] = derived_q3
    if fy_row and nine_row and "Q4" not in quarters:
        derived_q4 = float(fy_row["value"]) - float(nine_row["value"])
        if not arithmetic_reconciliation_within_tolerance(
            float(nine_row["value"]) + derived_q4,
            float(fy_row["value"]),
        ):
            return None
        quarters["Q4"] = derived_q4

    if len(quarters) != 4:
        return None
    if fy_row is not None:
        quarter_sum = sum(quarters.values())
        if not arithmetic_reconciliation_within_tolerance(quarter_sum, float(fy_row["value"])):
            return None
    return quarters


def _derived_quarter_row(
    *,
    template: dict[str, Any],
    value: float,
    fy: int,
    fp: str,
    end_row: dict[str, Any] | None,
    start_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "concept": template.get("concept"),
        "unit": template.get("unit"),
        "value": value,
        "start": start_row.get("start") if start_row else end_row.get("start") if end_row else None,
        "end": end_row.get("end") if end_row else None,
        "filed": end_row.get("filed") if end_row else None,
        "accn": end_row.get("accn") if end_row else None,
        "fy": fy,
        "fp": fp,
        "derivation": "derived_quarter",
        "derivation_inputs": {
            "start_row_end": start_row.get("end") if start_row else None,
            "end_row_end": end_row.get("end") if end_row else None,
        },
    }


def derive_standalone_quarters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    standalone: list[dict[str, Any]] = []
    fiscal_years = sorted({int(row["fy"]) for row in rows if row.get("fy") is not None}, reverse=True)
    for fy in fiscal_years:
        quarters = _standalone_quarters_for_fy(rows, fy)
        if quarters is None:
            fy_rows = [row for row in rows if row.get("fy") == fy]
            for row in fy_rows:
                fp = str(row.get("fp", "")).upper()
                if fp in {"Q1", "Q2", "Q3", "Q4"} and _duration_kind(row) == "quarterly":
                    standalone.append({**row})
            continue
        for fp, value in quarters.items():
            source = next(
                (
                    row
                    for row in rows
                    if row.get("fy") == fy and str(row.get("fp", "")).upper() == fp and _duration_kind(row) == "quarterly"
                ),
                None,
            )
            if source is not None:
                standalone.append({**source, "value": value})
                continue
            fy_rows = [row for row in rows if row.get("fy") == fy]
            q1_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "Q1"), None)
            h1_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "Q2" and _duration_kind(row) == "ytd_h1"), None)
            nine_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "Q3" and _duration_kind(row) == "ytd_9m"), None)
            fy_row = next((row for row in fy_rows if str(row.get("fp", "")).upper() == "FY"), None)
            if fp == "Q2" and h1_row is not None:
                standalone.append(_derived_quarter_row(template=rows[0], value=value, fy=fy, fp=fp, end_row=h1_row, start_row=q1_row))
            elif fp == "Q3" and nine_row is not None:
                standalone.append(_derived_quarter_row(template=rows[0], value=value, fy=fy, fp=fp, end_row=nine_row, start_row=h1_row))
            elif fp == "Q4" and fy_row is not None:
                standalone.append(_derived_quarter_row(template=rows[0], value=value, fy=fy, fp=fp, end_row=fy_row, start_row=nine_row))
            else:
                standalone.append(
                    {
                        "concept": rows[0].get("concept"),
                        "unit": rows[0].get("unit"),
                        "value": value,
                        "fy": fy,
                        "fp": fp,
                        "derivation": "derived_quarter",
                    }
                )
    standalone.sort(key=lambda row: _parse_iso_date(row.get("end")) or date.min)
    return standalone


def _quarters_adjacent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_end = _parse_iso_date(left.get("end"))
    right_end = _parse_iso_date(right.get("end"))
    if left_end is None or right_end is None:
        return False
    gap = (right_end - left_end).days
    return 80 <= gap <= 120


def consecutive_four_quarter_sequences(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not rows:
        return []
    unit = rows[0].get("unit")
    candidates = [
        row
        for row in rows
        if row.get("unit") == unit and _parse_iso_date(row.get("end")) is not None
    ]
    candidates.sort(key=lambda row: _parse_iso_date(row.get("end")) or date.min)

    sequences: list[list[dict[str, Any]]] = []
    for index in range(len(candidates) - 3):
        window = candidates[index : index + 4]
        ends = {_parse_iso_date(row.get("end")) for row in window}
        if None in ends or len(ends) != 4:
            continue
        if any(not _quarters_adjacent(window[i], window[i + 1]) for i in range(3)):
            continue
        sequences.append(window)
    return sequences


def _latest_ttm_duration_value(
    facts: dict[str, Any],
    concept: str,
    *,
    as_of: date | None = None,
) -> tuple[float | None, list[dict[str, Any]]]:
    rows = _same_unit(_rows_as_of(_point_in_time_values(facts, concept), as_of))
    if not rows:
        return None, []

    standalone = derive_standalone_quarters(rows)
    sequences = consecutive_four_quarter_sequences(standalone)
    if sequences:
        latest = max(sequences, key=lambda seq: _parse_iso_date(seq[-1].get("end")) or date.min)
        return sum(float(row["value"]) for row in latest), latest

    annual_rows = [row for row in rows if _duration_kind(row) == "annual"]
    if annual_rows:
        latest_annual = max(annual_rows, key=_period_end_then_filed)
        return float(latest_annual["value"]), [latest_annual]

    return None, []


def _ttm_duration_value(
    facts: dict[str, Any],
    concept: str,
    *,
    as_of: date | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    value, sources = _latest_ttm_duration_value(facts, concept, as_of=as_of)
    if value is None:
        return None, None
    return value, sources[-1] if sources else None


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
    latest = max(instant_rows, key=_period_end_then_filed)
    return float(latest["value"]), latest


def _instant_at_or_before(
    facts: dict[str, Any],
    concept: str,
    as_of: date,
    *,
    filed_as_of: date | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    rows = _same_unit(_point_in_time_values(facts, concept))
    instant_rows = [row for row in rows if _duration_kind(row) == "instant" or row.get("start") is None]
    filed_cutoff = filed_as_of or as_of
    eligible: list[dict[str, Any]] = []
    for row in instant_rows:
        end = _parse_iso_date(row.get("end"))
        filed = _parse_iso_date(row.get("filed"))
        if end is None or end > as_of:
            continue
        if filed is not None and filed > filed_cutoff:
            continue
        eligible.append(row)
    if not eligible:
        return None, None
    eligible = _dedupe_restatements(eligible)
    latest = max(eligible, key=_period_end_then_filed)
    return float(latest["value"]), latest


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
    for concept in ALL_REGISTRY_CONCEPTS:
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


def _build_field_lineage(
    metric: str,
    value: float | None,
    sources: list[dict[str, Any]],
    *,
    derivation: str = "rolling_ttm",
) -> FundamentalFieldLineage | None:
    if value is None or not sources:
        return None
    if len(sources) == 1:
        return row_to_field_lineage(metric, sources[0], derivation=derivation, value=value)
    return lineage_from_rows(metric, sources, derivation=derivation, value=value)


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

    field_lineage: dict[str, FundamentalFieldLineage] = {}
    exclusions: list[str] = []

    revenue, revenue_sources = _latest_ttm_duration_value(payload, "Revenues", as_of=as_of)
    if revenue is None:
        revenue, revenue_sources = _latest_ttm_duration_value(payload, "SalesRevenueNet", as_of=as_of)

    operating_income, operating_sources = _latest_ttm_duration_value(payload, "OperatingIncomeLoss", as_of=as_of)
    operating_cash_flow, ocf_sources = _latest_ttm_duration_value(
        payload, "NetCashProvidedByUsedInOperatingActivities", as_of=as_of
    )
    capex, capex_sources = _latest_ttm_duration_value(
        payload, "PaymentsToAcquirePropertyPlantAndEquipment", as_of=as_of
    )
    gross_profit, gross_sources = _latest_ttm_duration_value(payload, "GrossProfit", as_of=as_of)

    cash, cash_row = _latest_instant_value(payload, "CashAndCashEquivalentsAtCarryingValue", as_of=as_of)
    debt, debt_lineage, debt_exclusions = resolve_nonduplicative_debt(_latest_instant_value, payload, as_of=as_of)
    exclusions.extend(debt_exclusions)
    equity, equity_row = _latest_instant_value(payload, "CommonStockholdersEquity", as_of=as_of)
    if equity is None:
        equity, equity_row = _latest_instant_value(payload, "StockholdersEquity", as_of=as_of)

    net_income_common, net_income_sources = _latest_ttm_duration_value(
        payload,
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        as_of=as_of,
    )
    if net_income_common is None:
        net_income_common, net_income_sources = _latest_ttm_duration_value(payload, "NetIncomeLoss", as_of=as_of)

    ttm_start_date: date | None = None
    if revenue_sources:
        ttm_start_date = _parse_iso_date(revenue_sources[0].get("start"))
    begin_equity, begin_equity_row = (
        _instant_at_or_before(payload, "CommonStockholdersEquity", ttm_start_date, filed_as_of=as_of)
        if ttm_start_date is not None
        else (None, None)
    )
    end_equity = equity
    average_equity = (
        (begin_equity + end_equity) / 2.0
        if begin_equity is not None and end_equity is not None
        else None
    )
    roe = (
        net_income_common / average_equity
        if net_income_common is not None and average_equity not in {None, 0}
        else None
    )

    if revenue is None or revenue <= 0:
        return None

    period_ends = [
        _parse_iso_date(row.get("end"))
        for sources in (revenue_sources, operating_sources, gross_sources, net_income_sources)
        for row in sources
        if row.get("end")
    ]
    report_date = max((item for item in period_ends if item is not None), default=as_of or date.today())

    if revenue is not None and revenue_sources:
        field_lineage["revenue"] = _build_field_lineage("revenue", revenue, revenue_sources)
    if operating_income is not None and operating_sources:
        field_lineage["operating_income"] = _build_field_lineage("operating_income", operating_income, operating_sources)
    if gross_profit is not None and gross_sources:
        field_lineage["gross_profit"] = _build_field_lineage("gross_profit", gross_profit, gross_sources)
    if operating_cash_flow is not None and ocf_sources:
        field_lineage["operating_cash_flow"] = _build_field_lineage(
            "operating_cash_flow", operating_cash_flow, ocf_sources
        )
    if cash is not None and cash_row:
        field_lineage["cash"] = row_to_field_lineage("cash", cash_row, value=cash)
    if debt is not None and debt_lineage:
        field_lineage["total_debt"] = debt_lineage
    if average_equity is not None and (begin_equity_row or equity_row):
        equity_sources = [row for row in (begin_equity_row, equity_row) if row]
        field_lineage["average_common_equity"] = lineage_from_rows(
            "average_common_equity",
            equity_sources,
            value=average_equity,
            derivation="average_of_begin_and_end_instant_equity",
        )
    elif equity is not None and equity_row:
        field_lineage["average_common_equity"] = row_to_field_lineage(
            "average_common_equity", equity_row, value=equity, derivation="instant_end_only"
        )
    if roe is not None and net_income_sources:
        field_lineage["return_on_equity"] = _build_field_lineage(
            "return_on_equity",
            roe,
            net_income_sources,
            derivation="net_income_over_average_equity",
        )

    gross_margin = (gross_profit / revenue) if gross_profit is not None and revenue > 0 else None
    operating_margin = (operating_income / revenue) if operating_income is not None else None
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - abs(capex)

    return FundamentalSnapshot(
        symbol=symbol.upper(),
        period="TTM",
        report_date=report_date,
        revenue=round(revenue, 2),
        net_income_common=round(net_income_common, 2) if net_income_common is not None else None,
        average_common_equity=round(average_equity, 2) if average_equity is not None else None,
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
        return_on_equity=round(roe, 4) if roe is not None else None,
        source="sec_edgar_companyfacts",
        field_lineage=field_lineage,
        exclusions=exclusions,
    )
