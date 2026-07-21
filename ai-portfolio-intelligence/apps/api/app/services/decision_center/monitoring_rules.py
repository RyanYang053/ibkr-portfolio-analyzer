from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import decision_monitoring_repo


def list_monitoring_rules(account_id: str) -> list[dict[str, Any]]:
    return decision_monitoring_repo.list_rules(account_id)


def create_monitoring_rule(
    account_id: str,
    *,
    instrument_key: str | None,
    rule_type: str,
    threshold: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return decision_monitoring_repo.create_rule(
        account_id,
        instrument_key=instrument_key,
        rule_type=rule_type,
        threshold=threshold,
        note=note,
    )


def evaluate_monitoring_rules(
    account_id: str,
    *,
    holdings: list[dict[str, Any]],
    risk_metrics: dict[str, Any] | None = None,
    theses: dict[str, dict[str, Any]] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate stored rules against current holdings/risk/thesis state.

    Returns alerts only — does not place trades or send external notifications yet.
    """
    now = as_of or datetime.now(timezone.utc)
    rules = list_monitoring_rules(account_id)
    risk = dict(risk_metrics or {})
    thesis_by_key = {str(key).upper(): value for key, value in dict(theses or {}).items()}
    holdings_by_key: dict[str, dict[str, Any]] = {}
    for item in holdings:
        key = str(item.get("instrument_key") or item.get("symbol") or "").upper()
        if key:
            holdings_by_key[key] = item

    evaluations: list[dict[str, Any]] = []
    for rule in rules:
        if not rule.get("active", True):
            continue
        rule_type = str(rule.get("rule_type") or "").lower()
        threshold = rule.get("threshold")
        instrument_key = rule.get("instrument_key")
        triggered = False
        detail: dict[str, Any] = {}

        if rule_type in {"drawdown", "max_drawdown"}:
            raw = risk.get("max_drawdown_decimal", risk.get("max_drawdown"))
            if raw is None or threshold is None:
                detail = {"status": "insufficient_inputs"}
            else:
                value = float(raw)
                if abs(value) > 1.0:
                    value = value / 100.0
                triggered = abs(value) >= float(threshold)
                detail = {"max_drawdown_decimal": value, "threshold": float(threshold)}

        elif rule_type in {"concentration", "weight"}:
            if instrument_key is None:
                detail = {"status": "instrument_required"}
            else:
                holding = holdings_by_key.get(str(instrument_key).upper())
                if holding is None or threshold is None:
                    detail = {
                        "status": "insufficient_inputs",
                        "available_keys": sorted(holdings_by_key),
                    }
                else:
                    weight = float(holding.get("portfolio_weight") or holding.get("weight") or 0.0)
                    triggered = weight >= float(threshold)
                    detail = {"weight_percent": weight, "threshold": float(threshold)}

        elif rule_type in {"thesis_stale", "thesis_age_days"}:
            if instrument_key is None:
                detail = {"status": "instrument_required"}
            else:
                thesis = thesis_by_key.get(str(instrument_key).upper())
                if thesis is None or threshold is None:
                    detail = {"status": "insufficient_inputs"}
                else:
                    updated = thesis.get("updated_at")
                    age_days = None
                    if isinstance(updated, str):
                        try:
                            parsed = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                            age_days = (now - parsed).total_seconds() / 86400.0
                        except ValueError:
                            age_days = None
                    if age_days is None:
                        detail = {"status": "insufficient_inputs"}
                    else:
                        triggered = age_days >= float(threshold)
                        detail = {"age_days": round(age_days, 2), "threshold": float(threshold)}
        else:
            detail = {"status": "unsupported_rule_type", "rule_type": rule_type}

        evaluations.append(
            {
                "rule_id": rule.get("rule_id"),
                "rule_type": rule_type,
                "instrument_key": instrument_key,
                "threshold": threshold,
                "detail": detail,
                "triggered": bool(triggered),
                "evaluation_status": detail.get("status", "ok"),
            }
        )

    return {
        "account_id": account_id,
        "evaluated_at": now.isoformat(),
        "rules_evaluated": len(rules),
        "alerts": [item for item in evaluations if item.get("triggered")],
        "evaluations": evaluations,
        "alert_delivery": "desktop_inbox",
        "methodology_status": "experimental",
        "note": (
            "Rule evaluation is local/deterministic. Desktop inbox / notification outbox "
            "delivery is implemented; external email/push channels are not configured by default."
        ),
    }
