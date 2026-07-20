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


@dataclass(frozen=True)
class TaxExportReadiness:
    ready_for_review: bool
    tax_year: int
    transaction_count: int
    unresolved_items: tuple[str, ...]
    source_statement_ids: tuple[str, ...]
    status: TaxOutputStatus
    disclaimer: str = TAX_DISCLAIMER

    @property
    def filing_ready(self) -> bool:
        """Never expose filing-ready as True for this product."""
        return False

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
) -> TaxExportReadiness:
    unresolved: list[str] = list(unresolved_superficial_loss_cases)
    if not lots_reconciled:
        unresolved.append("lots_not_reconciled")
    if not transactions_reconciled:
        unresolved.append("transactions_not_reconciled")
    if not corporate_actions_reviewed:
        unresolved.append("corporate_actions_unreviewed")

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
    )
