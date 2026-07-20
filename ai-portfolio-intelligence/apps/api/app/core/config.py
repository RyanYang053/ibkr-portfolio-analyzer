from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.deployment_mode import DeploymentMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Portfolio Analyzer"
    environment: str = "development"
    deployment_mode: DeploymentMode = DeploymentMode.DEVELOPMENT
    database_url: str = "postgresql+psycopg://portfolio:portfolio@postgres:5432/portfolio"
    persistence_backend: Literal["json", "postgres"] = "json"
    jwt_secret: str = "dev-only-change-me"
    cors_origins: list[str] = ["http://localhost:3000", "tauri://localhost", "https://tauri.localhost"]
    broker_mode: str = "ibkr_readonly"
    local_api_host: str | None = None
    local_api_port: int | None = None
    local_session_token: str | None = None
    local_parent_pid: int | None = None
    desktop_owner_id: str = "local-owner"
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 4001
    ibkr_client_id: int = 10
    ibkr_account_id: Optional[str] = None
    ibkr_flex_token: Optional[str] = None
    ibkr_flex_query_id: Optional[str] = None
    ibkr_flex_activity_query_id: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    ai_timeout_seconds: float = 60.0
    allow_mock_options_strategy: bool = False
    risk_free_rate_annual: float = 0.0
    enable_strong_add_recommendations: bool = False
    disable_auth_enforcement: bool = False
    bootstrap_owner_email: str | None = None
    bootstrap_token: str | None = None
    allow_public_registration: bool = False
    access_token_hours: int = 12
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    trusted_proxies: list[str] = []
    audit_sensitive_keys: list[str] = [
        "password",
        "password_hash",
        "token",
        "secret",
        "api_key",
        "access_token",
        "refresh_token",
        "bootstrap_token",
        "jwt_secret",
        "ibkr_flex_token",
    ]
    allowed_ibkr_hosts: list[str] = ["127.0.0.1", "localhost"]
    api_bind_host: str = "127.0.0.1"
    scheduler_enabled: bool = True
    scheduler_run_in_api: bool = True
    scheduler_timezone: str = "America/New_York"
    scheduler_max_attempts: int = 3
    scheduler_lease_minutes: int = 30
    scheduler_readiness_grace_minutes: int = 15
    sec_edgar_user_agent: str | None = "PortfolioIntelligence/1.0 contact@example.com"
    sec_edgar_requests_per_second: float = 5.0
    sec_edgar_cache_hours: int = 24
    optimization_turnover_budget: float = 0.25
    optimization_liquidity_cap: float = 0.15
    optimization_participation_rate: float = 0.10
    optimization_max_exit_days: float = 5.0
    optimization_commission_bps: float = 5.0
    optimization_market_impact_bps: float = 10.0
    optimization_fx_conversion_bps: float = 2.0
    optimization_minimum_ticket_cost: float = 1.0
    optimization_transaction_cost_budget: float | None = None
    optimization_tax_budget: float | None = None
    optimization_return_shrinkage: float = 0.5
    default_reporting_currency: str = "USD"
    pnl_reconciliation_absolute_tolerance: float = 1.0
    pnl_reconciliation_tolerance_bps: float = 25.0
    snapshot_nav_tie_out_absolute_tolerance: float = 1.0
    snapshot_nav_tie_out_tolerance_bps: float = 10.0
    options_min_dte: int = 20
    options_max_dte: int = 60
    options_max_expirations: int = 3
    options_max_contracts: int = 80
    options_quote_timeout_seconds: float = 8.0
    options_greek_max_quote_age_minutes: int = 15
    options_min_open_interest: int = 50
    options_min_volume: int = 1
    attribution_reconciliation_tolerance: float = 1e-4


settings = Settings()


def is_desktop_local() -> bool:
    return settings.deployment_mode == DeploymentMode.DESKTOP_LOCAL


def validate_production_settings() -> None:
    from app.core.network_policy import assert_deployment_network_policy

    if is_desktop_local():
        bind_host = settings.local_api_host or settings.api_bind_host
        assert_deployment_network_policy(
            deployment_mode=settings.deployment_mode,
            bind_host=bind_host,
            database_url=settings.database_url,
            persistence_backend=settings.persistence_backend,
        )
        if settings.persistence_backend != "json":
            raise RuntimeError("Desktop v1 supports only the audited JSON state backend")
        if not settings.local_session_token or len(settings.local_session_token) < 43:
            raise RuntimeError("LOCAL_SESSION_TOKEN is required for DESKTOP_LOCAL mode")
        return

    if settings.environment == "development":
        return
    weak_secrets = {"", "change-me", "dev-only-change-me"}
    if settings.jwt_secret in weak_secrets:
        raise RuntimeError("A strong JWT_SECRET is required outside development")
    if settings.persistence_backend != "postgres":
        raise RuntimeError("PERSISTENCE_BACKEND=postgres is required outside development")
    if not settings.bootstrap_token:
        raise RuntimeError("BOOTSTRAP_TOKEN is required outside development when bootstrapping owners")
    if not settings.sec_edgar_user_agent or "example.com" in settings.sec_edgar_user_agent:
        raise RuntimeError("A real SEC EDGAR contact user agent is required")
