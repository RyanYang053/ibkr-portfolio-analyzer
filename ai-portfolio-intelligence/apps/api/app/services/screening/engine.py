"""Screening engine (plan §8.2).

Deterministic filter evaluation over a candidate universe. Missing metrics are
reported as ``missing_data`` — a filter over an unavailable metric is never
silently treated as a pass. No result is a buy recommendation.
"""

from __future__ import annotations

from typing import Callable
from uuid import uuid4

from app.schemas.screener import (
    FilterOp,
    ScreenDefinition,
    ScreenResult,
    ScreenRun,
)

MetricResolver = Callable[[str], dict[str, float | None]]

_OPS = {
    FilterOp.GTE: lambda a, b: a >= b,
    FilterOp.LTE: lambda a, b: a <= b,
    FilterOp.GT: lambda a, b: a > b,
    FilterOp.LT: lambda a, b: a < b,
    FilterOp.EQ: lambda a, b: a == b,
}


def _criterion_label(field: str, op: FilterOp, value: float) -> str:
    return f"{field} {op.value} {value}"


def run_screen(
    definition: ScreenDefinition,
    *,
    account_id: str,
    universe: list[tuple[str, str]],
    metric_resolver: MetricResolver,
    owned_symbols: set[str],
    watchlist_symbols: set[str] | None = None,
) -> ScreenRun:
    watchlist_symbols = watchlist_symbols or set()
    results: list[ScreenResult] = []

    for symbol, instrument_id in universe:
        metrics = metric_resolver(symbol) or {}
        matched: list[str] = []
        failed: list[str] = []
        missing: list[str] = []

        for flt in definition.filters:
            label = _criterion_label(flt.field, flt.op, flt.value)
            metric = metrics.get(flt.field)
            if metric is None:
                missing.append(flt.field)
                continue
            if _OPS[flt.op](metric, flt.value):
                matched.append(label)
            else:
                failed.append(label)

        evaluated = len(matched) + len(failed)
        research_ready = evaluated == len(definition.filters) and not failed and bool(definition.filters)
        results.append(
            ScreenResult(
                result_id=f"sr_{uuid4().hex[:12]}",
                symbol=symbol,
                instrument_id=instrument_id,
                rank=0,  # assigned after sort
                matched_criteria=matched,
                failed_criteria=failed,
                missing_data=missing,
                portfolio_fit={
                    "already_owned": symbol in owned_symbols,
                    "on_watchlist": symbol in watchlist_symbols,
                    "match_ratio": round(len(matched) / len(definition.filters), 3) if definition.filters else None,
                },
                research_ready=research_ready,
            )
        )

    # Rank: most matched criteria first, then fewest missing.
    results.sort(key=lambda r: (-len(r.matched_criteria), len(r.missing_data), r.symbol))
    for index, result in enumerate(results, start=1):
        result.rank = index

    fully_covered = sum(1 for r in results if not r.missing_data)
    return ScreenRun(
        run_id=f"srun_{uuid4().hex[:16]}",
        screen_id=definition.screen_id,
        account_id=account_id,
        universe_size=len(universe),
        results=results,
        data_quality={
            "status": "available",
            "universe_size": len(universe),
            "fully_covered": fully_covered,
            "note": "Screen results are research candidates, not buy recommendations. "
            "Filters over unavailable metrics are reported as missing data.",
        },
    )
