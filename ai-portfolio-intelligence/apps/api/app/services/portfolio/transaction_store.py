from __future__ import annotations

import hashlib
from datetime import date, datetime
from threading import Lock
from typing import Optional

from app.core.config import settings
from app.schemas.domain import Transaction
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.ledger_coverage import (
    TransactionLedgerCoverage,
    build_ledger_coverage,
    load_ledger_coverage,
    save_ledger_coverage,
)

DATA_DIR = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))),
    "data",
)
_FILE_LOCK = Lock()


def _transactions_path(account_id: str) -> str:
    safe_id = account_id.replace("/", "_").replace("..", "_")
    return __import__("os").path.join(DATA_DIR, f"transactions_{safe_id}.json")


def _atomic_write(path: str, payload: list[dict]) -> None:
    import json
    import os
    import tempfile

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
    return txn.source_row_id or txn.transaction_id or hashlib.sha256(
        "|".join(
            [
                txn.account_id,
                txn.event_timestamp.isoformat(),
                txn.action,
                txn.symbol,
                str(txn.con_id or ""),
                str(txn.quantity),
                str(txn.price),
                str(txn.amount),
                txn.currency,
                txn.source,
                txn.source_batch_id or "",
            ]
        ).encode()
    ).hexdigest()


def load_transactions(account_id: str) -> list[Transaction]:
    if settings.persistence_backend == "postgres":
        from app.db.ledger_transaction_repo import read_transactions

        stored = read_transactions(account_id)
        if stored is not None:
            return [Transaction(**item) for item in stored]

    path = _transactions_path(account_id)
    if not __import__("os").path.exists(path):
        return []
    import json

    try:
        with _FILE_LOCK, open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Transaction ledger is unreadable: {path}") from exc
    if not isinstance(raw, list):
        raise RuntimeError(f"Transaction ledger must contain a JSON array: {path}")
    return [Transaction(**item) for item in raw]


def save_transactions(account_id: str, transactions: list[Transaction]) -> list[Transaction]:
    existing = {_transaction_key(item): item for item in load_transactions(account_id)}
    for txn in transactions:
        existing[_transaction_key(txn)] = txn
    merged = sorted(
        existing.values(),
        key=lambda item: (item.event_timestamp, item.source_row_id or "", item.transaction_id or ""),
    )

    if settings.persistence_backend == "postgres":
        from app.db.ledger_transaction_repo import replace_transactions

        replace_transactions(account_id, merged)
    else:
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


def get_ledger_coverage(account_id: str) -> Optional[TransactionLedgerCoverage]:
    return load_ledger_coverage(account_id)


def sync_transactions(
    adapter: BrokerAdapter,
    account_id: str,
    lookback_days: int = 365,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> tuple[list[Transaction], TransactionLedgerCoverage]:
    end_date = period_end or date.today()
    start_date = period_start or end_date.fromordinal(end_date.toordinal() - lookback_days)
    execution_rows = adapter.get_transactions(account_id, start_date, end_date)

    from app.core.config import settings
    from app.services.broker.flex_query import (
        fetch_flex_cash_ledger,
        flex_activity_query_configured,
        mock_flex_transactions,
    )

    flex_rows: list[Transaction] = []
    flex_result = None
    rejected_row_count = 0
    flex_error: str | None = None
    imported_sections = ["executions"]

    if flex_activity_query_configured():
        try:
            flex_result = fetch_flex_cash_ledger(account_id)
            flex_rows = flex_result.transactions
            rejected_row_count = flex_result.rejected_row_count
            imported_sections.append("flex_cash_ledger")
        except Exception as exc:
            flex_error = str(exc)
    elif settings.broker_mode == "mock_ibkr_readonly":
        flex_rows = mock_flex_transactions(account_id)
        imported_sections.append("mock_flex_cash_ledger")

    merged = save_transactions(account_id, execution_rows + flex_rows)
    flex_period_start = flex_result.report_period_start if flex_result is not None else None
    flex_period_end = flex_result.report_period_end if flex_result is not None else None

    coverage = build_ledger_coverage(
        account_id=account_id,
        transactions=merged,
        imported_sections=imported_sections,
        rejected_row_count=rejected_row_count,
        flex_error=flex_error,
        period_start=flex_period_start,
        period_end=flex_period_end,
        flex_query_id=flex_result.query_id if flex_result is not None else None,
        flex_generated_at=flex_result.generated_at if flex_result is not None else None,
        flex_statement_account_id=flex_result.account_id if flex_result is not None else None,
    )
    save_ledger_coverage(coverage)
    return merged, coverage


def last_sync_timestamp(account_id: str) -> datetime | None:
    coverage = load_ledger_coverage(account_id)
    if coverage and coverage.last_successful_sync_at:
        return coverage.last_successful_sync_at
    rows = load_transactions(account_id)
    if not rows:
        return None
    return datetime.combine(max(item.trade_date for item in rows), datetime.min.time())
