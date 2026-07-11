from __future__ import annotations

from datetime import date

import pytest

from app.core.config import settings
from app.db.option_contract_repo import OptionContractNotFoundError, get_contract, require_contract, upsert_contract
from app.services.options.engine import OptionContract


def _sample_contract(con_id: int = 12345) -> OptionContract:
    return OptionContract(
        symbol="MSFT260116C00400000",
        strike=400.0,
        right="C",
        expiration=date(2026, 1, 16),
        bid=5.0,
        ask=5.2,
        mid=5.1,
        implied_volatility=0.25,
        delta=0.45,
        gamma=0.01,
        vega=0.2,
        theta=-0.05,
        con_id=con_id,
        underlying_con_id=999,
        underlying_symbol="MSFT",
        local_symbol="MSFT  260116C00400000",
        multiplier=100.0,
        currency="USD",
        provider="IBKR",
        greeks_source="broker_model",
    )


def test_upsert_and_require_contract_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "persistence_backend", "json")
    contract = _sample_contract()
    upsert_contract(contract, source_batch_id="batch-1")
    loaded = get_contract(12345)
    assert loaded is not None
    assert loaded.strike == 400.0
    assert loaded.underlying_con_id == 999
    assert loaded.greeks_source == "broker_model"
    assert require_contract(12345).symbol == "MSFT"


def test_require_contract_raises_when_missing(monkeypatch):
    monkeypatch.setattr(settings, "persistence_backend", "json")
    with pytest.raises(OptionContractNotFoundError):
        require_contract(999999)
