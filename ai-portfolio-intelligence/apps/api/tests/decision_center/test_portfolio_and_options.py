"""Portfolio packet and options expiry tests."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.decision_center.portfolio_orchestrator import build_portfolio_decision_packet
from app.services.options.expiry_calendar import build_options_expiry_calendar


def test_portfolio_packet_includes_no_trade_and_conflicts() -> None:
    packet = build_portfolio_decision_packet(
        account_id="A1",
        holding_packets=[
            {
                "decision_id": "dec_add",
                "symbol": "AAA",
                "outcome": "review_add",
                "priority": "routine",
                "blockers": [],
            },
            {
                "decision_id": "dec_trim",
                "symbol": "BBB",
                "outcome": "review_trim",
                "priority": "this_week",
                "blockers": ["over_concentrated"],
            },
        ],
        current_weights={"AAA": 5.0, "BBB": 15.0, "CASH": 10.0},
        cash_percent=10.0,
    )
    assert packet.order_generated is False
    assert packet.no_trade_scenario_id
    assert packet.urgent_decisions
    assert any(c.get("type") == "add_vs_trim_capacity" for c in packet.decision_conflicts)


def test_options_expiry_calendar_fail_closed() -> None:
    today = date.today()
    calendar = build_options_expiry_calendar(
        [
            {
                "symbol": "AAPL  250117C00150000",
                "asset_class": "OPT",
                "expiry": (today + timedelta(days=5)).strftime("%Y%m%d"),
            },
            {"symbol": "MSFT", "asset_class": "STK"},
        ]
    )
    assert calendar["count"] == 1
    assert calendar["events"][0]["priority"] == "urgent"
    assert calendar["events"][0]["american_exercise"] == "available_crr"
    assert calendar["order_generated"] is False
