"""Thin Qlib research adapter — disconnected from accounting / Decision Center."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class FeatureFrame:
    """Exported research features (returns/factors) — never ledger rows."""

    columns: Sequence[str]
    rows: Sequence[Mapping[str, Any]]
    as_of: str | None = None
    source: str = "exported_feature_frame"


@dataclass(frozen=True)
class ValidationReport:
    walk_forward_ok: bool
    cost_model_ok: bool
    liquidity_ok: bool
    notes: tuple[str, ...] = ()

    @property
    def ready_for_decision_center(self) -> bool:
        # Default disconnected: never auto-promote to Decision Center.
        return False


class ResearchModel(Protocol):
    def fit(self, frame: FeatureFrame) -> None: ...

    def predict(self, frame: FeatureFrame) -> Sequence[float]: ...


class DisconnectedQlibAdapter:
    """Stub adapter. Does not load Qlib; safe for default CI."""

    connected: bool = False

    def validate(self, frame: FeatureFrame) -> ValidationReport:
        _ = frame
        return ValidationReport(
            walk_forward_ok=False,
            cost_model_ok=False,
            liquidity_ok=False,
            notes=(
                "Qlib boundary is disconnected by default.",
                "Install/research environments may implement walk-forward validation separately.",
            ),
        )

    def score(self, frame: FeatureFrame) -> Sequence[float]:
        _ = frame
        raise RuntimeError("Qlib research adapter is disconnected from Decision Center")
