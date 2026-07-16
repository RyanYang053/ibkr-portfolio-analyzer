from __future__ import annotations

from datetime import date
from typing import Any

_FACTOR_KEY_MAP = {
    "market": "market",
    "mkt": "market",
    "value": "value",
    "momentum": "momentum",
    "mom": "momentum",
    "quality": "quality",
    "growth": "growth",
    "low volatility": "low_volatility",
    "low_volatility": "low_volatility",
}


def normalize_factor_exposures(raw: dict[str, Any] | None) -> dict[str, float]:
    """Map provider factor keys (often Title Case) onto lowercase lens keys."""
    if not raw:
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed != parsed:
            continue
        mapped = _FACTOR_KEY_MAP.get(str(key).strip().lower())
        if mapped is None:
            continue
        out[mapped] = parsed
    return out


def extract_risk_metrics(risk_payload: dict[str, Any] | None) -> dict[str, float]:
    """Keep only lens-relevant numeric risk fields; omit missing values."""
    if not risk_payload:
        return {}
    keys = (
        "volatility",
        "ewma_volatility",
        "max_drawdown",
        "conditional_var_95",
        "value_at_risk_95",
        "historical_var_95",
        "historical_es_95",
    )
    out: dict[str, float] = {}
    for key in keys:
        value = risk_payload.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed == parsed:
            out[key] = parsed
    return out


def load_fundamentals_for_symbol(symbol: str, *, as_of: date | None = None) -> dict[str, Any] | None:
    """Load PIT fundamentals when available; return None to fail closed."""
    as_of = as_of or date.today()
    try:
        from app.services.fundamentals.snapshot_store import get_point_in_time_fundamentals

        snapshot = get_point_in_time_fundamentals(symbol, as_of)
        if snapshot is not None:
            return snapshot.model_dump()
    except Exception:
        pass
    try:
        from app.services.fundamentals.providers import fetch_point_in_time_fundamentals

        return fetch_point_in_time_fundamentals(symbol)
    except Exception:
        return None


def load_account_risk_bundle(
    *,
    account_id: str,
    positions: list[Any],
    summary: Any,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Load account-level risk/factor inputs for Decision Center lenses.

    Risk metrics are portfolio-level (existing advanced_risk module). When history is
    insufficient the module returns nulls — we fail closed to empty dicts.
    """
    try:
        from app.services.portfolio.pnl_tracker import get_pnl_history
        from app.services.risk.advanced_risk import calculate_advanced_risk_metrics

        history = get_pnl_history(account_id)
        risk = calculate_advanced_risk_metrics(positions, summary, history)
        payload = risk.model_dump() if hasattr(risk, "model_dump") else dict(risk)
        risk_metrics = extract_risk_metrics(payload)
        raw_factors = payload.get("measured_factor_exposures") or payload.get("factor_exposures") or {}
        if not isinstance(raw_factors, dict):
            raw_factors = {}
        factors = normalize_factor_exposures(raw_factors)
        # Heuristic style buckets may include Quality when measured factors do not.
        if "quality" not in factors:
            heuristic = payload.get("heuristic_style_classification") or {}
            if isinstance(heuristic, dict):
                factors = {**normalize_factor_exposures(heuristic), **factors}
        return risk_metrics, factors
    except Exception:
        return {}, {}


def load_holding_market_inputs(
    *,
    symbol: str,
    account_id: str,
    positions: list[Any],
    summary: Any,
    as_of: date | None = None,
    cached_risk: tuple[dict[str, float], dict[str, float]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Assemble fundamentals / risk / factors for one holding; empty when unavailable."""
    fundamentals = load_fundamentals_for_symbol(symbol, as_of=as_of) or {}
    if cached_risk is not None:
        risk_metrics, factor_exposures = cached_risk
    else:
        risk_metrics, factor_exposures = load_account_risk_bundle(
            account_id=account_id,
            positions=positions,
            summary=summary,
        )
    return {
        "fundamentals": dict(fundamentals),
        "risk_metrics": extract_risk_metrics(risk_metrics) if risk_metrics else {},
        "factor_exposures": normalize_factor_exposures(factor_exposures),
    }
