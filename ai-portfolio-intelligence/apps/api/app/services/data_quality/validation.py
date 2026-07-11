from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from app.schemas.domain import AccountSummary, Position

FxResolver = Callable[[str, str], float]

FATAL_CODES = frozenset(
    {
        "NON_FINITE_SUMMARY_VALUE",
        "NON_POSITIVE_NET_LIQUIDATION",
        "NON_FINITE_POSITION_VALUE",
        "MISSING_MARKET_PRICE",
        "FX_CONVERSION_FAILED",
        "ACCOUNT_RECONCILIATION_GAP",
    }
)


def require_analytics_safe(validation: dict[str, Any]) -> None:
    fatal = [
        issue
        for issue in validation.get("issues", [])
        if issue.get("severity") == "error" and issue.get("code") in FATAL_CODES
    ]
    if fatal:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PORTFOLIO_SNAPSHOT_INVALID",
                "issues": fatal,
            },
        )


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


def _issue(severity: str, code: str, message: str, **context: Any) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "context": context,
    }


def validate_portfolio_snapshot(
    summary: AccountSummary,
    positions: list[Position],
    *,
    fx_resolver: FxResolver | None = None,
    now: datetime | None = None,
    stale_after_seconds: int = 120,
) -> dict[str, Any]:
    """Validate a broker snapshot before it is used for analytics.

    The function is intentionally deterministic and fail-closed. It checks numeric
    integrity, freshness, duplicate instruments, currency conversion, position
    arithmetic, reported weights, and a high-level account reconciliation. It does
    not claim exact accounting reconciliation because IBKR net liquidation may also
    include accrued interest, unsettled cash, and derivative values.
    """

    if fx_resolver is None:
        from app.services.broker.ibkr_readonly import get_exchange_rate

        fx_resolver = get_exchange_rate

    now = now or datetime.now(timezone.utc)
    issues: list[dict[str, Any]] = []

    numeric_summary_fields = (
        "net_liquidation",
        "cash",
        "buying_power",
        "margin_requirement",
        "excess_liquidity",
        "total_unrealized_pnl",
        "total_realized_pnl",
    )
    for field in numeric_summary_fields:
        value = getattr(summary, field)
        if not _finite(value):
            issues.append(_issue("error", "NON_FINITE_SUMMARY_VALUE", f"{field} is not finite", field=field, value=value))

    if summary.net_liquidation <= 0:
        issues.append(
            _issue(
                "error",
                "NON_POSITIVE_NET_LIQUIDATION",
                "Net liquidation must be positive before percentage-based analytics are produced.",
                value=summary.net_liquidation,
            )
        )

    timestamp = summary.data_timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
        issues.append(_issue("warning", "NAIVE_SUMMARY_TIMESTAMP", "Summary timestamp had no timezone and was interpreted as UTC."))
    age_seconds = max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds())
    if age_seconds > stale_after_seconds:
        issues.append(
            _issue(
                "warning",
                "STALE_SUMMARY",
                "Broker summary is older than the configured freshness threshold.",
                age_seconds=round(age_seconds, 1),
                stale_after_seconds=stale_after_seconds,
            )
        )

    duplicate_keys = Counter(
        (
            position.account_id,
            position.con_id,
            position.local_symbol or position.symbol.upper(),
            position.asset_class,
            position.currency,
        )
        for position in positions
    )
    for key, count in duplicate_keys.items():
        if count > 1:
            issues.append(
                _issue(
                    "warning",
                    "DUPLICATE_POSITION_KEY",
                    "Multiple positions share the same available instrument key and may be incorrectly merged.",
                    key=key,
                    count=count,
                )
            )

    base_currency = summary.base_currency.upper().strip()
    gross_market_value_base = 0.0
    net_market_value_base = 0.0
    calculated_weight_sum = 0.0
    reported_weight_sum = 0.0
    missing_prices = 0
    fx_failures = 0

    for position in positions:
        symbol = position.symbol.upper().strip()
        numeric_fields = (
            "quantity",
            "avg_cost",
            "market_price",
            "market_value",
            "unrealized_pnl",
            "realized_pnl",
            "portfolio_weight",
        )
        for field in numeric_fields:
            value = getattr(position, field)
            if not _finite(value):
                issues.append(
                    _issue(
                        "error",
                        "NON_FINITE_POSITION_VALUE",
                        f"{symbol} {field} is not finite.",
                        symbol=symbol,
                        field=field,
                        value=value,
                    )
                )

        if position.quantity != 0 and position.market_price <= 0:
            missing_prices += 1
            issues.append(
                _issue(
                    "error",
                    "MISSING_MARKET_PRICE",
                    f"{symbol} has non-zero quantity but no positive market price.",
                    symbol=symbol,
                    quantity=position.quantity,
                    market_price=position.market_price,
                )
            )

        if position.asset_class not in {"OPT", "FOP"} and position.quantity != 0 and position.market_price > 0:
            expected_market_value = position.quantity * position.market_price
            tolerance = max(1.0, abs(position.market_value) * 0.005)
            if abs(position.market_value - expected_market_value) > tolerance:
                issues.append(
                    _issue(
                        "warning",
                        "POSITION_VALUE_MISMATCH",
                        f"{symbol} market value is inconsistent with quantity times market price.",
                        symbol=symbol,
                        reported_market_value=position.market_value,
                        expected_market_value=round(expected_market_value, 4),
                        tolerance=round(tolerance, 4),
                    )
                )

        try:
            rate = float(fx_resolver(position.currency, base_currency))
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError("FX rate must be finite and positive")
        except Exception as exc:
            fx_failures += 1
            issues.append(
                _issue(
                    "error",
                    "FX_CONVERSION_FAILED",
                    f"Could not convert {symbol} from {position.currency} to {base_currency}.",
                    symbol=symbol,
                    currency=position.currency,
                    base_currency=base_currency,
                    error=str(exc),
                )
            )
            continue

        value_base = position.market_value * rate
        net_market_value_base += value_base
        gross_market_value_base += abs(value_base)
        reported_weight_sum += position.portfolio_weight

        if summary.net_liquidation > 0:
            calculated_weight = value_base / summary.net_liquidation * 100.0
            calculated_weight_sum += calculated_weight
            if abs(calculated_weight - position.portfolio_weight) > 0.5:
                issues.append(
                    _issue(
                        "warning",
                        "POSITION_WEIGHT_MISMATCH",
                        f"{symbol} reported portfolio weight does not match base-currency market value.",
                        symbol=symbol,
                        reported_weight=position.portfolio_weight,
                        calculated_weight=round(calculated_weight, 4),
                    )
                )

        position_timestamp = position.updated_at
        if position_timestamp.tzinfo is None:
            position_timestamp = position_timestamp.replace(tzinfo=timezone.utc)
        position_age = max(0.0, (now - position_timestamp.astimezone(timezone.utc)).total_seconds())
        if position_age > stale_after_seconds:
            issues.append(
                _issue(
                    "warning",
                    "STALE_POSITION",
                    f"{symbol} position data is stale.",
                    symbol=symbol,
                    age_seconds=round(position_age, 1),
                )
            )

    reconciliation_gap = summary.net_liquidation - (summary.cash + net_market_value_base)
    reconciliation_gap_pct = (
        abs(reconciliation_gap) / abs(summary.net_liquidation) * 100.0 if summary.net_liquidation else None
    )
    if reconciliation_gap_pct is not None and reconciliation_gap_pct > 5.0:
        issues.append(
            _issue(
                "error",
                "ACCOUNT_RECONCILIATION_GAP",
                "Cash plus converted position values differs materially from net liquidation.",
                gap=round(reconciliation_gap, 2),
                gap_percent=round(reconciliation_gap_pct, 3),
            )
        )
    elif reconciliation_gap_pct is not None and reconciliation_gap_pct > 1.0:
        issues.append(
            _issue(
                "warning",
                "ACCOUNT_RECONCILIATION_GAP",
                "Cash plus converted position values does not closely reconcile to net liquidation.",
                gap=round(reconciliation_gap, 2),
                gap_percent=round(reconciliation_gap_pct, 3),
            )
        )

    errors = sum(issue["severity"] == "error" for issue in issues)
    warnings = sum(issue["severity"] == "warning" for issue in issues)
    status = "fail" if errors else "warning" if warnings else "pass"
    score = max(0, 100 - errors * 20 - warnings * 5)

    return {
        "status": status,
        "score": score,
        "issues": issues,
        "metrics": {
            "base_currency": base_currency,
            "position_count": len(positions),
            "gross_market_value_base": round(gross_market_value_base, 2),
            "net_market_value_base": round(net_market_value_base, 2),
            "reported_weight_sum": round(reported_weight_sum, 4),
            "calculated_weight_sum": round(calculated_weight_sum, 4),
            "reconciliation_gap": round(reconciliation_gap, 2),
            "reconciliation_gap_percent": round(reconciliation_gap_pct, 4) if reconciliation_gap_pct is not None else None,
            "summary_age_seconds": round(age_seconds, 1),
            "missing_price_count": missing_prices,
            "fx_failure_count": fx_failures,
        },
        "methodology": (
            "Deterministic pre-analytics validation. Reconciliation is diagnostic rather than exact because "
            "IBKR net liquidation can include accrued interest, unsettled balances, and derivative values."
        ),
    }


