"""Decision Center orchestrator — single authority for holding outcomes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.product_contract import (
    OUTCOME_TO_ACTION_LABEL,
    DecisionOutcome,
    ImplementationStatus,
)
from app.core.product_scope import DECISION_DISCLAIMER
from app.db.decision_packet_repo import DecisionPacketRepository
from app.schemas.decision_context import DecisionContext, EvaluationMode
from app.schemas.decision_gate import GateResult
from app.schemas.decision_packet import HoldingDecisionPacket
from app.services.decision_center.evidence_registry import EvidenceRegistry
from app.services.decision_center.gates import default_gates
from app.services.decision_center.outcome_precedence import resolve_outcome
from app.services.decision_center.outcome_stability import stabilize_outcome
from app.services.decision_center.packet_digest import packet_digest
from app.services.decision_center.scenario_engine import build_decision_scenarios


def _priority(outcome: DecisionOutcome, blockers: list[str]) -> str:
    if outcome == DecisionOutcome.DATA_INSUFFICIENT or "source_integrity_failed" in blockers:
        return "urgent"
    if outcome in {DecisionOutcome.REVIEW_EXIT, DecisionOutcome.REVIEW_TRIM}:
        return "this_week"
    return "routine"


def _implementation_status(gates: list[GateResult], scenarios: list) -> ImplementationStatus:
    impl = next((g for g in gates if g.gate_id == "implementation"), None)
    if impl and not impl.passed:
        return ImplementationStatus.BLOCKED
    change_scenarios = [s for s in scenarios if s.scenario_type != "no_trade"]
    if not change_scenarios:
        return ImplementationStatus.NOT_APPLICABLE
    if any(s.implementation_ready for s in change_scenarios):
        return ImplementationStatus.REVIEW_READY
    return ImplementationStatus.BLOCKED


class DecisionOrchestrator:
    def __init__(
        self,
        gates: list | None = None,
        evidence_registry: EvidenceRegistry | None = None,
        packet_repo: DecisionPacketRepository | None = None,
    ) -> None:
        self._gates = gates or default_gates()
        self._evidence_registry = evidence_registry or EvidenceRegistry()
        self._packet_repo = packet_repo or DecisionPacketRepository()

    def evaluate(self, context: DecisionContext) -> HoldingDecisionPacket:
        evidence = self._evidence_registry.resolve_context_evidence(context)
        # Point-in-time fail-closed: drop future/unavailable evidence before gates.
        try:
            from app.services.validation.point_in_time_guard import filter_usable_evidence

            evidence_payloads = [
                e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                for e in evidence
            ]
            usable, rejected = filter_usable_evidence(evidence_payloads, as_of=context.as_of)
            if rejected:
                context.source_integrity_ok = False
                # Keep only usable evidence refs when timestamps are present.
                usable_ids = {row.get("evidence_id") for row in usable}
                evidence = [e for e in evidence if getattr(e, "evidence_id", None) in usable_ids]
                # P0.4 / §15.4: the fail-open recovery below (restore evidence, reset
                # source integrity) is ONLY permitted in live provisional mode, where
                # evidence is often synthesized without an available_at. In historical
                # replay this MUST fail closed — never recover, so the source-integrity
                # gate fails terminally and the outcome becomes DATA_INSUFFICIENT.
                live_mode = context.evaluation_mode == EvaluationMode.LIVE_PROVISIONAL
                if not evidence and evidence_payloads and live_mode:
                    missing_only = all(
                        r.get("reason") == "missing_available_at" for r in rejected
                    )
                    if missing_only:
                        evidence = self._evidence_registry.resolve_context_evidence(context)
                        context.source_integrity_ok = True
        except Exception:
            pass

        gate_results: list[GateResult] = []
        for gate in sorted(self._gates, key=lambda g: g.order):
            result = gate.evaluate(context)
            gate_results.append(result)
            if result.terminal and not result.passed:
                break

        candidate = resolve_outcome(gate_results, context)
        previous_packet = self._packet_repo.latest_for_instrument(
            context.account_id,
            context.instrument_key,
        )
        previous_outcome = None
        if previous_packet is not None:
            previous_outcome = previous_packet.outcome
        elif context.previous_outcome:
            try:
                previous_outcome = DecisionOutcome(context.previous_outcome)
            except ValueError:
                previous_outcome = None

        hard_breach = candidate in {
            DecisionOutcome.DATA_INSUFFICIENT,
            DecisionOutcome.REVIEW_EXIT,
            DecisionOutcome.REVIEW_TRIM,
        } or context.hard_risk_breach or context.hard_policy_breach

        outcome = stabilize_outcome(
            candidate=candidate,
            previous=previous_outcome,
            material_change=candidate != previous_outcome,
            hard_breach=hard_breach,
            confirmation_count=1 if hard_breach else 0,
        )

        scenarios = build_decision_scenarios(context, outcome, gate_results)
        blockers = []
        for gate in gate_results:
            if not gate.passed:
                blockers.extend(gate.blockers or [gate.gate_id])

        as_of = context.as_of
        next_review = (as_of + timedelta(days=30)).date()
        action = OUTCOME_TO_ACTION_LABEL[outcome]
        packet = HoldingDecisionPacket(
            decision_id=f"dec_{uuid4().hex}",
            account_id=context.account_id,
            instrument_key=context.instrument_key,
            symbol=context.symbol,
            as_of=as_of,
            evidence_cutoff=context.evidence_cutoff,
            outcome=outcome,
            candidate_outcome=candidate,
            previous_outcome=previous_outcome,
            outcome_changed=previous_outcome is not None and previous_outcome != outcome,
            change_reason_codes=(
                [f"outcome:{previous_outcome.value}->{outcome.value}"]
                if previous_outcome and previous_outcome != outcome
                else []
            ),
            priority=_priority(outcome, blockers),
            confidence_status="provisional",
            implementation_status=_implementation_status(gate_results, scenarios),
            gates=gate_results,
            evidence=evidence,
            scenarios=scenarios,
            blockers=blockers,
            review_triggers=[{"type": "scheduled", "next_review_date": str(next_review)}],
            next_review_date=next_review,
            calculation_run_ids=list(context.calculation_run_ids),
            methodology_versions=dict(context.methodology_versions)
            or {"decision_center_holding": "0.2.0"},
            action=action,
            valuation_status=context.valuation_status,
            lens_ensemble=context.lens_ensemble or {},
            methodology_id="decision_center_holding",
            methodology_status="experimental",
            disclaimer=DECISION_DISCLAIMER,
            requires_user_confirmation=True,
            order_generated=False,
        )
        digest_payload = packet.model_dump(mode="json")
        packet.packet_sha256 = packet_digest(digest_payload)
        self._packet_repo.save(packet)
        try:
            from app.services.decision_center.outcome_tracker import record_outcome_transition
            from app.services.decision_center.review_scheduler import upsert_review_schedule

            previous_value = previous_outcome.value if previous_outcome else None
            if previous_value != outcome.value:
                record_outcome_transition(
                    account_id=context.account_id,
                    instrument_key=context.instrument_key,
                    decision_id=packet.decision_id,
                    previous_outcome=previous_value,
                    outcome=outcome.value,
                    change_reason_codes=list(packet.change_reason_codes or []),
                )
            upsert_review_schedule(
                account_id=context.account_id,
                instrument_key=context.instrument_key,
                decision_id=packet.decision_id,
                review_due_at=str(next_review),
            )
        except Exception:
            pass
        return packet


def evaluate_account_decisions(*, adapter, account_id: str) -> dict[str, Any]:
    """Evaluate Decision Packets for all equity holdings in an account."""
    from app.services.decision_center.holding_decision import evaluate_holding_decision
    from app.services.decision_center.holding_evidence import build_decision_context_for_position
    from app.services.decision_center.thesis_service import get_thesis

    summary = adapter.get_account_summary(account_id)
    positions = adapter.get_positions(account_id)
    packets: list[dict[str, Any]] = []
    for position in positions:
        if getattr(position, "asset_class", None) in {"OPT", "FOP", "CASH"}:
            continue
        instrument_key = (
            f"{position.symbol}:{position.con_id}" if position.con_id else position.symbol
        )
        thesis = get_thesis(account_id, instrument_key) or {}
        context = build_decision_context_for_position(
            position,
            account_id=account_id,
            thesis=thesis,
        )
        packets.append(evaluate_holding_decision(context))
    return {
        "account_id": account_id,
        "net_liquidation": float(getattr(summary, "net_liquidation", 0) or 0),
        "packet_count": len(packets),
        "decision_ids": [p.get("decision_id") for p in packets if p.get("decision_id")],
        "order_generated": False,
        "status": "evaluated",
    }


def context_from_holding_dict(
    *,
    account_id: str,
    holding: dict[str, Any],
    as_of: datetime | None = None,
) -> DecisionContext:
    """Adapt legacy holding context payloads into DecisionContext."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    instrument_key = holding.get("instrument_key") or holding.get("symbol") or "UNKNOWN"
    symbol = holding.get("symbol") or str(instrument_key).split(":")[0]
    position = holding.get("position") or {
        "portfolio_weight": holding.get("portfolio_weight") or holding.get("weight"),
        "weight": holding.get("weight") or holding.get("portfolio_weight"),
    }
    fit = holding.get("portfolio_fit") or {}
    weight = float(
        fit.get("weight")
        or fit.get("weight_percent")
        or position.get("portfolio_weight")
        or position.get("weight")
        or 0
    )
    position = {
        **position,
        "portfolio_weight": weight,
        "weight": weight,
    }
    data_quality = holding.get("data_quality") or {"status": "ok", "missing": []}
    thesis = holding.get("thesis") or {}
    risk = holding.get("risk_metrics") or holding.get("risk") or {}
    if "over_concentrated" not in fit:
        max_single = float(
            (holding.get("policy") or {}).get("max_single_position_pct")
            or (holding.get("portfolio_fit") or {}).get("max_single_position_pct")
            or 12.0
        )
        fit = {**fit, "over_concentrated": weight > max_single, "weight": weight, "max_single_position_pct": max_single}
    else:
        fit = {**fit, "weight": weight}
    valuation_status = holding.get("valuation_status") or "withheld"
    lens = holding.get("lens_ensemble") or {}
    labels = list(lens.get("synthesis_labels") or [])
    return DecisionContext(
        account_id=account_id,
        instrument_key=str(instrument_key),
        symbol=str(symbol),
        as_of=now,
        evidence_cutoff=now,
        position=position,
        data_quality=data_quality,
        thesis=thesis,
        thesis_status=str(thesis.get("status") or holding.get("thesis_status") or "unknown"),
        risk=risk,
        portfolio_fit=fit,
        valuation_status=str(valuation_status),
        valuation=holding.get("valuation") or {},
        tax=holding.get("tax") or holding.get("tax_flags") or {},
        liquidity=holding.get("liquidity") or {},
        fundamentals=holding.get("fundamentals") or {},
        lens_ensemble=lens,
        policy=holding.get("policy") or {},
        financial_plan=holding.get("financial_plan") or {},
        hard_risk_breach=bool(holding.get("hard_risk_breach")),
        hard_policy_breach=bool(holding.get("hard_policy_breach")),
        add_capacity_available=not bool(fit.get("over_concentrated")),
        supportive_quality_evidence="quality_supportive" in labels,
        methodology_versions=holding.get("methodology_versions")
        or {
            "decision_center_holding": "experimental",
        },
        calculation_run_ids=list(holding.get("calculation_run_ids") or []),
        source_integrity_ok=holding.get("source_integrity_ok", True),
    )
