from __future__ import annotations

import json
import os
from statistics import mean
from typing import Literal, Optional

from app.schemas.domain import ScoreCalibrationReport

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CALIBRATION_FILE = os.path.join(DATA_DIR, "score_calibration_observations.json")
MIN_EXPERIMENTAL_OBSERVATIONS = 20


def _load_store() -> dict[str, list[dict[str, float | str | bool | list[str]]]]:
    from app.db.legacy_bridge import read_json_with_legacy

    raw = read_json_with_legacy(
        "score_calibration",
        "observations",
        CALIBRATION_FILE if os.path.exists(CALIBRATION_FILE) else None,
        default={},
    )
    return raw if isinstance(raw, dict) else {}


def _save_store(store: dict[str, list[dict[str, float | str | bool | list[str]]]]) -> None:
    from app.db.legacy_bridge import write_json_state

    write_json_state("score_calibration", "observations", store)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2)


def save_calibration_observations(model_name: str, observations: list[dict]) -> None:
    store = _load_store()
    store[model_name] = observations
    _save_store(store)


def load_calibration_observations(
    model_name: str,
    *,
    include_synthetic_demo: bool = False,
) -> list[dict]:
    observations = list(_load_store().get(model_name, []))
    if include_synthetic_demo:
        return observations
    return [item for item in observations if not item.get("synthetic_demo")]


def _observation_forward_return(item: dict) -> Optional[float]:
    for key in ("forward_excess_return", "forward_return"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    forward_total = item.get("forward_total_return")
    benchmark_total = item.get("benchmark_total_return")
    if isinstance(forward_total, (int, float)) and isinstance(benchmark_total, (int, float)):
        return float(forward_total) - float(benchmark_total)
    if isinstance(forward_total, (int, float)):
        return float(forward_total)
    return None


def get_calibration_status(model_name: str) -> Literal["sufficient", "insufficient"]:
    report = run_score_calibration(load_calibration_observations(model_name), model_name=model_name)
    status = report.data_quality.get("status", "insufficient")
    return "sufficient" if status == "sufficient" else "insufficient"


def demo_calibration_observations() -> list[dict]:
    rows = [
        ("MSFT", 82.0, 0.12, 0.06),
        ("META", 78.0, 0.09, 0.03),
        ("IONQ", 48.0, -0.08, -0.11),
        ("QQQ", 74.0, 0.07, 0.01),
        ("SOFI", 55.0, 0.01, -0.02),
        ("NKE", 42.0, -0.04, -0.07),
        ("CRM", 69.0, 0.05, 0.02),
        ("GOOGL", 76.0, 0.08, 0.04),
        ("LAES", 35.0, -0.15, -0.18),
        ("SPY", 71.0, 0.06, 0.0),
        ("CELH", 58.0, 0.02, -0.01),
        ("INFQ", 31.0, -0.12, -0.15),
        ("SOXX", 73.0, 0.10, 0.07),
        ("AAPL", 80.0, 0.11, 0.08),
        ("NVDA", 84.0, 0.18, 0.15),
        ("TSLA", 52.0, -0.02, -0.05),
        ("AMZN", 77.0, 0.09, 0.06),
        ("MSFT", 79.0, 0.06, 0.03),
        ("META", 75.0, 0.04, 0.01),
        ("QQQ", 72.0, 0.05, 0.02),
    ]
    observations: list[dict] = []
    for symbol, score, forward_total, benchmark_total in rows:
        forward_excess = forward_total - benchmark_total
        observations.append(
            {
                "symbol": symbol,
                "model_name": "universal",
                "model_version": "demo",
                "feature_snapshot_hash": "demo",
                "score": score,
                "observed_on": "2024-01-01",
                "matured_on": "2024-04-01",
                "forward_total_return": forward_total,
                "benchmark_total_return": benchmark_total,
                "forward_excess_return": forward_excess,
                "forward_return": forward_excess,
                "input_sources": ["synthetic_demo"],
                "synthetic_demo": True,
            }
        )
    return observations


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        start = index
        while index + 1 < len(order) and values[order[index + 1]] == values[order[index]]:
            index += 1
        average_rank = (start + index) / 2.0 + 1.0
        for position in range(start, index + 1):
            ranks[order[position]] = average_rank
        index += 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=False))
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    if x_var <= 0 or y_var <= 0:
        return None
    return numerator / (x_var * y_var) ** 0.5


