"""Tax reconciliation export helpers (not CRA filing)."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from app.core.product_scope import TAX_DISCLAIMER
from app.services.tax.tax_evidence import TaxExportReadiness, TaxOutputStatus

TAX_UI_LABELS: dict[str, str] = {
    "Filing-ready tax": "Tax reconciliation export",
    "Tax certified": "Reconciled tax estimate",
    "Final tax amount": "Estimated taxable gain/loss",
    "Deductible loss": "Potentially allowable loss",
    "Superficial loss applied": "Potential superficial-loss adjustment",
}


def safe_csv_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def assert_not_filing_ready(readiness: TaxExportReadiness) -> None:
    if readiness.filing_ready is not False:
        raise ValueError("Tax export must never be filing-ready")
    if readiness.status == TaxOutputStatus.WITHHELD and readiness.ready_for_review:
        raise ValueError("Withheld tax output cannot be ready for review")


def export_tax_worksheet_csv(
    rows: Iterable[dict[str, Any]],
    *,
    readiness: TaxExportReadiness,
) -> str:
    """Export a review worksheet CSV with mandatory disclaimer row metadata."""
    assert_not_filing_ready(readiness)
    buffer = io.StringIO()
    buffer.write(f"# disclaimer,{TAX_DISCLAIMER}\n")
    buffer.write(f"# tax_year,{readiness.tax_year}\n")
    buffer.write(f"# status,{readiness.status.value}\n")
    buffer.write(f"# ready_for_review,{str(readiness.ready_for_review).lower()}\n")
    buffer.write("# filing_ready,false\n")

    materialized = list(rows)
    if not materialized:
        buffer.write("symbol,quantity,estimated_gain_loss,notes\n")
        return buffer.getvalue()

    sanitized = [
        {key: safe_csv_value(value) for key, value in row.items()}
        for row in materialized
    ]
    fieldnames = list(sanitized[0].keys())
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(sanitized)
    return buffer.getvalue()
