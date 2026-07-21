"""Release E1: market regime engine (explainable, not LLM) + /markets API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.market import RegimeInputs, RegimeState
from app.services.market_intelligence.regime import classify_regime

# ------------------------------------------------------------ regime engine


def test_insufficient_data_when_too_few_dimensions():
    regime = classify_regime(RegimeInputs(trend="up"))
    assert regime.label == RegimeState.INSUFFICIENT_DATA
    assert regime.confidence == 0.0
    assert any("missing dimension" in d for d in regime.data_limitations)


def test_risk_on_expansion_classification_with_evidence():
    regime = classify_regime(
        RegimeInputs(trend="up", breadth="broad", volatility="low", risk_appetite="risk_on", credit="tightening")
    )
    assert regime.label == RegimeState.RISK_ON_EXPANSION
    assert regime.confidence > 0.5
    assert regime.supporting_evidence  # explainable
    assert regime.portfolio_implications


def test_risk_on_narrowing_vs_expansion():
    narrow = classify_regime(RegimeInputs(trend="up", breadth="narrow", volatility="low"))
    assert narrow.label == RegimeState.RISK_ON_NARROWING


def test_crisis_and_riskoff_and_volexpansion():
    crisis = classify_regime(RegimeInputs(trend="down", volatility="extreme", credit="blowout", breadth="collapsing"))
    assert crisis.label == RegimeState.CRISIS_DISLOCATION

    riskoff = classify_regime(RegimeInputs(trend="down", credit="widening", risk_appetite="risk_off"))
    assert riskoff.label == RegimeState.RISK_OFF_CONTRACTION

    volx = classify_regime(RegimeInputs(trend="flat", volatility="high", breadth="broad"))
    assert volx.label == RegimeState.VOLATILITY_EXPANSION


def test_changed_dimensions_tracked_against_previous():
    prev = classify_regime(RegimeInputs(trend="up", breadth="broad", volatility="low"))
    now = classify_regime(RegimeInputs(trend="up", breadth="narrow", volatility="low"), previous=prev)
    assert "breadth" in now.changed_dimensions
    assert now.previous_regime == prev.label


def test_regime_is_deterministic_not_llm():
    # Same inputs -> identical label every time (no stochastic/LLM step).
    inputs = RegimeInputs(trend="up", breadth="broad", volatility="low", risk_appetite="risk_on")
    labels = {classify_regime(inputs).label for _ in range(5)}
    assert len(labels) == 1
    assert classify_regime(inputs).methodology == "rule_based_regime_v1"


# ------------------------------------------------------------ routes


def test_markets_endpoints_are_honest_about_data():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        overview = client.get("/markets/overview")
        assert overview.status_code == 200
        body = overview.json()
        # Indicators without a provider are unavailable, not fabricated.
        assert all(ind["status"] == "unavailable" for ind in body["indicators"])
        assert "regime" in body

        regime = client.get("/markets/regime").json()
        assert regime["methodology"] == "rule_based_regime_v1"
        # No provider configured (non-demo) -> insufficient, honestly.
        assert regime["label"] in {s.value for s in RegimeState}

        sectors = client.get("/markets/sectors").json()
        assert sectors["status"] == "unavailable"

        calendar = client.get("/markets/calendar").json()
        assert "events" in calendar
    finally:
        settings.broker_mode = orig
