from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AccountingIdentity:
    beginning_nav: Decimal
    ending_nav: Decimal
    external_flow: Decimal
    investment_pnl: Decimal
    price_effect: Decimal
    fx_effect: Decimal
    cross_effect: Decimal
    trade_timing_effect: Decimal
    dividend_income: Decimal
    interest_income: Decimal
    fee_expense: Decimal
    withholding_tax: Decimal
    corporate_action_effect: Decimal
    residual: Decimal


def reconcile(identity: AccountingIdentity) -> Decimal:
    explained = (
        identity.price_effect
        + identity.fx_effect
        + identity.cross_effect
        + identity.trade_timing_effect
        + identity.dividend_income
        + identity.interest_income
        - identity.fee_expense
        - identity.withholding_tax
        + identity.corporate_action_effect
    )
    return identity.investment_pnl - explained
