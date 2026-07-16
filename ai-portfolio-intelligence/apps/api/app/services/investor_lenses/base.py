from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class LensComponent:
    name: str
    value: float | None
    evidence_refs: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class LensResult:
    lens_id: str
    version: str
    status: str  # available | provisional | withheld
    score: float | None
    components: tuple[LensComponent, ...] = ()
    exclusions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    methodology_id: str = ""
    inputs_used: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "version": self.version,
            "status": self.status,
            "score": self.score,
            "components": [
                {
                    "name": c.name,
                    "value": c.value,
                    "evidence_refs": list(c.evidence_refs),
                    "note": c.note,
                }
                for c in self.components
            ],
            "exclusions": list(self.exclusions),
            "evidence_refs": list(self.evidence_refs),
            "methodology_id": self.methodology_id or self.lens_id,
            "inputs_used": list(self.inputs_used),
        }


@dataclass(frozen=True)
class LensInputs:
    """Deterministic inputs only — never LLM-derived scores."""

    symbol: str
    fundamentals: Mapping[str, Any] = field(default_factory=dict)
    risk_metrics: Mapping[str, Any] = field(default_factory=dict)
    factor_exposures: Mapping[str, Any] = field(default_factory=dict)
    liquidity: Mapping[str, Any] = field(default_factory=dict)
    tax_flags: Mapping[str, Any] = field(default_factory=dict)
    position: Mapping[str, Any] = field(default_factory=dict)


def _num(payload: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed == parsed:  # not NaN
            return parsed
    return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _mean_available(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


LensFn = Callable[[LensInputs], LensResult]
