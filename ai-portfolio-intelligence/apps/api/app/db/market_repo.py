"""Market intelligence persistence (plan §7 / §17).

SQL-backed for sqlite/postgres; JSON state store for the json test backend.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.market import EconomicEvent, MarketRegime, MarketSnapshot

_NAMESPACE = "market_intelligence"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def save_market_regime(regime: MarketRegime) -> MarketRegime:
    now = _now()
    payload = regime.model_dump(mode="json")
    regime_id = f"reg_{uuid4().hex[:16]}"
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO market_regimes (regime_id, as_of, label, confidence, payload_json, created_at)
                    VALUES (:rid, :as_of, :label, :confidence, {json_cast("payload_json")}, :created_at)
                    """
                ),
                {
                    "rid": regime_id,
                    "as_of": regime.as_of or now,
                    "label": regime.label.value,
                    "confidence": regime.confidence,
                    "payload_json": json.dumps(payload),
                    "created_at": now,
                },
            )
            session.commit()
        return regime

    from app.db.state_store import get_state_store

    store = get_state_store()
    store.write_json(_NAMESPACE, "latest_regime", payload)
    return regime


def latest_market_regime() -> MarketRegime | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM market_regimes ORDER BY as_of DESC LIMIT 1")
            ).scalar()
        if row is None:
            return None
        payload = row if isinstance(row, dict) else json.loads(row)
        return MarketRegime.model_validate(payload)

    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NAMESPACE, "latest_regime", default=None)
    return MarketRegime.model_validate(payload) if payload else None


def save_market_snapshot(snapshot: MarketSnapshot) -> MarketSnapshot:
    now = _now()
    payload = snapshot.model_dump(mode="json")
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO market_snapshots (snapshot_id, as_of, payload_json, created_at)
                    VALUES (:sid, :as_of, {json_cast("payload_json")}, :created_at)
                    """
                ),
                {
                    "sid": f"snap_{uuid4().hex[:16]}",
                    "as_of": snapshot.as_of or now,
                    "payload_json": json.dumps(payload),
                    "created_at": now,
                },
            )
            session.commit()
        return snapshot

    from app.db.state_store import get_state_store

    get_state_store().write_json(_NAMESPACE, "latest_snapshot", payload)
    return snapshot


def list_economic_events(*, limit: int = 100) -> list[EconomicEvent]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text("SELECT payload_json FROM economic_events ORDER BY event_time ASC LIMIT :limit"),
                {"limit": limit},
            ).scalars().all()
        out = []
        for row in rows:
            payload = row if isinstance(row, dict) else json.loads(row)
            out.append(EconomicEvent.model_validate(payload))
        return out

    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NAMESPACE, "economic_events", default={"events": []}) or {}
    return [EconomicEvent.model_validate(e) for e in payload.get("events", [])]
