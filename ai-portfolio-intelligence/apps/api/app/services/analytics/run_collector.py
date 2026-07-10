from __future__ import annotations

from app.schemas.domain import AccountSummary, Position
from app.services.market_data.fx_store import make_transaction_fx_resolver
from app.services.portfolio.pnl_decomposition import calculate_pnl_decomposition
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, get_pnl_history
from app.services.portfolio.performance_returns import calculate_performance_returns
from app.services.risk.advanced_risk import calculate_advanced_risk_metrics


def collect_portfolio_calculation_run_ids(
    account_id: str,
    summary: AccountSummary,
    positions: list[Position],
    *,
    allow_mock: bool = False,
) -> list[str]:
    history: list[PortfolioPnLSnapshot] = get_pnl_history(account_id)
    if len(history) < 2:
        return []

    fx_resolver = make_transaction_fx_resolver()
    run_ids: list[str] = []
    try:
        performance = calculate_performance_returns(
            account_id,
            history,
            summary.base_currency,
            fx_resolver,
            allow_mock=allow_mock,
        )
        if performance.calculation_run_id:
            run_ids.append(performance.calculation_run_id)
    except Exception:
        pass

    try:
        risk = calculate_advanced_risk_metrics(positions, summary, history)
        if risk.calculation_run_id:
            run_ids.append(risk.calculation_run_id)
    except Exception:
        pass

    try:
        decomposition = calculate_pnl_decomposition(
            account_id,
            history,
            positions,
            summary.base_currency,
            fx_resolver,
        )
        batch_id = decomposition.calculation_run.get("calculation_run_id")
        if isinstance(batch_id, str):
            run_ids.append(batch_id)
    except Exception:
        pass

    return list(dict.fromkeys(run_ids))
