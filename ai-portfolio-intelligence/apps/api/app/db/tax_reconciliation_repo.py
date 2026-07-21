"""Tax reconciliation run persistence (state-store fallback when table missing)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.db.sql_dialect import json_cast
from app.db.state_store import get_state_store

_NAMESPACE = "tax_reconciliation_runs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save_tax_reconciliation_run(
    *,
    account_id: str,
    tax_year: int,
    status: str,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    rid = run_id or uuid4().hex
    created = _now()
    row = {
        "run_id": rid,
        "account_id": account_id,
        "tax_year": int(tax_year),
        "status": status,
        "payload_json": payload or {},
        "created_at": created.isoformat(),
    }
    try:
        from sqlalchemy import text

        from app.core.config import settings
        from app.db.session import SessionLocal

        if settings.persistence_backend in {"postgres", "sqlite"}:
            with SessionLocal() as session:
                session.execute(
                    text(
                        f"""
                        INSERT INTO tax_reconciliation_runs
                            (run_id, account_id, tax_year, status, payload_json, created_at)
                        VALUES
                            (:run_id, :account_id, :tax_year, :status, {json_cast("payload_json")}, :created_at)
                        """
                    ),
                    {
                        "run_id": rid,
                        "account_id": account_id,
                        "tax_year": int(tax_year),
                        "status": status,
                        # P0.3: serialize the dict before binding to raw SQL params.
                        "payload_json": json.dumps(payload or {}),
                        "created_at": created,
                    },
                )
                session.commit()
    except SQLAlchemyError:
        # Table may be absent (pure JSON mode). State store remains the projection.
        pass

    store = get_state_store()
    store.write_json(_NAMESPACE, rid, row)
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"run_ids": []}) or {}
    ids = list(index.get("run_ids") or [])
    if rid not in ids:
        ids.insert(0, rid)
    store.write_json(_NAMESPACE, f"index:{account_id}", {"run_ids": ids[:200]})
    store.write_json(_NAMESPACE, f"latest:{account_id}:{tax_year}", row)
    return row


def get_tax_reconciliation_run(run_id: str) -> dict[str, Any] | None:
    return get_state_store().read_json(_NAMESPACE, run_id, default=None)


def latest_tax_reconciliation_run(account_id: str, tax_year: int) -> dict[str, Any] | None:
    return get_state_store().read_json(_NAMESPACE, f"latest:{account_id}:{tax_year}", default=None)


def list_tax_reconciliation_runs(account_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"run_ids": []}) or {}
    out: list[dict[str, Any]] = []
    for rid in list(index.get("run_ids") or [])[:limit]:
        row = store.read_json(_NAMESPACE, str(rid), default=None)
        if row:
            out.append(row)
    return out
