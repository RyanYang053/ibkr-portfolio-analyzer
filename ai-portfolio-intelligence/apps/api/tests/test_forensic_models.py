"""Unit tests for app.services.valuation.forensic_models."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from app.services.valuation import forensic_models as fm


def test_altman_z_score_and_zone():
    inputs = fm.AltmanInputs(
        working_capital=200, retained_earnings=300, ebit=150,
        market_value_equity=800, total_liabilities=500, sales=1200, total_assets=1000,
    )
    # 0.24 + 0.42 + 0.495 + 0.96 + 1.2
    assert fm.altman_z_score(inputs) == pytest.approx(3.315)
    assert fm.altman_zone(3.315) == "safe"
    assert fm.altman_zone(2.0) == "grey"
    assert fm.altman_zone(1.0) == "distress"
    assert fm.altman_zone(None) == "unknown"


def test_altman_none_on_degenerate_balance_sheet():
    inputs = fm.AltmanInputs(0, 0, 0, 0, 0, 0, 0)
    assert fm.altman_z_score(inputs) is None


def test_beneish_no_change_company_is_not_a_manipulator():
    period = fm.BeneishPeriod(
        receivables=100, sales=1000, cost_of_goods_sold=600, current_assets=400, ppe=500,
        total_assets=1500, depreciation=50, sga=100, total_debt=300,
        net_income_continuing=80, cash_from_operations=80,
    )
    m = fm.beneish_m_score(period, period)
    assert m == pytest.approx(-2.48, abs=1e-9)
    assert fm.beneish_manipulation_flag(m) is False
    assert fm.beneish_manipulation_flag(None) is None


def test_graham_number():
    assert fm.graham_number(5.0, 20.0) == pytest.approx(math.sqrt(2250.0))
    assert fm.graham_number(-1.0, 20.0) is None
    assert fm.graham_number(5.0, None) is None


def test_dupont_decomposition_roe_consistency():
    result = fm.dupont_decomposition(net_income=100, revenue=1000, total_assets=2000, equity=800)
    assert result is not None
    assert result["net_margin"] == pytest.approx(0.1)
    assert result["asset_turnover"] == pytest.approx(0.5)
    assert result["equity_multiplier"] == pytest.approx(2.5)
    assert result["roe"] == pytest.approx(100 / 800)  # 0.125
    assert fm.dupont_decomposition(1, 0, 1, 1) is None


def test_wacc():
    assert fm.wacc(600, 400, 0.10, 0.05, 0.21) == pytest.approx(0.0758)
    assert fm.wacc(0, 0, 0.1, 0.05, 0.2) is None


def test_scores_from_snapshot():
    snap = SimpleNamespace(
        net_income_common=500, revenue=5000, diluted_shares=100, tangible_book_per_share=20
    )
    scores = fm.scores_from_snapshot(snap)
    assert scores["graham_number"] == pytest.approx(math.sqrt(22.5 * 5 * 20))
    assert scores["net_margin"] == pytest.approx(0.1)

    sparse = SimpleNamespace(net_income_common=None, revenue=None, diluted_shares=None, tangible_book_per_share=None)
    assert fm.scores_from_snapshot(sparse) == {"graham_number": None, "net_margin": None}
