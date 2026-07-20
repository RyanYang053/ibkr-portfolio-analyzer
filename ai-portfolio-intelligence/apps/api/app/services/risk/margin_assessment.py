"""Broker-reported margin monitoring plus internal stress estimates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from app.core.product_scope import MARGIN_DISCLAIMER


class MarginSource(StrEnum):
    BROKER_REPORTED = "broker_reported"
    INTERNAL_SCENARIO_ESTIMATE = "internal_scenario_estimate"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MarginAssessment:
    source: MarginSource
    broker_initial_margin: Decimal | None
    broker_maintenance_margin: Decimal | None
    broker_excess_liquidity: Decimal | None
    internal_stress_loss: Decimal | None
    observed_at: datetime
    account_id: str | None = None
    currency: str | None = None
    stale: bool = False
    broker_equivalent: bool = False
    disclaimer: str = MARGIN_DISCLAIMER

    def __post_init__(self) -> None:
        if self.broker_equivalent and self.source != MarginSource.BROKER_REPORTED:
            raise ValueError(
                "broker_equivalent may only be True for directly broker-reported values"
            )
        if self.source != MarginSource.BROKER_REPORTED and self.broker_equivalent:
            raise ValueError("internal estimates must set broker_equivalent=False")


def from_broker_summary(
    *,
    account_id: str,
    currency: str,
    initial_margin: Decimal | None,
    maintenance_margin: Decimal | None,
    excess_liquidity: Decimal | None,
    observed_at: datetime | None = None,
    stale: bool = False,
) -> MarginAssessment:
    return MarginAssessment(
        source=MarginSource.BROKER_REPORTED,
        broker_initial_margin=initial_margin,
        broker_maintenance_margin=maintenance_margin,
        broker_excess_liquidity=excess_liquidity,
        internal_stress_loss=None,
        observed_at=observed_at or datetime.now(timezone.utc),
        account_id=account_id,
        currency=currency,
        stale=stale,
        broker_equivalent=False,  # still labeled broker-reported, not independently verified
    )


def internal_stress_estimate(
    *,
    stress_loss: Decimal,
    observed_at: datetime | None = None,
) -> MarginAssessment:
    return MarginAssessment(
        source=MarginSource.INTERNAL_SCENARIO_ESTIMATE,
        broker_initial_margin=None,
        broker_maintenance_margin=None,
        broker_excess_liquidity=None,
        internal_stress_loss=stress_loss,
        observed_at=observed_at or datetime.now(timezone.utc),
        broker_equivalent=False,
    )
