from __future__ import annotations

import csv
import io
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.domain import Transaction

FLEX_SEND_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
FLEX_GET_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"


def flex_query_configured() -> bool:
    return bool(settings.ibkr_flex_token and settings.ibkr_flex_query_id)


def _map_flex_action(description: str, amount: float) -> str:
    text = description.lower()
    if "deposit" in text or "fund transfer in" in text:
        return "deposit"
    if "withdrawal" in text or "fund transfer out" in text:
        return "withdrawal"
    if "dividend" in text:
        return "dividend"
    if "interest" in text:
        return "interest"
    if "fee" in text or "commission" in text:
        return "fee"
    if "split" in text or "spinoff" in text or "merger" in text:
        return "corporate_action"
    if amount < 0:
        return "withdrawal"
    if amount > 0:
        return "deposit"
    return "transfer"


def _parse_flex_csv(account_id: str, payload: str) -> list[Transaction]:
    reader = csv.DictReader(io.StringIO(payload))
    transactions: list[Transaction] = []
    for row in reader:
        account = row.get("AccountId") or row.get("ClientAccountID") or account_id
        if account and account != account_id:
            continue
        date_text = row.get("Date") or row.get("TradeDate") or row.get("ReportDate") or ""
        if not date_text:
            continue
        try:
            trade_day = datetime.strptime(date_text[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        description = row.get("Description") or row.get("ActivityDescription") or row.get("Symbol") or ""
        symbol = row.get("Symbol") or row.get("UnderlyingSymbol") or "CASH"
        amount_raw = row.get("Amount") or row.get("NetCash") or row.get("Proceeds") or "0"
        try:
            amount = float(str(amount_raw).replace(",", ""))
        except ValueError:
            amount = 0.0
        quantity_raw = row.get("Quantity") or row.get("TradeQuantity") or "1"
        try:
            quantity = float(str(quantity_raw).replace(",", "") or 1.0)
        except ValueError:
            quantity = 1.0
        price_raw = row.get("Price") or row.get("TradePrice") or "0"
        try:
            price = float(str(price_raw).replace(",", "") or 0.0)
        except ValueError:
            price = 0.0
        commission_raw = row.get("Commission") or row.get("Comm/Fee") or "0"
        try:
            commission = float(str(commission_raw).replace(",", "") or 0.0)
        except ValueError:
            commission = 0.0
        currency = row.get("CurrencyPrimary") or row.get("Currency") or "USD"
        action = _map_flex_action(description, amount)
        if action in {"buy", "sell"}:
            action = "buy" if quantity > 0 else "sell"
        transactions.append(
            Transaction(
                account_id=account_id,
                symbol=symbol.upper(),
                trade_date=trade_day,
                action=action,  # type: ignore[arg-type]
                quantity=abs(quantity),
                price=abs(price) if price else abs(amount / quantity) if quantity else abs(amount),
                commission=abs(commission),
                currency=currency,
                amount=abs(amount),
                source="ibkr_flex_query",
                transaction_id=row.get("TransactionID") or row.get("TradeID") or None,
            )
        )
    return transactions


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


def fetch_flex_transactions(account_id: str, query_id: Optional[str] = None) -> list[Transaction]:
    token = settings.ibkr_flex_token
    query = query_id or settings.ibkr_flex_query_id
    if not token or not query:
        raise RuntimeError("IBKR Flex Query is not configured. Set IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID.")
    payload = _request_flex_statement(token, query)
    return _parse_flex_csv(account_id, payload)


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
