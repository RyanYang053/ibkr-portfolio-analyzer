from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.portfolio.accounting_identity import AccountingIdentity, reconcile


@settings(max_examples=50)
@given(
    beginning_nav=st.decimals(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    ending_nav=st.decimals(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    external_flow=st.decimals(min_value=-100_000, max_value=100_000, allow_nan=False, allow_infinity=False),
    price_effect=st.decimals(min_value=-50_000, max_value=50_000, allow_nan=False, allow_infinity=False),
    fx_effect=st.decimals(min_value=-10_000, max_value=10_000, allow_nan=False, allow_infinity=False),
    cross_effect=st.decimals(min_value=-5_000, max_value=5_000, allow_nan=False, allow_infinity=False),
    trade_timing=st.decimals(min_value=-5_000, max_value=5_000, allow_nan=False, allow_infinity=False),
    dividend=st.decimals(min_value=0, max_value=10_000, allow_nan=False, allow_infinity=False),
    interest=st.decimals(min_value=0, max_value=5_000, allow_nan=False, allow_infinity=False),
    fee=st.decimals(min_value=0, max_value=5_000, allow_nan=False, allow_infinity=False),
    withholding=st.decimals(min_value=0, max_value=5_000, allow_nan=False, allow_infinity=False),
    corporate=st.decimals(min_value=-5_000, max_value=5_000, allow_nan=False, allow_infinity=False),
)
def test_accounting_identity_residual_is_investment_pnl_minus_explained(
    beginning_nav,
    ending_nav,
    external_flow,
    price_effect,
    fx_effect,
    cross_effect,
    trade_timing,
    dividend,
    interest,
    fee,
    withholding,
    corporate,
):
    investment_pnl = ending_nav - beginning_nav - external_flow
    identity = AccountingIdentity(
        beginning_nav=Decimal(beginning_nav),
        ending_nav=Decimal(ending_nav),
        external_flow=Decimal(external_flow),
        investment_pnl=Decimal(investment_pnl),
        price_effect=Decimal(price_effect),
        fx_effect=Decimal(fx_effect),
        cross_effect=Decimal(cross_effect),
        trade_timing_effect=Decimal(trade_timing),
        dividend_income=Decimal(dividend),
        interest_income=Decimal(interest),
        fee_expense=Decimal(fee),
        withholding_tax=Decimal(withholding),
        corporate_action_effect=Decimal(corporate),
        residual=Decimal("0"),
    )
    residual = reconcile(identity)
    explained = (
        Decimal(price_effect)
        + Decimal(fx_effect)
        + Decimal(cross_effect)
        + Decimal(trade_timing)
        + Decimal(dividend)
        + Decimal(interest)
        - Decimal(fee)
        - Decimal(withholding)
        + Decimal(corporate)
    )
    assert residual == Decimal(investment_pnl) - explained
