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
    "High heuristic score",
    "Moderate heuristic score",
    "Low heuristic score",
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
    symbol: str = ""
    trade_date: date
    trade_timestamp: Optional[datetime] = None
    effective_timestamp: Optional[datetime] = None
    settlement_date: Optional[date] = None
    action: Literal[
        "buy",
        "sell",
        "dividend",
        "dividend_reversal",
        "fee",
        "fee_reversal",
        "interest",
        "interest_reversal",
        "withholding_tax",
        "withholding_tax_reversal",
        "fx",
        "deposit",
        "withdrawal",
        "transfer",
        "transfer_in",
        "transfer_out",
        "contribution",
        "distribution",
        "cash_in_lieu",
        "corporate_action",
    ]
    quantity: float = 0.0
    price: float = 0.0
    commission: float = 0.0
    currency: str
    fx_rate: Optional[float] = None
    source: str = "unspecified"
    source_batch_id: Optional[str] = None
    source_row_id: Optional[str] = None
    source_hash: Optional[str] = None
    con_id: Optional[int] = None
    local_symbol: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None

    @property
    def event_timestamp(self) -> datetime:
        if self.effective_timestamp is not None:
            return self.effective_timestamp
        if self.trade_timestamp is not None:
            return self.trade_timestamp
        return datetime.combine(self.trade_date, datetime.min.time(), tzinfo=timezone.utc)


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
    factor_coverage: dict[str, bool] = Field(default_factory=dict)
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
    con_id: Optional[int] = None
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
    atr_percent: Optional[float] = None
    realized_volatility_20d: Optional[float] = None
    beta: Optional[float]
    volume_ratio: Optional[float]
    relative_strength_spy: Optional[float]
    relative_strength_qqq: Optional[float]
    drawdown_from_52w_high: float
    trend_classification: str


class FundamentalFieldLineage(BaseModel):
    metric: str
    concept: str
    unit: str
    value: float
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    filed_date: Optional[date] = None
    accepted_at: Optional[datetime] = None
    accession: Optional[str] = None
    form: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    source_hash: Optional[str] = None
    derivation: str = "reported"
    source_ids: list[str] = Field(default_factory=list)


class FundamentalSnapshot(BaseModel):
    symbol: str
    period: str
    report_date: date
    currency: str = "USD"
    revenue: Optional[float] = None
    net_income_common: Optional[float] = None
    average_common_equity: Optional[float] = None
    tangible_common_equity: Optional[float] = None
    diluted_shares: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    free_cash_flow: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    cash: Optional[float] = None
    total_debt: Optional[float] = None
    pe_forward: Optional[float] = None
    ev_sales: Optional[float] = None
    fcf_yield: Optional[float] = None
    source: str = "mock_fundamentals"
    price_to_tangible_book: Optional[float] = None
    tangible_book_per_share: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_tangible_equity: Optional[float] = None
    net_interest_margin: Optional[float] = None
    ffo_per_share: Optional[float] = None
    affo_per_share: Optional[float] = None
    occupancy_rate: Optional[float] = None
    rate_base: Optional[float] = None
    rate_base_growth: Optional[float] = None
    allowed_roe: Optional[float] = None
    field_lineage: dict[str, FundamentalFieldLineage] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)


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
    con_id: int | None = None
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


class PortfolioOptimizationItem(BaseModel):
    symbol: str
    current_weight: float
    optimal_weight: float
    current_value: float
    proposed_trade_value: float
    proposed_trade_qty: float
    action: Literal["Buy", "Sell", "Hold"]
    reason: str


class TaxTransitionSummary(BaseModel):
    jurisdiction: str
    methodology_status: str
    sell_candidate_lot_ids: list[str] = Field(default_factory=list)
    blocked_lots: list[dict[str, str]] = Field(default_factory=list)
    estimated_tax: float = 0.0
    after_tax_feasible: bool = True
    exclusions: list[str] = Field(default_factory=list)


class PortfolioOptimizationProposal(BaseModel):
    objective: str
    proposed_trades: list[PortfolioOptimizationItem]
    expected_volatility: Optional[float] = None
    expected_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    modeled_sleeve_expected_volatility: Optional[float] = None
    modeled_sleeve_expected_return: Optional[float] = None
    modeled_sleeve_sharpe: Optional[float] = None
    standalone_sleeve_expected_return: Optional[float] = None
    standalone_sleeve_expected_volatility: Optional[float] = None
    standalone_sleeve_sharpe: Optional[float] = None
    portfolio_expected_return_contribution: Optional[float] = None
    portfolio_expected_volatility_contribution: Optional[float] = None
    modeled_portfolio_coverage_percent: Optional[float] = None
    constraints_applied: list[str] = Field(default_factory=list)
    methodology: str
    compliance_disclaimer: str = DISCLAIMER
    tax_transition: Optional[TaxTransitionSummary] = None
    tax_lot_ids_considered: list[str] = Field(default_factory=list)


class StressScenario(BaseModel):
    name: str
    description: str
    portfolio_change_pct: float
    estimated_loss: float
    risk_level: str


