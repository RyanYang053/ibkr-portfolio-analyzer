"""Research candidate repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.db.state_store import get_state_store

_NAMESPACE = "research_candidates"


class ResearchCandidateRepository:
    def save_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        payload = dict(candidate)
        candidate_id = str(payload.get("candidate_id") or f"cand_{uuid4().hex[:10]}")
        payload["candidate_id"] = candidate_id
        payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        store = get_state_store()
        account_id = str(payload.get("account_id") or "default")
        store.write_json(_NAMESPACE, candidate_id, payload)
        instrument_key = str(payload.get("instrument_key") or payload.get("symbol") or candidate_id)
        store.write_json(_NAMESPACE, f"latest:{account_id}:{instrument_key}", payload)
        index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"ids": []}) or {}
        ids = list(index.get("ids") or [])
        if candidate_id not in ids:
            ids.insert(0, candidate_id)
        store.write_json(_NAMESPACE, f"index:{account_id}", {"ids": ids[:500]})

        if settings.persistence_backend in {"postgres", "sqlite"}:
            try:
                self._save_db(payload)
            except Exception:
                pass
        return payload

    def latest_snapshot(self, account_id: str, instrument_key: str) -> dict[str, Any] | None:
        store = get_state_store()
        return store.read_json(_NAMESPACE, f"latest:{account_id}:{instrument_key}", default=None)

    def list_for_account(self, account_id: str, limit: int = 100) -> list[dict[str, Any]]:
        store = get_state_store()
        index = store.read_json(_NAMESPACE, f"index:{account_id}", default={}) or {}
        out: list[dict[str, Any]] = []
        for candidate_id in list(index.get("ids") or [])[:limit]:
            row = store.read_json(_NAMESPACE, str(candidate_id), default=None)
            if row:
                out.append(row)
        return out

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        return get_state_store().read_json(_NAMESPACE, candidate_id, default=None)

    def _save_db(self, payload: dict[str, Any]) -> None:
        import json

        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO research_candidates (
                        candidate_id, account_id, instrument_key, symbol, priority,
                        score, payload_json, updated_at
                    ) VALUES (
                        :candidate_id, :account_id, :instrument_key, :symbol, :priority,
                        :score, :payload_json, :updated_at
                    )
                    ON CONFLICT (candidate_id) DO UPDATE SET
                        priority = EXCLUDED.priority,
                        score = EXCLUDED.score,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "candidate_id": payload["candidate_id"],
                    "account_id": payload.get("account_id"),
                    "instrument_key": payload.get("instrument_key"),
                    "symbol": payload.get("symbol"),
                    "priority": payload.get("priority"),
                    "score": payload.get("score"),
                    "payload_json": json.dumps(payload),
                    "updated_at": payload.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                },
            )
            session.commit()
