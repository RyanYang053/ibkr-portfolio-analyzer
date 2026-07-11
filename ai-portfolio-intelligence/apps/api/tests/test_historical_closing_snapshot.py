from __future__ import annotations

from datetime import date

import pytest

from app.services.portfolio.pnl_decomposition import calculate_pnl_decomposition
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, PositionPnL


def test_decomposition_uses_snapshots_not_live_positions(monkeypatch):
    history = [
        PortfolioPnLSnapshot(
            date="2026-01-01",
            timestamp="2026-01-01T00:00:00+00:00",
            net_liquidation=100_000,
            cash=10_000,
            buying_power=50_000,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
        ),
        PortfolioPnLSnapshot(
            date="2026-01-31",
            timestamp="2026-01-31T00:00:00+00:00",
            net_liquidation=105_000,
            cash=10_000,
            buying_power=50_000,
            margin_requirement=0,
            daily_pnl=5000,
            daily_pnl_percent=5,
            positions=[],
        ),
    ]

    def _fail_require(*_args, **_kwargs):
        raise ValueError("designated EOD snapshot missing")

    monkeypatch.setattr(
        "app.db.portfolio_snapshot_repo.require_complete_snapshot",
        _fail_require,
    )
    monkeypatch.setattr(
        "app.services.portfolio.pnl_decomposition.load_ledger_coverage",
        lambda _account: type("C", (), {"status": "complete", "source": "test", "period_start": date(2025, 1, 1), "period_end": date(2026, 12, 31)})(),
    )
    monkeypatch.setattr(
        "app.services.portfolio.pnl_decomposition.ledger_covers_period",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "app.services.portfolio.pnl_decomposition.get_transactions",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.db.portfolio_snapshot_repo.list_snapshot_ids_for_business_dates",
        lambda *_args, **_kwargs: [],
    )

    monkeypatch.setattr(
        "app.services.portfolio.pnl_decomposition.create_calculation_run",
        lambda **_kwargs: type("R", (), {"calculation_run_id": "test-run"})(),
    )
    monkeypatch.setattr(
        "app.services.portfolio.pnl_decomposition.run_metadata_dict",
        lambda _run: {},
    )
    monkeypatch.setattr(
        "app.db.portfolio_snapshot_repo.link_calculation_run_snapshots",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.db.portfolio_snapshot_repo.link_calculation_run_transaction_batches",
        lambda *_args, **_kwargs: None,
    )

    result = calculate_pnl_decomposition(
        "TEST",
        history,
        [],
        "USD",
        lambda *_args, **_kwargs: 1.0,
    )
    assert result.reconciliation_status in {
        "withheld_missing_opening_snapshot",
        "withheld_missing_closing_snapshot",
        "withheld_incomplete_ledger",
    }
    assert result.reconciliation_gap is None
