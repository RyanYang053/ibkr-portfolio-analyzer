"""Unit tests for greedy whole-share discrete allocation."""

from __future__ import annotations

import pytest

from app.services.portfolio_construction.discrete_allocation import greedy_whole_share_allocation


def test_floor_allocation_with_small_leftover():
    alloc = greedy_whole_share_allocation(
        {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2},
        {"AAA": 50.0, "BBB": 30.0, "CCC": 110.0},
        10_000.0,
    )
    assert alloc.shares == {"AAA": 100, "BBB": 100, "CCC": 18}
    assert alloc.leftover_cash == pytest.approx(20.0)
    assert alloc.allocated_value == pytest.approx(9_980.0)


def test_greedy_pass_spends_remaining_cash():
    alloc = greedy_whole_share_allocation(
        {"X": 0.5, "Y": 0.5}, {"X": 50.0, "Y": 50.0}, 175.0
    )
    # floor buys 1 each (100); greedy buys one more of the first most-underweight name
    assert alloc.shares == {"X": 2, "Y": 1}
    assert alloc.leftover_cash == pytest.approx(25.0)


def test_conservation_of_value():
    alloc = greedy_whole_share_allocation(
        {"A": 0.4, "B": 0.35, "C": 0.25},
        {"A": 12.34, "B": 87.65, "C": 5.01},
        50_000.0,
    )
    spent = sum(alloc.shares[s] * p for s, p in {"A": 12.34, "B": 87.65, "C": 5.01}.items() if s in alloc.shares)
    assert alloc.leftover_cash >= 0
    assert spent + alloc.leftover_cash == pytest.approx(50_000.0)
    assert alloc.allocated_value == pytest.approx(spent)


def test_zero_weight_symbols_ignored():
    alloc = greedy_whole_share_allocation(
        {"A": 1.0, "B": 0.0}, {"A": 100.0, "B": 25.0}, 1_000.0
    )
    assert "B" not in alloc.shares
    assert alloc.shares == {"A": 10}


def test_validation_errors():
    with pytest.raises(ValueError):
        greedy_whole_share_allocation({"A": 1.0}, {"A": 10.0}, 0.0)
    with pytest.raises(ValueError):
        greedy_whole_share_allocation({"A": 1.0}, {"A": 0.0}, 1_000.0)
    with pytest.raises(ValueError):
        greedy_whole_share_allocation({"A": -0.1}, {"A": 10.0}, 1_000.0)
    with pytest.raises(ValueError):
        greedy_whole_share_allocation({"A": 0.7, "B": 0.5}, {"A": 10.0, "B": 10.0}, 1_000.0)
    with pytest.raises(ValueError):
        greedy_whole_share_allocation({"A": 1.0}, {}, 1_000.0)
