"""Demo mode must be able to consolidate its own multi-currency accounts.

The mock broker ships a USD account and a CAD account, so Consolidated View
needs a CAD/USD cross rate. Sourcing that rate live made the demo's headline
view fail on any machine that could not reach the FX endpoint — in a product
that otherwise runs entirely offline.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.broker import ibkr_readonly


@pytest.fixture(autouse=True)
def clear_fx_cache():
    with ibkr_readonly._fx_cache_lock:
        ibkr_readonly._fx_cache.clear()
    yield
    with ibkr_readonly._fx_cache_lock:
        ibkr_readonly._fx_cache.clear()


@pytest.fixture()
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")


def _fail_on_network(*args, **kwargs):
    raise AssertionError("demo mode must not reach the network for FX")


def test_demo_mode_resolves_cross_rate_without_network(demo_mode, monkeypatch):
    monkeypatch.setattr(ibkr_readonly, "_fetch_current_fx_quote", _fail_on_network)

    quote = ibkr_readonly.get_exchange_rate_quote("CAD", "USD")

    assert quote.rate > 0
    # The rate is labelled, so no caller can present it as an observed market
    # rate the way a silent fallback would.
    assert quote.source == "mock_fx"


def test_demo_mode_rate_is_deterministic(demo_mode):
    first = ibkr_readonly.get_exchange_rate("CAD", "USD")
    second = ibkr_readonly.get_exchange_rate("CAD", "USD")
    assert first == second

    # Inverse pairs must agree, or consolidation would not round-trip.
    assert ibkr_readonly.get_exchange_rate("USD", "CAD") == pytest.approx(1 / first, rel=1e-9)


def test_identity_pair_is_never_mocked(demo_mode):
    quote = ibkr_readonly.get_exchange_rate_quote("USD", "USD")
    assert quote.rate == 1.0
    assert quote.source == "identity"


def test_live_mode_still_fails_closed_when_no_rate_is_observable(monkeypatch):
    """Demo fallbacks must not leak into a live broker session."""
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")

    def _unreachable(pair):
        raise RuntimeError(f"Live FX rate unavailable for {pair[0]}/{pair[1]}")

    monkeypatch.setattr(ibkr_readonly, "_fetch_current_fx_quote", _unreachable)

    with pytest.raises(RuntimeError, match="Live FX rate unavailable"):
        ibkr_readonly.get_exchange_rate_quote("CAD", "USD")


def test_unknown_pair_in_demo_mode_still_fails_closed(demo_mode, monkeypatch):
    """A currency the demo does not model must not silently invent a rate."""

    def _unreachable(pair):
        raise RuntimeError(f"Live FX rate unavailable for {pair[0]}/{pair[1]}")

    monkeypatch.setattr(ibkr_readonly, "_fetch_current_fx_quote", _unreachable)

    with pytest.raises(RuntimeError, match="Live FX rate unavailable"):
        ibkr_readonly.get_exchange_rate_quote("JPY", "USD")
