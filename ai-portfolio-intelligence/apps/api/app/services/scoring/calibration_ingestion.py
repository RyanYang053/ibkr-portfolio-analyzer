from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from threading import Lock
from typing import Optional

from app.services.scoring.calibration import load_calibration_observations, save_calibration_observations

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
PENDING_FILE = os.path.join(DATA_DIR, "score_calibration_pending.json")
_FILE_LOCK = Lock()
FORWARD_TRADING_DAYS = 63


def _add_trading_days(start: date, trading_days: int) -> date:
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


def record_score_observation(
    *,
    symbol: str,
    model_name: str,
    score: float,
    observed_on: Optional[date] = None,
) -> None:
    if score is None:
        return
    observed = observed_on or date.today()
    store = _load_pending()
    bucket = store.setdefault(model_name, [])
    key = f"{symbol.upper()}:{observed.isoformat()}"
    if any(item.get("key") == key for item in bucket):
        return
    bucket.append(
        {
            "key": key,
            "symbol": symbol.upper(),
            "score": round(float(score), 4),
            "observed_on": observed.isoformat(),
        }
    )
    _save_pending(store)


def _forward_return(symbol: str, start_date: date, end_date: date, allow_mock: bool) -> Optional[float]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(symbol.upper(), start_date, end_date, total_return=True)
    closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
    dates = sorted(closes)
    if len(dates) < 2 or closes[dates[0]] <= 0:
        return None
    return (closes[dates[-1]] / closes[dates[0]]) - 1.0


def materialize_calibration_observations(model_name: str, *, allow_mock: bool = False) -> int:
    """Promote matured pending score observations into the calibration store."""
    pending_store = _load_pending()
    pending = list(pending_store.get(model_name, []))
    if not pending:
        return 0

    observations = load_calibration_observations(model_name)
    existing_keys = {
        f"{item.get('symbol')}:{item.get('observed_on')}"
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
        key = str(item.get("key") or f"{item['symbol']}:{item['observed_on']}")
        if key in existing_keys:
            continue
        forward = _forward_return(str(item["symbol"]), observed_on, maturity, allow_mock=allow_mock)
        if forward is None:
            remaining.append(item)
            continue
        observations.append(
            {
                "symbol": item["symbol"],
                "score": float(item["score"]),
                "forward_return": round(forward, 6),
                "observed_on": item["observed_on"],
            }
        )
        existing_keys.add(key)
        promoted += 1

    pending_store[model_name] = remaining
    _save_pending(pending_store)
    if promoted:
        save_calibration_observations(model_name, observations)
    return promoted
