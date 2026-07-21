"""Contract tests for read-only Decision OS invariants."""

from __future__ import annotations

from pathlib import Path

from app.core.product_contract import (
    AI_MAY_SET_DECISION_OUTCOME,
    FORBIDDEN_AUTHORITATIVE_ACTIONS,
    HUMAN_REVIEW_REQUIRED,
    MISSING_CRITICAL_DATA_FAILS_CLOSED,
    NO_TRADE_SCENARIO_REQUIRED,
    ORDER_GENERATED_DEFAULT,
    ORDER_SUBMISSION_ALLOWED,
)


def test_read_only_invariants() -> None:
    assert ORDER_SUBMISSION_ALLOWED is False
    assert ORDER_GENERATED_DEFAULT is False
    assert HUMAN_REVIEW_REQUIRED is True
    assert AI_MAY_SET_DECISION_OUTCOME is False
    assert MISSING_CRITICAL_DATA_FAILS_CLOSED is True
    assert NO_TRADE_SCENARIO_REQUIRED is True


def test_no_order_submission_surface_in_api_routes() -> None:
    api_root = Path(__file__).resolve().parents[2] / "app" / "api" / "routes"
    forbidden = ("place_order", "submit_order", "execute_trade", "order_submission")
    offenders: list[str] = []
    for path in api_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def test_forbidden_actions_documented() -> None:
    assert "Strong Add" in FORBIDDEN_AUTHORITATIVE_ACTIONS
    assert "Buy" in FORBIDDEN_AUTHORITATIVE_ACTIONS
    assert "Sell" in FORBIDDEN_AUTHORITATIVE_ACTIONS
