import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.routes import (
    ai,
    alerts,
    analysis,
    broker,
    chat,
    construction,
    data_health,
    decision_center,
    decisions,
    desktop,
    health,
    instruments,
    journal,
    markets,
    methodologies,
    monitoring,
    planning,
    pnl,
    portfolio,
    reports,
    research,
    stocks,
    trade_plans,
    watchlist,
)
from app.core.config import is_desktop_local, settings, validate_production_settings
from app.core.local_runtime import load_local_runtime_from_env
from app.core.request_context import activate_request_context, clear_request_context
from app.middleware.local_session import LocalSessionMiddleware
from app.services.scheduler import run_background_scheduler


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        source_ip = request.client.host if request.client else None
        activate_request_context(request_id=request_id, source_ip=source_ip)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_settings()
    if is_desktop_local():
        from app.core.desktop_bootstrap import bootstrap_desktop_persistence

        bootstrap_desktop_persistence()

    from app.db.broker_config_repo import apply_persisted_broker_config

    apply_persisted_broker_config()
    scheduler_task = None
    if settings.scheduler_enabled and settings.scheduler_run_in_api:
        scheduler_task = asyncio.create_task(run_background_scheduler())
    yield
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Read-only AI portfolio intelligence and research API.",
    lifespan=lifespan,
)

# Middleware is LIFO: last added runs first on the request.
app.add_middleware(RequestContextMiddleware)

_local_runtime = load_local_runtime_from_env()
if _local_runtime is not None:
    app.add_middleware(LocalSessionMiddleware, runtime=_local_runtime)

# CORS must be outermost so OPTIONS preflight never hits the session gate.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(desktop.router)
if not is_desktop_local():
    from app.api.routes import admin, auth

    app.include_router(auth.router)
    app.include_router(admin.router)
app.include_router(ai.router)
app.include_router(broker.router)
app.include_router(portfolio.router)
app.include_router(instruments.router)
app.include_router(markets.router)
app.include_router(decision_center.router)
app.include_router(decisions.router)
app.include_router(planning.router)
app.include_router(construction.router)
app.include_router(research.router)
app.include_router(trade_plans.router)
app.include_router(journal.router)
app.include_router(monitoring.router)
app.include_router(data_health.router)
app.include_router(methodologies.router)
app.include_router(stocks.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.include_router(watchlist.router)
app.include_router(alerts.router)
app.include_router(chat.router)
app.include_router(pnl.router)

if is_desktop_local():
    from app.api.routes import desktop_secrets

    app.include_router(desktop_secrets.router)


@app.get("/health")
def legacy_health() -> dict[str, str]:
    return {"status": "healthy", "mode": settings.broker_mode, "trading": "disabled", "live": "/health/live", "ready": "/health/ready"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "positioning": "Read-only portfolio analysis and decision support. The system does not execute trades.",
    }
