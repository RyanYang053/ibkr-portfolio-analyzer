from __future__ import annotations

from typing import Any


def simulate_holding_action(
    *,
    action: str,
    current_weight: float,
    proposed_weight: float | None = None,
    estimated_tax: float | None = None,
    account_id: str | None = None,
    symbol: str | None = None,
    position: Any | None = None,
    summary: Any | None = None,
    risk_metrics: dict[str, Any] | None = None,
    tax_jurisdiction: str | None = None,
    account_type: str | None = None,
) -> dict[str, Any]:
    """Action simulator wired to tax/risk diagnostics — review framing only.

    Never claims implementation_ready. Uses lot-level tax transition when available;
    otherwise withholds tax estimate for taxable accounts.
    """
    target = proposed_weight if proposed_weight is not None else current_weight
    delta = target - current_weight
    action_l = action.lower()
    if action_l in {"trim", "exit", "review trim", "review exit"}:
        direction = "reduce"
    elif action_l in {"add", "review add"}:
        direction = "increase"
    else:
        direction = "hold"

    tax_block = _estimate_tax_impact(
        direction=direction,
        weight_delta=delta,
        estimated_tax=estimated_tax,
        account_id=account_id,
        symbol=symbol,
        position=position,
        summary=summary,
        tax_jurisdiction=tax_jurisdiction,
        account_type=account_type,
    )
    risk_block = _estimate_risk_impact(
        current_weight=current_weight,
        proposed_weight=target,
        risk_metrics=risk_metrics or {},
    )

    exclusions = list(tax_block.get("exclusions") or []) + list(risk_block.get("exclusions") or [])
    implementation_ready = False
    methodology_status = "experimental"
    if tax_block.get("status") == "withheld" and str(account_type or "").lower() == "taxable" and direction == "reduce":
        methodology_status = "withheld_lot_inputs_unavailable"

    return {
        "action": action,
        "direction": direction,
        "current_weight_percent": current_weight,
        "proposed_weight_percent": target,
        "weight_delta_percent": round(delta, 4),
        "estimated_tax": tax_block.get("estimated_tax"),
        "tax": tax_block,
        "risk": risk_block,
        "exclusions": exclusions,
        "implementation_ready": implementation_ready,
        "note": (
            "Simulation is decision-support only; not an order or recommendation to trade. "
            "Tax and risk blocks use live portfolio/tax/risk services when available."
        ),
        "methodology_status": methodology_status,
    }


