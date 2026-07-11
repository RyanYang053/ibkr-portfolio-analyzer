from __future__ import annotations

import numpy as np


def historical_mean_descriptive(returns: list[list[float]]) -> list[float]:
    if not returns:
        return []
    matrix = np.array(returns, dtype=float)
    return [float(value) for value in matrix.mean(axis=0)]


def equilibrium_returns(covariance: list[list[float]], market_weights: list[float], *, risk_aversion: float = 2.5) -> list[float]:
    sigma = np.array(covariance, dtype=float)
    weights = np.array(market_weights, dtype=float)
    if weights.sum() <= 0:
        weights = np.ones(len(market_weights)) / len(market_weights)
    else:
        weights = weights / weights.sum()
    pi = risk_aversion * sigma @ weights
    return [float(value) for value in pi]


def black_litterman_posterior(
    covariance: list[list[float]],
    market_weights: list[float],
    views: dict[int, float] | None = None,
    *,
    risk_aversion: float = 2.5,
    tau: float = 0.05,
    view_confidence: float = 0.5,
) -> list[float]:
    from app.services.portfolio_construction.advanced_optimizer import black_litterman_posterior_returns

    return black_litterman_posterior_returns(
        covariance,
        market_weights,
        views,
        risk_aversion=risk_aversion,
        tau=tau,
        view_confidence=view_confidence,
    )


def shrink_expected_returns(
    expected: list[float],
    equilibrium: list[float],
    *,
    shrinkage: float = 0.5,
) -> list[float]:
    if not expected:
        return equilibrium
    alpha = max(0.0, min(1.0, shrinkage))
    return [alpha * eq + (1.0 - alpha) * value for value, eq in zip(expected, equilibrium)]


def fundamental_scenario_returns(
    symbols: list[str],
    *,
    base_growth: dict[str, float] | None = None,
    margin_assumption: float = 0.0,
) -> list[float]:
    base_growth = base_growth or {}
    return [float(base_growth.get(symbol, margin_assumption)) for symbol in symbols]


def production_expected_returns(
    covariance: list[list[float]],
    market_weights: list[float],
    *,
    views: dict[int, float] | None = None,
    shrinkage: float = 0.5,
) -> list[float]:
    """Equilibrium prior + approved views with shrinkage; never raw historical mean alone."""
    prior = equilibrium_returns(covariance, market_weights)
    if not views:
        return prior
    posterior = black_litterman_posterior(covariance, market_weights, views)
    return shrink_expected_returns(posterior, prior, shrinkage=shrinkage)
