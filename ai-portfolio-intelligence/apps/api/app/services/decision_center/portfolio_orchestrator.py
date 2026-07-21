"""Portfolio-level Decision Packet orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.product_contract import DecisionOutcome
from app.schemas.portfolio_decision_packet import PortfolioDecisionPacket
from app.services.decision_center.packet_digest import packet_digest
from app.services.portfolio_construction.scenario_service import build_construction_scenarios


def _conflict_rows(holding_packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adds = [p for p in holding_packets if p.get("outcome") == DecisionOutcome.REVIEW_ADD.value]
    trims = [
        p
        for p in holding_packets
        if p.get("outcome") in {DecisionOutcome.REVIEW_TRIM.value, DecisionOutcome.REVIEW_EXIT.value}
    ]
    conflicts: list[dict[str, Any]] = []
    if adds and trims:
        conflicts.append(
            {
                "type": "add_vs_trim_capacity",
                "message": "Review-add candidates compete with trim/exit reviews for capital capacity.",
                "add_decision_ids": [p.get("decision_id") for p in adds],
                "trim_decision_ids": [p.get("decision_id") for p in trims],
            }
        )
    return conflicts


def build_portfolio_decision_packet(
    *,
    account_id: str,
    holding_packets: list[dict[str, Any]],
    current_weights: dict[str, float] | None = None,
    cash_percent: float | None = None,
    as_of: datetime | None = None,
) -> PortfolioDecisionPacket:
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    urgent = [
        str(p.get("decision_id"))
        for p in holding_packets
        if p.get("priority") in {"urgent", "this_week", "critical", "high"}
        or p.get("outcome")
        in {
            DecisionOutcome.DATA_INSUFFICIENT.value,
            DecisionOutcome.REVIEW_EXIT.value,
            DecisionOutcome.REVIEW_TRIM.value,
        }
    ]
    weights = current_weights or {
        str(p.get("symbol")): float(
            (p.get("position") or {}).get("portfolio_weight")
            or (p.get("portfolio_fit") or {}).get("weight")
            or 0
        )
        for p in holding_packets
        if p.get("symbol")
    }
    construction = build_construction_scenarios(
        account_id=account_id,
        current_weights=weights,
        cash_percent=cash_percent,
    )
    policy_breaches = [r.get("code") for r in construction.get("policy_repairs") or []]
    packet = PortfolioDecisionPacket(
        portfolio_decision_id=f"pdec_{uuid4().hex}",
        account_scope=[account_id],
        as_of=now,
        holding_decision_ids=[str(p.get("decision_id")) for p in holding_packets if p.get("decision_id")],
        urgent_decisions=urgent,
        capital_budget=None,
        tax_budget=None,
        risk_budget_status={"status": "provisional"},
        policy_breaches=[str(c) for c in policy_breaches if c],
        goal_feasibility={"status": "provisional"},
        decision_conflicts=_conflict_rows(holding_packets),
        construction_scenario_ids=[
            str(s.get("scenario_id")) for s in construction.get("scenarios") or [] if s.get("scenario_id")
        ],
        no_trade_scenario_id=construction.get("no_trade_scenario_id"),
        matrix_rows=[
            {
                "decision_id": p.get("decision_id"),
                "symbol": p.get("symbol"),
                "outcome": p.get("outcome"),
                "priority": p.get("priority"),
                "blockers": p.get("blockers") or [],
            }
            for p in holding_packets
        ],
        order_generated=False,
        requires_user_confirmation=True,
    )
    digest_payload = packet.model_dump(mode="json")
    packet.packet_sha256 = packet_digest(digest_payload)
    return packet
