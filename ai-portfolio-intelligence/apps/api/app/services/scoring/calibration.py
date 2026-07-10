from __future__ import annotations

from statistics import mean
from typing import Optional

from app.schemas.domain import ScoreCalibrationReport


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
