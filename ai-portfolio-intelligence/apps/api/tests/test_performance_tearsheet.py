"""Tests for the performance tearsheet report builder."""

from __future__ import annotations

from app.services.reports.builders import build_performance_tearsheet, render_report_html

METRICS = {
    "sharpe_ratio": 1.2,
    "sortino_ratio": 1.5,
    "calmar_ratio": 0.9,
    "omega_ratio": 1.8,
    "information_ratio": 0.4,
    "volatility": 14.2,
    "max_drawdown": -12.3,
    "ulcer_index": 5.1,
    "pain_index": 3.2,
    "conditional_drawdown_at_risk_95": 9.4,
    "value_at_risk_95": 4500.0,
    "conditional_var_95": 6100.0,
    "tail_ratio": 1.1,
    "gain_to_pain_ratio": 0.8,
    "portfolio_beta_spy": 0.95,
    "up_capture": 1.05,
    "down_capture": 0.88,
    "up_down_capture": 1.19,
    "batting_average": 0.56,
}


def test_tearsheet_sections_available_and_mapped():
    report = build_performance_tearsheet(account_id="U1", as_of="2026-07-21", metrics=METRICS)
    assert report["report_type"] == "performance_tearsheet"
    assert report["risk_adjusted_ratios"]["status"] == "available"
    assert report["risk_adjusted_ratios"]["sharpe"] == 1.2
    assert report["risk_adjusted_ratios"]["omega"] == 1.8
    assert report["tail_risk"]["tail_ratio"] == 1.1
    assert report["market_capture"]["up_down_capture"] == 1.19


def test_tearsheet_marks_missing_sections_unavailable():
    report = build_performance_tearsheet(account_id="U1", as_of="2026-07-21", metrics={})
    for key in ("risk_adjusted_ratios", "volatility_and_drawdown", "tail_risk", "market_capture"):
        assert report[key]["status"] == "unavailable"


def test_tearsheet_renders_to_html():
    report = build_performance_tearsheet(account_id="U1", as_of="2026-07-21", metrics=METRICS)
    out = render_report_html(report)
    assert "<h1" in out
    assert "Performance Tearsheet" in out
    assert "sharpe" in out
