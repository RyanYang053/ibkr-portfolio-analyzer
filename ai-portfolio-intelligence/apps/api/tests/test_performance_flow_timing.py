from __future__ import annotations

from datetime import date

from app.schemas.domain import Transaction
from app.services.portfolio.performance_returns import _subperiod_twr_interval_return
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot


def _snapshot(day: str, nav: float) -> PortfolioPnLSnapshot:
    return PortfolioPnLSnapshot(
        date=day,
        timestamp=f"{day}T16:00:00+00:00",
        net_liquidation=nav,
        cash=nav * 0.1,
        buying_power=nav * 0.2,
        margin_requirement=0,
        daily_pnl=0,
        daily_pnl_percent=0,
        positions=[],
        data_quality={},
    )


def test_subperiod_twr_withheld_without_valuation_timing():
    snapshots = [_snapshot("2026-01-01", 100_000), _snapshot("2026-01-02", 101_000), _snapshot("2026-01-15", 106_000)]
    txns = [
        Transaction(
            account_id="TEST-001",
            symbol="CASH",
            trade_date=date(2026, 1, 2),
            action="deposit",
            quantity=1,
            price=5000,
            commission=0,
            currency="USD",
            amount=5000,
        )
    ]
    result = _subperiod_twr_interval_return(
        snapshots,
        txns,
        date(2026, 1, 1),
        date(2026, 1, 15),
        "USD",
        lambda _a, _b: 1.0,
    )
    assert result is None


def test_subperiod_twr_allowed_with_explicit_timing_metadata():
    snapshots = [
        PortfolioPnLSnapshot(
            date="2026-01-01",
            timestamp="2026-01-01T16:00:00+00:00",
            net_liquidation=100_000,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
            data_quality={"valuation_timing": "post_close", "observed_at": "2026-01-01T16:00:00+00:00"},
        ),
        PortfolioPnLSnapshot(
            date="2026-01-05",
            timestamp="2026-01-05T16:00:00+00:00",
            net_liquidation=105_000,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
            data_quality={"valuation_timing": "post_close", "observed_at": "2026-01-05T16:00:00+00:00"},
        ),
        PortfolioPnLSnapshot(
            date="2026-01-15",
            timestamp="2026-01-15T16:00:00+00:00",
            net_liquidation=106_000,
            cash=10_000,
            buying_power=20_000,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
            data_quality={"valuation_timing": "post_close", "observed_at": "2026-01-15T16:00:00+00:00"},
        ),
    ]
    txns = [
        Transaction(
            account_id="TEST-001",
            symbol="CASH",
            trade_date=date(2026, 1, 5),
            action="deposit",
            quantity=1,
            price=5000,
            commission=0,
            currency="USD",
            amount=5000,
        )
    ]
    result = _subperiod_twr_interval_return(
        snapshots,
        txns,
        date(2026, 1, 1),
        date(2026, 1, 15),
        "USD",
        lambda _a, _b: 1.0,
    )
    assert result is not None
