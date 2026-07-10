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
    "Data Insufficient",
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
    # IBKR contract identity — retained through ingestion and consolidation.
    con_id: Optional[int] = None
    local_symbol: Optional[str] = None
    multiplier: float = 1.0
    price_source: str = "broker"


class Transaction(BaseModel):
    account_id: str
    symbol: str
    trade_date: date
    settlement_date: Optional[date] = None
    action: Literal[
        "buy",
        "sell",
        "dividend",
        "fee",
        "interest",
        "fx",
        "deposit",
        "withdrawal",
        "transfer",
        "transfer_in",
        "transfer_out",
        "contribution",
        "distribution",
        "corporate_action",
    ]
    quantity: float
    price: float
    commission: float
    currency: str
    fx_rate: Optional[float] = None
    source: str = "mock_ibkr_readonly"
    con_id: Optional[int] = None
    local_symbol: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: Optional[float] = None


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
    final_score: Optional[float]
    interpretation: str
    sub_scores: dict[str, float]
    explanation: str
    supporting_evidence: list[str]
    missing_data: list[str]
    confidence: ConfidenceLevel
    data_timestamp: datetime


class Provenance(BaseModel):
    live_portfolio_data: bool
    live_market_data: bool
    cached_data: bool
    mock_fallback_data: bool
    web_grounded_context: bool


class Recommendation(BaseModel):
    symbol: str
    action: ActionCategory
    score: Optional[float]
    confidence: ConfidenceLevel
    add_zone: Optional[str]
    hold_zone: Optional[str]
    trim_review_zone: Optional[str]
    exit_review_trigger: Optional[str]
    explanation: str
    evidence: list[str]
    data_freshness: dict[str, str]
    provenance: Optional[Provenance] = None
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
    atr_14: Optional[float]
    beta: Optional[float]
    volume_ratio: Optional[float]
    relative_strength_spy: Optional[float]
    relative_strength_qqq: Optional[float]
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
    provenance: Optional[Provenance] = None
    human_review_required: bool = True
    disclaimer: str = DISCLAIMER

    @property
    def risk_alerts(self) -> list[Any]:
        alerts = self.report_json.get("risk_alerts", [])
        return alerts if isinstance(alerts, list) else []


class InvestorProfile(BaseModel):
    objective: Literal["Growth", "Income", "Capital Preservation", "Speculation"]
    time_horizon_years: int
    risk_tolerance: Literal["Low", "Medium", "High"]
    risk_capacity: Literal["Low", "Medium", "High"]
    liquidity_needs: float
    net_worth_range: str
    tax_residency: Literal["US", "Canada", "Other"]
    account_type: Literal["Tax-Free", "Taxable", "Margin", "Corporate"]
    restrictions: list[str] = []


class InvestmentPolicyStatement(BaseModel):
    target_equity_percent: float
    target_cash_percent: float
    target_bond_percent: float
    max_single_stock_weight: float = 12.0
    max_speculative_weight: float = 5.0
    max_sector_weight: float = 35.0
    max_options_exposure: float = 3.0
    minimum_cash: float
    benchmark: str = "SPY"
    rebalancing_drift_threshold: float = 5.0


class RebalanceProposalItem(BaseModel):
    symbol: str
    current_weight: float
    target_weight: float
    current_value: float
    proposed_trade_value: float
    proposed_trade_qty: float
    action: Literal["Buy", "Sell", "Hold"]
    reason: str


class RebalanceProposal(BaseModel):
    proposed_trades: list[RebalanceProposalItem]
    cash_impact: float
    tax_impact_warning: str
    compliance_disclaimer: str = DISCLAIMER


class StressScenario(BaseModel):
    name: str
    description: str
    portfolio_change_pct: float
    estimated_loss: float
    risk_level: str


class AdvancedRiskMetrics(BaseModel):
    max_drawdown: Optional[float]
    volatility: Optional[float]
    portfolio_beta_spy: Optional[float]
    portfolio_beta_qqq: Optional[float]
    value_at_risk_95: Optional[float]
    conditional_var_95: Optional[float]
    historical_var_95: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    jensens_alpha: Optional[float] = None
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None
    correlation_matrix: dict[str, dict[str, float]]
    factor_exposures: dict[str, float]
    stress_tests: list[StressScenario]
    data_quality: dict[str, str]
    methodology: dict[str, str]


class PerformanceAttribution(BaseModel):
    security_selection_return: dict[str, float]
    sector_allocation_return: dict[str, float]
    asset_class_return: dict[str, float]
    realized_vs_unrealized: dict[str, float]
    benchmark_relative_alpha: Optional[float]
    data_quality: dict[str, str]
    methodology: str
    # Brinson-Fachler decomposition (allocation / selection / interaction).
    allocation_effect: Optional[float] = None
    selection_effect: Optional[float] = None
    interaction_effect: Optional[float] = None
    total_active_return: Optional[float] = None
    brinson_by_sector: dict[str, dict[str, float]] = Field(default_factory=dict)
    tax_lot_realized_by_symbol: dict[str, float] = Field(default_factory=dict)
    tax_lot_total_realized: Optional[float] = None


class PerformanceReturns(BaseModel):
    time_weighted_return: Optional[float]
    time_weighted_return_annualized: Optional[float]
    xirr: Optional[float]
    period_days: int
    observation_count: int
    daily_returns: list[dict[str, float | str]]
    benchmark_comparison: dict[str, float | str | None] = Field(default_factory=dict)
    data_quality: dict[str, str]
    methodology: str


class TaxLot(BaseModel):
    account_id: str
    symbol: str
    con_id: Optional[int] = None
    quantity: float
    cost_basis_per_share: float
    acquired_date: date
    currency: str
    source: str = "transaction_ledger"


class RealizedLotAttribution(BaseModel):
    symbol: str
    realized_gain_loss: float
    short_term_gain_loss: Optional[float] = None
    long_term_gain_loss: Optional[float] = None
    quantity_sold: float
    unmatched_sell_quantity: float = 0.0
    proceeds: float
    cost_basis: float
    holding_period_days: int = 0
    method: str = "fifo"


class TaxLotAttributionReport(BaseModel):
    account_id: str
    lots_open: list[TaxLot]
    realized_by_symbol: list[RealizedLotAttribution]
    total_realized_gain_loss: float
    total_short_term: float
    total_long_term: float
    reporting_currency: str = "USD"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    unmatched_sell_quantity: float = 0.0
    data_quality: dict[str, str]
    methodology: str


class FundamentalSnapshotRecord(BaseModel):
    symbol: str
    as_of_date: date
    snapshot: FundamentalSnapshot
    point_in_time: bool = True
    source: str
    report_period: Optional[str] = None
    ingested_at: Optional[datetime] = None
    synthetic_demo: bool = False


class ScoreCalibrationReport(BaseModel):
    model_name: str
    observation_count: int
    information_coefficient: Optional[float]
    rank_correlation: Optional[float]
    hit_rate_top_quintile: Optional[float]
    calibration_buckets: list[dict[str, float | int | str]]
    data_quality: dict[str, str]
    methodology: str



def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def recent_mock_date(days_ago: int = 1) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
