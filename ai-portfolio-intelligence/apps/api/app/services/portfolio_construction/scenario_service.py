"""Unified portfolio construction scenarios — always includes no-trade baseline."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.core.product_contract import ORDER_GENERATED_DEFAULT
from app.db.financial_plan_repo import FinancialPlanRepository
from app.services.portfolio_construction.implementation_readiness import (
    evaluate_implementation_readiness,
)
from app.services.portfolio_construction.no_trade_baseline import (
    assert_no_orders,
    build_no_trade_baseline,
)
from app.services.portfolio_construction.policy_repair import suggest_policy_repairs


def _scenario(
    *,
    scenario_type: str,
    account_id: str,
    proposed_weights: dict[str, float],
    current_weights: dict[str, float],
    no_trade_id: str,
    blockers: list[str],
    tax_ready: bool = False,
    liquidity_ready: bool = False,
    policy_ok: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    turnover = 0.5 * sum(
        abs(float(proposed_weights.get(k, 0)) - float(current_weights.get(k, 0)))
        for k in set(proposed_weights) | set(current_weights)
    )
    readiness = evaluate_implementation_readiness(
        blockers=blockers,
        tax_ready=tax_ready,
        liquidity_ready=liquidity_ready,
        policy_ok=policy_ok,
    )
    payload = {
        "scenario_id": f"{scenario_type}_{uuid4().hex[:10]}",
        "scenario_type": scenario_type,
        "account_id": account_id,
        "proposed_weights": dict(proposed_weights),
        "turnover": round(turnover, 6),
        "expected_tax": None if not tax_ready else 0.0,
        "expected_transaction_cost": None if not liquidity_ready else 0.0,
        "compared_to_no_trade": {
            "turnover": round(turnover, 6),
            "weight_deltas": {
                k: round(float(proposed_weights.get(k, 0)) - float(current_weights.get(k, 0)), 6)
                for k in set(proposed_weights) | set(current_weights)
                if abs(float(proposed_weights.get(k, 0)) - float(current_weights.get(k, 0))) > 1e-9
            },
            "no_trade_scenario_id": no_trade_id,
        },
        **readiness,
        "order_generated": ORDER_GENERATED_DEFAULT,
        "orders": [],
    }
    if extra:
        payload.update(extra)
    return assert_no_orders(payload)


def _clip_weights(weights: dict[str, float], max_single: float) -> dict[str, float]:
    clipped = {k: min(float(v), max_single) for k, v in weights.items()}
    total = sum(clipped.values()) or 1.0
    return {k: round(v / total * 100.0, 6) for k, v in clipped.items()}


def _min_turnover_weights(
    current: dict[str, float],
    target: dict[str, float] | None,
    max_single: float,
) -> dict[str, float]:
    if not target:
        return _clip_weights(current, max_single)
    blended = {
        k: 0.7 * float(current.get(k, 0)) + 0.3 * float(target.get(k, 0))
        for k in set(current) | set(target)
    }
    return _clip_weights(blended, max_single)


def _max_risk_reduction_weights(current: dict[str, float], max_single: float) -> dict[str, float]:
    # Shrink largest names toward equal-weight among existing names.
    names = list(current.keys()) or ["CASH"]
    equal = 100.0 / len(names)
    shrunk = {
        k: 0.5 * float(current.get(k, 0)) + 0.5 * equal
        for k in names
    }
    return _clip_weights(shrunk, max_single)


def _cash_deployment_weights(
    current: dict[str, float],
    *,
    cash_percent: float,
    min_cash: float,
    core_symbol: str | None,
) -> dict[str, float]:
    deployable = max(0.0, cash_percent - min_cash)
    if deployable <= 0 or not core_symbol:
        return dict(current)
    updated = dict(current)
    updated[core_symbol] = float(updated.get(core_symbol, 0)) + deployable
    updated["CASH"] = min_cash
    total = sum(updated.values()) or 1.0
    return {k: round(v / total * 100.0, 6) for k, v in updated.items()}


def _tax_lot_readiness(account_id: str, symbols: list[str]) -> tuple[bool, dict[str, Any]]:
    try:
        from datetime import date

        from app.db.tax_lot_snapshot_repo import list_tax_lot_snapshots

        lots = list_tax_lot_snapshots(account_id, as_of_date=date.today())
    except Exception:
        return False, {"lot_count": 0, "symbols_with_lots": []}
    wanted = {s.upper() for s in symbols if s.upper() != "CASH"}
    matched = [lot for lot in lots if str(lot.get("symbol") or "").upper() in wanted]
    symbols_with_lots = sorted({str(lot.get("symbol") or "").upper() for lot in matched})
    return (
        len(matched) > 0,
        {
            "lot_count": len(matched),
            "symbols_with_lots": symbols_with_lots,
            "coverage_ratio": (len(symbols_with_lots) / len(wanted)) if wanted else 0.0,
        },
    )


def _tax_aware_lot_plan(
    *,
    account_id: str,
    current_weights: dict[str, float],
    proposed_weights: dict[str, float],
) -> dict[str, Any]:
    """Prefer tax-aware lot selection for reductions; never emits order tickets."""
    try:
        from datetime import date

        from app.db.tax_lot_snapshot_repo import list_tax_lot_snapshots
        from app.services.tax.lot_optimizer import optimize_tax_aware_sales

        lots = list_tax_lot_snapshots(account_id, as_of_date=date.today())
    except Exception:
        return {
            "method": "unavailable",
            "lot_preferences": [],
            "provisional_expected_tax": None,
            "methodology_status": "experimental",
            "order_generated": False,
        }

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for lot in lots:
        symbol = str(lot.get("symbol") or "").upper()
        if not symbol:
            continue
        by_symbol.setdefault(symbol, []).append(lot)

    positions = [
        {"symbol": symbol, "lots": symbol_lots, "mark_price": None}
        for symbol, symbol_lots in by_symbol.items()
    ]
    plan = optimize_tax_aware_sales(
        positions,
        proposed_weights,
        current_weights=current_weights,
        method="hifo",
    )
    preferences = [
        {
            "symbol": pick["symbol"],
            "weight_reduction_percent": round(
                abs(
                    float(proposed_weights.get(pick["symbol"], 0))
                    - float(current_weights.get(pick["symbol"], 0))
                ),
                6,
            ),
            "quantity": pick["quantity"],
            "cost_basis_per_share": pick["cost_basis_per_share"],
            "acquired_date": pick.get("acquired_date"),
            "lot_method": pick.get("method") or "hifo",
            "preference_reason": "tax_aware_lot_optimizer",
            "estimated_gain_loss": pick.get("estimated_gain_loss"),
        }
        for pick in plan.get("lot_picks") or []
    ]
    return {
        "method": "hifo_preference" if preferences else "no_reductions",
        "lot_preferences": preferences[:40],
        "lot_picks": plan.get("lot_picks") or [],
        "reduction_symbols": sorted(
            {
                s.upper()
                for s in set(current_weights) | set(proposed_weights)
                if s.upper() != "CASH"
                and float(proposed_weights.get(s, 0)) - float(current_weights.get(s, 0)) < -1e-9
            }
        ),
        "provisional_expected_tax": plan.get("provisional_expected_tax"),
        "methodology_status": "approved_for_personal_use",
        "order_generated": False,
        "orders": [],
        "note": "Lot preferences are informational; no sell orders are generated.",
    }


def build_construction_scenarios(
    *,
    account_id: str,
    current_weights: dict[str, float],
    sector_weights: dict[str, float] | None = None,
    target_weights: dict[str, float] | None = None,
    cash_percent: float | None = None,
    core_etf: str | None = None,
) -> dict[str, Any]:
    plan = FinancialPlanRepository().latest()
    policy = plan.policy if plan else None
    max_single = float(getattr(policy, "max_single_position_pct", None) or 12.0) if policy else 12.0
    min_cash = float(getattr(policy, "min_cash_pct", None) or 10.0) if policy else 10.0
    cash = float(cash_percent if cash_percent is not None else current_weights.get("CASH", 0.0))

    repairs = suggest_policy_repairs(
        policy=policy,
        current_weights=current_weights,
        sector_weights=sector_weights,
    )
    high_blockers = [r["code"] for r in repairs if r.get("severity") == "high"]
    medium_blockers = [r["code"] for r in repairs if r.get("severity") in {"high", "medium"}]

    baseline = assert_no_orders(
        build_no_trade_baseline(current_weights=current_weights, account_id=account_id)
    )
    scenarios: list[dict[str, Any]] = [baseline]

    # Policy repair — minimum changes to fix breaches
    repaired = _clip_weights(current_weights, max_single)
    scenarios.append(
        _scenario(
            scenario_type="policy_repair",
            account_id=account_id,
            proposed_weights=repaired,
            current_weights=current_weights,
            no_trade_id=baseline["scenario_id"],
            blockers=medium_blockers,
            policy_ok=not high_blockers,
            extra={"policy_repairs_applied": repairs},
        )
    )

    # Minimum turnover toward optional targets
    scenarios.append(
        _scenario(
            scenario_type="minimum_turnover",
            account_id=account_id,
            proposed_weights=_min_turnover_weights(current_weights, target_weights, max_single),
            current_weights=current_weights,
            no_trade_id=baseline["scenario_id"],
            blockers=medium_blockers,
            policy_ok=not high_blockers,
        )
    )

    # Maximum risk reduction within caps
    scenarios.append(
        _scenario(
            scenario_type="maximum_risk_reduction",
            account_id=account_id,
            proposed_weights=_max_risk_reduction_weights(current_weights, max_single),
            current_weights=current_weights,
            no_trade_id=baseline["scenario_id"],
            blockers=medium_blockers,
            policy_ok=not high_blockers,
        )
    )

    # Tax-aware — lot inventory unlocks readiness; HIFO preference when reducing
    tax_ready, tax_meta = _tax_lot_readiness(account_id, list(current_weights.keys()))
    tax_proposed = _min_turnover_weights(current_weights, target_weights, max_single)
    tax_lot_plan = (
        _tax_aware_lot_plan(
            account_id=account_id,
            current_weights=current_weights,
            proposed_weights=tax_proposed,
        )
        if tax_ready
        else {
            "method": "withheld",
            "lot_preferences": [],
            "provisional_expected_tax": None,
            "methodology_status": "experimental",
        }
    )
    tax_blockers = list(medium_blockers)
    if not tax_ready:
        tax_blockers.append("tax_lot_inputs_required")
    scenarios.append(
        _scenario(
            scenario_type="tax_aware",
            account_id=account_id,
            proposed_weights=tax_proposed,
            current_weights=current_weights,
            no_trade_id=baseline["scenario_id"],
            blockers=tax_blockers,
            tax_ready=tax_ready,
            policy_ok=not high_blockers,
            extra={
                "note": (
                    "Tax-aware scenario uses lot_optimizer for reductions; "
                    "never generates orders."
                    if tax_ready
                    else "Tax-aware scenario withheld until lot-level inputs are available."
                ),
                "tax_lot_meta": tax_meta,
                "tax_lot_plan": tax_lot_plan,
                "expected_tax": tax_lot_plan.get("provisional_expected_tax"),
                "methodology_status": tax_lot_plan.get("methodology_status") or "experimental",
            },
        )
    )

    # Goal-aligned — prefer target weights when available
    goal_weights = target_weights or repaired
    scenarios.append(
        _scenario(
            scenario_type="goal_aligned",
            account_id=account_id,
            proposed_weights=_clip_weights(goal_weights, max_single),
            current_weights=current_weights,
            no_trade_id=baseline["scenario_id"],
            blockers=medium_blockers,
            policy_ok=not high_blockers,
            extra={"goal_feasibility": "provisional"},
        )
    )

    # Cash deployment above reserve
    scenarios.append(
        _scenario(
            scenario_type="cash_deployment",
            account_id=account_id,
            proposed_weights=_cash_deployment_weights(
                current_weights,
                cash_percent=cash,
                min_cash=min_cash,
                core_symbol=core_etf,
            ),
            current_weights=current_weights,
            no_trade_id=baseline["scenario_id"],
            blockers=([] if core_etf else ["core_etf_not_configured"]) + medium_blockers,
            liquidity_ready=bool(core_etf),
            policy_ok=not high_blockers,
            extra={"deployable_cash_percent": max(0.0, cash - min_cash)},
        )
    )

    if target_weights:
        scenarios.append(
            _scenario(
                scenario_type="rebalance",
                account_id=account_id,
                proposed_weights=dict(target_weights),
                current_weights=current_weights,
                no_trade_id=baseline["scenario_id"],
                blockers=medium_blockers,
                policy_ok=not high_blockers,
            )
        )

    from app.services.portfolio_construction.scenario_comparison import compare_scenarios

    comparison = compare_scenarios(scenarios)
    deployable = max(0.0, cash - min_cash)
    return {
        "account_id": account_id,
        "scenarios": scenarios,
        "comparison": comparison,
        "capital_budget": {
            "cash_percent": cash,
            "min_cash_percent": min_cash,
            "deployable_cash_percent": deployable,
            "max_single_position_pct": max_single,
            "note": "Budget is policy-derived; no order tickets are created.",
        },
        "policy_repairs": repairs,
        "no_trade_required": True,
        "no_trade_scenario_id": baseline["scenario_id"],
        "order_generated": ORDER_GENERATED_DEFAULT,
        "disclaimer": "Construction scenarios are informational. No orders are generated.",
    }
