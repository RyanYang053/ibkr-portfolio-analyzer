"""Imported-execution match persistence (plan §9.4 / §17)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.execution_match import ExecutionMatch

_NS = "execution_matches"


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def save_execution_match(match: ExecutionMatch) -> ExecutionMatch:
    now = datetime.now(timezone.utc)
    if match.created_at is None:
        match.created_at = now
    payload = match.model_dump(mode="json")
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO execution_matches (match_id, trade_plan_id, account_id, instrument_id, matched, payload_json, created_at)
                    VALUES (:mid, :tid, :account_id, :instrument_id, :matched, {json_cast("payload_json")}, :created_at)
                    ON CONFLICT(match_id) DO UPDATE SET payload_json = excluded.payload_json, matched = excluded.matched
                    """
                ),
                {"mid": match.match_id, "tid": match.trade_plan_id, "account_id": match.account_id,
                 "instrument_id": match.instrument_id, "matched": match.matched,
                 "payload_json": json.dumps(payload), "created_at": match.created_at},
            )
            session.commit()
        return match
    from app.db.state_store import get_state_store

    store = get_state_store()
    store.write_json(_NS, match.match_id, payload)
    idx = store.read_json(_NS, f"plan:{match.trade_plan_id}", default={"ids": []}) or {"ids": []}
    ids = list(idx.get("ids") or [])
    if match.match_id not in ids:
        ids.insert(0, match.match_id)
        store.write_json(_NS, f"plan:{match.trade_plan_id}", {"ids": ids})
    return match


def list_matches_for_plan(trade_plan_id: str) -> list[ExecutionMatch]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text("SELECT payload_json FROM execution_matches WHERE trade_plan_id = :tid ORDER BY created_at DESC"),
                {"tid": trade_plan_id},
            ).scalars().all()
        return [ExecutionMatch.model_validate(r if isinstance(r, dict) else json.loads(r)) for r in rows]
    from app.db.state_store import get_state_store

    store = get_state_store()
    idx = store.read_json(_NS, f"plan:{trade_plan_id}", default={"ids": []}) or {"ids": []}
    out = []
    for mid in idx.get("ids") or []:
        payload = store.read_json(_NS, str(mid), default=None)
        if payload:
            out.append(ExecutionMatch.model_validate(payload))
    return out
