from __future__ import annotations

from datetime import date

import pytest

from app.schemas.domain import Position, Transaction, utc_now
from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of
from app.services.attribution.brinson_ledger import (
    AttributionDataIncomplete,
    beginning_sector_weights,
    reconstruct_holdings_at_date,
)
from app.services.attribution.daily_contribution import build_daily_contribution
from app.services.attribution.linking import active_return_reconciles
from app.services.market_data.exchange_calendar import previous_trading_session


def _txn(**kwargs) -> Transaction:
    return Transaction(source="test", **kwargs)


def test_previous_trading_session_skips_weekend():
    assert previous_trading_session(date(2026, 7, 6)).isoformat() == "2026-07-02"


def test_reconstruct_holdings_supports_short_positions():
    transactions = [
        _txn(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2024, 1, 1),
            action="sell",
            quantity=10,
            price=300,
            commission=0,
            currency="USD",
        )
    ]
    holdings = reconstruct_holdings_at_date(transactions, date(2024, 1, 2))
    assert holdings[("MSFT", None)] == pytest.approx(-10.0)


def test_beginning_sector_weights_requires_fx(monkeypatch):
    monkeypatch.setattr(
        "app.services.attribution.brinson_ledger._price_on_or_before",
        lambda symbol, _as_of, allow_mock=False: 100.0,
    )
    transactions = [
        _txn(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=10,
            price=100,
            commission=0,
            currency="CAD",
        )
    ]
    positions = [
        Position(
            account_id="MOCK-001",
            symbol="RY",
            company_name="Royal Bank",
            asset_class="STK",
            quantity=10,
            avg_cost=100,
            market_price=110,
            market_value=1100,
            unrealized_pnl=100,
            currency="CAD",
            exchange="TSE",
            sector="Financials",
            industry="Banks",
            portfolio_weight=100,
            stock_type="core",
            updated_at=utc_now(),
        )
    ]
    with pytest.raises(AttributionDataIncomplete):
        beginning_sector_weights(
            transactions,
            positions,
            date(2024, 6, 1),
            "USD",
            lambda _a, _b: (_ for _ in ()).throw(TypeError("missing trade date fx")),
            allow_mock=True,
        )


def test_geometric_linking_reconciles_active_return():
    contributions = [
        build_daily_contribution(
            contribution_date=date(2025, 1, 2),
            security_return=0.01,
            portfolio_weight=1.0,
            portfolio_sector_weight=1.0,
            benchmark_sector_weight=1.0,
            portfolio_sector_return=0.01,
            benchmark_sector_return=0.005,
            portfolio_return=0.01,
            benchmark_return=0.005,
        ),
        build_daily_contribution(
            contribution_date=date(2025, 1, 3),
            security_return=0.02,
            portfolio_weight=1.0,
            portfolio_sector_weight=1.0,
            benchmark_sector_weight=1.0,
            portfolio_sector_return=0.02,
            benchmark_sector_return=0.01,
            portfolio_return=0.02,
            benchmark_return=0.01,
        ),
    ]
    ok, gap = active_return_reconciles(contributions, tolerance=0.01)
    assert ok or abs(gap) <= 0.01


def test_daily_attribution_series_builds_linked_contributions():
    from app.services.attribution.daily_series import (
        DAILY_ATTRIBUTION_STATUS,
        build_daily_attribution_contributions,
    )
    from app.services.attribution.linking import active_return_reconciles
    from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

    history = [
        PortfolioPnLSnapshot(
            date="2025-01-02",
            timestamp="2025-01-02T16:00:00+00:00",
            net_liquidation=100_000,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
            data_quality={},
            investment_return_percent=0.5,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-03",
            timestamp="2025-01-03T16:00:00+00:00",
            net_liquidation=100_500,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=500,
            daily_pnl_percent=0.5,
            positions=[],
            data_quality={},
            investment_return_percent=0.4,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-06",
            timestamp="2025-01-06T16:00:00+00:00",
            net_liquidation=100_900,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=400,
            daily_pnl_percent=0.4,
            positions=[],
            data_quality={},
            investment_return_percent=-0.1,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-07",
            timestamp="2025-01-07T16:00:00+00:00",
            net_liquidation=100_800,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=-100,
            daily_pnl_percent=-0.1,
            positions=[],
            data_quality={},
            investment_return_percent=0.2,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-08",
            timestamp="2025-01-08T16:00:00+00:00",
            net_liquidation=101_000,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=200,
            daily_pnl_percent=0.2,
            positions=[],
            data_quality={},
            investment_return_percent=0.1,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-09",
            timestamp="2025-01-09T16:00:00+00:00",
            net_liquidation=101_100,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=100,
            daily_pnl_percent=0.1,
            positions=[],
            data_quality={},
            investment_return_percent=0.3,
        ),
        PortfolioPnLSnapshot(
            date="2025-01-10",
            timestamp="2025-01-10T16:00:00+00:00",
            net_liquidation=101_400,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=300,
            daily_pnl_percent=0.3,
            positions=[],
            data_quality={},
            investment_return_percent=0.0,
        ),
    ]
    contributions, status, _quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 10),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        history=history,
    )
    assert status == DAILY_ATTRIBUTION_STATUS
    assert DAILY_ATTRIBUTION_STATUS == "experimental_static_weight_daily_attribution"
    assert contributions
    ok, gap = active_return_reconciles(contributions, tolerance=0.25)
    assert ok or abs(gap) <= 0.25


def test_holdings_based_daily_attribution_from_security_inputs():
    from app.services.attribution.daily_series import (
        DailySecurityInput,
        HOLDINGS_DAILY_ATTRIBUTION_STATUS,
        build_daily_attribution_contributions,
    )

    security_inputs = [
        DailySecurityInput(
            date=date(2025, 1, 3),
            instrument_key="AAA:1",
            sector="Technology",
            beginning_weight=1.0,
            total_return=0.01,
        ),
        DailySecurityInput(
            date=date(2025, 1, 6),
            instrument_key="AAA:1",
            sector="Technology",
            beginning_weight=1.0,
            total_return=-0.005,
        ),
    ]
    contributions, status, _quality = build_daily_attribution_contributions(
        positions=[],
        period_start=date(2025, 1, 2),
        period_end=date(2025, 1, 10),
        portfolio_sector_weights={"Technology": 1.0},
        allow_mock=True,
        security_inputs=security_inputs,
    )
    assert status == HOLDINGS_DAILY_ATTRIBUTION_STATUS
    assert len(contributions) == 2
    assert contributions[0].portfolio_return == 0.01
    assert contributions[1].portfolio_return == -0.005


def test_benchmark_weights_withheld_outside_mock():
    assert benchmark_sector_weights_as_of(date.today(), allow_mock=False) is None
