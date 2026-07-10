from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.services.scheduler import run_background_scheduler

logger = logging.getLogger("scheduler-worker")


async def main() -> None:
    if not settings.scheduler_enabled:
        logger.info("Scheduler worker disabled by configuration")
        return
    from app.db.broker_config_repo import apply_persisted_broker_config

    if apply_persisted_broker_config():
        logger.info("Applied persisted broker runtime configuration")
    logger.info("Starting dedicated scheduler worker")
    await run_background_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
