from __future__ import annotations

import asyncio
import logging

from app.core.config import settings, validate_production_settings
from app.services.scheduler import run_background_scheduler

logger = logging.getLogger("scheduler-worker")


def _ensure_database_ready() -> None:
    from app.api.routes.health import _alembic_ready, _postgres_ready

    postgres_ok, postgres_detail = _postgres_ready()
    if not postgres_ok:
        raise RuntimeError(f"Postgres is not ready: {postgres_detail}")

    if settings.persistence_backend == "postgres":
        alembic_ok, alembic_detail = _alembic_ready()
        if not alembic_ok:
            raise RuntimeError(f"Database migrations are not current: {alembic_detail}")


async def main() -> None:
    validate_production_settings()
    _ensure_database_ready()
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
