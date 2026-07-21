from __future__ import annotations

import json
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.account_deps import resolve_authorized_account_id, resolve_portfolio_scope_id
from app.api.auth_deps import Principal, get_current_principal, require_scope
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.core.audit import log_audit_action
from app.core.config import settings
from app.services.ai.client import GeminiClient, configure_runtime_gemini
from app.services.ai.report_generator import generate_ai_portfolio_memo, generate_stock_research_report
from app.services.ai.thesis_tracker import get_thesis, update_thesis
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import find_portfolio_position
from app.services.portfolio.snapshot import gate_professional_response

router = APIRouter(
    prefix="/ai",
    tags=["ai-research"],
    dependencies=[Depends(get_current_principal)],
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "schedule_settings.json")
RUNS_FILE = os.path.join(DATA_DIR, "schedule_runs.json")


class AIConfigureRequest(BaseModel):
    api_key: str = Field(min_length=10)
    model: str = "gemini-2.5-flash"


class ThesisUpdateRequest(BaseModel):
    thesis: str = Field(min_length=10)
    key_assumptions: list[str] = Field(default_factory=list)
    break_triggers: list[str] = Field(default_factory=list)


class AIScheduleSettings(BaseModel):
    enabled: bool
    morning_time: str = "09:30"
    midday_time: str = "12:30"
    night_time: str = "20:00"


class ScheduledAnalyzeRequest(BaseModel):
    period: str  # "morning" | "midday" | "night"


def _load_settings() -> dict[str, Any]:
    from app.db.legacy_bridge import read_json_with_legacy, write_json_state

    default = {
        "enabled": False,
        "morning_time": "09:30",
        "midday_time": "12:30",
        "night_time": "20:00",
    }
    data = read_json_with_legacy("ai_schedule", "settings", SETTINGS_FILE if os.path.exists(SETTINGS_FILE) else None, default=None)
    if isinstance(data, dict):
        return data
    write_json_state("ai_schedule", "settings", default)
    return default


def _save_settings(settings: dict[str, Any]) -> None:
    from app.db.legacy_bridge import write_json_state

    write_json_state("ai_schedule", "settings", settings)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def _seed_initial_runs() -> list[dict[str, Any]]:
    return []


def _load_runs() -> list[dict[str, Any]]:
    from app.db.legacy_bridge import read_json_with_legacy, write_json_state

    data = read_json_with_legacy("ai_schedule", "runs", RUNS_FILE if os.path.exists(RUNS_FILE) else None, default=None)
    if isinstance(data, list):
        return data
    runs = _seed_initial_runs()
    write_json_state("ai_schedule", "runs", runs)
    return runs


def _save_runs(runs: list[dict[str, Any]]) -> None:
    from app.db.legacy_bridge import write_json_state

    write_json_state("ai_schedule", "runs", runs)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RUNS_FILE, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)


@router.get("/status")
def ai_status() -> dict[str, object]:
    client = GeminiClient()
    settings = _load_settings()
    return {
        "provider": "gemini",
        "model": client.model,
        "configured": client.configured,
        "mode": "live_gemini" if client.configured else "deterministic_fallback",
        "schedule": settings,
    }


