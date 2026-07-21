"""Financial plan repository — JSON-backed with optional SQL tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.state_store import get_state_store
from app.schemas.financial_plan import FinancialPlan

_NAMESPACE = "financial_plans"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FinancialPlanRepository:
    def save(self, plan: FinancialPlan) -> FinancialPlan:
        payload = plan.model_dump(mode="json")
        if settings.persistence_backend in {"postgres", "sqlite"}:
            try:
                self._save_db(payload)
            except Exception:
                pass
        store = get_state_store()
        store.write_json(_NAMESPACE, plan.plan_id, payload)
        store.write_json(_NAMESPACE, "latest", {"plan_id": plan.plan_id})
        return plan

    def get(self, plan_id: str = "default") -> FinancialPlan | None:
        if settings.persistence_backend in {"postgres", "sqlite"}:
            try:
                row = self._get_db(plan_id)
                if row:
                    return FinancialPlan.model_validate(row)
            except Exception:
                pass
        store = get_state_store()
        payload = store.read_json(_NAMESPACE, plan_id, default=None)
        if not payload:
            return None
        return FinancialPlan.model_validate(payload)

    def latest(self) -> FinancialPlan | None:
        store = get_state_store()
        latest = store.read_json(_NAMESPACE, "latest", default=None)
        if latest and latest.get("plan_id"):
            return self.get(str(latest["plan_id"]))
        return self.get("default")

    def _save_db(self, payload: dict[str, Any]) -> None:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO financial_plans (
                        plan_id, owner_label, base_currency, planning_horizon_years,
                        payload_json, created_at, updated_at
                    ) VALUES (
                        :plan_id, :owner_label, :base_currency, :planning_horizon_years,
                        :payload_json, :created_at, :updated_at
                    )
                    ON CONFLICT (plan_id) DO UPDATE SET
                        owner_label = EXCLUDED.owner_label,
                        base_currency = EXCLUDED.base_currency,
                        planning_horizon_years = EXCLUDED.planning_horizon_years,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "plan_id": payload["plan_id"],
                    "owner_label": payload.get("owner_label"),
                    "base_currency": payload.get("base_currency"),
                    "planning_horizon_years": payload.get("planning_horizon_years"),
                    "payload_json": json.dumps(payload),
                    "created_at": payload.get("created_at") or _now().isoformat(),
                    "updated_at": payload.get("updated_at") or _now().isoformat(),
                },
            )
            session.commit()

    def _get_db(self, plan_id: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM financial_plans WHERE plan_id = :plan_id"),
                {"plan_id": plan_id},
            ).mappings().first()
        if not row:
            return None
        payload = row["payload_json"]
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload) if payload else None
