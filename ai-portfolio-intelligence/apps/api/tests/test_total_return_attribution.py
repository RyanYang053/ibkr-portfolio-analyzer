from __future__ import annotations

from datetime import date

from app.schemas.domain import Transaction
from app.services.attribution.daily_series import (
    TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS,
    WITHHELD_ATTRIBUTION_STATUS,
    DailySecurityInput,
    allocate_ledger_legs_for_day,
    build_daily_attribution_contributions,
    build_daily_security_inputs_from_history,
    enrich_security_inputs_with_ledger_legs,
)


def _txn(**kwargs) -> Transaction:
    return Transaction(source="test", **kwargs)


def test_income_fee_tax_fx_corp_legs_compose_total_return():
    inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="AAA:1",
            sector="Technology",
            beginning_weight=1.0,
            total_return=0.01,  # price
        )
    ]
    transactions = [
        _txn(
            account_id="A1",
            symbol="AAA",
            con_id=1,
            trade_date=date(2025, 1, 3),
            action="dividend",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=2.0,
        ),
        _txn(
            account_id="A1",
            symbol="AAA",
            con_id=1,
            trade_date=date(2025, 1, 3),
            action="fee",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=0.5,
        ),
        _txn(
            account_id="A1",
            symbol="AAA",
            con_id=1,
            trade_date=date(2025, 1, 3),
            action="withholding_tax",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=0.3,
        ),
        _txn(
            account_id="A1",
            symbol="AAA",
            con_id=1,
            trade_date=date(2025, 1, 3),
            action="fx",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=0.1,
        ),
        _txn(
            account_id="A1",
            symbol="AAA",
            con_id=1,
            trade_date=date(2025, 1, 3),
            action="corporate_action",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=0.2,
        ),
    ]
    enriched, cash = enrich_security_inputs_with_ledger_legs(
        inputs,
        transactions,
        beginning_nav_by_day={date(2025, 1, 3): 100.0},
    )
    assert len(enriched) == 1
    row = enriched[0]
    assert row.legs_from_ledger is True
    assert abs(row.income_return - 0.02) < 1e-9
    assert abs(row.fee_return - (-0.005)) < 1e-9
    assert abs(row.tax_return - (-0.003)) < 1e-9
    assert abs(row.fx_return - 0.001) < 1e-9
    assert abs(row.corp_action_return - 0.002) < 1e-9
    # price + income + fx + fee + tax + corp
    expected = 0.01 + 0.02 + 0.001 - 0.005 - 0.003 + 0.002
    assert abs(row.composed_total_return - expected) < 1e-9
    assert cash[date(2025, 1, 3)]["income"] == 0.0

    contributions, status, quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 6),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=enriched,
        cash_sleeve_returns=cash,
    )
    assert status == WITHHELD_ATTRIBUTION_STATUS
    assert contributions
    day = next(c for c in contributions if c.contribution_date == date(2025, 1, 3))
    assert abs(day.income_contribution - 0.02) < 1e-9
    assert abs(day.fee_contribution - (-0.005)) < 1e-9
    assert abs(day.tax_contribution - (-0.003)) < 1e-9
    assert "cash_sleeve_contribution_sum" in quality


def test_non_price_legs_are_portfolio_contributions_not_double_weighted():
    """Ledger dollars/NAV must not be multiplied again by beginning_weight."""
    inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="AAA:1",
            sector="Technology",
            beginning_weight=0.25,
            total_return=0.0,
        )
    ]
    transactions = [
        _txn(
            account_id="A1",
            symbol="AAA",
            con_id=1,
            trade_date=date(2025, 1, 3),
            action="dividend",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=4.0,
        )
    ]
    enriched, cash = enrich_security_inputs_with_ledger_legs(
        inputs,
        transactions,
        beginning_nav_by_day={date(2025, 1, 3): 100.0},
    )
    assert abs(enriched[0].income_return - 0.04) < 1e-9
    contributions, _status, _quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 6),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=enriched,
        cash_sleeve_returns=cash,
    )
    day = next(c for c in contributions if c.contribution_date == date(2025, 1, 3))
    assert abs(day.income_contribution - 0.04) < 1e-9


