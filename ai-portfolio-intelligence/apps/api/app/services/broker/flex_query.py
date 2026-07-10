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


def _parse_flex_csv(account_id: str, payload: str) -> FlexParseResult:
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
            )
        )
    return result


def _request_flex_statement(token: str, query_id: str, timeout_seconds: float = 30.0) -> str:
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
        raise RuntimeError("IBKR Flex activity query returned XML instead of CSV; configure an activity CSV query.")
    return _parse_flex_csv(account_id, payload)


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
        ),
    ]
