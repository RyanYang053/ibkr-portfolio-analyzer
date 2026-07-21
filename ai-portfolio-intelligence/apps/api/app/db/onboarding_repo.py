"""Onboarding state persistence (plan §21 / §17)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.onboarding import OnboardingStage

_NS = "onboarding_stages"


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def _load(row) -> dict:
    return row if isinstance(row, dict) else json.loads(row)


def upsert_stage(owner_id: str, stage: OnboardingStage) -> OnboardingStage:
    now = datetime.now(timezone.utc)
    payload = stage.model_dump(mode="json")
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO onboarding_stages (owner_id, stage, status, payload_json, updated_at)
                    VALUES (:owner_id, :stage, :status, {json_cast("payload_json")}, :updated_at)
                    ON CONFLICT(owner_id, stage) DO UPDATE SET
                        status = excluded.status, payload_json = excluded.payload_json, updated_at = excluded.updated_at
                    """
                ),
                {"owner_id": owner_id, "stage": stage.stage, "status": stage.status.value,
                 "payload_json": json.dumps(payload), "updated_at": now},
            )
            session.commit()
        return stage
    from app.db.state_store import get_state_store

    get_state_store().write_json(_NS, f"{owner_id}:{stage.stage}", payload)
    return stage


def get_stages(owner_id: str) -> dict[str, OnboardingStage]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text("SELECT payload_json FROM onboarding_stages WHERE owner_id = :o"), {"o": owner_id}
            ).scalars().all()
        out = {}
        for r in rows:
            stage = OnboardingStage.model_validate(_load(r))
            out[stage.stage] = stage
        return out
    from app.db.state_store import get_state_store

    store = get_state_store()
    out: dict[str, OnboardingStage] = {}
    from app.schemas.onboarding import ONBOARDING_STAGES

    for name in ONBOARDING_STAGES:
        payload = store.read_json(_NS, f"{owner_id}:{name}", default=None)
        if payload:
            out[name] = OnboardingStage.model_validate(payload)
    return out
