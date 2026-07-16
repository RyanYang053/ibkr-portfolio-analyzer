from __future__ import annotations

from datetime import date

from app.schemas.domain import Transaction
from app.services.attribution.daily_series import (
    DailySecurityInput,
    TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS,
    allocate_ledger_legs_for_day,
    build_daily_attribution_contributions,
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
    assert status == TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS
    assert contributions
    day = next(c for c in contributions if c.contribution_date == date(2025, 1, 3))
    assert abs(day.income_contribution - 0.02) < 1e-9
    assert abs(day.fee_contribution - (-0.005)) < 1e-9
    assert abs(day.tax_contribution - (-0.003)) < 1e-9
    assert "cash_sleeve_contribution_sum" in quality


def test_sold_between_snapshots_keeps_exit_and_income_leg():
    inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="EXIT:9",
            sector="Technology",
            beginning_weight=0.5,
            total_return=-1.0,  # full exit of long
        ),
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="KEEP:1",
            sector="Technology",
            beginning_weight=0.5,
            total_return=0.0,
        ),
    ]
    transactions = [
        _txn(
            account_id="A1",
            symbol="EXIT",
            con_id=9,
            trade_date=date(2025, 1, 3),
            action="dividend",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            amount=5.0,
        )
    ]
    enriched, _cash = enrich_security_inputs_with_ledger_legs(
        inputs,
        transactions,
        beginning_nav_by_day={date(2025, 1, 3): 100.0},
    )
    exit_row = next(row for row in enriched if row.instrument_key == "EXIT:9")
    assert exit_row.total_return == -1.0
    assert abs(exit_row.income_return - 0.05) < 1e-9


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
    assert status == TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS
    assert contributions
    assert quality.get("nav_residual_within_tolerance") is False
    assert quality.get("contribution_identity_ok") is False


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
