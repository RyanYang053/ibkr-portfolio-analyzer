from collections import defaultdict

from app.schemas.domain import AccountSummary, Alert, PortfolioRisk, Position, utc_now


def _exposure(positions: list[Position], field: str, base_currency: str) -> dict[str, float]:
    from app.services.broker.ibkr_readonly import get_exchange_rate
    converted = [(pos, pos.market_value * get_exchange_rate(pos.currency, base_currency)) for pos in positions]
    total = sum(val for pos, val in converted)
    grouped: dict[str, float] = defaultdict(float)
    for pos, val in converted:
        grouped[getattr(pos, field)] += val
    return {key: round(value / (total or 1) * 100, 2) for key, value in sorted(grouped.items())}


def analyze_portfolio_risk(summary: AccountSummary, positions: list[Position]) -> PortfolioRisk:
    from app.services.broker.ibkr_readonly import get_exchange_rate
    converted_positions = [(pos, pos.market_value * get_exchange_rate(pos.currency, summary.base_currency)) for pos in positions]
    
    invested = sum(val for pos, val in converted_positions)
    total_value = summary.net_liquidation
    cash_percent = summary.cash / total_value * 100
    etf_percent = sum(val for pos, val in converted_positions if pos.is_etf) / total_value * 100
    speculative_percent = sum(val for pos, val in converted_positions if pos.is_speculative) / total_value * 100
    top_5_concentration = sum(sorted((val for pos, val in converted_positions), reverse=True)[:5]) / total_value * 100
    herfindahl = sum((val / total_value) ** 2 for pos, val in converted_positions)
    margin_usage_percent = summary.margin_requirement / total_value * 100
    sector_exposure = _exposure(positions, "sector", summary.base_currency)
    currency_exposure = _exposure(positions, "currency", summary.base_currency)

    alerts: list[Alert] = []
    if max((position.portfolio_weight for position in positions), default=0) > 12:
        alerts.append(Alert(alert_type="single_name_concentration", severity="medium", message="A single position is above the default 12% review threshold."))
    if sector_exposure.get("Technology", 0) > 35:
        alerts.append(Alert(alert_type="sector_concentration", severity="high", message="Technology exposure is above the default sector risk threshold."))
    if speculative_percent > 5:
        alerts.append(Alert(alert_type="speculative_exposure", severity="high", message="Speculative exposure is above the default 5% basket threshold."))
    if cash_percent < 10:
        alerts.append(Alert(alert_type="low_cash", severity="medium", message="Cash is below the default 10% risk buffer."))
    if margin_usage_percent > 20:
        alerts.append(Alert(alert_type="margin_risk", severity="medium", message="Margin requirement is elevated for risk awareness only."))

    risk_score = min(100, 28 + top_5_concentration * 0.55 + speculative_percent * 1.4 + margin_usage_percent * 0.7)
    return PortfolioRisk(
        total_value=round(total_value, 2),
        risk_score=round(risk_score, 1),
        cash_percent=round(cash_percent, 2),
        etf_percent=round(etf_percent, 2),
        single_stock_percent=round((invested / total_value * 100) - etf_percent, 2),
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
