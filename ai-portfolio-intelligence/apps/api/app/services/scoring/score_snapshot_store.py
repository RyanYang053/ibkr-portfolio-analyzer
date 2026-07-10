from __future__ import annotations

from datetime import date

from app.db.state_store import get_state_store
from app.schemas.domain import StockScore


def _snapshot_key(user_id: str, symbol: str, business_date: str) -> str:
    return f"{user_id}:{symbol.upper()}:{business_date}"


def save_daily_score_snapshot(user_id: str, score: StockScore) -> None:
    business_date = score.data_timestamp.date().isoformat()
    store = get_state_store()
    store.write_json(
        "score_snapshots",
        _snapshot_key(user_id, score.symbol, business_date),
        {
            "symbol": score.symbol,
            "business_date": business_date,
            "final_score": score.final_score,
            "interpretation": score.interpretation,
            "sub_scores": score.sub_scores,
            "confidence": score.confidence,
            "missing_data": score.missing_data,
            "immutable": True,
        },
    )


def get_daily_score_snapshot(user_id: str, symbol: str, business_date: date | None = None) -> dict | None:
    active_date = (business_date or date.today()).isoformat()
    store = get_state_store()
    payload = store.read_json("score_snapshots", _snapshot_key(user_id, symbol, active_date))
    return payload if isinstance(payload, dict) else None
