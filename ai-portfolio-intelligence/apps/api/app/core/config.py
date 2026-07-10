from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "AI Portfolio Intelligence and Research System"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://portfolio:portfolio@postgres:5432/portfolio"
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
    # Explicit rather than a stale hard-coded market assumption. Configure from a
    # trusted source when risk-adjusted return metrics are required.
    risk_free_rate_annual: float = 0.0
    # Strong Add requires validated walk-forward calibration evidence.
    enable_strong_add_recommendations: bool = False


settings = Settings()
