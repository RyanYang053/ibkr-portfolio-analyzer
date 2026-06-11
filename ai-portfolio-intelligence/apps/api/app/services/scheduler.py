from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from app.api.deps import get_broker_adapter
from app.api.routes.ai import ScheduledAnalyzeRequest, _load_runs, _load_settings, trigger_scheduled_analysis
from app.services.portfolio.pnl_tracker import get_pnl_history, record_pnl_snapshot

logger = logging.getLogger("scheduler")

SCHEDULER_INTERVAL_SECONDS = 60
RUN_WINDOW_MINUTES = 10


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _slot_is_due(now: datetime, scheduled_time: time, already_ran: bool) -> bool:
    if already_ran:
        return False
    scheduled_at = datetime.combine(now.date(), scheduled_time)
    elapsed = now - scheduled_at
    return timedelta(0) <= elapsed <= timedelta(minutes=RUN_WINDOW_MINUTES)


def _run_scheduler_sync(now: datetime | None = None) -> None:
    settings = _load_settings()
    if not settings.get("enabled"):
        return

    current_time = now or datetime.now()
    today_str = current_time.date().isoformat()
    runs = _load_runs()
    adapter = None

    for period, setting_name, default_time in (
        ("morning", "morning_time", "09:30"),
        ("midday", "midday_time", "12:30"),
        ("night", "night_time", "20:00"),
    ):
        already_ran = any(
            run.get("timestamp", "").startswith(today_str) and run.get("period") == period
            for run in runs
        )
        try:
            due = _slot_is_due(
                current_time,
                _parse_time(str(settings.get(setting_name, default_time))),
                already_ran,
            )
        except ValueError:
            logger.error("Skipping invalid %s schedule value: %r", period, settings.get(setting_name))
            continue

        if not due:
            continue

        logger.info("Triggering scheduled %s analysis", period)
        try:
            adapter = adapter or get_broker_adapter()
            trigger_scheduled_analysis(ScheduledAnalyzeRequest(period=period), adapter)
        except Exception as exc:
            logger.error("Failed %s analysis: %s", period, exc)

    if current_time.weekday() >= 5:
        return

    snapshot_due = _slot_is_due(
        current_time,
        time(16, 0),
        already_ran=False,
    )
    if not snapshot_due:
        return

    try:
        adapter = adapter or get_broker_adapter()
        accounts = adapter.get_accounts()
        for account in accounts:
            history = get_pnl_history(account.id)
            if any(entry.date == today_str for entry in history):
                continue
            logger.info("Triggering scheduled daily snapshot for account %s", account.id)
            summary = adapter.get_account_summary(account.id)
            positions = adapter.get_positions(account.id)
            record_pnl_snapshot(summary, positions, account.id)

        if len(accounts) > 1:
            consolidated_history = get_pnl_history("all")
            if not any(entry.date == today_str for entry in consolidated_history):
                from app.api.routes.portfolio import _get_consolidated_summary_and_positions

                logger.info("Triggering scheduled daily consolidated snapshot")
                summary, positions = _get_consolidated_summary_and_positions(adapter)
                record_pnl_snapshot(summary, positions, "all")
    except Exception as exc:
        logger.error("Failed recording scheduled PnL snapshots: %s", exc)


async def run_background_scheduler() -> None:
    from starlette.concurrency import run_in_threadpool

    logger.info("Background scheduler daemon started")
    while True:
        try:
            await run_in_threadpool(_run_scheduler_sync)
        except Exception as exc:
            logger.error("Scheduler loop encountered error: %s", exc)
        await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
