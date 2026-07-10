from __future__ import annotations

import json
import os
from statistics import mean
from typing import Literal, Optional

from app.schemas.domain import ScoreCalibrationReport

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CALIBRATION_FILE = os.path.join(DATA_DIR, "score_calibration_observations.json")


def _load_store() -> dict[str, list[dict[str, float | str]]]:
    if not os.path.exists(CALIBRATION_FILE):
        return {}
    try:
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_store(store: dict[str, list[dict[str, float | str]]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2)


def save_calibration_observations(model_name: str, observations: list[dict[str, float | str]]) -> None:
    store = _load_store()
    store[model_name] = observations
    _save_store(store)


def load_calibration_observations(model_name: str) -> list[dict[str, float | str]]:
    return list(_load_store().get(model_name, []))


def get_calibration_status(model_name: str) -> Literal["sufficient", "insufficient"]:
    report = run_score_calibration(load_calibration_observations(model_name), model_name=model_name)
    status = report.data_quality.get("status", "insufficient")
    return "sufficient" if status == "sufficient" else "insufficient"


def demo_calibration_observations() -> list[dict[str, float | str]]:
    return [
        {"symbol": "MSFT", "score": 82.0, "forward_return": 0.12},
        {"symbol": "META", "score": 78.0, "forward_return": 0.09},
        {"symbol": "IONQ", "score": 48.0, "forward_return": -0.08},
        {"symbol": "QQQ", "score": 74.0, "forward_return": 0.07},
        {"symbol": "SOFI", "score": 55.0, "forward_return": 0.01},
        {"symbol": "NKE", "score": 42.0, "forward_return": -0.04},
        {"symbol": "CRM", "score": 69.0, "forward_return": 0.05},
        {"symbol": "GOOGL", "score": 76.0, "forward_return": 0.08},
        {"symbol": "LAES", "score": 35.0, "forward_return": -0.15},
        {"symbol": "SPY", "score": 71.0, "forward_return": 0.06},
        {"symbol": "CELH", "score": 58.0, "forward_return": 0.02},
        {"symbol": "INFQ", "score": 31.0, "forward_return": -0.12},
        {"symbol": "SOXX", "score": 73.0, "forward_return": 0.10},
        {"symbol": "AAPL", "score": 80.0, "forward_return": 0.11},
        {"symbol": "NVDA", "score": 84.0, "forward_return": 0.18},
        {"symbol": "TSLA", "score": 52.0, "forward_return": -0.02},
        {"symbol": "AMZN", "score": 77.0, "forward_return": 0.09},
        {"symbol": "MSFT", "score": 79.0, "forward_return": 0.06},
        {"symbol": "META", "score": 75.0, "forward_return": 0.04},
        {"symbol": "QQQ", "score": 72.0, "forward_return": 0.05},
    ]


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
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
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
    observations: list[dict[str, float | str]],
    model_name: str = "universal",
) -> ScoreCalibrationReport:
    """Walk-forward style calibration on (score, forward_return) pairs.

    Observations must include numeric `score` and `forward_return` keys.
    """
    usable = [
        item
        for item in observations
        if isinstance(item.get("score"), (int, float)) and isinstance(item.get("forward_return"), (int, float))
    ]
    scores = [float(item["score"]) for item in usable]
    forward_returns = [float(item["forward_return"]) for item in usable]

    information_coefficient = _pearson(scores, forward_returns)
    rank_correlation = _spearman(scores, forward_returns)

    hit_rate = None
    if len(usable) >= 10:
        cutoff = sorted(scores)[int(len(scores) * 0.8)]
        top_quintile = [forward_returns[index] for index, score in enumerate(scores) if score >= cutoff]
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
                forward_returns[index]
                for index, score in enumerate(scores)
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

    data_quality = {
        "observation_count": str(len(usable)),
        "minimum_required": "20 for stable IC estimates",
        "status": "sufficient" if len(usable) >= 20 else "insufficient",
    }
    methodology = (
        "Out-of-sample calibration ranks historical scores against realized forward returns. "
        "Information coefficient is Pearson correlation; rank correlation is Spearman. "
        "Top-quintile hit rate measures how often the highest scores preceded positive forward returns."
    )

    return ScoreCalibrationReport(
        model_name=model_name,
        observation_count=len(usable),
        information_coefficient=round(information_coefficient, 4) if information_coefficient is not None else None,
        rank_correlation=round(rank_correlation, 4) if rank_correlation is not None else None,
        hit_rate_top_quintile=round(hit_rate, 4) if hit_rate is not None else None,
        calibration_buckets=buckets,
        data_quality=data_quality,
        methodology=methodology,
    )