def validate_and_gate_snapshot(
    summary: AccountSummary,
    positions: list[Position],
    *,
    fx_resolver: FxResolver | None = None,
) -> dict[str, Any]:
    validation = validate_portfolio_snapshot(summary, positions, fx_resolver=fx_resolver)
    require_analytics_safe(validation)
    return validation


def build_valuation_disclosure(
    summary: AccountSummary,
    positions: list[Position],
    validation: dict[str, Any],
) -> dict[str, Any]:
    from app.services.broker.ibkr_readonly import get_exchange_rate

    base_currency = summary.base_currency.upper().strip()
    total_gross_base = 0.0
    included_gross_base = 0.0
    excluded_gross_base = 0.0
    excluded_con_ids: list[int] = []
    exclusion_reasons: dict[str, str] = {}
    valuation_sources: dict[str, str] = {}
    unmeasurable_exclusion = False
    oldest_timestamp = summary.data_timestamp
    if oldest_timestamp.tzinfo is None:
        oldest_timestamp = oldest_timestamp.replace(tzinfo=timezone.utc)

    for position in positions:
        if position.quantity == 0:
            continue
        symbol = position.symbol.upper().strip()
        identity = str(position.con_id) if position.con_id is not None else symbol

        if position.market_price <= 0:
            if position.con_id is not None:
                excluded_con_ids.append(position.con_id)
            exclusion_reasons[symbol] = "MISSING_MARKET_PRICE"
            if position.market_value and position.market_value > 0:
                try:
                    rate = float(get_exchange_rate(position.currency, base_currency))
                    if math.isfinite(rate) and rate > 0:
                        excluded_gross_base += abs(position.market_value * rate)
                    else:
                        unmeasurable_exclusion = True
                except Exception:
                    unmeasurable_exclusion = True
            else:
                unmeasurable_exclusion = True
            continue

        try:
            rate = float(get_exchange_rate(position.currency, base_currency))
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError("FX rate must be finite and positive")
            value_base = abs(position.market_value * rate)
            total_gross_base += value_base
            included_gross_base += value_base
            valuation_sources[identity] = position.price_source or "broker"
            position_timestamp = position.updated_at
            if position_timestamp.tzinfo is None:
                position_timestamp = position_timestamp.replace(tzinfo=timezone.utc)
            if position_timestamp < oldest_timestamp:
                oldest_timestamp = position_timestamp
        except Exception:
            if position.con_id is not None:
                excluded_con_ids.append(position.con_id)
            exclusion_reasons[symbol] = "FX_CONVERSION_FAILED"
            try:
                excluded_gross_base += abs(position.market_value)
            except Exception:
                pass

    measurable_denominator = total_gross_base + excluded_gross_base
    if unmeasurable_exclusion:
        included_percent = None
    elif measurable_denominator > 0:
        included_percent = included_gross_base / measurable_denominator * 100.0
    else:
        included_percent = None

    return {
        "included_gross_value_percent": round(included_percent, 4) if included_percent is not None else None,
        "coverage_measurable": included_percent is not None,
        "excluded_con_ids": sorted(set(excluded_con_ids)),
        "exclusion_reasons": exclusion_reasons,
        "oldest_source_timestamp": oldest_timestamp.isoformat(),
        "valuation_sources": valuation_sources,
        "validation_status": validation.get("status"),
        "missing_price_count": validation.get("metrics", {}).get("missing_price_count", 0),
    }


