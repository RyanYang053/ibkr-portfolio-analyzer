from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.api.deps import get_broker_adapter
from app.core.config import settings
from app.db.scheduler_store import complete_job, job_already_completed, try_acquire_job
from app.services.ai.scheduled_analysis_service import run_scheduled_analysis
from app.services.portfolio.pnl_tracker import get_pnl_history, record_pnl_snapshot
from app.services.scheduler_lease import SchedulerLeaseHeartbeat

logger = logging.getLogger("scheduler")

SCHEDULER_INTERVAL_SECONDS = 60
RUN_WINDOW_MINUTES = 10


def _market_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.scheduler_timezone)
    except Exception:
        return ZoneInfo("America/New_York")


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _slot_is_due(now: datetime, scheduled_time: time) -> bool:
    scheduled_at = datetime.combine(now.date(), scheduled_time, tzinfo=now.tzinfo)
    elapsed = now - scheduled_at
    return timedelta(0) <= elapsed <= timedelta(minutes=RUN_WINDOW_MINUTES)


def _ensure_timezone(current_time: datetime) -> datetime:
    if current_time.tzinfo is None:
        return current_time.replace(tzinfo=_market_timezone())
    return current_time


def _record_scheduled_score_snapshots(positions) -> None:
    from app.services.scoring.score_snapshot_store import save_daily_score_snapshot
    from app.services.scoring.stock_score import score_stock

    for position in positions:
        if position.quantity <= 0:
            continue
        try:
            score = score_stock(position, record_observations=True)
            save_daily_score_snapshot("scheduler", score)
        except Exception as exc:
            logger.warning("Skipping scheduled score snapshot for %s: %s", position.symbol, exc)


def _run_scheduler_sync(now: datetime | None = None) -> None:
    from app.api.routes.ai import _load_settings

    schedule_settings = _load_settings()
    if not schedule_settings.get("enabled"):
        return

    current_time = _ensure_timezone(now or datetime.now(_market_timezone()))
    business_date = current_time.date()
    adapter = None

    for period, setting_name, default_time in (
        ("morning", "morning_time", "09:30"),
        ("midday", "midday_time", "12:30"),
        ("night", "night_time", "20:00"),
    ):
        if job_already_completed("scheduled_analysis", None, business_date, period):
            continue
        try:
            due = _slot_is_due(
                current_time,
                _parse_time(str(schedule_settings.get(setting_name, default_time))),
            )
        except ValueError:
            logger.error("Skipping invalid %s schedule value: %r", period, schedule_settings.get(setting_name))
            continue

        if not due:
            continue
        if not try_acquire_job("scheduled_analysis", None, business_date, period):
            continue

        logger.info("Triggering scheduled %s analysis", period)
        try:
            adapter = adapter or get_broker_adapter()
            with SchedulerLeaseHeartbeat("scheduled_analysis", None, business_date, period):
                run_scheduled_analysis(
                    period=period,
                    account_id=settings.ibkr_account_id,
                    adapter=adapter,
                    principal_user_id="scheduler-system",
                )
            complete_job("scheduled_analysis", None, business_date, period, status="completed")
        except Exception as exc:
            logger.error("Failed %s analysis: %s", period, exc)
            complete_job(
                "scheduled_analysis",
                None,
                business_date,
                period,
                status="failed",
                error_message=str(exc),
            )

    if current_time.weekday() >= 5:
        return

    if not _slot_is_due(current_time, time(16, 0)):
        return

    try:
        adapter = adapter or get_broker_adapter()
        accounts = adapter.get_accounts()
        for account in accounts:
            slot = f"snapshot:{account.id}"
            if job_already_completed("pnl_snapshot", account.id, business_date, slot):
                continue
            history = get_pnl_history(account.id)
            if any(entry.date == business_date.isoformat() for entry in history):
                complete_job("pnl_snapshot", account.id, business_date, slot, status="completed")
                continue
            if not try_acquire_job("pnl_snapshot", account.id, business_date, slot):
                continue
            logger.info("Triggering scheduled daily snapshot for account %s", account.id)
            try:
                summary = adapter.get_account_summary(account.id)
                positions = adapter.get_positions(account.id)
                from app.services.data_quality.validation import validate_and_gate_snapshot

                validate_and_gate_snapshot(summary, positions)
                record_pnl_snapshot(summary, positions, account.id)
                _record_scheduled_score_snapshots(positions)
                complete_job("pnl_snapshot", account.id, business_date, slot, status="completed")
            except Exception as exc:
                complete_job(
                    "pnl_snapshot",
                    account.id,
                    business_date,
                    slot,
                    status="failed",
                    error_message=str(exc),
                )

        if len(accounts) > 1:
            slot = "snapshot:all"
            if not job_already_completed("pnl_snapshot", "all", business_date, slot):
                consolidated_history = get_pnl_history("all")
                if not any(entry.date == business_date.isoformat() for entry in consolidated_history):
                    if try_acquire_job("pnl_snapshot", "all", business_date, slot):
                        from app.api.routes.portfolio import _get_consolidated_summary_and_positions

                        logger.info("Triggering scheduled daily consolidated snapshot")
                        try:
                            account_ids = [account.id for account in accounts]
                            summary, positions = _get_consolidated_summary_and_positions(adapter, account_ids)
                            from app.services.data_quality.validation import validate_and_gate_snapshot

                            validate_and_gate_snapshot(summary, positions)
                            record_pnl_snapshot(summary, positions, "all")
                            complete_job("pnl_snapshot", "all", business_date, slot, status="completed")
                        except Exception as exc:
                            complete_job(
                                "pnl_snapshot",
                                "all",
                                business_date,
                                slot,
                                status="failed",
                                error_message=str(exc),
                            )
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
