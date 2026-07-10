from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from threading import Lock
from typing import Optional

from app.schemas.domain import Transaction
from app.services.broker.base import BrokerAdapter

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_FILE_LOCK = Lock()


def _transactions_path(account_id: str) -> str:
    safe_id = account_id.replace("/", "_").replace("..", "_")
    return os.path.join(DATA_DIR, f"transactions_{safe_id}.json")


def _atomic_write(path: str, payload: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _FILE_LOCK:
        fd, temporary_path = tempfile.mkstemp(prefix="transactions_", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def _transaction_key(txn: Transaction) -> str:
    if txn.transaction_id:
        return txn.transaction_id
    return "|".join(
        [
            txn.account_id,
            txn.trade_date.isoformat(),
            txn.action,
            txn.symbol,
            str(txn.quantity),
            str(txn.price),
            str(txn.commission),
            txn.currency,
            str(txn.con_id or ""),
        ]
    )


def load_transactions(account_id: str) -> list[Transaction]:
    path = _transactions_path(account_id)
    if not os.path.exists(path):
        return []
    try:
        with _FILE_LOCK, open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Transaction ledger is unreadable: {path}") from exc
    if not isinstance(raw, list):
        raise RuntimeError(f"Transaction ledger must contain a JSON array: {path}")
    return [Transaction(**item) for item in raw]


def save_transactions(account_id: str, transactions: list[Transaction]) -> list[Transaction]:
    existing = { _transaction_key(item): item for item in load_transactions(account_id) }
    for txn in transactions:
        existing[_transaction_key(txn)] = txn
    merged = sorted(existing.values(), key=lambda item: (item.trade_date, item.symbol, item.action))
    _atomic_write(_transactions_path(account_id), [item.model_dump(mode="json") for item in merged])
    return merged


def get_transactions(
    account_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> list[Transaction]:
    rows = load_transactions(account_id)
    if start_date:
        rows = [item for item in rows if item.trade_date >= start_date]
    if end_date:
        rows = [item for item in rows if item.trade_date <= end_date]
    return rows


def sync_transactions(adapter: BrokerAdapter, account_id: str, lookback_days: int = 365) -> list[Transaction]:
    end_date = date.today()
    start_date = end_date.fromordinal(end_date.toordinal() - lookback_days)
    fetched = adapter.get_transactions(account_id, start_date, end_date)
    return save_transactions(account_id, fetched)


def external_cash_flow_amount(txn: Transaction) -> float:
    """Signed external cash flow in transaction currency (positive = money added to account)."""
    notional = txn.amount
    if notional is None:
        notional = txn.quantity * txn.price
    if txn.action in {"deposit"}:
        return abs(notional)
    if txn.action in {"withdrawal"}:
        return -abs(notional)
    if txn.action == "dividend":
        return abs(notional)
    if txn.action == "fee":
        return 0.0  # Fees reduce NAV directly; they are not external flows.
    if txn.action == "interest":
        return abs(notional)
    return 0.0


def external_cash_flows_by_date(
    transactions: list[Transaction],
    base_currency: str,
    fx_resolver,
) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for txn in transactions:
        amount = external_cash_flow_amount(txn)
        if amount == 0.0:
            continue
        rate = fx_resolver(txn.currency, base_currency)
        grouped[txn.trade_date.isoformat()] = grouped.get(txn.trade_date.isoformat(), 0.0) + amount * rate
    return grouped


def last_sync_timestamp(account_id: str) -> datetime | None:
    rows = load_transactions(account_id)
    if not rows:
        return None
    return datetime.combine(max(item.trade_date for item in rows), datetime.min.time())
