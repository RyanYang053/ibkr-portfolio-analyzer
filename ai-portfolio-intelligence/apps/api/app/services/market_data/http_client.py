from __future__ import annotations

import time
from typing import Any

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def request_with_retry(
    url: str,
    *,
    timeout: float = 5.0,
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
) -> httpx.Response:
    last_error: Exception | None = None
    with httpx.Client(headers=DEFAULT_HEADERS) as client:
        for attempt in range(max_attempts):
            try:
                response = client.get(url, timeout=timeout)
                if response.status_code == 200:
                    return response
                last_error = RuntimeError(f"HTTP {response.status_code} for {url}")
            except Exception as exc:
                last_error = exc
            if attempt + 1 < max_attempts:
                time.sleep(backoff_seconds * (attempt + 1))
    raise RuntimeError(f"Request failed for {url}") from last_error


def filter_rows_by_date(
    rows: list[dict[str, Any]],
    start_date,
    end_date,
) -> list[dict[str, Any]]:
    start_text = start_date.isoformat()
    end_text = end_date.isoformat()
    return [row for row in rows if start_text <= str(row.get("date", ""))[:10] <= end_text]
