"""Tax reconciliation runner — compare lot snapshots to attribution and persist runs."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.db.tax_lot_snapshot_repo import list_tax_lot_snapshots
from app.db.tax_reconciliation_repo import save_tax_reconciliation_run
from app.services.tax.tax_evidence import evaluate_tax_export_readiness


def run_tax_reconciliation(
    *,
    account_id: str,
    tax_year: int | None = None,
    transactions: list[Any] | None = None,
    lots_reconciled: bool | None = None,
    transactions_reconciled: bool | None = None,
    corporate_actions_reviewed: bool = True,
) -> dict[str, Any]:
    year = int(tax_year or date.today().year)
    lots = list_tax_lot_snapshots(account_id, as_of_date=date.today())
    lot_count = len(lots)
    txn_count = len(transactions or [])

    # Default: lots present => provisional lot reconcile; transactions optional.
    lots_ok = lots_reconciled if lots_reconciled is not None else lot_count > 0
    tx_ok = transactions_reconciled if transactions_reconciled is not None else txn_count > 0

    readiness = evaluate_tax_export_readiness(
        tax_year=year,
        transaction_count=txn_count,
        lots_reconciled=lots_ok,
        transactions_reconciled=tx_ok,
        corporate_actions_reviewed=corporate_actions_reviewed,
        source_statement_ids=tuple(
            sorted({str(lot.get("source") or "lot_snapshot") for lot in lots})
        )[:20],
    )

    status = "reconciled" if readiness.filing_worksheet_ready else str(readiness.status.value)
    payload = {
        "lot_count": lot_count,
        "transaction_count": txn_count,
        "filing_ready": readiness.filing_ready,
        "filing_worksheet_ready": readiness.filing_worksheet_ready,
        "unresolved_items": list(readiness.unresolved_items),
        "methodology_approved_for_personal_use": readiness.methodology_approved_for_personal_use,
        "order_generated": False,
        "disclaimer": readiness.disclaimer,
    }
    row = save_tax_reconciliation_run(
        account_id=account_id,
        tax_year=year,
        status=status,
        payload=payload,
    )
    return {
        "ok": True,
        "run": row,
        "readiness": {
            "status": readiness.status.value,
            "filing_ready": readiness.filing_ready,
            "filing_worksheet_ready": readiness.filing_worksheet_ready,
            "unresolved_items": list(readiness.unresolved_items),
            "ready_for_review": readiness.ready_for_review,
        },
        "order_generated": False,
    }
