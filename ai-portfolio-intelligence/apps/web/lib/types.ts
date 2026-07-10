export type Position = {
  account_id: string;
  symbol: string;
  company_name: string;
  asset_class: string;
  quantity: number;
  avg_cost: number;
  market_price: number;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  currency: string;
  exchange: string;
  sector: string;
  industry: string;
  portfolio_weight: number;
  stock_type: string;
  is_etf: boolean;
  is_speculative: boolean;
  updated_at: string;
};

export type PortfolioSummary = {
  summary: {
    account_id?: string;
    net_liquidation: number;
    cash: number;
    buying_power: number;
    margin_requirement: number;
    total_unrealized_pnl: number;
    total_realized_pnl: number;
    base_currency: string;
    data_timestamp: string;
  };
  risk: PortfolioRisk;
  positions: Position[];
  suitability_warnings?: string[];
};

export type PortfolioRisk = {
  total_value: number;
  risk_score: number;
  cash_percent: number;
  etf_percent: number;
  single_stock_percent: number;
  speculative_percent: number;
  sector_exposure: Record<string, number>;
  currency_exposure: Record<string, number>;
  top_5_concentration: number;
  herfindahl_concentration_score: number;
  herfindahl_concentration_label: string;
  margin_usage_percent: number;
  alerts: Alert[];
};

export type Alert = {
  alert_type: string;
  severity: "low" | "medium" | "high";
  symbol?: string;
  message: string;
};

export type Recommendation = {
  symbol: string;
  action: string;
  score: number | null;
  confidence: string;
  add_zone: string | null;
  hold_zone: string | null;
  trim_review_zone: string | null;
  exit_review_trigger: string | null;
  explanation: string;
  evidence: string[];
  human_review_reminder: string;
  disclaimer: string;
};

export type AIStatus = {
  provider: string;
  model: string;
  configured: boolean;
  mode: string;
  schedule: {
    enabled: boolean;
    interval_hours: number;
    last_run_at: string | null;
  };
};

export type BrokerStatus = {
  status: string;
  mode: string;
  host?: string;
  port?: string;
  client_id?: string;
  account_id?: string;
  error?: string;
  trading: string;
};

export type AIStockReport = {
  schema_version: string;
  symbol: string;
  company: string;
  portfolio_role: string;
  summary: EvidenceText | string;
  why_action: EvidenceText;
  business_summary: EvidenceText | string;
  fundamental_view: EvidenceText | string;
  valuation_view: EvidenceText | string;
  technical_view: EvidenceText | string;
  risk_view: EvidenceText | string;
  portfolio_fit: EvidenceText | string;
  final_score: number | null;
  rule_engine_action: string;
  action: string;
  add_zone: string | null;
  hold_zone: string | null;
  trim_review_zone: string | null;
  exit_review_trigger: string | null;
  confidence: string;
  confidence_limits: {
    confidence_cap: string;
    add_zone_allowed: boolean;
    action_override: string | null;
  };
  data_quality: {
    missing_categories: string[];
    missing_categories_count: number;
    stale_categories: string[];
    confidence_cap: string;
  };
  thesis: {
    status: string;
    status_reason: string;
    stored_thesis: string;
    invalidation_triggers: string[];
  };
  thesis_invalidation_triggers: string[];
  claims: Array<EvidenceText & { id: string; type: string }>;
  strengths: EvidenceText[];
  weaknesses: EvidenceText[];
  risks: EvidenceText[];
  main_evidence: EvidenceText[];
  main_risks: string[];
  missing_data: string[];
  human_review_required: boolean;
  disclaimer: string;
  provider: string;
  provider_error?: string;
  provenance?: {
    live_portfolio_data: boolean;
    live_market_data: boolean;
    cached_data: boolean;
    mock_fallback_data: boolean;
    web_grounded_context: boolean;
  };
};

export type EvidenceText = {
  text: string;
  evidence_ids: string[];
};

export type OptionsStrategyDetails = {
  name: string;
  type: string;
  expiration: string;
  strikes: string;
  net_credit_debit: number;
  max_profit: string;
  max_loss: string;
  breakeven: number;
  probability_of_profit: number;
  rationale: string;
  eligible: boolean;
  eligibility_reason: string;
};

export type OptionsStrategyReport = {
  symbol: string;
  stock_price: number;
  implied_volatility: number;
  iv_percentile: number;
  implied_move_percent: number;
  strategies: OptionsStrategyDetails[];
  market_sentiment: string;
  human_review_required: boolean;
  disclaimer: string;
  provider: string;
  provider_error?: string;
  asOf: string;
  dataSource: "IBKR" | "Polygon" | "Tradier" | "GeminiGroundedSearch" | "Mock";
  isMock: boolean;
  quoteDelaySeconds?: number;
  sourceUrls?: string[];
  warnings: string[];
  provenance?: {
    live_portfolio_data: boolean;
    live_market_data: boolean;
    cached_data: boolean;
    mock_fallback_data: boolean;
    web_grounded_context: boolean;
  };
};


