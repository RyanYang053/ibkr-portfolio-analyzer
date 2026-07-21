"""Trade Plan persistence with versioning (plan §9 / §17).

SQL-backed for sqlite/postgres; JSON state store for the json test backend.
Every save appends an immutable version row for the audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.trade_plan import TradePlan

_NAMESPACE = "trade_plans"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def _plan_to_columns(plan: TradePlan) -> dict[str, Any]:
    return {
        "trade_plan_id": plan.trade_plan_id,
        "account_id": plan.account_id,
        "instrument_id": plan.instrument_id,
        "symbol": plan.symbol,
        "direction": plan.direction.value,
        "plan_type": plan.plan_type,
        "status": plan.status.value,
    }


def save_trade_plan(plan: TradePlan) -> TradePlan:
    now = _now()
    if plan.created_at is None:
        plan.created_at = now
    payload = plan.model_dump(mode="json")

    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        cols = _plan_to_columns(plan)
        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO trade_plans (
                        trade_plan_id, account_id, instrument_id, symbol, direction,
                        plan_type, status, payload_json, created_at, updated_at
                    ) VALUES (
                        :trade_plan_id, :account_id, :instrument_id, :symbol, :direction,
                        :plan_type, :status, {json_cast("payload_json")}, :created_at, :updated_at
                    )
                    ON CONFLICT(trade_plan_id) DO UPDATE SET
                        status = excluded.status,
                        symbol = excluded.symbol,
                        direction = excluded.direction,
                        plan_type = excluded.plan_type,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """
                ),
                {**cols, "payload_json": json.dumps(payload), "created_at": plan.created_at, "updated_at": now},
            )
            next_version = (
                session.execute(
                    text("SELECT COALESCE(MAX(version), 0) + 1 FROM trade_plan_versions WHERE trade_plan_id = :tid"),
                    {"tid": plan.trade_plan_id},
                ).scalar()
                or 1
            )
            session.execute(
                text(
                    f"""
                    INSERT INTO trade_plan_versions (trade_plan_id, version, status, payload_json, created_at)
                    VALUES (:tid, :version, :status, {json_cast("payload_json")}, :created_at)
                    """
                ),
                {
                    "tid": plan.trade_plan_id,
                    "version": int(next_version),
                    "status": plan.status.value,
                    "payload_json": json.dumps(payload),
                    "created_at": now,
                },
            )
            session.commit()
        return plan

    # json backend
    from app.db.state_store import get_state_store

    store = get_state_store()
    store.write_json(_NAMESPACE, plan.trade_plan_id, payload)
    index = store.read_json(_NAMESPACE, f"index:{plan.account_id}", default={"ids": []}) or {"ids": []}
    ids = list(index.get("ids") or [])
    if plan.trade_plan_id not in ids:
        ids.insert(0, plan.trade_plan_id)
        store.write_json(_NAMESPACE, f"index:{plan.account_id}", {"ids": ids})
    versions = store.read_json(_NAMESPACE, f"versions:{plan.trade_plan_id}", default={"versions": []}) or {}
    vlist = list(versions.get("versions") or [])
    vlist.append({"version": len(vlist) + 1, "status": plan.status.value, "created_at": now.isoformat()})
    store.write_json(_NAMESPACE, f"versions:{plan.trade_plan_id}", {"versions": vlist})
    return plan


def get_trade_plan(trade_plan_id: str) -> TradePlan | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM trade_plans WHERE trade_plan_id = :tid"),
                {"tid": trade_plan_id},
            ).scalar()
        if row is None:
            return None
        payload = row if isinstance(row, dict) else json.loads(row)
        return TradePlan.model_validate(payload)

    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NAMESPACE, trade_plan_id, default=None)
    return TradePlan.model_validate(payload) if payload else None


def list_trade_plans(account_id: str, *, status: str | None = None, limit: int = 200) -> list[TradePlan]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        clause = "WHERE account_id = :account_id"
        params: dict[str, Any] = {"account_id": account_id, "limit": limit}
        if status:
            clause += " AND status = :status"
            params["status"] = status
        with SessionLocal() as session:
            rows = session.execute(
                text(f"SELECT payload_json FROM trade_plans {clause} ORDER BY updated_at DESC LIMIT :limit"),
                params,
            ).scalars().all()
        out = []
        for row in rows:
            payload = row if isinstance(row, dict) else json.loads(row)
            out.append(TradePlan.model_validate(payload))
        return out

    from app.db.state_store import get_state_store

    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"ids": []}) or {"ids": []}
    out = []
    for tid in (index.get("ids") or [])[:limit]:
        payload = store.read_json(_NAMESPACE, str(tid), default=None)
        if not payload:
            continue
        plan = TradePlan.model_validate(payload)
        if status and plan.status.value != status:
            continue
        out.append(plan)
    return out
