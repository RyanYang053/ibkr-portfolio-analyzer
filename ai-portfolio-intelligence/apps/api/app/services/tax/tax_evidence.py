"""Tax evidence and export readiness for personal decision-support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.product_scope import TAX_DISCLAIMER


class TaxOutputStatus(StrEnum):
    ESTIMATE = "estimate"
    RECONCILED_ESTIMATE = "reconciled_estimate"
    REVIEW_REQUIRED = "review_required"
    WITHHELD = "withheld"


def _tax_methodology_approved() -> bool:
    try:
        from app.db.methodology_repo import load_methodology_registry

        record = next(
            (
                item
                for item in load_methodology_registry()
                if item.methodology_id == "tax_lot_methodology"
            ),
            None,
        )
        return bool(record and record.approval_status in {"approved", "approved_for_personal_use"})
    except Exception:
        return False


@dataclass(frozen=True)
class TaxExportReadiness:
    ready_for_review: bool
    tax_year: int
    transaction_count: int
    unresolved_items: tuple[str, ...]
    source_statement_ids: tuple[str, ...]
    status: TaxOutputStatus
    disclaimer: str = TAX_DISCLAIMER
    wash_sales_fully_adjusted: bool = True
    methodology_approved_for_personal_use: bool = False

    @property
    def filing_ready(self) -> bool:
        """Filing worksheet ready when reconciled, methodology approved, and wash sales adjusted."""
        return (
            self.status == TaxOutputStatus.RECONCILED_ESTIMATE
            and self.methodology_approved_for_personal_use
            and not self.unresolved_items
            and self.wash_sales_fully_adjusted
        )

    @property
    def filing_worksheet_ready(self) -> bool:
        return self.filing_ready

    @property
    def tax_export_ready(self) -> bool:
        return self.ready_for_review and self.status == TaxOutputStatus.RECONCILED_ESTIMATE


def evaluate_tax_export_readiness(
    *,
    tax_year: int,
    transaction_count: int,
    lots_reconciled: bool,
    transactions_reconciled: bool,
    corporate_actions_reviewed: bool,
    unresolved_superficial_loss_cases: tuple[str, ...] = (),
    source_statement_ids: tuple[str, ...] = (),
    withheld: bool = False,
    wash_sales_fully_adjusted: bool = True,
    methodology_approved_for_personal_use: bool | None = None,
) -> TaxExportReadiness:
    unresolved: list[str] = list(unresolved_superficial_loss_cases)
    if not lots_reconciled:
        unresolved.append("lots_not_reconciled")
    if not transactions_reconciled:
        unresolved.append("transactions_not_reconciled")
    if not corporate_actions_reviewed:
        unresolved.append("corporate_actions_unreviewed")
    if not wash_sales_fully_adjusted:
        unresolved.append("wash_sales_not_fully_adjusted")

    approved = (
        _tax_methodology_approved()
        if methodology_approved_for_personal_use is None
        else bool(methodology_approved_for_personal_use)
    )

    if withheld:
        status = TaxOutputStatus.WITHHELD
        ready = False
    elif unresolved_superficial_loss_cases:
        status = TaxOutputStatus.REVIEW_REQUIRED
        ready = False
    elif unresolved:
        status = TaxOutputStatus.ESTIMATE
        ready = False
    else:
        status = TaxOutputStatus.RECONCILED_ESTIMATE
        ready = True

    return TaxExportReadiness(
        ready_for_review=ready,
        tax_year=tax_year,
        transaction_count=transaction_count,
        unresolved_items=tuple(unresolved),
        source_statement_ids=source_statement_ids,
        status=status,
        wash_sales_fully_adjusted=wash_sales_fully_adjusted,
        methodology_approved_for_personal_use=approved,
    )
