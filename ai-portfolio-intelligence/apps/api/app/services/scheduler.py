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
from app.services.scheduler_lease import SchedulerLeaseHeartbeat, SchedulerLeaseLost
from app.services.system_actor import SCHEDULER_ACTOR

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


def _scheduled_analysis_account_ids(adapter) -> list[str]:
    configured = settings.ibkr_account_id
    if configured:
        return [configured]
    return [account.id for account in adapter.get_accounts()]


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


def _run_scheduled_analysis_for_accounts(
    *,
    adapter,
    period: str,
    business_date: date,
    account_ids: list[str],
) -> None:
    for account_id in account_ids:
        slot = f"{period}:{account_id}"
        if job_already_completed("scheduled_analysis", account_id, business_date, slot):
            continue
        if not try_acquire_job("scheduled_analysis", account_id, business_date, slot):
            continue

        logger.info("Triggering scheduled %s analysis for account %s", period, account_id)
        try:
            with SchedulerLeaseHeartbeat("scheduled_analysis", account_id, business_date, slot) as lease:
                lease.assert_owned()
                result = run_scheduled_analysis(
                    period=period,
                    authorized_account_id=account_id,
                    adapter=adapter,
                    actor=SCHEDULER_ACTOR,
                )
                lease.assert_owned()
            if not complete_job(
                "scheduled_analysis",
                account_id,
                business_date,
                slot,
                status="completed",
                payload=result,
            ):
                raise SchedulerLeaseLost("Lost scheduler lease before completing scheduled analysis")
        except SchedulerLeaseLost:
            raise
        except Exception as exc:
            logger.error("Failed %s analysis for account %s: %s", period, account_id, exc)
            complete_job(
                "scheduled_analysis",
                account_id,
                business_date,
                slot,
                status="failed",
                error_message=str(exc),
            )


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

        adapter = adapter or get_broker_adapter()
        account_ids = _scheduled_analysis_account_ids(adapter)
        if not account_ids:
            continue
        _run_scheduled_analysis_for_accounts(
            adapter=adapter,
            period=period,
            business_date=business_date,
            account_ids=account_ids,
        )

    try:
        _run_weekly_backup_job(business_date=business_date, current_time=current_time)
    except SchedulerLeaseLost:
        raise
    except Exception as exc:
        logger.error("Failed weekly backup job: %s", exc)

    if current_time.weekday() >= 5:
        return

    try:
        if _slot_is_due(current_time, time(10, 0)) or _slot_is_due(current_time, time(15, 0)):
            adapter = adapter or get_broker_adapter()
            _run_decision_and_monitoring_jobs(adapter=adapter, business_date=business_date)
    except SchedulerLeaseLost:
        raise
    except Exception as exc:
        logger.error("Failed decision/monitoring evaluation jobs: %s", exc)

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
                if try_acquire_job("pnl_snapshot", account.id, business_date, slot):
                    complete_job("pnl_snapshot", account.id, business_date, slot, status="completed")
                continue
            if not try_acquire_job("pnl_snapshot", account.id, business_date, slot):
                continue
            logger.info("Triggering scheduled daily snapshot for account %s", account.id)
            try:
                with SchedulerLeaseHeartbeat("pnl_snapshot", account.id, business_date, slot) as lease:
                    lease.assert_owned()
                    summary = adapter.get_account_summary(account.id)
                    positions = adapter.get_positions(account.id)
                    from app.services.data_quality.validation import validate_and_gate_snapshot

                    validate_and_gate_snapshot(summary, positions)
                    lease.assert_owned()
                    record_pnl_snapshot(summary, positions, account.id)
                    _record_scheduled_score_snapshots(positions)
                    lease.assert_owned()
                if not complete_job("pnl_snapshot", account.id, business_date, slot, status="completed"):
                    raise SchedulerLeaseLost("Lost scheduler lease before completing PnL snapshot")
            except SchedulerLeaseLost:
                raise
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
                        logger.info("Triggering scheduled daily consolidated snapshot")
                        try:
                            with SchedulerLeaseHeartbeat("pnl_snapshot", "all", business_date, slot) as lease:
                                lease.assert_owned()
                                from app.api.routes.portfolio import _get_consolidated_summary_and_positions

                                account_ids = [account.id for account in accounts]
                                summary, positions = _get_consolidated_summary_and_positions(adapter, account_ids)
                                from app.services.data_quality.validation import validate_and_gate_snapshot

                                validate_and_gate_snapshot(summary, positions)
                                lease.assert_owned()
                                record_pnl_snapshot(summary, positions, "all")
                                lease.assert_owned()
                            if not complete_job("pnl_snapshot", "all", business_date, slot, status="completed"):
                                raise SchedulerLeaseLost("Lost scheduler lease before completing consolidated snapshot")
                        except SchedulerLeaseLost:
                            raise
                        except Exception as exc:
                            complete_job(
                                "pnl_snapshot",
                                "all",
                                business_date,
                                slot,
                                status="failed",
                                error_message=str(exc),
                            )
    except SchedulerLeaseLost:
        raise
    except Exception as exc:
        logger.error("Failed recording scheduled PnL snapshots: %s", exc)


