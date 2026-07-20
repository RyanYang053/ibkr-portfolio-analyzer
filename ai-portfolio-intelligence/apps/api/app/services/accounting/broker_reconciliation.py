"""Broker statement reconciliation for personal portfolio analytics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.core.product_scope import ACCOUNTING_DISCLAIMER
from app.services.accounting.portfolio_identity import PortfolioIdentity


class AccountingStatus(StrEnum):
    RECONCILED = "reconciled"
    RECONCILED_WITH_TOLERANCE = "reconciled_with_tolerance"
    DEGRADED = "degraded"
    WITHHELD = "withheld"


def personal_residual_tolerance(ending_nav: Decimal) -> Decimal:
    """Personal-use gate: cent floor or 0.1 bp of ending NAV."""
    return max(Decimal("0.01"), abs(ending_nav) * Decimal("0.00001"))


@dataclass(frozen=True)
class BrokerReconciliationReport:
    status: AccountingStatus
    residual: Decimal
    tolerance: Decimal
    unsupported_events: tuple[str, ...]
    source_lineage_complete: bool
    disclaimer: str = ACCOUNTING_DISCLAIMER


def evaluate_reconciliation(
    identity: PortfolioIdentity,
    *,
    unsupported_events: tuple[str, ...] = (),
    source_lineage_complete: bool = True,
    withheld: bool = False,
) -> BrokerReconciliationReport:
    """Classify broker-reconciled personal accounting status."""
    residual = identity.unexplained_residual
    tolerance = personal_residual_tolerance(identity.ending_nav)

    if withheld or unsupported_events:
        status = AccountingStatus.WITHHELD
    elif not source_lineage_complete:
        status = AccountingStatus.DEGRADED
    elif residual == 0:
        status = AccountingStatus.RECONCILED
    elif abs(residual) <= tolerance:
        status = AccountingStatus.RECONCILED_WITH_TOLERANCE
    else:
        status = AccountingStatus.DEGRADED

    return BrokerReconciliationReport(
        status=status,
        residual=residual,
        tolerance=tolerance,
        unsupported_events=unsupported_events,
        source_lineage_complete=source_lineage_complete,
    )
