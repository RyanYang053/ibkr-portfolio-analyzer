"""Screener persistence (plan §8.2 / §17)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.screener import ScreenDefinition, ScreenResult, ScreenRun

_NS = "screener"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def _load(row: Any) -> dict:
    return row if isinstance(row, dict) else json.loads(row)


def save_definition(defn: ScreenDefinition, account_id: str) -> ScreenDefinition:
    now = _now()
    if defn.created_at is None:
        defn.created_at = now
    defn.updated_at = now
    payload = defn.model_dump(mode="json")
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO screen_definitions (screen_id, account_id, name, payload_json, created_at, updated_at)
                    VALUES (:sid, :account_id, :name, {json_cast("payload_json")}, :created_at, :updated_at)
                    ON CONFLICT(screen_id) DO UPDATE SET
                        name = excluded.name, payload_json = excluded.payload_json, updated_at = excluded.updated_at
                    """
                ),
                {"sid": defn.screen_id, "account_id": account_id, "name": defn.name,
                 "payload_json": json.dumps(payload), "created_at": defn.created_at, "updated_at": now},
            )
            session.commit()
        return defn
    from app.db.state_store import get_state_store

    store = get_state_store()
    store.write_json(_NS, f"def:{defn.screen_id}", payload)
    idx = store.read_json(_NS, f"defindex:{account_id}", default={"ids": []}) or {"ids": []}
    ids = list(idx.get("ids") or [])
    if defn.screen_id not in ids:
        ids.insert(0, defn.screen_id)
        store.write_json(_NS, f"defindex:{account_id}", {"ids": ids})
    return defn


def get_definition(screen_id: str) -> ScreenDefinition | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM screen_definitions WHERE screen_id = :sid"), {"sid": screen_id}
            ).scalar()
        return ScreenDefinition.model_validate(_load(row)) if row is not None else None
    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NS, f"def:{screen_id}", default=None)
    return ScreenDefinition.model_validate(payload) if payload else None


def list_definitions(account_id: str) -> list[ScreenDefinition]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text("SELECT payload_json FROM screen_definitions WHERE account_id = :a ORDER BY updated_at DESC"),
                {"a": account_id},
            ).scalars().all()
        return [ScreenDefinition.model_validate(_load(r)) for r in rows]
    from app.db.state_store import get_state_store

    store = get_state_store()
    idx = store.read_json(_NS, f"defindex:{account_id}", default={"ids": []}) or {"ids": []}
    out = []
    for sid in idx.get("ids") or []:
        payload = store.read_json(_NS, f"def:{sid}", default=None)
        if payload:
            out.append(ScreenDefinition.model_validate(payload))
    return out


def save_run(run: ScreenRun) -> ScreenRun:
    now = _now()
    if run.as_of is None:
        run.as_of = now
    payload = run.model_dump(mode="json")
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO screen_runs (run_id, screen_id, account_id, payload_json, created_at)
                    VALUES (:rid, :sid, :account_id, {json_cast("payload_json")}, :created_at)
                    ON CONFLICT(run_id) DO UPDATE SET payload_json = excluded.payload_json
                    """
                ),
                {"rid": run.run_id, "sid": run.screen_id, "account_id": run.account_id,
                 "payload_json": json.dumps(payload), "created_at": now},
            )
            for result in run.results:
                session.execute(
                    text(
                        f"""
                        INSERT INTO screen_results (result_id, run_id, symbol, instrument_id, payload_json)
                        VALUES (:result_id, :run_id, :symbol, :instrument_id, {json_cast("payload_json")})
                        ON CONFLICT(result_id) DO UPDATE SET payload_json = excluded.payload_json
                        """
                    ),
                    {"result_id": result.result_id, "run_id": run.run_id, "symbol": result.symbol,
                     "instrument_id": result.instrument_id, "payload_json": json.dumps(result.model_dump(mode="json"))},
                )
            session.commit()
        return run
    from app.db.state_store import get_state_store

    store = get_state_store()
    store.write_json(_NS, f"run:{run.run_id}", payload)
    for result in run.results:
        store.write_json(_NS, f"result:{result.result_id}", {"run_id": run.run_id, "result": result.model_dump(mode="json")})
    return run


def get_run(run_id: str) -> ScreenRun | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM screen_runs WHERE run_id = :rid"), {"rid": run_id}
            ).scalar()
        return ScreenRun.model_validate(_load(row)) if row is not None else None
    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NS, f"run:{run_id}", default=None)
    return ScreenRun.model_validate(payload) if payload else None


def get_result(result_id: str) -> ScreenResult | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM screen_results WHERE result_id = :rid"), {"rid": result_id}
            ).scalar()
        return ScreenResult.model_validate(_load(row)) if row is not None else None
    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NS, f"result:{result_id}", default=None)
    return ScreenResult.model_validate(payload["result"]) if payload else None