def prepare_professional_response(
    result: Any,
    summary: AccountSummary,
    positions: list[Position],
    validation: dict[str, Any],
    *,
    methodology_id: str | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.services.governance.runtime_gate import enforce_or_mark_experimental
    from app.services.guardrails.engine import append_compliance_disclaimer

    payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    payload["snapshot_validation"] = validation
    payload["valuation_disclosure"] = build_valuation_disclosure(summary, positions, validation)

    resolved_methodology = methodology_id or payload.get("methodology_id")
    if isinstance(resolved_methodology, str) and resolved_methodology:
        payload = enforce_or_mark_experimental(
            resolved_methodology,
            payload,
            production=settings.environment != "development",
        )
        if payload.get("status") == "withheld_unapproved_methodology":
            for key in ("proposed_trades", "strategies", "trade_proposals", "rebalance_actions"):
                if key in payload:
                    payload[key] = []
            payload["implementation_ready"] = False

    methodology_status = str(payload.get("methodology_status") or "")
    jurisdiction = str(payload.get("jurisdiction") or payload.get("tax_labeling_jurisdiction") or "")
    if jurisdiction == "CA" and methodology_status.startswith("provisional"):
        payload["tax_output_provisional"] = True
        payload["professional_language_allowed"] = False
        payload["filing_ready"] = False

    return append_compliance_disclaimer(payload)
