"""Personal portfolio accounting identity (broker-reconciled analytics)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.product_scope import ACCOUNTING_DISCLAIMER


@dataclass(frozen=True)
class PortfolioIdentity:
    beginning_nav: Decimal
    ending_nav: Decimal
    deposits: Decimal
    withdrawals: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    dividends: Decimal
    interest: Decimal
    commissions_and_fees: Decimal
    withholding_tax: Decimal
    fx_translation: Decimal
    corporate_actions: Decimal
    unexplained_residual: Decimal
    disclaimer: str = ACCOUNTING_DISCLAIMER


def build_portfolio_identity(
    *,
    beginning_nav: Decimal,
    ending_nav: Decimal,
    deposits: Decimal = Decimal("0"),
    withdrawals: Decimal = Decimal("0"),
    realized_pnl: Decimal = Decimal("0"),
    unrealized_pnl: Decimal = Decimal("0"),
    dividends: Decimal = Decimal("0"),
    interest: Decimal = Decimal("0"),
    commissions_and_fees: Decimal = Decimal("0"),
    withholding_tax: Decimal = Decimal("0"),
    fx_translation: Decimal = Decimal("0"),
    corporate_actions: Decimal = Decimal("0"),
) -> PortfolioIdentity:
    """Build identity and compute residual from the NAV bridge."""
    external_flow = deposits - withdrawals
    explained = (
        external_flow
        + realized_pnl
        + unrealized_pnl
        + dividends
        + interest
        - commissions_and_fees
        - withholding_tax
        + fx_translation
        + corporate_actions
    )
    residual = ending_nav - beginning_nav - explained
    return PortfolioIdentity(
        beginning_nav=beginning_nav,
        ending_nav=ending_nav,
        deposits=deposits,
        withdrawals=withdrawals,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        dividends=dividends,
        interest=interest,
        commissions_and_fees=commissions_and_fees,
        withholding_tax=withholding_tax,
        fx_translation=fx_translation,
        corporate_actions=corporate_actions,
        unexplained_residual=residual,
    )
