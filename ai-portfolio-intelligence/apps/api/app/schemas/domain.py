from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


DISCLAIMER = (
    "This is portfolio analysis and decision support only. "
    "The system does not execute trades. The user must independently review any "
    "suggestion before making investment decisions outside the platform."
)

ActionCategory = Literal[
    "Strong Add",
    "Add",
    "Hold",
    "Watch",
    "Trim Review",
    "Exit Review",
    "Avoid",
]

ConfidenceLevel = Literal["High", "Medium-High", "Medium", "Low"]


class BrokerAccount(BaseModel):
    id: str
    broker_name: str = "Interactive Brokers"
    account_number_hash: str
    account_alias: str
    account_type: str
    base_currency: str
    status: str
    last_sync_at: datetime


class AccountSummary(BaseModel):
    account_id: str
    net_liquidation: float
    cash: float
    buying_power: float
    margin_requirement: float
    excess_liquidity: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    base_currency: str
    data_timestamp: datetime


class Position(BaseModel):
    account_id: str
    symbol: str
    company_name: str
    asset_class: str
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0
    currency: str
    exchange: str
    sector: str
    industry: str
    portfolio_weight: float
    stock_type: str
    is_etf: bool = False
    is_speculative: bool = False
    updated_at: datetime


class Transaction(BaseModel):
    account_id: str
    symbol: str
    trade_date: date
    settlement_date: Optional[date] = None
    action: Literal["buy", "sell", "dividend", "fee", "interest", "fx", "deposit", "withdrawal"]
    quantity: float
    price: float
    commission: float
    currency: str
    fx_rate: Optional[float] = None
    source: str = "mock_ibkr_readonly"


class OpenOrderReadOnly(BaseModel):
    account_id: str
    symbol: str
    side: str
    quantity: float
    status: str
    note: str = "Read-only broker status. This application cannot modify or submit orders."


class Alert(BaseModel):
    alert_type: str
    severity: Literal["low", "medium", "high"]
    symbol: Optional[str] = None
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PortfolioRisk(BaseModel):
    total_value: float
    risk_score: float
    cash_percent: float
    etf_percent: float
    single_stock_percent: float
    speculative_percent: float
    sector_exposure: dict[str, float]
    currency_exposure: dict[str, float]
    top_5_concentration: float
    herfindahl_concentration_score: float
    herfindahl_concentration_label: str
    margin_usage_percent: float
    alerts: list[Alert]
    data_timestamp: datetime


class StockScore(BaseModel):
    symbol: str
    stock_type: str
    final_score: float
    interpretation: str
    sub_scores: dict[str, float]
    explanation: str
    supporting_evidence: list[str]
    missing_data: list[str]
    confidence: ConfidenceLevel
    data_timestamp: datetime


class Recommendation(BaseModel):
    symbol: str
    action: ActionCategory
    score: float
    confidence: ConfidenceLevel
    add_zone: str
    hold_zone: str
    trim_review_zone: str
    exit_review_trigger: str
    explanation: str
    evidence: list[str]
    data_freshness: dict[str, str]
    human_review_required: bool = True
    human_review_reminder: str = "Human review required before any investment decision."
    disclaimer: str = DISCLAIMER


class TechnicalIndicators(BaseModel):
    symbol: str
    date: date
    sma_20: float
    sma_50: float
    sma_100: float
    sma_200: float
    ema_8: float
    ema_21: float
    rsi_14: float
    macd: float
    macd_signal: float
    macd_histogram: float
    atr_14: float
    beta: float
    volume_ratio: float
    relative_strength_spy: float
    relative_strength_qqq: float
    drawdown_from_52w_high: float
    trend_classification: str


class FundamentalSnapshot(BaseModel):
    symbol: str
    period: str
    report_date: date
    revenue_growth_yoy: float
    gross_margin: float
    operating_margin: float
    free_cash_flow: float
    cash: float
    total_debt: float
    pe_forward: Optional[float]
    ev_sales: Optional[float]
    fcf_yield: Optional[float]
    source: str = "mock_fundamentals"


class AIReport(BaseModel):
    report_type: str
    title: str
    report_json: dict[str, Any]
    report_markdown: str
    data_timestamp: datetime
    confidence: ConfidenceLevel
    missing_data: list[str]
    human_review_required: bool = True
    disclaimer: str = DISCLAIMER

    @property
    def risk_alerts(self) -> list[Any]:
        alerts = self.report_json.get("risk_alerts", [])
        return alerts if isinstance(alerts, list) else []


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def recent_mock_date(days_ago: int = 1) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
