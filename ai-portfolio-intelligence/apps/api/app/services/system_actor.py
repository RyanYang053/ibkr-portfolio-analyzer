from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemActor:
    actor_id: str
    purpose: str


SCHEDULER_ACTOR = SystemActor(
    actor_id="scheduler-service",
    purpose="scheduled_portfolio_analysis",
)
