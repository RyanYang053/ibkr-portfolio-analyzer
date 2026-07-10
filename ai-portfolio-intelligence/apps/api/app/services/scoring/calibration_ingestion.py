from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from threading import Lock
from typing import Optional

from app.schemas.domain import ScoreCalibrationObservation
from app.services.scoring.calibration import load_calibration_observations, save_calibration_observations

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
PENDING_FILE = os.path.join(DATA_DIR, "score_calibration_pending.json")
_FILE_LOCK = Lock()
FORWARD_TRADING_DAYS = 63
BENCHMARK_SYMBOL = "SPY"


def _add_trading_days(start: date, trading_days: int) -> date:
    """Weekday-only maturity approximation. Exchange holidays are not modeled."""
    current = start
    remaining = trading_days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _load_pending() -> dict[str, list[dict]]:
    if not os.path.exists(PENDING_FILE):
        return {}
    with _FILE_LOCK, open(PENDING_FILE, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return raw if isinstance(raw, dict) else {}


def _save_pending(store: dict[str, list[dict]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with _FILE_LOCK:
        fd, temporary_path = tempfile.mkstemp(prefix="calibration_pending_", suffix=".tmp", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(store, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, PENDING_FILE)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def _period_total_return(symbol: str, start_date: date, end_date: date, allow_mock: bool) -> Optional[float]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(symbol.upper(), start_date, end_date, total_return=True)
    closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
    dates = sorted(closes)
    if len(dates) < 2 or closes[dates[0]] <= 0:
        return None
    return (closes[dates[-1]] / closes[dates[0]]) - 1.0


def record_score_observation(
    *,
    symbol: str,
    model_name: str,
    score: float,
    observed_on: Optional[date] = None,
    model_version: str,
    feature_snapshot_hash: str,
    input_sources: list[str],
    synthetic_demo: bool = False,
) -> None:
    if score is None:
        return
    observed = observed_on or date.today()
    store = _load_pending()
    bucket = store.setdefault(model_name, [])
    key = f"{symbol.upper()}:{observed.isoformat()}:{model_version}:{feature_snapshot_hash}"
    if any(item.get("key") == key for item in bucket):
        return
    bucket.append(
        {
            "key": key,
            "symbol": symbol.upper(),
            "model_name": model_name,
            "model_version": model_version,
            "feature_snapshot_hash": feature_snapshot_hash,
            "score": round(float(score), 4),
            "observed_on": observed.isoformat(),
            "input_sources": sorted(set(input_sources)),
            "synthetic_demo": synthetic_demo,
        }
    )
    _save_pending(store)


def materialize_calibration_observations(model_name: str, *, allow_mock: bool = False) -> int:
    """Promote matured pending score observations into the live calibration store."""
    pending_store = _load_pending()
    pending = list(pending_store.get(model_name, []))
    if not pending:
        return 0

    observations = load_calibration_observations(model_name, include_synthetic_demo=True)
    existing_keys = {
        str(item.get("key") or f"{item.get('symbol')}:{item.get('observed_on')}:{item.get('model_version')}")
        for item in observations
        if isinstance(item, dict)
    }
    promoted = 0
    remaining: list[dict] = []
    today = date.today()

    for item in pending:
        observed_on = date.fromisoformat(str(item["observed_on"]))
        maturity = _add_trading_days(observed_on, FORWARD_TRADING_DAYS)
        if maturity > today:
            remaining.append(item)
            continue
        key = str(item.get("key") or f"{item['symbol']}:{item['observed_on']}:{item.get('model_version', 'unknown')}")
        if key in existing_keys:
            continue
        forward_total = _period_total_return(str(item["symbol"]), observed_on, maturity, allow_mock=allow_mock)
        benchmark_total = _period_total_return(BENCHMARK_SYMBOL, observed_on, maturity, allow_mock=allow_mock)
        if forward_total is None or benchmark_total is None:
            remaining.append(item)
            continue
        forward_excess = forward_total - benchmark_total
        observation = ScoreCalibrationObservation(
            symbol=str(item["symbol"]),
            model_name=str(item.get("model_name") or model_name),
            model_version=str(item.get("model_version") or "unknown"),
            feature_snapshot_hash=str(item.get("feature_snapshot_hash") or ""),
            score=float(item["score"]),
            observed_on=observed_on,
            matured_on=maturity,
            forward_total_return=round(forward_total, 6),
            benchmark_total_return=round(benchmark_total, 6),
            forward_excess_return=round(forward_excess, 6),
            forward_return=round(forward_excess, 6),
            input_sources=list(item.get("input_sources") or []),
            synthetic_demo=bool(item.get("synthetic_demo")),
        )
        observations.append(observation.model_dump(mode="json"))
        existing_keys.add(key)
        promoted += 1

    pending_store[model_name] = remaining
    _save_pending(pending_store)
    if promoted:
        save_calibration_observations(model_name, observations)
    return promoted
