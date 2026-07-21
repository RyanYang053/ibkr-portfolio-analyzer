"""UTC timestamp helpers for point-in-time evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class UtcTimestamp:
    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise ValueError("UtcTimestamp requires timezone-aware datetime")
        object.__setattr__(self, "value", self.value.astimezone(timezone.utc))


@dataclass(frozen=True)
class EvidenceCutoff:
    """Latest instant evidence may be used for a decision evaluation."""

    as_of: datetime

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("EvidenceCutoff requires timezone-aware datetime")
        object.__setattr__(self, "as_of", self.as_of.astimezone(timezone.utc))

    def allows(self, available_at: datetime) -> bool:
        if available_at.tzinfo is None:
            raise ValueError("available_at must be timezone-aware")
        return available_at.astimezone(timezone.utc) <= self.as_of
