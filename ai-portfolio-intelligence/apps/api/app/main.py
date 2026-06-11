from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.api.routes import admin, ai, alerts, analysis, auth, broker, chat, pnl, portfolio, reports, stocks, watchlist
from app.core.config import settings
from app.services.scheduler import run_background_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background scheduler daemon
    scheduler_task = asyncio.create_task(run_background_scheduler())
    yield
    # Cancel background task on shutdown
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ai.router)
app.include_router(broker.router)
app.include_router(portfolio.router)
app.include_router(stocks.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.include_router(watchlist.router)
app.include_router(alerts.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(pnl.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "mode": settings.broker_mode, "trading": "disabled"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "positioning": "Read-only portfolio analysis and decision support. The system does not execute trades.",
    }
