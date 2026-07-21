"""Onboarding state-machine API (plan §21).

Persists setup progress in SQLite (not localStorage) and exposes readiness scores.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.db.onboarding_repo import get_stages, upsert_stage
from app.schemas.onboarding import (
    ONBOARDING_STAGES,
    READINESS_GROUPS,
    OnboardingStage,
    OnboardingStageUpdate,
    StageStatus,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"], dependencies=[Depends(get_current_principal)])


def _owner(principal: Principal) -> str:
    return str(getattr(principal, "user_id", None) or "local-owner")


def _all_stages(owner_id: str) -> list[OnboardingStage]:
    stored = get_stages(owner_id)
    return [stored.get(name, OnboardingStage(stage=name)) for name in ONBOARDING_STAGES]


def _readiness(stages: list[OnboardingStage]) -> dict[str, object]:
    status_by_stage = {s.stage: s.status for s in stages}

    def score(names: tuple[str, ...]) -> float:
        if not names:
            return 0.0
        complete = sum(1 for n in names if status_by_stage.get(n) == StageStatus.COMPLETE)
        return round(complete / len(names), 3)

    scores = {group: score(names) for group, names in READINESS_GROUPS.items()}
    overall_complete = sum(1 for s in stages if s.status == StageStatus.COMPLETE)
    scores["overall"] = round(overall_complete / len(ONBOARDING_STAGES), 3)
    return scores


@router.get("/state")
def onboarding_state(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    stages = _all_stages(_owner(principal))
    return {
        "stages": [s.model_dump(mode="json") for s in stages],
        "readiness": _readiness(stages),
        "complete": all(s.status == StageStatus.COMPLETE for s in stages),
        "persistence": "sqlite",
    }


@router.get("/readiness")
def onboarding_readiness(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {"readiness": _readiness(_all_stages(_owner(principal)))}


@router.put("/stages/{stage}")
def update_stage(
    stage: str,
    body: OnboardingStageUpdate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    if stage not in ONBOARDING_STAGES:
        raise HTTPException(status_code=404, detail=f"Unknown onboarding stage: {stage}")
    now = datetime.now(timezone.utc)
    stored = get_stages(_owner(principal)).get(stage, OnboardingStage(stage=stage, detected_at=now))
    stored.status = body.status
    if body.validation_status is not None:
        stored.validation_status = body.validation_status
    if body.blockers is not None:
        stored.blockers = body.blockers
    if body.user_acknowledged is not None:
        stored.user_acknowledged = body.user_acknowledged
    if body.status == StageStatus.COMPLETE and stored.completed_at is None:
        stored.completed_at = now
    upsert_stage(_owner(principal), stored)
    return stored.model_dump(mode="json")