@router.post("/configure", dependencies=[Depends(require_scope("configuration:write"))])
def configure_ai(
    payload: AIConfigureRequest,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    if settings.environment != "development":
        raise HTTPException(
            status_code=403,
            detail="Runtime AI credential changes are disabled in production",
        )
    configure_runtime_gemini(payload.api_key, payload.model)
    client = GeminiClient()
    log_audit_action(
        action="ai_configured",
        object_type="configuration",
        object_id=payload.model,
        actor_id=principal.user_id,
    )
    return {
        "provider": "gemini",
        "model": client.model,
        "configured": client.configured,
        "mode": "live_gemini" if client.configured else "deterministic_fallback",
    }


def _get_filtered_runs(adapter: BrokerAdapter) -> list[dict[str, Any]]:
    from app.core.config import settings
    is_demo = settings.broker_mode == "mock_ibkr_readonly"
    runs = _load_runs()
    if not is_demo:
        runs = [r for r in runs if not r.get("is_mock")]
    return runs


@router.get("/schedule")
def get_schedule(adapter: BrokerAdapter = Depends(get_broker_adapter)) -> dict[str, object]:
    return {
        "settings": _load_settings(),
        "runs": _get_filtered_runs(adapter)
    }


@router.put("/schedule", dependencies=[Depends(require_scope("configuration:write"))])
def update_schedule(
    payload: AIScheduleSettings,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    settings = payload.model_dump()
    _save_settings(settings)
    log_audit_action(
        action="ai_schedule_updated",
        object_type="configuration",
        actor_id=principal.user_id,
        metadata=settings,
    )
    return {
        "settings": settings,
        "runs": _get_filtered_runs(adapter)
    }


@router.get("/thesis/{symbol}")
def read_thesis(symbol: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    from app.services.tenant_scope import tenant_user_id

    return get_thesis(symbol, user_id=tenant_user_id(principal))


@router.put("/thesis/{symbol}", dependencies=[Depends(require_scope("portfolio:write"))])
def write_thesis(
    symbol: str,
    payload: ThesisUpdateRequest,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    from app.services.tenant_scope import tenant_user_id

    res = update_thesis(
        symbol,
        payload.thesis,
        payload.key_assumptions,
        payload.break_triggers,
        user_id=tenant_user_id(principal),
    )
    log_audit_action(
        action="thesis_updated",
        object_type="security",
        object_id=symbol.upper(),
        actor_id=principal.user_id,
    )
    return res


@router.post("/analyze-stock/{symbol}")
def analyze_stock(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_portfolio_scope_id(account_id, adapter, principal)
    try:
        position = find_portfolio_position(symbol, adapter, active_id, con_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
    if position is not None:
        res = generate_stock_research_report(
            position,
            user_id=principal.user_id,
            account_id=active_id,
        )
        log_audit_action(
            action="ai_analysis_triggered",
            object_type="security",
            object_id=symbol.upper(),
            actor_id=principal.user_id,
            account_id=active_id,
            metadata={"provider": res.get("provider")},
        )
        return gate_professional_response(adapter, principal, active_id, res)
    raise HTTPException(status_code=404, detail="Symbol not found in portfolio")


@router.post("/analyze-portfolio")
def analyze_portfolio(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.api.routes.portfolio import _resolve_account_data
    from app.services.data_quality.validation import validate_and_gate_snapshot

    try:
        summary, positions = _resolve_account_data(adapter, account_id, principal)
        active_id = summary.account_id
        validate_and_gate_snapshot(summary, positions)
        from app.core.config import settings
        from app.services.analytics.run_collector import collect_portfolio_calculation_run_ids

        allow_mock = settings.broker_mode == "mock_ibkr_readonly"
        run_ids = collect_portfolio_calculation_run_ids(
            active_id,
            summary,
            positions,
            allow_mock=allow_mock,
        )
        res = generate_ai_portfolio_memo(
            summary,
            positions,
            user_id=principal.user_id,
            calculation_run_ids=run_ids,
        )
        log_audit_action(
            action="ai_analysis_triggered",
            object_type="portfolio",
            actor_id=principal.user_id,
            account_id=active_id,
            metadata={"provider": res.get("provider")},
        )
        return res
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.post("/scheduled-analyze")
def trigger_scheduled_analysis(
    payload: ScheduledAnalyzeRequest,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    """Trigger a mock or real scheduled daily slot analysis (Morning, Midday, Night)."""
    from app.services.ai.scheduled_analysis_service import run_scheduled_analysis
    from app.services.system_actor import SystemActor

    try:
        active_id = resolve_authorized_account_id(account_id, adapter, principal)
        return run_scheduled_analysis(
            period=payload.period,
            authorized_account_id=active_id,
            adapter=adapter,
            actor=SystemActor(actor_id=principal.user_id, purpose="manual_scheduled_analysis"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


def _get_fallback_analysis_text(period: str, net_liq: float, cash: float) -> str:
    """Return an honest fallback without fabricating market conditions or security facts."""
    label = {"morning": "Morning", "midday": "Midday", "night": "Night"}.get(period, "Scheduled")
    return f"""### **{label} Portfolio Data Check**

* **Portfolio Snapshot**: Net liquidation is ${net_liq:,.2f}; cash is ${cash:,.2f}.
* **Market Analysis**: Current market, technical, and catalyst data unavailable because Gemini analysis did not complete.
* **Decision Support**: No security action or price level is generated from incomplete data. Refresh after the missing data source is restored."""
