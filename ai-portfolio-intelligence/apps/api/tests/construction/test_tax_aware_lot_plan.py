"""Tax-aware construction uses lot preferences when lots exist."""

from __future__ import annotations

from datetime import date


def test_tax_aware_includes_lot_plan_when_lots_exist(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")

    from app.db.tax_lot_snapshot_repo import replace_tax_lot_snapshots
    from app.services.portfolio_construction.scenario_service import build_construction_scenarios

    replace_tax_lot_snapshots(
        account_id="ACC-1",
        as_of_date=date.today(),
        lots=[
            {
                "symbol": "AAPL",
                "con_id": 1,
                "quantity": 10,
                "cost_basis_per_share": 150.0,
                "acquired_date": "2020-01-01",
                "currency": "USD",
                "jurisdiction": "US",
                "lot_method": "fifo",
                "source": "test",
                "payload": {},
            },
            {
                "symbol": "AAPL",
                "con_id": 1,
                "quantity": 5,
                "cost_basis_per_share": 200.0,
                "acquired_date": "2021-01-01",
                "currency": "USD",
                "jurisdiction": "US",
                "lot_method": "fifo",
                "source": "test",
                "payload": {},
            },
        ],
    )

    result = build_construction_scenarios(
        account_id="ACC-1",
        current_weights={"AAPL": 40.0, "MSFT": 50.0, "CASH": 10.0},
        target_weights={"AAPL": 10.0, "MSFT": 50.0, "CASH": 40.0},
    )
    tax = next(s for s in result["scenarios"] if s["scenario_type"] == "tax_aware")
    assert tax["order_generated"] is False
    assert tax["orders"] == []
    assert "tax_lot_inputs_required" not in tax["blockers"]
    plan = tax["tax_lot_plan"]
    assert plan["method"] == "hifo_preference"
    assert plan["lot_preferences"]
    # Higher cost basis preferred first
    assert plan["lot_preferences"][0]["cost_basis_per_share"] == 200.0
