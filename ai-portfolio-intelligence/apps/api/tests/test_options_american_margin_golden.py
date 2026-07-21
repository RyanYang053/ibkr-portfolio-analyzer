from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.methodology_registry import DEFAULT_METHODOLOGIES
from app.services.options.american_pricer import price_american, try_price_american
from app.services.options.regt_margin import estimate_regt_margin

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "options"


@pytest.mark.golden
def test_american_put_golden_fixture():
    payload = json.loads((FIXTURE_DIR / "american_put.json").read_text(encoding="utf-8"))
    inputs = payload["inputs"]
    price = price_american(
        inputs["spot"],
        inputs["strike"],
        inputs["t"],
        inputs["r"],
        inputs["q"],
        inputs["sigma"],
        inputs["steps"],
        inputs["option_type"],
    )
    expected = float(payload["expected"]["price"])
    tol = float(payload["expected"].get("tol_rel", 0.02))
    assert price == pytest.approx(expected, rel=tol)


@pytest.mark.golden
def test_regt_short_put_golden_fixture():
    payload = json.loads((FIXTURE_DIR / "regt_short_put.json").read_text(encoding="utf-8"))
    inputs = payload["inputs"]
    estimate = estimate_regt_margin(
        strategy=inputs["strategy"],
        underlying_price=inputs["underlying_price"],
        strike=inputs["strike"],
        shares=inputs["shares"],
        premium=inputs["premium"],
    )
    expected = float(payload["expected"]["requirement"])
    tol = float(payload["expected"].get("tol_abs", 0.01))
    assert estimate.requirement == pytest.approx(expected, abs=tol)
    assert estimate.order_generated is False
    assert estimate.methodology_id == "options_margin_regt"
    assert estimate.broker_equivalent is True


def test_american_pricer_withholds_invalid_inputs():
    price, exclusions = try_price_american(0, 100, 1, 0.05, 0, 0.2, 50, "put")
    assert price is None
    assert exclusions


def test_options_methodologies_registered_personal_use():
    by_id = {item.methodology_id: item for item in DEFAULT_METHODOLOGIES}
    assert by_id["options_american_pricer"].approval_status == "approved_for_personal_use"
    assert by_id["options_margin_regt"].approval_status == "approved_for_personal_use"
    assert by_id["options_american_pricer"].independent_validation_fixture.endswith("american_put.json")
    assert by_id["options_margin_regt"].independent_validation_fixture.endswith("regt_short_put.json")
