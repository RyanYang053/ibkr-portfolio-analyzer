from __future__ import annotations

import csv
import io
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.domain import Transaction

FLEX_SEND_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
FLEX_GET_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"

ACTIVITY_TYPE_MAP = {
    "deposits": "deposit",
    "deposit": "deposit",
    "contributions": "contribution",
    "contribution": "contribution",
    "withdrawals": "withdrawal",
    "withdrawal": "withdrawal",
    "distributions": "distribution",
    "distribution": "distribution",
    "transfers in": "transfer_in",
    "transfer in": "transfer_in",
    "transfers out": "transfer_out",
    "transfer out": "transfer_out",
    "dividends": "dividend",
    "dividend": "dividend",
    "interest": "interest",
    "fees": "fee",
    "fee": "fee",
    "commissions": "fee",
    "commission": "fee",
    "trades": "buy",
    "trade": "buy",
    "buy": "buy",
    "sell": "sell",
    "corp actions": "corporate_action",
    "corporate actions": "corporate_action",
    "corporate action": "corporate_action",
    "fx": "fx",
    "forex": "fx",
}


@dataclass
class FlexParseResult:
    transactions: list[Transaction] = field(default_factory=list)
    rejected_rows: list[dict[str, str]] = field(default_factory=list)
    imported_sections: list[str] = field(default_factory=list)
    report_period_start: Optional[date] = None
    report_period_end: Optional[date] = None
    query_id: Optional[str] = None
    generated_at: Optional[datetime] = None
    account_id: Optional[str] = None

    @property
    def rejected_row_count(self) -> int:
        return len(self.rejected_rows)


def flex_activity_query_configured() -> bool:
    return bool(settings.ibkr_flex_token and settings.ibkr_flex_activity_query_id)


def flex_query_configured() -> bool:
    return flex_activity_query_configured() or bool(settings.ibkr_flex_token and settings.ibkr_flex_query_id)