def _estimate_tax_impact(
    *,
    direction: str,
    weight_delta: float,
    estimated_tax: float | None,
    account_id: str | None,
    symbol: str | None,
    position: Any | None,
    summary: Any | None,
    tax_jurisdiction: str | None,
    account_type: str | None,
) -> dict[str, Any]:
    if estimated_tax is not None:
        return {
            "status": "provided",
            "estimated_tax": estimated_tax,
            "source": "request_override",
            "exclusions": [],
        }
    if direction != "reduce" or abs(weight_delta) < 1e-9:
        return {"status": "not_applicable", "estimated_tax": 0.0, "exclusions": []}

    acct_type = str(account_type or "Taxable")
    if acct_type.lower() in {"ira", "rrsp", "tfsa", "tax_deferred", "tax_free"}:
        return {"status": "available", "estimated_tax": 0.0, "exclusions": ["tax_advantaged_account"]}

    if not account_id or not symbol or summary is None:
        return {
            "status": "withheld",
            "estimated_tax": None,
            "exclusions": ["tax_context_incomplete"],
        }

    try:
        from datetime import date as date_cls

        from app.services.portfolio.tax_lots import build_tax_lot_attribution
        from app.services.portfolio.transaction_store import get_transactions
        from app.services.portfolio_construction.tax_transition import (
            TaxTransitionRequest,
            build_tax_lot_transition_inputs_from_open_lots,
            evaluate_tax_transition,
            lot_marginal_tax_rate,
        )

        jurisdiction = (tax_jurisdiction or "US").upper()
        transactions = get_transactions(account_id)
        tax_report = build_tax_lot_attribution(
            account_id,
            transactions,
            reporting_currency=str(getattr(summary, "base_currency", "USD") or "USD"),
            tax_labeling_jurisdiction=jurisdiction,  # type: ignore[arg-type]
        )
        mark = float(getattr(position, "market_price", 0.0) or 0.0) if position is not None else 0.0
        lot_inputs = build_tax_lot_transition_inputs_from_open_lots(
            tax_report.lots_open,
            marks_by_symbol={symbol.upper(): mark},
            as_of=date_cls.today(),
        )
        symbol_lots = [lot for lot in lot_inputs if lot.symbol.upper() == symbol.upper()]
        if not symbol_lots:
            return {
                "status": "withheld",
                "estimated_tax": None,
                "exclusions": ["lot_level_tax_inputs_unavailable"],
                "methodology_status": str(tax_report.methodology_status or "withheld"),
            }

        # Scale sell fraction from weight reduction vs current weight.
        current_w = abs(float(getattr(position, "portfolio_weight", 0.0) or 0.0)) if position else 0.0
        sell_fraction = min(1.0, abs(weight_delta) / current_w) if current_w > 1e-9 else 1.0
        nav = max(abs(float(getattr(summary, "net_liquidation", 0.0) or 0.0)), 1.0)
        sell_dollars_target = abs(weight_delta) / 100.0 * nav if abs(weight_delta) > 1 else abs(weight_delta) * nav

        # Prefer weight in percent units from Decision Center; fall back to fraction.
        if abs(weight_delta) > 1.0:
            sell_dollars_target = abs(weight_delta) / 100.0 * nav

        remaining = sell_dollars_target
        estimated = 0.0
        selected: list[dict[str, Any]] = []
        # Tax-aware: harvest losses first, then lowest marginal rate gains.
        ordered = sorted(
            symbol_lots,
            key=lambda lot: (
                0 if lot.unrealized_gain_loss <= 0 else 1,
                lot_marginal_tax_rate(lot, account_type=acct_type, jurisdiction=jurisdiction),
            ),
        )
        for lot in ordered:
            if remaining <= 1e-9:
                break
            take = min(remaining, abs(lot.market_value))
            frac = take / abs(lot.market_value) if abs(lot.market_value) > 1e-9 else 0.0
            rate = lot_marginal_tax_rate(lot, account_type=acct_type, jurisdiction=jurisdiction)
            lot_tax = max(0.0, lot.unrealized_gain_loss) * rate * frac
            estimated += lot_tax
            selected.append({"lot_id": lot.lot_id, "sell_dollars": round(take, 2), "estimated_tax": round(lot_tax, 2)})
            remaining -= take

        transition = evaluate_tax_transition(
            TaxTransitionRequest(
                account_type=acct_type,
                jurisdiction=jurisdiction,
                tax_lots=symbol_lots,
                tax_budget=None,
            )
        )
        return {
            "status": "available",
            "estimated_tax": round(estimated, 2),
            "sell_fraction": round(sell_fraction, 6),
            "selected_lots": selected,
            "sell_candidates": list(transition.sell_candidates),
            "blocked_lots": list(transition.blocked_lots),
            "source": "lot_level_tax_transition",
            "methodology_status": str(tax_report.methodology_status or "experimental"),
            "exclusions": list(transition.exclusions),
        }
    except Exception as exc:
        return {
            "status": "withheld",
            "estimated_tax": None,
            "exclusions": [f"tax_simulation_failed:{exc.__class__.__name__}"],
        }


def _estimate_risk_impact(
    *,
    current_weight: float,
    proposed_weight: float,
    risk_metrics: dict[str, Any],
) -> dict[str, Any]:
    exclusions: list[str] = []
    max_dd = risk_metrics.get("max_drawdown_decimal", risk_metrics.get("max_drawdown"))
    max_dd_decimal: float | None = None
    if max_dd is not None:
        raw = float(max_dd)
        if abs(raw) > 1.0:
            exclusions.append("max_drawdown_percent_normalized")
            max_dd_decimal = raw / 100.0
        else:
            max_dd_decimal = raw

    over_concentrated = proposed_weight > 10.0
    return {
        "status": "available",
        "current_weight_percent": current_weight,
        "proposed_weight_percent": proposed_weight,
        "over_concentrated_after": over_concentrated,
        "max_drawdown_decimal": max_dd_decimal,
        "exclusions": exclusions,
    }
