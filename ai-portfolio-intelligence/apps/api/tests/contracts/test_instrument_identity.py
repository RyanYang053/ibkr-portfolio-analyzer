"""Instrument identity contracts."""

from __future__ import annotations

import pytest

from app.domain.instrument import InstrumentId, instrument_key


def test_conid_first_key() -> None:
    assert instrument_key("aapl", 265598) == "AAPL:265598"
    inst = InstrumentId(symbol="aapl", con_id=265598)
    assert inst.key == "AAPL:265598"
    assert inst.provisional is False


def test_symbol_only_is_provisional() -> None:
    inst = InstrumentId(symbol="XYZ")
    assert inst.provisional is True
    assert inst.key == "XYZ"


def test_empty_symbol_rejected() -> None:
    with pytest.raises(ValueError):
        InstrumentId(symbol="")
