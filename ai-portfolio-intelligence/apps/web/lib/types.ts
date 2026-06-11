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
  score: number;
  confidence: string;
  add_zone: string;
  hold_zone: string;
  trim_review_zone: string;
  exit_review_trigger: string;
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
  summary: string;
  why_action: EvidenceText;
  business_summary: string;
  fundamental_view: string;
  valuation_view: string;
  technical_view: string;
  risk_view: string;
  portfolio_fit: string;
  final_score: number;
  rule_engine_action: string;
  action: string;
  add_zone: string | null;
  hold_zone: string;
  trim_review_zone: string;
  exit_review_trigger: string;
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
};

export type EvidenceText = {
  text: string;
  evidence_ids: string[];
};
