import asyncio
import logging
from datetime import datetime, date, time
import os

from app.services.broker.base import BrokerAdapter
from app.api.deps import get_broker_adapter
from app.services.portfolio.pnl_tracker import record_pnl_snapshot
from app.api.routes.ai import _load_settings, trigger_scheduled_analysis, ScheduledAnalyzeRequest

logger = logging.getLogger("scheduler")

async def run_background_scheduler():
    logger.info("Background scheduler daemon started")
    while True:
        try:
            settings = _load_settings()
            if settings.get("enabled"):
                now = datetime.now()
                today_str = date.today().isoformat()
                
                # Check for daily AI analysis slots
                morning_time_str = settings.get("morning_time", "09:30")
                midday_time_str = settings.get("midday_time", "12:30")
                night_time_str = settings.get("night_time", "20:00")
                
                # Load runs
                from app.api.routes.ai import _load_runs
                runs = _load_runs()
                
                # 1. Morning check
                m_hour, m_minute = map(int, morning_time_str.split(":"))
                m_time = time(m_hour, m_minute)
                if now.time() >= m_time:
                    has_morning = any(r.get("timestamp", "").startswith(today_str) and r.get("period") == "morning" for r in runs)
                    if not has_morning:
                        logger.info("Triggering scheduled morning analysis")
                        try:
                            adapter = get_broker_adapter()
                            trigger_scheduled_analysis(ScheduledAnalyzeRequest(period="morning"), adapter)
                        except Exception as e:
                            logger.error(f"Failed morning analysis: {e}")
                            
                # 2. Midday check
                mid_hour, mid_minute = map(int, midday_time_str.split(":"))
                mid_time = time(mid_hour, mid_minute)
                if now.time() >= mid_time:
                    has_midday = any(r.get("timestamp", "").startswith(today_str) and r.get("period") == "midday" for r in runs)
                    if not has_midday:
                        logger.info("Triggering scheduled midday analysis")
                        try:
                            adapter = get_broker_adapter()
                            trigger_scheduled_analysis(ScheduledAnalyzeRequest(period="midday"), adapter)
                        except Exception as e:
                            logger.error(f"Failed midday analysis: {e}")
                            
                # 3. Night check
                n_hour, n_minute = map(int, night_time_str.split(":"))
                n_time = time(n_hour, n_minute)
                if now.time() >= n_time:
                    has_night = any(r.get("timestamp", "").startswith(today_str) and r.get("period") == "night" for r in runs)
                    if not has_night:
                        logger.info("Triggering scheduled night analysis")
                        try:
                            adapter = get_broker_adapter()
                            trigger_scheduled_analysis(ScheduledAnalyzeRequest(period="night"), adapter)
                        except Exception as e:
                            logger.error(f"Failed night analysis: {e}")
                
                # 4. Market Close Snapshot check (4:00 PM / 16:00 local time)
                # Record a PnL snapshot on all accounts and consolidated if not already recorded today
                if now.time() >= time(16, 0) and now.weekday() < 5: # Monday to Friday
                    try:
                        adapter = get_broker_adapter()
                        accounts = adapter.get_accounts()
                        for acct in accounts:
                            from app.services.portfolio.pnl_tracker import get_pnl_history
                            history = get_pnl_history(acct.id)
                            has_snapshot = any(entry.date == today_str for entry in history)
                            if not has_snapshot:
                                logger.info(f"Triggering scheduled daily snapshot for account {acct.id}")
                                summary = adapter.get_account_summary(acct.id)
                                positions = adapter.get_positions(acct.id)
                                record_pnl_snapshot(summary, positions, acct.id)
                                
                        # Consolidated as well
                        from app.services.portfolio.pnl_tracker import get_pnl_history
                        history_all = get_pnl_history("all")
                        has_snapshot_all = any(entry.date == today_str for entry in history_all)
                        if not has_snapshot_all:
                            logger.info("Triggering scheduled daily consolidated snapshot")
                            from app.api.routes.portfolio import _get_consolidated_summary_and_positions
                            summary, positions = _get_consolidated_summary_and_positions(adapter)
                            record_pnl_snapshot(summary, positions, "all")
                    except Exception as e:
                        logger.error(f"Failed recording scheduled PnL snapshots: {e}")
                        
        except Exception as e:
            logger.error(f"Scheduler loop encountered error: {e}")
            
        await asyncio.sleep(60)
