from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.options.chain_provider import ChainResolution, OptionsChainUnavailable
from app.services.options import ibkr_options_provider as provider


def test_resolve_options_chain_raises_when_all_providers_fail(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")

    def _fail_ibkr(*_args, **_kwargs):
        raise RuntimeError("IBKR unavailable")

    def _fail_yahoo(*_args, **_kwargs):
        raise RuntimeError("Yahoo unavailable")

    monkeypatch.setattr(provider, "fetch_ibkr_options_chain", _fail_ibkr)
    monkeypatch.setattr("app.services.options.chain_provider.fetch_live_options_chain", _fail_yahoo)

    with pytest.raises(OptionsChainUnavailable) as exc_info:
        provider.resolve_options_chain("MSFT", 400.0)

    errors = exc_info.value.errors
    assert len(errors) == 2
    providers = {item["provider"] for item in errors}
    assert providers == {"IBKR", "LiveYahooOptions"}


def test_resolve_options_chain_returns_chain_resolution(monkeypatch):
    from datetime import date

    from app.services.options.engine import OptionContract

    contract = OptionContract(
        symbol="MSFT260116C00400000",
        strike=400,
        right="C",
        expiration=date(2026, 1, 16),
        bid=5,
        ask=5.2,
        mid=5.1,
        implied_volatility=0.25,
        provider="IBKR",
    )
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")
    monkeypatch.setattr(provider, "fetch_ibkr_options_chain", lambda *_a, **_k: [contract])

    resolution = provider.resolve_options_chain("MSFT", 400.0)
    assert isinstance(resolution, ChainResolution)
    assert resolution.selected_provider == "IBKR"
    assert resolution.contracts[0].provider == "IBKR"
    assert resolution.provider_attempts[0]["provider"] == "IBKR"