def _run_weekly_backup_job(*, business_date: date, current_time: datetime) -> None:
    """Create a local desktop backup once per ISO week (no passphrase — zip only).

    Encrypted verify-restore remains a manual Settings action with the user's passphrase.
    """
    from app.core.config import is_desktop_local

    if not is_desktop_local():
        return
    if not _slot_is_due(current_time, time(17, 0)):
        return
    week_key = business_date.strftime("%G-W%V")
    job_name = "encrypted_backup"
    account_id = "desktop"
    slot = f"weekly:{week_key}"
    if job_already_completed(job_name, account_id, business_date, slot):
        return
    if not try_acquire_job(job_name, account_id, business_date, slot):
        return
    logger.info("Triggering weekly desktop backup for %s", week_key)
    try:
        with SchedulerLeaseHeartbeat(job_name, account_id, business_date, slot) as lease:
            lease.assert_owned()
            from app.core.desktop_bootstrap import backup_desktop_data

            path = backup_desktop_data(reason="scheduled_weekly")
            lease.assert_owned()
        payload = {
            "backup_path": str(path) if path else None,
            "week": week_key,
            "order_generated": False,
            "note": "Zip backup only; passphrase encryption and verify-restore are manual.",
        }
        if not complete_job(job_name, account_id, business_date, slot, status="completed", payload=payload):
            raise SchedulerLeaseLost("Lost scheduler lease before completing weekly backup")
    except SchedulerLeaseLost:
        raise
    except Exception as exc:
        complete_job(
            job_name,
            account_id,
            business_date,
            slot,
            status="failed",
            error_message=str(exc),
        )
        raise


def _run_decision_and_monitoring_jobs(*, adapter, business_date: date) -> None:
    """Periodic decision packet refresh and monitoring evaluation (lease/idempotent)."""
    account_ids = _scheduled_analysis_account_ids(adapter)
    for account_id in account_ids:
        for job_name, runner in (
            ("decision_evaluation", _evaluate_decisions_for_account),
            ("monitoring_evaluation", _evaluate_monitoring_for_account),
        ):
            slot = f"{job_name}:{account_id}"
            if job_already_completed(job_name, account_id, business_date, slot):
                continue
            if not try_acquire_job(job_name, account_id, business_date, slot):
                continue
            logger.info("Triggering %s for account %s", job_name, account_id)
            try:
                with SchedulerLeaseHeartbeat(job_name, account_id, business_date, slot) as lease:
                    lease.assert_owned()
                    payload = runner(adapter=adapter, account_id=account_id)
                    lease.assert_owned()
                if not complete_job(
                    job_name,
                    account_id,
                    business_date,
                    slot,
                    status="completed",
                    payload=payload,
                ):
                    raise SchedulerLeaseLost(f"Lost scheduler lease before completing {job_name}")
            except SchedulerLeaseLost:
                raise
            except Exception as exc:
                logger.error("Failed %s for account %s: %s", job_name, account_id, exc)
                complete_job(
                    job_name,
                    account_id,
                    business_date,
                    slot,
                    status="failed",
                    error_message=str(exc),
                )


def _evaluate_decisions_for_account(*, adapter, account_id: str) -> dict:
    try:
        from app.services.decision_center.orchestrator import evaluate_account_decisions

        return evaluate_account_decisions(adapter=adapter, account_id=account_id)
    except Exception as exc:
        return {
            "account_id": account_id,
            "order_generated": False,
            "status": "evaluation_failed",
            "error": str(exc),
            "fail_closed": True,
        }


def _evaluate_monitoring_for_account(*, adapter, account_id: str) -> dict:
    from app.services.decision_center.monitoring_service import run_monitoring_evaluation

    positions = adapter.get_positions(account_id)
    holdings = [
        {
            "symbol": p.symbol,
            "instrument_key": f"{p.symbol}:{p.con_id}" if p.con_id else p.symbol,
            "portfolio_weight": float(getattr(p, "portfolio_weight", 0) or 0),
        }
        for p in positions
        if getattr(p, "asset_class", None) not in {"OPT", "FOP", "CASH"}
    ]
    return run_monitoring_evaluation(account_id=account_id, holdings=holdings)


async def run_background_scheduler() -> None:
    from starlette.concurrency import run_in_threadpool

    logger.info("Background scheduler daemon started")
    while True:
        try:
            await run_in_threadpool(_run_scheduler_sync)
        except SchedulerLeaseLost as exc:
            logger.error("Scheduler loop lost lease ownership: %s", exc)
        except Exception as exc:
            logger.error("Scheduler loop encountered error: %s", exc)
        await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