def _spearman(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    return _pearson(_rank(xs), _rank(ys))


def run_score_calibration(
    observations: list[dict],
    model_name: str = "universal",
) -> ScoreCalibrationReport:
    """Walk-forward calibration on (score, benchmark-relative forward return) pairs."""
    usable = []
    for item in observations:
        score = item.get("score")
        forward = _observation_forward_return(item)
        if isinstance(score, (int, float)) and forward is not None:
            usable.append((float(score), forward, item))

    scores = [score for score, _, _ in usable]
    forward_returns = [forward for _, forward, _ in usable]
    non_demo_count = sum(1 for _, _, item in usable if not item.get("synthetic_demo"))

    information_coefficient = _pearson(scores, forward_returns)
    rank_correlation = _spearman(scores, forward_returns)

    hit_rate = None
    if len(usable) >= 10:
        cutoff = sorted(scores)[int(len(scores) * 0.8)]
        top_quintile = [forward for score, forward, _ in usable if score >= cutoff]
        if top_quintile:
            hit_rate = sum(1 for value in top_quintile if value > 0) / len(top_quintile)

    buckets: list[dict[str, float | int | str]] = []
    if usable:
        minimum = min(scores)
        maximum = max(scores)
        width = (maximum - minimum) / 5.0 if maximum > minimum else 1.0
        for bucket_index in range(5):
            low = minimum + bucket_index * width
            high = minimum + (bucket_index + 1) * width
            members = [
                forward
                for score, forward, _ in usable
                if (score >= low if bucket_index > 0 else score >= low)
                and (score < high if bucket_index < 4 else score <= high)
            ]
            buckets.append(
                {
                    "bucket": f"{low:.1f}-{high:.1f}",
                    "count": len(members),
                    "average_forward_return": round(mean(members), 4) if members else 0.0,
                }
            )

    if non_demo_count >= 100 and information_coefficient is not None and information_coefficient >= 0.05:
        status = "validated"
    elif non_demo_count >= MIN_EXPERIMENTAL_OBSERVATIONS and information_coefficient is not None and information_coefficient < 0:
        status = "degraded"
    elif non_demo_count == 0 and len(usable) >= MIN_EXPERIMENTAL_OBSERVATIONS:
        status = "retired"
    elif non_demo_count >= MIN_EXPERIMENTAL_OBSERVATIONS:
        status = "experimental"
    elif len(usable) >= MIN_EXPERIMENTAL_OBSERVATIONS:
        status = "experimental"
    else:
        status = "insufficient"

    data_quality = {
        "observation_count": str(len(usable)),
        "non_demo_observation_count": str(non_demo_count),
        "minimum_required": f"{MIN_EXPERIMENTAL_OBSERVATIONS} non-demo, PIT-safe observations across regimes",
        "status": status,
        "return_basis": "benchmark_relative_excess",
    }
    methodology = (
        "Out-of-sample calibration ranks historical scores against realized benchmark-relative forward excess "
        "returns (security total return minus SPY total return over the same maturity window). "
        "Information coefficient is Pearson correlation; rank correlation is Spearman. "
        "The top-minus-bottom quantile spread is the highest score bucket's mean forward return less the "
        "lowest bucket's — positive means the model separates winners from losers. "
        "Observations remain experimental until enough non-demo, point-in-time-safe samples exist."
    )

    quantile_spread = None
    if len(buckets) == 5 and int(buckets[4]["count"]) > 0 and int(buckets[0]["count"]) > 0:
        quantile_spread = round(
            float(buckets[4]["average_forward_return"]) - float(buckets[0]["average_forward_return"]), 4
        )

    return ScoreCalibrationReport(
        model_name=model_name,
        observation_count=len(usable),
        information_coefficient=round(information_coefficient, 4) if information_coefficient is not None else None,
        rank_correlation=round(rank_correlation, 4) if rank_correlation is not None else None,
        hit_rate_top_quintile=round(hit_rate, 4) if hit_rate is not None else None,
        quantile_spread_top_minus_bottom=quantile_spread,
        calibration_buckets=buckets,
        data_quality=data_quality,
        methodology=methodology,
    )
