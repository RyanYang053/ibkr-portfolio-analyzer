"""Implementation readiness for construction scenarios."""

from __future__ import annotations

from typing import Any

from app.core.product_contract import ImplementationStatus, ORDER_GENERATED_DEFAULT


def evaluate_implementation_readiness(
    *,
    blockers: list[str] | None = None,
    tax_ready: bool = False,
    liquidity_ready: bool = False,
    policy_ok: bool = True,
) -> dict[str, Any]:
    issues = list(blockers or [])
    if not tax_ready:
        issues.append("tax_lot_inputs_unavailable")
    if not liquidity_ready:
        issues.append("liquidity_not_confirmed")
    if not policy_ok:
        issues.append("policy_breach")

    status = (
        ImplementationStatus.REVIEW_READY
        if not issues
        else ImplementationStatus.BLOCKED
    )
    return {
        "implementation_status": status.value,
        "implementation_ready": status == ImplementationStatus.REVIEW_READY,
        "blockers": issues,
        "order_generated": ORDER_GENERATED_DEFAULT,
        "requires_user_confirmation": True,
    }
