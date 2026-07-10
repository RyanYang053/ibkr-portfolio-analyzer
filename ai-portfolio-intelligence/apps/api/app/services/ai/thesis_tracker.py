from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.domain import Position


import json
import os

THESES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "theses.json")

def _load_theses() -> dict[str, dict[str, Any]]:
    from app.db.legacy_bridge import read_json_with_legacy

    data = read_json_with_legacy("investment_theses", "all", THESES_FILE if os.path.exists(THESES_FILE) else None, default={})
    return data if isinstance(data, dict) else {}


_runtime_theses: dict[str, dict[str, Any]] = _load_theses()

def _save_theses() -> None:
    from app.db.legacy_bridge import write_json_state

    write_json_state("investment_theses", "all", _runtime_theses)
    try:
        with open(THESES_FILE, "w", encoding="utf-8") as f:
            json.dump(_runtime_theses, f, indent=2)
    except Exception:
        pass


def get_thesis(symbol: str) -> dict[str, Any]:
    normalized = symbol.upper()
    return _runtime_theses.get(
        normalized,
        {
            "symbol": normalized,
            "thesis": "No custom thesis stored.",
            "key_assumptions": [],
            "break_triggers": [],
            "created_at": None,
            "updated_at": None,
        },
    )


def update_thesis(symbol: str, thesis: str, key_assumptions: list[str], break_triggers: list[str]) -> dict[str, Any]:
    normalized = symbol.upper()
    now = datetime.now(timezone.utc).isoformat()
    existing = get_thesis(normalized)
    updated = {
        "symbol": normalized,
        "thesis": thesis,
        "key_assumptions": key_assumptions,
        "break_triggers": break_triggers,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    _runtime_theses[normalized] = updated
    _save_theses()
    return updated


def evaluate_thesis(
    position: Position | None,
    score: Any,
    data_quality: dict[str, Any],
    current_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = position.symbol if position else "UNKNOWN"
    stored = get_thesis(symbol)
    missing_count = data_quality.get("missing_categories_count", 0)
    current_data = current_data or {}
    assumption_checks = [
        _evaluate_statement(statement, current_data)
        for statement in stored.get("key_assumptions", [])
    ]
    trigger_checks = [
        _evaluate_statement(statement, current_data, is_break_trigger=True)
        for statement in stored.get("break_triggers", [])
    ]
    custom_thesis_stored = bool(stored.get("updated_at"))
    triggered_break_conditions = [
        check["statement"] for check in trigger_checks if check["status"] == "breached"
    ]

    if not custom_thesis_stored:
        status = "weakened"
        reason = "No custom investment thesis has been stored for this holding."
    elif triggered_break_conditions:
        status = "broken"
        reason = "One or more stored thesis invalidation triggers are supported by current structured data."
    elif (
        missing_count > 0
        or any(check["status"] != "supported" for check in assumption_checks)
        or any(check["status"] == "not_evaluable" for check in trigger_checks)
    ):
        status = "weakened"
        reason = "The stored thesis cannot be fully confirmed because required assumptions or break triggers lack verified evidence."
    elif position and position.is_speculative and position.portfolio_weight > 3:
        status = "weakened"
        reason = "Speculative exposure is above the default review range."
    else:
        status = "intact"
        reason = "Current structured data does not breach the stored thesis assumptions."

    return {
        "symbol": symbol,
        "stored_thesis": stored["thesis"],
        "custom_thesis_stored": custom_thesis_stored,
        "key_assumptions": stored["key_assumptions"],
        "status": status,
        "status_reason": reason,
        "invalidation_triggers": stored["break_triggers"],
        "assumption_checks": assumption_checks,
        "trigger_checks": trigger_checks,
        "triggered_break_conditions": triggered_break_conditions,
        "last_reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def _evaluate_statement(
    statement: str,
    current_data: dict[str, Any],
    *,
    is_break_trigger: bool = False,
) -> dict[str, str]:
    normalized = statement.lower()
    fundamentals = _as_dict(current_data.get("fundamentals"))
    technicals = _as_dict(current_data.get("technicals"))

    status = "not_evaluable"
    evidence = "No structured field is mapped to this statement."

    if "growth" in normalized or "revenue" in normalized:
        value = fundamentals.get("revenue_growth_yoy")
        if value is not None:
            breached = value <= 0
            status = "breached" if breached == is_break_trigger else "supported"
            evidence = f"revenue_growth_yoy={value}"
    elif "margin" in normalized:
        value = fundamentals.get("operating_margin")
        if value is not None:
            breached = value < 0
            status = "breached" if breached == is_break_trigger else "supported"
            evidence = f"operating_margin={value}"
    elif "cash runway" in normalized or "balance sheet" in normalized:
        cash = fundamentals.get("cash")
        debt = fundamentals.get("total_debt")
        if cash is not None and debt is not None:
            breached = cash <= debt
            status = "breached" if breached == is_break_trigger else "supported"
            evidence = f"cash={cash}; total_debt={debt}"
    elif "technical" in normalized or "breakdown" in normalized:
        trend = str(technicals.get("trend_classification", "")).lower()
        if trend:
            breached = trend in {"downtrend", "breakdown", "weakening"}
            status = "breached" if breached == is_break_trigger else "supported"
            evidence = f"trend_classification={trend}"

    return {"statement": statement, "status": status, "evidence": evidence}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}