class AdvancedRiskMetrics(BaseModel):
    max_drawdown: Optional[float]
    volatility: Optional[float]
    ewma_volatility: Optional[float] = None
    portfolio_beta_spy: Optional[float]
    portfolio_beta_qqq: Optional[float]
    value_at_risk_95: Optional[float]
    conditional_var_95: Optional[float]
    historical_var_95: Optional[float] = None
    historical_es_95: Optional[float] = None
    filtered_historical_var_95: Optional[float] = None
    filtered_historical_es_95: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    jensens_alpha: Optional[float] = None
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    ulcer_index: Optional[float] = None
    max_drawdown_duration_days: Optional[int] = None
    recovery_duration_days: Optional[int] = None
    risk_contribution: dict[str, float] = Field(default_factory=dict)
    risk_contribution_pct: dict[str, float] = Field(default_factory=dict)
    marginal_volatility: dict[str, float] = Field(default_factory=dict)
    correlation_matrix: dict[str, dict[str, float]]
    factor_exposures: dict[str, float]
    measured_factor_exposures: dict[str, float] = Field(default_factory=dict)
    heuristic_style_classification: dict[str, float] = Field(default_factory=dict)
    factor_model_status: str = "withheld"
    factor_diagnostics: dict[str, object] = Field(default_factory=dict)
    component_volatility_daily: dict[str, float] = Field(default_factory=dict)
    component_volatility_annualized: dict[str, float] = Field(default_factory=dict)
    contribution_to_variance_percent: dict[str, float] = Field(default_factory=dict)
    marginal_volatility_daily: dict[str, float] = Field(default_factory=dict)
    marginal_volatility_annualized: dict[str, float] = Field(default_factory=dict)
    stress_tests: list[StressScenario]
    data_quality: dict[str, str]
    methodology: dict[str, str]
    calculation_run_id: Optional[str] = None


class PerformanceAttribution(BaseModel):
    current_unrealized_pnl_by_security: dict[str, float] = Field(default_factory=dict)
    current_unrealized_pnl_by_sector: dict[str, float] = Field(default_factory=dict)
    current_unrealized_pnl_by_asset_class: dict[str, float] = Field(default_factory=dict)
    security_selection_pnl: dict[str, float] = Field(default_factory=dict)
    sector_allocation_pnl: dict[str, float] = Field(default_factory=dict)
    asset_class_pnl: dict[str, float] = Field(default_factory=dict)
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
    report_title: str = "Current Unrealized P&L Decomposition"
    calculation_run_id: Optional[str] = None


class PerformanceReturns(BaseModel):
    time_weighted_return: Optional[float]
    time_weighted_return_annualized: Optional[float]
    modified_dietz_return: Optional[float] = None
    modified_dietz_return_annualized: Optional[float] = None
    return_methodology: str = "withheld"
    xirr: Optional[float]
    period_days: int
    observation_count: int
    daily_returns: list[dict[str, float | str]]
    benchmark_comparison: dict[str, float | str | None] = Field(default_factory=dict)
    data_quality: dict[str, str]
    methodology: str
    calculation_run_id: Optional[str] = None


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
    tax_realized_gain_loss: float
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
    total_realized_gain_loss: Optional[float] = None
    total_short_term: Optional[float] = None
    total_long_term: Optional[float] = None
    reporting_currency: str = "USD"
    jurisdiction: str = "OTHER"
    methodology_status: str = "experimental"
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
    filing_date: Optional[date] = None
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


class ScoreCalibrationObservation(BaseModel):
    symbol: str
    model_name: str
    model_version: str
    feature_snapshot_hash: str
    score: float
    observed_on: date
    matured_on: Optional[date] = None
    forward_total_return: Optional[float] = None
    benchmark_total_return: Optional[float] = None
    forward_excess_return: Optional[float] = None
    forward_return: Optional[float] = None
    input_sources: list[str] = Field(default_factory=list)
    synthetic_demo: bool = False


class SourceRecord(BaseModel):
    source_id: str
    source_type: str
    label: str
    as_of: Optional[datetime] = None
    url: Optional[str] = None


class DataQualityContext(BaseModel):
    ledger_status: str
    performance_status: str
    risk_status: str
    attribution_status: str
    notes: list[str] = Field(default_factory=list)


class PortfolioResearchContext(BaseModel):
    user_id: str
    account_id: str
    as_of: datetime
    reporting_currency: str
    performance_summary: dict[str, object] = Field(default_factory=dict)
    attribution_summary: dict[str, object] = Field(default_factory=dict)
    risk_summary: dict[str, object] = Field(default_factory=dict)
    exposure_summary: dict[str, object] = Field(default_factory=dict)
    holdings: list[dict[str, object]] = Field(default_factory=list)
    events: list[dict[str, object]] = Field(default_factory=list)
    policy_summary: dict[str, object] = Field(default_factory=dict)
    suitability_summary: dict[str, object] = Field(default_factory=dict)
    data_quality: DataQualityContext
    sources: list[SourceRecord] = Field(default_factory=list)
    calculation_run_ids: list[str] = Field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def recent_mock_date(days_ago: int = 1) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
