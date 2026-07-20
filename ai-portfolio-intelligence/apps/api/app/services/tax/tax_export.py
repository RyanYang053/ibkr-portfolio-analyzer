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


def assert_not_filing_ready(readiness: TaxExportReadiness) -> None:
    assert readiness.filing_ready is False
    assert readiness.status != TaxOutputStatus.WITHHELD or not readiness.ready_for_review


def export_tax_worksheet_csv(
    rows: Iterable[dict[str, Any]],
    *,
    readiness: TaxExportReadiness,
) -> str:
    """Export a review worksheet CSV with mandatory disclaimer row metadata."""
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

    fieldnames = list(materialized[0].keys())
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(materialized)
    return buffer.getvalue()