def test_exit_without_execution_evidence_is_withheld():
    from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, PositionPnL

    history = [
        PortfolioPnLSnapshot(
            date="2025-01-02",
            timestamp="2025-01-02T16:00:00+00:00",
            net_liquidation=100.0,
            cash=0.0,
            buying_power=0.0,
            margin_requirement=0.0,
            daily_pnl=0.0,
            daily_pnl_percent=0.0,
            positions=[
                PositionPnL(
                    symbol="EXIT",
                    quantity=1,
                    market_price=100.0,
                    market_value=100.0,
                    unrealized_pnl=0.0,
                    con_id=9,
                )
            ],
        ),
        PortfolioPnLSnapshot(
            date="2025-01-03",
            timestamp="2025-01-03T16:00:00+00:00",
            net_liquidation=105.0,
            cash=105.0,
            buying_power=0.0,
            margin_requirement=0.0,
            daily_pnl=5.0,
            daily_pnl_percent=5.0,
            positions=[],
        ),
    ]
    findings: list[dict[str, object]] = []
    rows = build_daily_security_inputs_from_history(
        history,
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 3),
        positions=[],
        transactions=[],
        quality_findings=findings,
    )
    assert rows == []
    assert findings
    assert findings[0]["code"] == "exit_execution_evidence_missing"
    assert findings[0]["instrument_key"] == "EXIT:9"
    assert findings[0]["date"] == "2025-01-03"


def test_mixed_ledger_day_evaluated_row_by_row():
    inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="LEDGER:1",
            sector="Technology",
            beginning_weight=0.5,
            total_return=0.02,
            income_return=0.01,  # already portfolio contribution
            legs_from_ledger=True,
        ),
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="PRICE:2",
            sector="Technology",
            beginning_weight=0.5,
            total_return=0.04,
            income_return=0.10,  # instrument return; must be weight-scaled
            legs_from_ledger=False,
        ),
    ]
    contributions, _status, _quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 6),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=inputs,
        cash_sleeve_returns={},
        history=[],
    )
    day = next(c for c in contributions if c.contribution_date == date(2025, 1, 3))
    # 0.01 ledger contribution + 0.5 * 0.10 weight-scaled = 0.06
    assert abs(day.income_contribution - 0.06) < 1e-9
    # Day-level any(legs_from_ledger) would have incorrectly summed 0.01 + 0.10 = 0.11
    assert abs(day.income_contribution - 0.11) > 1e-9


def test_nav_fallback_marked_non_authoritative():
    from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

    history = [
        PortfolioPnLSnapshot(
            date="2025-01-02",
            timestamp="2025-01-02T16:00:00+00:00",
            net_liquidation=100.0,
            cash=100.0,
            buying_power=0.0,
            margin_requirement=0.0,
            daily_pnl=0.0,
            daily_pnl_percent=0.0,
            positions=[],
            investment_return_percent=None,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-03",
            timestamp="2025-01-03T16:00:00+00:00",
            net_liquidation=101.0,
            cash=101.0,
            buying_power=0.0,
            margin_requirement=0.0,
            daily_pnl=1.0,
            daily_pnl_percent=1.0,
            positions=[],
            investment_return_percent=None,
        ),
    ]
    _contributions, _status, quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 3),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=[],
        history=history,
    )
    assert quality.get("investment_return_non_authoritative") is True
    assert quality.get("investment_return_source") == "nav_change_fallback"
    assert "2025-01-03" in (quality.get("investment_return_degraded_days") or [])
    findings = quality.get("data_quality_findings") or []
    assert any(item.get("code") == "investment_return_nav_fallback" for item in findings)

