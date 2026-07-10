from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "AI Portfolio Intelligence and Research System"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://portfolio:portfolio@postgres:5432/portfolio"
    persistence_backend: Literal["json", "postgres"] = "json"
    jwt_secret: str = "dev-only-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]
    broker_mode: str = "ibkr_readonly"
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
    allowed_ibkr_hosts: list[str] = ["127.0.0.1", "localhost"]
    api_bind_host: str = "127.0.0.1"
    scheduler_enabled: bool = True
    scheduler_run_in_api: bool = True
    scheduler_timezone: str = "America/New_York"


settings = Settings()


def validate_production_settings() -> None:
    if settings.environment == "development":
        return
    weak_secrets = {"", "change-me", "dev-only-change-me"}
    if settings.jwt_secret in weak_secrets:
        raise RuntimeError("A strong JWT_SECRET is required outside development")
    if settings.persistence_backend != "postgres":
        raise RuntimeError("PERSISTENCE_BACKEND=postgres is required outside development")
