from __future__ import annotations

import csv
import io
import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import httpx

from app.core.config import is_desktop_local, settings
from app.schemas.domain import Transaction
from app.services.secrets.secret_store import get_secret_store

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


def configured_flex_token() -> str | None:
    if is_desktop_local():
        return get_secret_store().get("ibkr_flex_token")
    return settings.ibkr_flex_token


def flex_activity_query_configured() -> bool:
    return bool(configured_flex_token() and settings.ibkr_flex_activity_query_id)


def flex_query_configured() -> bool:
    return flex_activity_query_configured() or bool(
        configured_flex_token() and settings.ibkr_flex_query_id
    )


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


def _parse_strict_float(value: str | None) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _parse_when_generated(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    for fmt, length in (("%Y%m%d;%H%M%S", 15), ("%Y-%m-%d %H:%M:%S", 19)):
        try:
            return datetime.strptime(text[:length], fmt)
        except ValueError:
            continue
    return None


def _resolve_execution_action(row: dict[str, str], mapped_action: str) -> tuple[str | None, Optional[str]]:
    side = (row.get("BuySell") or row.get("buySell") or row.get("Side") or "").strip().upper()
    if side in {"B", "BUY"}:
        return "buy", None
    if side in {"S", "SELL"}:
        return "sell", None
    if mapped_action not in {"buy", "sell"}:
        return mapped_action, None
    quantity = _parse_strict_float(str(row.get("Quantity") or row.get("TradeQuantity") or ""))
    if quantity is None:
        return None, "invalid_numeric_field"
    return ("buy" if quantity > 0 else "sell"), None


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


def _append_flex_transaction(
    result: FlexParseResult,
    account_id: str,
    row: dict[str, str],
    trade_day: date,
    action: str,
) -> None:
    quantity = _parse_strict_float(str(row.get("Quantity") or row.get("TradeQuantity") or ""))
    price = _parse_strict_float(str(row.get("Price") or row.get("TradePrice") or ""))
    amount = _parse_strict_float(str(row.get("Amount") or row.get("NetCash") or row.get("Proceeds") or ""))
    commission = _parse_strict_float(str(row.get("Commission") or row.get("Comm/Fee") or ""))
    if action in {"buy", "sell"} and quantity is None:
        result.rejected_rows.append({"reason": "invalid_numeric_field", "row": row})
        return
    quantity_value = abs(quantity) if quantity is not None else 1.0
    price_value = abs(price) if price is not None else 0.0
    amount_value = abs(amount) if amount is not None else 0.0
    commission_value = abs(commission) if commission is not None else 0.0
    if action in {"buy", "sell"} and price_value <= 0 and amount_value <= 0:
        result.rejected_rows.append({"reason": "invalid_numeric_field", "row": row})
        return
    resolved_price = price_value if price_value > 0 else (
        amount_value / quantity_value if quantity_value else amount_value
    )
    result.transactions.append(
        Transaction(
            account_id=account_id,
            symbol=str(row.get("Symbol") or row.get("UnderlyingSymbol") or "CASH").upper(),
            trade_date=trade_day,
            action=action,  # type: ignore[arg-type]
            quantity=quantity_value,
            price=resolved_price,
            commission=commission_value,
            currency=str(row.get("CurrencyPrimary") or row.get("Currency") or "USD"),
            amount=amount_value if amount_value else None,
            source="ibkr_flex_query",
            transaction_id=row.get("TransactionID") or row.get("TradeID"),
            description=row.get("Description") or row.get("ActivityDescription"),
        )
    )


def _parse_flex_xml(account_id: str, payload: str, query_id: Optional[str] = None) -> FlexParseResult:
    root = ET.fromstring(payload)
    statement = root.find(".//FlexStatement")
    if statement is None:
        statement = root.find("FlexStatement")
    statement_account = statement.get("accountId") if statement is not None else None
    report_start = _parse_flex_date(statement.get("fromDate") if statement is not None else None)
    report_end = _parse_flex_date(statement.get("toDate") if statement is not None else None)
    generated_at = _parse_when_generated(statement.get("whenGenerated") if statement is not None else None)

    result = FlexParseResult(
        imported_sections=["flex_xml"],
        report_period_start=report_start,
        report_period_end=report_end,
        query_id=query_id,
        generated_at=generated_at,
        account_id=statement_account or account_id,
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
            "BuySell": row.get("buySell") or row.get("side"),
        }
        row_account = mapped.get("AccountId") or account_id
        if row_account != account_id:
            result.rejected_rows.append({"reason": "account_mismatch", "row": mapped})
            continue
        mapped_action = _map_flex_action(mapped)
        if mapped_action is None:
            result.rejected_rows.append({"reason": "unknown_activity_type", "row": mapped})
            continue
        action, reject_reason = _resolve_execution_action(mapped, mapped_action)
        if action is None:
            result.rejected_rows.append({"reason": reject_reason or "invalid_activity", "row": mapped})
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
        _append_flex_transaction(result, account_id, mapped, trade_day, action)
    return result


def _parse_flex_csv(account_id: str, payload: str) -> FlexParseResult:
    if not payload.strip():
        return FlexParseResult(imported_sections=["flex_csv"])
    reader = csv.DictReader(io.StringIO(payload))
    result = FlexParseResult(imported_sections=["flex_csv"])
    for row in reader:
        account = row.get("AccountId") or row.get("ClientAccountID") or account_id
        if account and account != account_id:
            result.rejected_rows.append({"reason": "account_mismatch", "row": row})
            continue
        date_text = row.get("Date") or row.get("TradeDate") or row.get("ReportDate") or ""
        if not date_text:
            result.rejected_rows.append({"reason": "missing_date", "row": row})
            continue
        try:
            trade_day = datetime.strptime(date_text[:10], "%Y-%m-%d").date()
        except ValueError:
            parsed = _parse_flex_date(date_text)
            if parsed is None:
                result.rejected_rows.append({"reason": "invalid_date", "row": row})
                continue
            trade_day = parsed

        mapped_action = _map_flex_action(row)
        if mapped_action is None:
            result.rejected_rows.append({"reason": "unknown_activity_type", "row": row})
            continue
        action, reject_reason = _resolve_execution_action(row, mapped_action)
        if action is None:
            result.rejected_rows.append({"reason": reject_reason or "invalid_activity", "row": row})
            continue
        row_payload = {
            **row,
            "Symbol": (row.get("Symbol") or row.get("UnderlyingSymbol") or "CASH").upper(),
        }
        _append_flex_transaction(result, account_id, row_payload, trade_day, action)
    return result


def _request_flex_statement(
    token: str,
    query_id: str,
    timeout_seconds: float = 30.0,
) -> str:
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
            text = response.text.lstrip()

            if not text.startswith("<"):
                return response.text

            poll_root = ET.fromstring(text)
            if poll_root.find(".//FlexStatement") is not None:
                return response.text

            poll_status = poll_root.findtext("Status")
            error_message = poll_root.findtext("ErrorMessage")
            if error_message and poll_status not in {None, "Success"}:
                raise RuntimeError(f"IBKR Flex polling failed: {error_message}")

            time.sleep(1.0)

    raise RuntimeError("IBKR Flex statement polling timed out")


def fetch_flex_cash_ledger(account_id: str, query_id: Optional[str] = None) -> FlexParseResult:
    token = configured_flex_token()
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