def test_exit_uses_execution_price_not_minus_one():
    from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, PositionPnL

    history = [
        PortfolioPnLSnapshot(
            date="2025-01-02",
            timestamp="2025-01-02T16:00:00+00:00",
            net_liquidation=100.0,
            cash=0.0,
            buying_power=0.0,
            margin_requirement=0.0,
            daily_pnl=0.0,
            daily_pnl_percent=0.0,
            positions=[
                PositionPnL(
                    symbol="EXIT",
                    quantity=1,
                    market_price=100.0,
                    market_value=100.0,
                    unrealized_pnl=0.0,
                    con_id=9,
                )
            ],
        ),
        PortfolioPnLSnapshot(
            date="2025-01-03",
            timestamp="2025-01-03T16:00:00+00:00",
            net_liquidation=105.0,
            cash=105.0,
            buying_power=0.0,
            margin_requirement=0.0,
            daily_pnl=5.0,
            daily_pnl_percent=5.0,
            positions=[],
        ),
    ]
    transactions = [
        _txn(
            account_id="A1",
            symbol="EXIT",
            con_id=9,
            trade_date=date(2025, 1, 3),
            action="sell",
            quantity=1,
            price=105.0,
            commission=0,
            currency="USD",
        )
    ]
    rows = build_daily_security_inputs_from_history(
        history,
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 3),
        positions=[],
        transactions=transactions,
    )
    assert len(rows) == 1
    assert abs(rows[0].total_return - 0.05) < 1e-9


def test_zero_non_price_legs_are_not_total_return():
    inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="AAA:1",
            sector="Technology",
            beginning_weight=1.0,
            total_return=0.01,
            legs_from_ledger=True,
        )
    ]
    _contributions, status, _quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 6),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=inputs,
        cash_sleeve_returns={},
        history=[],
    )
    assert status == WITHHELD_ATTRIBUTION_STATUS
    assert status != TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS


def test_cash_sleeve_interest_allocated_separately():
    per_instrument, cash = allocate_ledger_legs_for_day(
        [
            _txn(
                account_id="A1",
                symbol="",
                trade_date=date(2025, 1, 3),
                action="interest",
                quantity=0,
                price=0,
                commission=0,
                currency="USD",
                amount=1.5,
            )
        ],
        day=date(2025, 1, 3),
        beginning_nav=150.0,
        instrument_keys={"AAA:1"},
    )
    assert per_instrument["AAA:1"]["income"] == 0.0
    assert cash["income"] == 1.5


def test_nav_residual_gate_fails_without_history_alignment():
    inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="AAA:1",
            sector="Technology",
            beginning_weight=1.0,
            total_return=0.01,
            income_return=0.0,
            fx_return=0.0,
            fee_return=0.0,
            tax_return=0.0,
            corp_action_return=0.0,
            legs_from_ledger=True,
        )
    ]
    contributions, status, quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 6),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=inputs,
        cash_sleeve_returns={},
        history=[],
    )
    assert status == WITHHELD_ATTRIBUTION_STATUS
    assert contributions
    assert quality.get("nav_residual_within_tolerance") is False
    assert quality.get("contribution_identity_ok") is False
    # Zero non-price legs must not claim full total-return status.
    assert status != TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS


def test_production_brinson_requires_nav_residual():
    from app.services.attribution.daily_contribution import DailyContribution
    from app.services.attribution.daily_series import TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS
    from app.services.attribution.engine import _production_brinson_ready

    daily = [
        DailyContribution(
            contribution_date=date(2025, 1, 3),
            security_contribution=0.01,
            income_contribution=0.0,
            fx_contribution=0.0,
            fee_contribution=0.0,
            tax_contribution=0.0,
            allocation_effect=0.01,
            selection_effect=0.0,
            interaction_effect=0.0,
            portfolio_return=0.01,
            benchmark_return=0.0,
        )
    ]
    base_kwargs = dict(
        ledger_brinson_ready=True,
        by_sector={"Technology": {"allocation": 0.0, "selection": 0.0, "interaction": 0.0}},
        benchmark_source="licensed_constituent_weights",
        cash_flow_status="sufficient",
        allow_mock=False,
        allocation=0.0,
        selection=0.0,
        interaction=0.0,
        total_active=0.0,
        daily_contributions=daily,
        daily_attribution_status=TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS,
    )
    assert (
        _production_brinson_ready(
            **base_kwargs,
            daily_quality={"nav_residual_within_tolerance": False, "contribution_identity_ok": True},
        )
        is False
    )
    assert (
        _production_brinson_ready(
            **base_kwargs,
            daily_quality={"nav_residual_within_tolerance": True, "contribution_identity_ok": True},
        )
        is True
    )
