"""Equity option Reg T style margin estimates (CBOE/FINRA published formulas)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.product_scope import MARGIN_DISCLAIMER

StrategyKind = Literal[
    "short_call_uncovered",
    "short_put_uncovered",
    "covered_call",
    "debit_spread",
    "credit_spread",
    "spread",
]


def _methodology_approved() -> bool:
    try:
        from app.db.methodology_repo import load_methodology_registry

        record = next(
            (
                item
                for item in load_methodology_registry()
                if item.methodology_id == "options_margin_regt"
            ),
            None,
        )
        return bool(record and record.approval_status in {"approved", "approved_for_personal_use"})
    except Exception:
        return False


@dataclass(frozen=True)
class RegTMarginEstimate:
    requirement: float
    strategy: str
    methodology_id: str = "options_margin_regt"
    broker_equivalent: bool = False
    order_generated: bool = False
    disclaimer: str = MARGIN_DISCLAIMER
    detail: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "strategy": self.strategy,
            "methodology_id": self.methodology_id,
            "broker_equivalent": self.broker_equivalent,
            "order_generated": False,
            "disclaimer": self.disclaimer,
            "detail": self.detail or {},
            "note": (
                "IBKR may use Portfolio Margin (TIMS), which can differ materially "
                "from these Reg T worksheet estimates."
            ),
        }


def uncovered_short_call_requirement(
    *,
    underlying_price: float,
    strike: float,
    shares: float,
    premium: float,
) -> float:
    """max(20%*underlying*shares - OTM, 10%*underlying*shares) + premium."""
    otm = max(0.0, strike - underlying_price) * shares
    base = max(0.20 * underlying_price * shares - otm, 0.10 * underlying_price * shares)
    return base + abs(premium)


def uncovered_short_put_requirement(
    *,
    underlying_price: float,
    strike: float,
    shares: float,
    premium: float,
) -> float:
    """max(20%*underlying*shares - OTM, 10%*strike*shares) + premium."""
    otm = max(0.0, underlying_price - strike) * shares
    base = max(0.20 * underlying_price * shares - otm, 0.10 * strike * shares)
    return base + abs(premium)


def covered_call_incremental_requirement(*, stock_loan_value_reduction: float = 0.0) -> float:
    """Covered call: no incremental equity requirement beyond the long stock."""
    return max(0.0, float(stock_loan_value_reduction))


def spread_max_loss_requirement(*, max_loss: float) -> float:
    return abs(float(max_loss))


def estimate_regt_margin(
    *,
    strategy: StrategyKind,
    underlying_price: float,
    strike: float,
    shares: float,
    premium: float = 0.0,
    max_loss: float | None = None,
    stock_loan_value_reduction: float = 0.0,
) -> RegTMarginEstimate:
    approved = _methodology_approved()
    if strategy == "short_call_uncovered":
        req = uncovered_short_call_requirement(
            underlying_price=underlying_price,
            strike=strike,
            shares=shares,
            premium=premium,
        )
    elif strategy == "short_put_uncovered":
        req = uncovered_short_put_requirement(
            underlying_price=underlying_price,
            strike=strike,
            shares=shares,
            premium=premium,
        )
    elif strategy == "covered_call":
        req = covered_call_incremental_requirement(
            stock_loan_value_reduction=stock_loan_value_reduction
        )
    else:
        req = spread_max_loss_requirement(max_loss=max_loss if max_loss is not None else 0.0)

    return RegTMarginEstimate(
        requirement=round(float(req), 4),
        strategy=strategy,
        broker_equivalent=approved,
        detail={
            "underlying_price": underlying_price,
            "strike": strike,
            "shares": shares,
            "premium": premium,
            "max_loss": max_loss,
            "methodology_status": "approved_for_personal_use" if approved else "experimental",
        },
    )
