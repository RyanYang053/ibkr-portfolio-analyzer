from decimal import Decimal

from app.services.accounting import build_portfolio_identity, evaluate_reconciliation
from app.services.accounting.broker_reconciliation import AccountingStatus


def test_perfect_nav_bridge_reconciles():
    identity = build_portfolio_identity(
        beginning_nav=Decimal("100000"),
        ending_nav=Decimal("101250"),
        deposits=Decimal("1000"),
        withdrawals=Decimal("0"),
        realized_pnl=Decimal("200"),
        unrealized_pnl=Decimal("50"),
        dividends=Decimal("25"),
        interest=Decimal("0"),
        commissions_and_fees=Decimal("10"),
        withholding_tax=Decimal("5"),
        fx_translation=Decimal("0"),
        corporate_actions=Decimal("-10"),
    )
    # 100000 + 1000 + 200 + 50 + 25 - 10 - 5 - 10 = 101250
    assert identity.unexplained_residual == Decimal("0")
    report = evaluate_reconciliation(identity)
    assert report.status == AccountingStatus.RECONCILED


def test_small_residual_within_personal_tolerance():
    identity = build_portfolio_identity(
        beginning_nav=Decimal("100000"),
        ending_nav=Decimal("100000.05"),
        deposits=Decimal("0"),
    )
    report = evaluate_reconciliation(identity)
    assert report.status == AccountingStatus.RECONCILED_WITH_TOLERANCE
