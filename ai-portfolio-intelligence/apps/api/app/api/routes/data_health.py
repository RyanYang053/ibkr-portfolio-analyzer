"""Data health and point-in-time validation API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.db.database_health import database_health
from app.services.broker.base import BrokerAdapter
from app.services.data_quality.data_health_center import build_data_health_report
from app.services.validation.decision_calibration import calibration_summary
from app.services.validation.point_in_time_guard import assert_point_in_time, filter_usable_evidence
from app.services.validation.walk_forward import (
    evaluate_historical_decision,
    summarize_walk_forward,
    walk_forward_splits,
)

router = APIRouter(
    prefix="/data-health",
    tags=["data-health"],
    dependencies=[Depends(get_current_principal)],
)


class PitCheckRequest(BaseModel):
    observed_at: str | None = None
    available_at: str | None = None
    as_of: str
    field_name: str = "value"


class EvidenceFilterRequest(BaseModel):
    as_of: str
    records: list[dict[str, Any]] = Field(default_factory=list)


class HistoricalDecisionRequest(BaseModel):
    as_of: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    methodology_version: str = "decision_center_holding/0.2.0"
    policy_version: str = "policy/default"
    outcome: str | None = None


@router.get("")
def data_health_overview(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    broker_status: dict[str, Any] = {"connected": False}
    schedule_runs: list[dict[str, Any]] = []
    try:
        accounts = adapter.get_accounts()
        broker_status = {"connected": bool(accounts), "account_count": len(accounts)}
        try:
            from app.api.routes.desktop_secrets import flex_token_status

            # Optional — may not exist outside desktop.
            status = flex_token_status()  # type: ignore[misc]
            if isinstance(status, dict):
                broker_status["flex_configured"] = bool(status.get("configured"))
        except Exception:
            broker_status["flex_configured"] = False
    except Exception as exc:
        broker_status = {"connected": False, "message": str(exc)}
    try:
        from app.services.ai.scheduled_analysis_service import list_recent_schedule_runs

        schedule_runs = list_recent_schedule_runs()
    except Exception:
        try:
            from app.api.routes.ai import _load_settings

            schedule = _load_settings()
            schedule_runs = list(schedule.get("runs") or [])
        except Exception:
            schedule_runs = []

    report = build_data_health_report(
        account_id=account_id,
        broker_status=broker_status if isinstance(broker_status, dict) else {"connected": False},
        schedule_runs=schedule_runs,
        methodology_summary={"overall_status": "experimental"},
    )
    report["database"] = database_health()
    report["calibration"] = calibration_summary()
    return report


@router.post("/point-in-time")
def point_in_time_check(body: PitCheckRequest) -> dict[str, Any]:
    return assert_point_in_time(
        observed_at=body.observed_at,
        available_at=body.available_at,
        as_of=body.as_of,
        field_name=body.field_name,
    )


@router.post("/evidence/filter")
def evidence_filter(body: EvidenceFilterRequest) -> dict[str, Any]:
    usable, rejected = filter_usable_evidence(body.records, as_of=body.as_of)
    return {
        "usable": usable,
        "rejected": rejected,
        "usable_count": len(usable),
        "rejected_count": len(rejected),
        "order_generated": False,
    }


@router.get("/walk-forward")
def walk_forward(dates: str | None = None) -> dict[str, Any]:
    date_list = [d.strip() for d in (dates or "").split(",") if d.strip()]
    if not date_list:
        # Prefer real snapshot dates when available; never invent a synthetic calendar.
        try:
            from app.db.state_store import get_state_store

            store = get_state_store()
            index = store.read_json("portfolio_snapshots", "dates", default={"dates": []}) or {}
            date_list = [str(d) for d in (index.get("dates") or []) if d]
        except Exception:
            date_list = []
    if len(date_list) < 80:
        return {
            "split_count": 0,
            "splits": [],
            "evaluation_count": 0,
            "status": "insufficient_history",
            "methodology_status": "experimental",
            "order_generated": False,
            "message": (
                "Provide >=80 as_of dates via ?dates= or persist portfolio snapshot dates. "
                "Synthetic walk-forward calendars are not generated."
            ),
            "metrics": {
                "decision_stability": None,
                "false_positive_review_rate": None,
                "no_trade_differential": None,
                "note": "Numeric calibration withheld until approved methodology fixtures exist.",
            },
        }
    splits = walk_forward_splits(date_list)
    return summarize_walk_forward(splits)


@router.post("/walk-forward/evaluate")
def walk_forward_evaluate(body: HistoricalDecisionRequest) -> dict[str, Any]:
    as_of = datetime.fromisoformat(body.as_of.replace("Z", "+00:00"))
    return evaluate_historical_decision(
        as_of=as_of,
        evidence=body.evidence,
        methodology_version=body.methodology_version,
        policy_version=body.policy_version,
        outcome=body.outcome,
    )


@router.post("/outcome-attribution")
def outcome_attribution(body: dict[str, Any]) -> dict[str, Any]:
    from app.services.validation.outcome_attribution import attribute_decision_outcome

    return attribute_decision_outcome(
        decision_id=str(body.get("decision_id") or "unknown"),
        instrument_key=str(body.get("instrument_key") or "unknown"),
        outcome=str(body.get("outcome") or "monitor"),
        as_of=str(body.get("as_of") or datetime.now(timezone.utc).isoformat()),
        forward_returns=body.get("forward_returns"),
        no_trade_baseline_returns=body.get("no_trade_baseline_returns"),
    )


@router.get("/database")
def data_health_database() -> dict[str, Any]:
    return database_health()
