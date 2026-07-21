from __future__ import annotations

from collections import defaultdict

from app.schemas.domain import AccountSummary, Alert, PortfolioRisk, Position, utc_now


def _group_gross_exposure(converted: list[tuple[Position, float]], field: str) -> dict[str, float]:
    gross = sum(abs(value) for _, value in converted)
    grouped: dict[str, float] = defaultdict(float)
    for position, value in converted:
        grouped[str(getattr(position, field) or "Unknown")] += abs(value)
    if gross <= 0:
        return {key: 0.0 for key in sorted(grouped)}
    return {key: round(value / gross * 100.0, 2) for key, value in sorted(grouped.items())}


def analyze_portfolio_risk(
    summary: AccountSummary,
    positions: list[Position],
    *,
    policy: dict | None = None,
) -> PortfolioRisk:
    """Calculate transparent exposure and concentration diagnostics.

    Concentration is measured on gross absolute exposure so that short positions do
    not cancel long positions. Portfolio-level exposure percentages use absolute net
    liquidation as their denominator and may therefore exceed 100% in leveraged
    accounts.

    Thresholds come from the user's portfolio policy when provided; otherwise
    documented defaults are used (not a parallel hard-coded policy framework).
    """

    from app.services.broker.ibkr_readonly import get_exchange_rate

    limits = {
        "max_single_stock_weight": 12.0,
        "max_sector_weight": 35.0,
        "max_speculative_weight": 5.0,
        "min_cash_percent": 10.0,
        "max_margin_usage_percent": 20.0,
        "max_gross_exposure_percent": 120.0,
    }
    if policy:
        for key in list(limits):
            if policy.get(key) is not None:
                limits[key] = float(policy[key])
        # Common IPS field aliases
        if policy.get("max_single_name_weight") is not None:
            limits["max_single_stock_weight"] = float(policy["max_single_name_weight"])
        if policy.get("cash_floor_percent") is not None:
            limits["min_cash_percent"] = float(policy["cash_floor_percent"])

    converted: list[tuple[Position, float]] = []
    for position in positions:
        rate = get_exchange_rate(position.currency, summary.base_currency)
        converted.append((position, position.market_value * rate))

    alerts: list[Alert] = []
    net_liquidation = float(summary.net_liquidation)
    denominator = abs(net_liquidation)
    if denominator <= 0:
        denominator = 1.0
        alerts.append(
            Alert(
                alert_type="invalid_net_liquidation",
                severity="high",
                message="Net liquidation is non-positive; percentage risk metrics are not reliable.",
            )
        )

    gross_position_value = sum(abs(value) for _, value in converted)
    net_position_value = sum(value for _, value in converted)
    gross_exposure_percent = gross_position_value / denominator * 100.0

    cash_percent = summary.cash / denominator * 100.0
    etf_percent = sum(abs(value) for position, value in converted if position.is_etf) / denominator * 100.0
    speculative_percent = (
        sum(abs(value) for position, value in converted if position.is_speculative) / denominator * 100.0
    )
    single_stock_percent = (
        sum(
            abs(value)
            for position, value in converted
            if not position.is_etf and position.asset_class not in {"OPT", "FOP"}
        )
        / denominator
        * 100.0
    )

    gross_values = sorted((abs(value) for _, value in converted), reverse=True)
    top_5_concentration = sum(gross_values[:5]) / (gross_position_value or 1.0) * 100.0
    largest_position_percent = (gross_values[0] / denominator * 100.0) if gross_values else 0.0

    if gross_position_value > 0:
        herfindahl = sum((abs(value) / gross_position_value) ** 2 for _, value in converted)
    else:
        herfindahl = 0.0

    margin_usage_percent = max(0.0, summary.margin_requirement) / denominator * 100.0
    sector_exposure = _group_gross_exposure(converted, "sector")
    currency_exposure = _group_gross_exposure(converted, "currency")

    if largest_position_percent > limits["max_single_stock_weight"]:
        alerts.append(
            Alert(
                alert_type="single_name_concentration",
                severity="medium",
                message=(
                    f"A single position is above the policy {limits['max_single_stock_weight']:.0f}% "
                    "of net-liquidation review threshold."
                ),
            )
        )
    if sector_exposure.get("Technology", 0.0) > limits["max_sector_weight"]:
        alerts.append(
            Alert(
                alert_type="sector_concentration",
                severity="high",
                message=(
                    f"Technology represents more than {limits['max_sector_weight']:.0f}% "
                    "of gross invested exposure."
                ),
            )
        )
    if speculative_percent > limits["max_speculative_weight"]:
        alerts.append(
            Alert(
                alert_type="speculative_exposure",
                severity="high",
                message=(
                    f"Speculative gross exposure is above {limits['max_speculative_weight']:.0f}% "
                    "of net liquidation."
                ),
            )
        )
    if cash_percent < limits["min_cash_percent"]:
        alerts.append(
            Alert(
                alert_type="low_cash",
                severity="medium",
                message=(
                    f"Cash is below the policy {limits['min_cash_percent']:.0f}% "
                    "net-liquidation buffer."
                ),
            )
        )
    if margin_usage_percent > limits["max_margin_usage_percent"]:
        alerts.append(
            Alert(
                alert_type="margin_risk",
                severity="medium",
                message=(
                    f"Initial margin requirement is above {limits['max_margin_usage_percent']:.0f}% "
                    "of net liquidation."
                ),
            )
        )
    if gross_exposure_percent > limits["max_gross_exposure_percent"]:
        alerts.append(
            Alert(
                alert_type="gross_leverage",
                severity="high",
                message=(
                    f"Gross position exposure is above {limits['max_gross_exposure_percent']:.0f}% "
                    "of net liquidation."
                ),
            )
        )

    # Transparent 0-100 diagnostic score. Each component is capped so no single
    # metric dominates the result. This is a policy-risk indicator, not a forecast.
    concentration_component = 25.0 * min(1.0, herfindahl / 0.25)
    largest_name_component = 20.0 * min(1.0, largest_position_percent / 25.0)
    speculative_component = 20.0 * min(1.0, speculative_percent / 20.0)
    leverage_component = 20.0 * min(1.0, max(0.0, gross_exposure_percent - 100.0) / 100.0)
    margin_component = 15.0 * min(1.0, margin_usage_percent / 50.0)
    risk_score = min(
        100.0,
        concentration_component
        + largest_name_component
        + speculative_component
        + leverage_component
        + margin_component,
    )

    # The existing response schema has no explicit gross/net exposure fields. Add
    # these diagnostics to alert messages until the API schema is versioned.
    if positions:
        alerts.append(
            Alert(
                alert_type="exposure_methodology",
                severity="low",
                message=(
                    f"Gross exposure is {gross_exposure_percent:.2f}% and net position exposure is "
                    f"{net_position_value / denominator * 100.0:.2f}% of net liquidation. "
                    "Concentration uses absolute market values."
                ),
            )
        )

    return PortfolioRisk(
        total_value=round(net_liquidation, 2),
        risk_score=round(risk_score, 1),
        cash_percent=round(cash_percent, 2),
        etf_percent=round(etf_percent, 2),
        single_stock_percent=round(single_stock_percent, 2),
        speculative_percent=round(speculative_percent, 2),
        sector_exposure=sector_exposure,
        currency_exposure=currency_exposure,
        top_5_concentration=round(top_5_concentration, 2),
        herfindahl_concentration_score=round(herfindahl, 4),
        herfindahl_concentration_label=_herfindahl_label(herfindahl),
        margin_usage_percent=round(margin_usage_percent, 2),
        alerts=alerts,
        data_timestamp=utc_now(),
    )


def _herfindahl_label(score: float) -> str:
    if score < 0.08:
        return "Diversified"
    if score < 0.15:
        return "Moderate concentration"
    if score < 0.25:
        return "High concentration"
    return "Very concentrated"
