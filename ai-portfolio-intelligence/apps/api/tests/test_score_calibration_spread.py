"""Top-minus-bottom quantile spread added to score calibration."""

from __future__ import annotations

from app.services.scoring.calibration import run_score_calibration


def test_quantile_spread_positive_for_monotonic_signal():
    observations = [{"score": float(s), "forward_return": s / 1000.0} for s in range(0, 100, 2)]
    report = run_score_calibration(observations, model_name="test")

    assert report.quantile_spread_top_minus_bottom is not None
    assert report.quantile_spread_top_minus_bottom > 0
    top = float(report.calibration_buckets[4]["average_forward_return"])
    bottom = float(report.calibration_buckets[0]["average_forward_return"])
    assert report.quantile_spread_top_minus_bottom == round(top - bottom, 4)


def test_quantile_spread_none_when_extreme_buckets_empty():
    report = run_score_calibration([{"score": 1.0, "forward_return": 0.01}], model_name="test")
    assert report.quantile_spread_top_minus_bottom is None
