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


def test_benchmark_weights_withheld_outside_mock():
    assert benchmark_sector_weights_as_of(date.today(), allow_mock=False) is None
