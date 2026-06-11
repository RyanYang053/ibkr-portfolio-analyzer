from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.domain import Position


DEFAULT_THESES: dict[str, dict[str, Any]] = {
    "MSFT": {
        "symbol": "MSFT",
        "thesis": "Mega-cap quality compounder supported by durable software, cloud, and AI infrastructure demand.",
        "key_assumptions": ["Revenue growth remains positive", "Margins remain resilient", "Balance sheet remains strong"],
        "break_triggers": ["Sustained growth slowdown", "Margin compression", "Technical breakdown plus fundamentals deterioration"],
        "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
    },
    "IONQ": {
        "symbol": "IONQ",
        "thesis": "Speculative quantum position depends on commercialization progress, cash runway, and controlled dilution.",
        "key_assumptions": ["Cash runway remains adequate", "Commercial milestones continue", "Dilution risk stays manageable"],
        "break_triggers": ["Cash runway pressure", "Rising dilution risk", "Milestone delays"],
        "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
    },
}

import json
import os

THESES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "theses.json")

def _load_theses() -> dict[str, dict[str, Any]]:
    if os.path.exists(THESES_FILE):
        try:
            with open(THESES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_runtime_theses: dict[str, dict[str, Any]] = _load_theses()

def _save_theses() -> None:
    try:
        with open(THESES_FILE, "w", encoding="utf-8") as f:
            json.dump(_runtime_theses, f, indent=2)
    except Exception:
        pass


def get_thesis(symbol: str) -> dict[str, Any]:
    normalized = symbol.upper()
    return _runtime_theses.get(
        normalized,
        DEFAULT_THESES.get(
            normalized,
            {
                "symbol": normalized,
                "thesis": "No custom thesis stored yet. AI should treat this as a watchlist-style review.",
                "key_assumptions": ["Position data remains current", "Core risk rules remain acceptable"],
                "break_triggers": ["Missing critical data", "Thesis data unavailable"],
                "created_at": "2026-06-09T00:00:00Z",
                "updated_at": "2026-06-09T00:00:00Z",
            },
        ),
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


def evaluate_thesis(position: Position | None, score: Any, data_quality: dict[str, Any]) -> dict[str, Any]:
    symbol = position.symbol if position else "UNKNOWN"
    stored = get_thesis(symbol)
    missing_count = data_quality.get("missing_categories_count", 0)
    final_score = getattr(score, "final_score", None)

    if missing_count > 2:
        status = "unknown_due_to_missing_data"
        reason = "More than two major data categories are missing, so the stored thesis cannot be confirmed."
    elif final_score is not None and final_score < 45:
        status = "broken"
        reason = "The current score is below the thesis break threshold."
    elif position and position.is_speculative and position.portfolio_weight > 3:
        status = "weakened"
        reason = "Speculative exposure is above the default review range."
    else:
        status = "intact"
        reason = "Current structured data does not breach the stored thesis assumptions."

    return {
        "symbol": symbol,
        "stored_thesis": stored["thesis"],
        "key_assumptions": stored["key_assumptions"],
        "status": status,
        "status_reason": reason,
        "invalidation_triggers": stored["break_triggers"],
        "last_reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