def _normalize_key(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _map_flex_action(row: dict[str, str]) -> str | None:
    activity = _normalize_key(row.get("ActivityType") or row.get("TransactionType") or row.get("Type") or "")
    description = _normalize_key(row.get("Description") or row.get("ActivityDescription") or "")

    if activity in ACTIVITY_TYPE_MAP:
        return ACTIVITY_TYPE_MAP[activity]

    for token, action in ACTIVITY_TYPE_MAP.items():
        if token and token in activity:
            return action

    description_rules = [
        ("electronic fund transfer deposit", "deposit"),
        ("fund transfer in", "transfer_in"),
        ("fund transfer out", "transfer_out"),
        ("wire deposit", "deposit"),
        ("wire withdrawal", "withdrawal"),
        ("withdrawal", "withdrawal"),
        ("deposit", "deposit"),
        ("dividend", "dividend"),
        ("interest", "interest"),
        ("commission", "fee"),
        ("fee", "fee"),
        ("stock split", "corporate_action"),
        ("spinoff", "corporate_action"),
        ("merger", "corporate_action"),
    ]
    for phrase, action in description_rules:
        if phrase in description:
            return action

    return None


def _parse_float(value: str | None, default: float = 0.0) -> float:
    if value in (None, "", "N/A"):
        return default
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return default


def _parse_flex_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _parse_flex_xml(account_id: str, payload: str, query_id: Optional[str] = None) -> FlexParseResult:
    root = ET.fromstring(payload)
    statement = root.find(".//FlexStatement") or root.find("FlexStatement")
    report_start = _parse_flex_date(statement.get("fromDate") if statement is not None else None)
    report_end = _parse_flex_date(statement.get("toDate") if statement is not None else None)
    generated_at = None
    when_generated = statement.get("whenGenerated") if statement is not None else None
    if when_generated:
        try:
            generated_at = datetime.strptime(when_generated[:14], "%Y%m%d;%H%M%S")
        except ValueError:
            generated_at = None

    result = FlexParseResult(
        imported_sections=["flex_xml"],
        report_period_start=report_start,
        report_period_end=report_end,
        query_id=query_id,
        generated_at=generated_at,
        account_id=(statement.get("accountId") if statement is not None else None) or account_id,
    )

    for row in root.findall(".//CashTransaction") + root.findall(".//Trade") + root.findall(".//CorporateAction"):
        mapped = {
            "AccountId": row.get("accountId") or account_id,
            "Date": row.get("date") or row.get("tradeDate") or row.get("reportDate"),
            "Description": row.get("description"),
            "ActivityDescription": row.get("description"),
            "ActivityType": row.get("type") or row.get("activityType"),
            "Symbol": row.get("symbol") or row.get("underlyingSymbol") or "CASH",
            "Amount": row.get("amount") or row.get("netCash") or row.get("proceeds"),
            "Quantity": row.get("quantity") or row.get("tradeQuantity") or "1",
            "Price": row.get("price") or row.get("tradePrice") or "0",
            "Commission": row.get("commission") or row.get("comm/fee") or "0",
            "CurrencyPrimary": row.get("currency") or row.get("currencyPrimary") or "USD",
            "TransactionID": row.get("transactionID") or row.get("tradeID"),
        }
        action = _map_flex_action(mapped)
        if action is None:
            result.rejected_rows.append({"reason": "unknown_activity_type", "row": mapped})
            continue
        date_text = mapped.get("Date") or ""
        try:
            trade_day = datetime.strptime(str(date_text)[:10], "%Y-%m-%d").date()
        except ValueError:
            parsed = _parse_flex_date(str(date_text))
            if parsed is None:
                result.rejected_rows.append({"reason": "invalid_date", "row": mapped})
                continue
            trade_day = parsed
        quantity = _parse_float(str(mapped.get("Quantity")), default=1.0)
        price = _parse_float(str(mapped.get("Price")))
        amount = _parse_float(str(mapped.get("Amount")))
        commission = _parse_float(str(mapped.get("Commission")))
        currency = str(mapped.get("CurrencyPrimary") or "USD")
        symbol = str(mapped.get("Symbol") or "CASH").upper()
        if action in {"buy", "sell"}:
            action = "buy" if quantity > 0 else "sell"
        result.transactions.append(
            Transaction(
                account_id=account_id,
                symbol=symbol,
                trade_date=trade_day,
                action=action,  # type: ignore[arg-type]
                quantity=abs(quantity),
                price=abs(price) if price else abs(amount / quantity) if quantity else abs(amount),
                commission=abs(commission),
                currency=currency,
                amount=abs(amount) if amount else None,
                source="ibkr_flex_query",
                transaction_id=mapped.get("TransactionID"),
                description=mapped.get("Description"),
            )
        )

    if result.transactions and (result.report_period_start is None or result.report_period_end is None):
        dates = [txn.trade_date for txn in result.transactions]
        result.report_period_start = min(dates)
        result.report_period_end = max(dates)
    return result


def _parse_flex_csv(account_id: str, payload: str) -> FlexParseResult:
    if not payload.strip():
        return FlexParseResult(imported_sections=["flex_csv"])
    reader = csv.DictReader(io.StringIO(payload))
    result = FlexParseResult(imported_sections=["flex_csv"])
    for row in reader:
        account = row.get("AccountId") or row.get("ClientAccountID") or account_id
        if account and account != account_id:
            continue
        date_text = row.get("Date") or row.get("TradeDate") or row.get("ReportDate") or ""
        if not date_text:
            result.rejected_rows.append({"reason": "missing_date", "row": row})
            continue
        try:
            trade_day = datetime.strptime(date_text[:10], "%Y-%m-%d").date()
        except ValueError:
            result.rejected_rows.append({"reason": "invalid_date", "row": row})
            continue

        action = _map_flex_action(row)
        if action is None:
            result.rejected_rows.append({"reason": "unknown_activity_type", "row": row})
            continue

        symbol = (row.get("Symbol") or row.get("UnderlyingSymbol") or "CASH").upper()
        amount = _parse_float(row.get("Amount") or row.get("NetCash") or row.get("Proceeds"))
        quantity = _parse_float(row.get("Quantity") or row.get("TradeQuantity"), default=1.0)
        price = _parse_float(row.get("Price") or row.get("TradePrice"))
        commission = _parse_float(row.get("Commission") or row.get("Comm/Fee"))
        currency = row.get("CurrencyPrimary") or row.get("Currency") or "USD"
        description = row.get("Description") or row.get("ActivityDescription") or None

        if action in {"buy", "sell"}:
            action = "buy" if quantity > 0 else "sell"

        result.transactions.append(
            Transaction(
                account_id=account_id,
                symbol=symbol,
                trade_date=trade_day,
                action=action,  # type: ignore[arg-type]
                quantity=abs(quantity),
                price=abs(price) if price else abs(amount / quantity) if quantity else abs(amount),
                commission=abs(commission),
                currency=currency,
                amount=abs(amount) if amount else None,
                source="ibkr_flex_query",
                transaction_id=row.get("TransactionID") or row.get("TradeID") or None,
                description=description,
            )
        )
    if result.transactions:
        dates = [txn.trade_date for txn in result.transactions]
        result.report_period_start = min(dates)
        result.report_period_end = max(dates)
    return result
    with httpx.Client(timeout=timeout_seconds) as client:
        send = client.get(FLEX_SEND_URL, params={"t": token, "q": query_id, "v": "3"})
        send.raise_for_status()
        root = ET.fromstring(send.text)
        status = root.findtext("Status")
        if status != "Success":
            message = root.findtext("ErrorMessage") or send.text
            raise RuntimeError(f"IBKR Flex request failed: {message}")
        reference = root.findtext("ReferenceCode")
        if not reference:
            raise RuntimeError("IBKR Flex request did not return a reference code")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            response = client.get(FLEX_GET_URL, params={"t": token, "q": reference, "v": "3"})
            response.raise_for_status()
            if response.text.startswith("<?xml"):
                poll_root = ET.fromstring(response.text)
                if poll_root.findtext("Status") == "Success":
                    raise RuntimeError("IBKR Flex returned XML without statement payload")
                time.sleep(1.0)
                continue
            return response.text
        raise RuntimeError("IBKR Flex statement polling timed out")


def fetch_flex_cash_ledger(account_id: str, query_id: Optional[str] = None) -> FlexParseResult:
    token = settings.ibkr_flex_token
    query = query_id or settings.ibkr_flex_activity_query_id or settings.ibkr_flex_query_id
    if not token or not query:
        raise RuntimeError(
            "IBKR Flex Query is not configured. Set IBKR_FLEX_TOKEN and IBKR_FLEX_ACTIVITY_QUERY_ID."
        )
    payload = _request_flex_statement(token, query)
    if payload.strip().startswith("<?xml"):
        return _parse_flex_xml(account_id, payload, query_id=query)
    result = _parse_flex_csv(account_id, payload)
    result.query_id = query
    return result


def fetch_flex_transactions(account_id: str, query_id: Optional[str] = None) -> list[Transaction]:
    return fetch_flex_cash_ledger(account_id, query_id=query_id).transactions


def mock_flex_transactions(account_id: str) -> list[Transaction]:
    today = date.today()
    return [
        Transaction(
            account_id=account_id,
            symbol="CASH",
            trade_date=today.fromordinal(today.toordinal() - 200),
            action="deposit",
            quantity=1,
            price=50000,
            commission=0,
            currency="USD",
            amount=50000,
            source="mock_flex_query",
            transaction_id=f"{account_id}:flex:deposit:1",
        ),
        Transaction(
            account_id=account_id,
            symbol="MSFT",
            trade_date=today.fromordinal(today.toordinal() - 90),
            action="dividend",
            quantity=45,
            price=0.83,
            commission=0,
            currency="USD",
            amount=37.35,
            source="mock_flex_query",
            transaction_id=f"{account_id}:flex:dividend:MSFT",
        ),
        Transaction(
            account_id=account_id,
            symbol="SPY",
            trade_date=today.fromordinal(today.toordinal() - 30),
            action="corporate_action",
            quantity=52,
            price=0,
            commission=0,
            currency="USD",
            amount=0,
            source="mock_flex_query",
            transaction_id=f"{account_id}:flex:corp:SPY",
            description="Stock Split 2 for 1",
        ),
    ]
