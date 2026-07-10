from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from threading import Lock
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.domain import Transaction

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_FILE_LOCK = Lock()

EXTERNAL_INFLOW_ACTIONS = frozenset({"deposit", "contribution", "transfer_in"})
EXTERNAL_OUTFLOW_ACTIONS = frozenset({"withdrawal", "distribution", "transfer_out"})
INTERNAL_ACTIONS = frozenset(
    {"buy", "sell", "dividend", "fee", "interest", "fx", "corporate_action", "transfer"}
)
EXECUTION_ACTIONS = frozenset({"buy", "sell"})


class TransactionLedgerCoverage(BaseModel):
    account_id: str
    source: str
    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None
    imported_sections: list[str] = Field(default_factory=list)
    rejected_row_count: int = 0
    status: Literal["completed", "partial", "error"] = "partial"
    last_successful_sync_at: Optional[datetime] = None
    has_external_cash_flows: bool = False
    execution_only: bool = False
    flex_error: Optional[str] = None


def _coverage_path(account_id: str) -> str:
    safe_id = account_id.replace("/", "_").replace("..", "_")
    return os.path.join(DATA_DIR, f"ledger_coverage_{safe_id}.json")


def save_ledger_coverage(coverage: TransactionLedgerCoverage) -> TransactionLedgerCoverage:
    os.makedirs(DATA_DIR, exist_ok=True)
    with _FILE_LOCK:
        fd, temporary_path = tempfile.mkstemp(prefix="ledger_coverage_", suffix=".tmp", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(coverage.model_dump(mode="json"), handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, _coverage_path(coverage.account_id))
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
    return coverage


def load_ledger_coverage(account_id: str) -> Optional[TransactionLedgerCoverage]:
    path = _coverage_path(account_id)
    if not os.path.exists(path):
        return None
    with _FILE_LOCK, open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return TransactionLedgerCoverage(**raw)


def is_external_cash_flow(txn: Transaction) -> bool:
    return txn.action in EXTERNAL_INFLOW_ACTIONS or txn.action in EXTERNAL_OUTFLOW_ACTIONS


def external_cash_flow_amount(txn: Transaction) -> float:
    """Signed external cash flow. Positive = money added to the account from outside."""
    if txn.action in INTERNAL_ACTIONS or txn.action in EXECUTION_ACTIONS:
        return 0.0
    notional = txn.amount if txn.amount is not None else txn.quantity * txn.price
    if txn.action in EXTERNAL_INFLOW_ACTIONS:
        return abs(notional)
    if txn.action in EXTERNAL_OUTFLOW_ACTIONS:
        return -abs(notional)
    return 0.0


def external_cash_flows_for_interval(
    transactions: list[Transaction],
    interval_start_exclusive: date,
    interval_end_inclusive: date,
    base_currency: str,
    fx_resolver,
) -> float:
    """Sum external flows with trade_date in (interval_start_exclusive, interval_end_inclusive].

    Weekend and holiday flows are assigned to the next portfolio snapshot interval.
    """
    total = 0.0
    for txn in transactions:
        if txn.trade_date <= interval_start_exclusive or txn.trade_date > interval_end_inclusive:
            continue
        amount = external_cash_flow_amount(txn)
        if amount == 0.0:
            continue
        rate = fx_resolver(txn.currency, base_currency)
        total += amount * rate
    return total


def build_ledger_coverage(
    account_id: str,
    transactions: list[Transaction],
    imported_sections: list[str],
    rejected_row_count: int = 0,
    flex_error: Optional[str] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> TransactionLedgerCoverage:
    external_rows = [txn for txn in transactions if is_external_cash_flow(txn)]
    execution_rows = [txn for txn in transactions if txn.action in EXECUTION_ACTIONS]
    has_external = bool(external_rows)
    execution_only = bool(execution_rows) and not has_external

    coverage_start = min((txn.trade_date for txn in external_rows), default=None)
    coverage_end = max((txn.trade_date for txn in external_rows), default=None)
    if not coverage_start and transactions:
        coverage_start = min(txn.trade_date for txn in transactions)
        coverage_end = max(txn.trade_date for txn in transactions)

    sources = sorted({txn.source for txn in transactions if txn.source})
    source = ",".join(sources) if sources else "none"

    status: Literal["completed", "partial", "error"] = "partial"
    if flex_error:
        status = "error" if not transactions else "partial"
    elif has_external and period_start and period_end and coverage_start and coverage_end:
        if coverage_start <= period_start and coverage_end >= period_end:
            status = "completed"
        else:
            status = "partial"
    elif has_external:
        status = "partial"
    elif execution_only:
        status = "partial"

    return TransactionLedgerCoverage(
        account_id=account_id,
        source=source,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        imported_sections=imported_sections,
        rejected_row_count=rejected_row_count,
        status=status,
        last_successful_sync_at=datetime.now(timezone.utc),
        has_external_cash_flows=has_external,
        execution_only=execution_only,
        flex_error=flex_error,
    )


def ledger_covers_period(coverage: Optional[TransactionLedgerCoverage], period_start: date, period_end: date) -> bool:
    if coverage is None or not coverage.has_external_cash_flows:
        return False
    if coverage.execution_only:
        return False
    if coverage.status == "error":
        return False
    if coverage.coverage_start is None or coverage.coverage_end is None:
        return False
    return coverage.coverage_start <= period_start and coverage.coverage_end >= period_end
