from __future__ import annotations

import json
import os
from typing import Any

# Filepath mapping to apps/api/ai_reports.json
REPORTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "ai_reports.json")

def _load_reports() -> dict[str, dict[str, Any]]:
    if os.path.exists(REPORTS_FILE):
        try:
            with open(REPORTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# In-memory store initialized from file cache
_ai_reports_cache: dict[str, dict[str, Any]] = _load_reports()

def _save_reports() -> None:
    try:
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(_ai_reports_cache, f, indent=2)
    except Exception:
        pass

def get_cached_report(symbol: str) -> dict[str, Any] | None:
    return _ai_reports_cache.get(symbol.upper().strip())

def set_cached_report(symbol: str, report: dict[str, Any]) -> None:
    _ai_reports_cache[symbol.upper().strip()] = report
    _save_reports()
