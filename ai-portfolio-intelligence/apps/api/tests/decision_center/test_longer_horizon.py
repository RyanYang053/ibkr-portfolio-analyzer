"""Longer-horizon Decision OS coverage: research, construction, attribution, planning."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.portfolio_construction.replacement_universe import build_replacement_universe
from app.services.research.catalyst_calendar import build_catalyst_calendar
from app.services.validation.outcome_attribution import attribute_decision_outcome
from app.services.validation.walk_forward import walk_forward_splits


def test_catalyst_calendar_uses_option_expiry() -> None:
    today = date.today()
    events = build_catalyst_calendar(
        symbols=["AAPL"],
        as_of=today,
        option_positions=[{"symbol": "AAPL", "expiry": (today + timedelta(days=21)).isoformat()}],
    )
    assert any(e["catalyst_type"] == "option_expiry" for e in events)
    assert all(e.get("source") != "stub_calendar" for e in events)


def test_replacement_universe_does_not_invent_tickers() -> None:
    universe = build_replacement_universe(
        plan={"policy": {"prohibited_symbols": ["XYZ"], "constraints": {"core_etf": "VOO"}}},
        watchlist_symbols=["VOO", "AAPL", "XYZ"],
        held_symbols=["AAPL"],
    )
    assert universe["core_etf"] == "VOO"
    assert "AAPL" not in universe["buy_candidates"]
    assert "XYZ" not in universe["buy_candidates"]
    assert "MSFT" not in universe["buy_candidates"]


def test_outcome_attribution_keeps_confidence_withheld() -> None:
    result = attribute_decision_outcome(
        decision_id="dec_1",
        instrument_key="AAPL:1",
        outcome="monitor",
        as_of="2024-01-01T00:00:00+00:00",
        forward_returns={30: 0.02},
        no_trade_baseline_returns={30: 0.01},
    )
    assert result["confidence_status"] == "withheld"
    assert result["windows"][0]["differential_vs_no_trade"] == 0.01
    assert result["order_generated"] is False


def test_walk_forward_splits_require_enough_dates() -> None:
    dates = [f"2024-01-{i:02d}" for i in range(1, 29)]
    assert walk_forward_splits(dates, train_size=60, test_size=20) == []
