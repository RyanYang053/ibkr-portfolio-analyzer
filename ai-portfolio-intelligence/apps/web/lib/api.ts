import type { AIStatus, AIStockReport, Alert, BrokerStatus, PortfolioRisk, PortfolioSummary, Position, Recommendation, OptionsStrategyReport } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!response.ok) return fallback;
    return response.json();
  } catch {
    return fallback;
  }
}

const fallbackPositions: Position[] = [];

const fallbackRisk: PortfolioRisk = {
  total_value: 0,
  risk_score: 0,
  cash_percent: 0,
  etf_percent: 0,
  single_stock_percent: 0,
  speculative_percent: 0,
  sector_exposure: {},
  currency_exposure: {},
  top_5_concentration: 0,
  herfindahl_concentration_score: 0,
  herfindahl_concentration_label: "Disconnected",
  margin_usage_percent: 0,
  alerts: [
    { alert_type: "broker_not_connected", severity: "medium", message: "IBKR read-only connector is not configured. No mock portfolio data is being shown." }
  ]
};

export async function getPortfolioSummary(accountId?: string): Promise<PortfolioSummary> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const data = await getJson<PortfolioSummary>(`/portfolio/summary${query}`, {
    summary: {
      account_id: "DISCONNECTED",
      net_liquidation: 0,
      cash: 0,
      buying_power: 0,
      margin_requirement: 0,
      total_unrealized_pnl: 0,
      total_realized_pnl: 0,
      base_currency: "USD",
      data_timestamp: new Date().toISOString()
    },
    risk: fallbackRisk,
    positions: fallbackPositions
  });
  if (data && data.risk) {
    data.risk = { ...fallbackRisk, ...data.risk };
  }
  return data;
}

export async function getPositions(accountId?: string): Promise<Position[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return getJson<Position[]>(`/portfolio/positions${query}`, fallbackPositions);
}

export async function getRisk(accountId?: string): Promise<PortfolioRisk> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const risk = await getJson<PortfolioRisk>(`/portfolio/risk${query}`, fallbackRisk);
  return { ...fallbackRisk, ...risk };
}

export async function getAlerts(): Promise<Alert[]> {
  return getJson<Alert[]>("/alerts", fallbackRisk.alerts);
}

export async function getRecommendations(): Promise<Recommendation[]> {
  return getJson<Recommendation[]>("/recommendations", []);
}

export async function getAccounts(): Promise<any[]> {
  return getJson("/broker/accounts", []);
}

export async function getHoldingAnalysis(symbol: string): Promise<{ position: Position; recommendation: Recommendation; score: { final_score: number | null; interpretation: string; sub_scores: Record<string, number> }; last_ai_report?: AIStockReport | null }> {
  return getJson(`/stocks/${symbol}/analysis`, {
    position: {
      account_id: "DISCONNECTED",
      symbol,
      company_name: "IBKR not connected",
      asset_class: "UNKNOWN",
      quantity: 0,
      avg_cost: 0,
      market_price: 0,
      market_value: 0,
      unrealized_pnl: 0,
      realized_pnl: 0,
      currency: "USD",
      exchange: "",
      sector: "",
      industry: "",
      portfolio_weight: 0,
      stock_type: "unknown",
      is_etf: false,
      is_speculative: false,
      updated_at: new Date().toISOString()
    },
    recommendation: {
      symbol,
      action: "Data Insufficient",
      score: null,
      confidence: "Low",
      add_zone: null,
      hold_zone: null,
      trim_review_zone: null,
      exit_review_trigger: null,
      explanation: "IBKR read-only connector is not configured. Mock holding analysis is disabled.",
      evidence: ["broker_not_connected"],
      human_review_reminder: "Human review required before any investment decision.",
      disclaimer: "This is portfolio analysis and decision support only. The system does not execute trades."
    },
    score: { final_score: null, interpretation: "Data Insufficient", sub_scores: {} },
    last_ai_report: null
  });
}

export async function getReports() {
  return getJson("/reports", []);
}

export async function getWatchlist() {
  return getJson("/watchlist", []);
}

export async function getAuditLogs() {
  return getJson("/admin/audit-logs", []);
}

export async function getAIStatus(): Promise<AIStatus> {
  return getJson<AIStatus>("/ai/status", {
    provider: "gemini",
    model: "gemini-2.5-flash",
    configured: false,
    mode: "deterministic_fallback",
    schedule: { enabled: false, interval_hours: 24, last_run_at: null }
  });
}

export async function refreshAIStockReport(symbol: string): Promise<AIStockReport> {
  const response = await fetch(`${API_URL}/ai/analyze-stock/${symbol}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`AI analysis failed with status ${response.status}`);
  }
  return response.json();
}

export async function configureAI(apiKey: string, model: string): Promise<AIStatus & { api_key: string }> {
  const response = await fetch(`${API_URL}/ai/configure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, model })
  });
  if (!response.ok) {
    throw new Error(`AI configuration failed with status ${response.status}`);
  }
  return response.json();
}

export async function getBrokerStatus(): Promise<BrokerStatus> {
  return getJson<BrokerStatus>("/broker/status", {
    status: "not_connected",
    mode: "ibkr_readonly",
    host: "127.0.0.1",
    port: "4002",
    client_id: "10",
    trading: "disabled"
  });
}

export async function configureBrokerReadonly(payload: { mode: string; host: string; port: number; client_id: number; account_id?: string }) {
  const response = await fetch(`${API_URL}/broker/configure-readonly`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`IBKR configuration failed with status ${response.status}`);
  }
  return response.json();
}

export async function getTechnicals(symbol: string): Promise<{
  symbol: string;
  date: string;
  sma_20: number;
  sma_50: number;
  sma_100: number;
  sma_200: number;
  ema_8: number;
  ema_21: number;
  rsi_14: number | null;
  macd: number;
  macd_signal: number;
  macd_histogram: number;
  atr_14: number | null;
  beta: number | null;
  volume_ratio: number | null;
  relative_strength_spy: number | null;
  relative_strength_qqq: number | null;
  drawdown_from_52w_high: number | null;
  trend_classification: string | null;
  historical_prices: number[];
}> {
  return getJson(`/stocks/${symbol}/technicals`, {
    symbol,
    date: new Date().toISOString().split("T")[0],
    sma_20: 0,
    sma_50: 0,
    sma_100: 0,
    sma_200: 0,
    ema_8: 0,
    ema_21: 0,
    rsi_14: null,
    macd: 0,
    macd_signal: 0,
    macd_histogram: 0,
    atr_14: null,
    beta: null,
    volume_ratio: null,
    relative_strength_spy: null,
    relative_strength_qqq: null,
    drawdown_from_52w_high: null,
    trend_classification: null,
    historical_prices: []
  });
}

export async function getNews(symbol: string): Promise<Array<{
  symbol: string;
  title: string;
  summary: string;
  link: string;
  providerPublishTime: number;
  source: string;
}>> {
  return getJson(`/stocks/${symbol}/news`, []);
}

export async function getFundamentals(symbol: string): Promise<{
  symbol: string;
  period: string;
  report_date: string;
  revenue_growth_yoy: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  free_cash_flow: number | null;
  cash: number | null;
  total_debt: number | null;
  pe_forward: number | null;
  ev_sales: number | null;
  fcf_yield: number | null;
}> {
  return getJson(`/stocks/${symbol}/fundamentals`, {
    symbol,
    period: "TTM",
    report_date: new Date().toISOString().split("T")[0],
    revenue_growth_yoy: null,
    gross_margin: null,
    operating_margin: null,
    free_cash_flow: null,
    cash: null,
    total_debt: null,
    pe_forward: null,
    ev_sales: null,
    fcf_yield: null,
  });
}

export async function refreshAIPortfolioReport(): Promise<any> {
  const response = await fetch(`${API_URL}/ai/analyze-portfolio`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`AI Portfolio analysis failed with status ${response.status}`);
  }
  return response.json();
}

export async function getChartData(symbol: string, range: string): Promise<Array<{
  date: string;
  close: number;
  open: number;
  high: number;
  low: number;
}>> {
  return getJson(`/stocks/${symbol}/chart?range=${range}`, []);
}

export async function addWatchlistItem(payload: {
  symbol: string;
  reason: string;
  target_add_price?: number;
  target_trim_review_price?: number;
}): Promise<Record<string, any>> {
  const response = await fetch(`${API_URL}/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to add watchlist item: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteWatchlistItem(id: number): Promise<Record<string, any>> {
  const response = await fetch(`${API_URL}/watchlist/${id}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Failed to delete watchlist item: ${response.statusText}`);
  }
  return response.json();
}

export async function sendChatMessage(
  message: string,
  taggedSymbols: string[],
  history: Array<{ role: string; content: string }>
): Promise<{ response: string }> {
  const response = await fetch(`${API_URL}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, tagged_symbols: taggedSymbols, history })
  });
  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.statusText}`);
  }
  return response.json();
}

export async function getPnlHistory(accountId?: string): Promise<any[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return getJson(`/portfolio/pnl-history${query}`, []);
}

export async function recordSnapshot(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const response = await fetch(`${API_URL}/portfolio/pnl-history/record${query}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to record snapshot: ${response.statusText}`);
  }
  return response.json();
}

export async function getScheduleSettings(): Promise<{ settings: any; runs: any[] }> {
  return getJson("/ai/schedule", {
    settings: { enabled: false, morning_time: "09:30", midday_time: "12:30", night_time: "20:00" },
    runs: []
  });
}

export async function updateScheduleSettings(payload: { enabled: boolean; morning_time: string; midday_time: string; night_time: string }): Promise<any> {
  const response = await fetch(`${API_URL}/ai/schedule`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to update schedule settings: ${response.statusText}`);
  }
  return response.json();
}

export async function triggerScheduledAnalyze(period: string): Promise<any> {
  const response = await fetch(`${API_URL}/ai/scheduled-analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period })
  });
  if (!response.ok) {
    throw new Error(`Scheduled analysis failed: ${response.statusText}`);
  }
  return response.json();
}

export async function getInvestorProfile(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return getJson(`/portfolio/profile${query}`, {
    objective: "Growth",
    time_horizon_years: 10,
    risk_tolerance: "High",
    risk_capacity: "Medium",
    liquidity_needs: 10000.0,
    net_worth_range: "100k-500k",
    tax_residency: "Canada",
    account_type: "Tax-Free",
    restrictions: []
  });
}

export async function updateInvestorProfile(profile: any, accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const response = await fetch(`${API_URL}/portfolio/profile${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile)
  });
  if (!response.ok) {
    throw new Error(`Failed to update investor profile: ${response.statusText}`);
  }
  return response.json();
}

export async function getPortfolioPolicy(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return getJson(`/portfolio/policy${query}`, {
    target_equity_percent: 85.0,
    target_cash_percent: 15.0,
    target_bond_percent: 0.0,
    max_single_stock_weight: 12.0,
    max_speculative_weight: 5.0,
    max_sector_weight: 35.0,
    max_options_exposure: 3.0,
    minimum_cash: 10000.0,
    benchmark: "SPY",
    rebalancing_drift_threshold: 5.0
  });
}

export async function updatePortfolioPolicy(policy: any, accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const response = await fetch(`${API_URL}/portfolio/policy${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policy)
  });
  if (!response.ok) {
    throw new Error(`Failed to update portfolio policy: ${response.statusText}`);
  }
  return response.json();
}

export async function getAdvancedRiskMetrics(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return getJson(`/portfolio/advanced-risk${query}`, {
    max_drawdown: null,
    volatility: null,
    portfolio_beta_spy: null,
    portfolio_beta_qqq: null,
    value_at_risk_95: null,
    conditional_var_95: null,
    sharpe_ratio: null,
    sortino_ratio: null,
    jensens_alpha: null,
    tracking_error: null,
    information_ratio: null,
    correlation_matrix: {},
    factor_exposures: {},
    stress_tests: [],
    data_quality: { historical_metrics: "unavailable" },
    methodology: {}
  });
}

export async function getPerformanceAttribution(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return getJson(`/portfolio/attribution${query}`, {
    security_selection_return: {},
    sector_allocation_return: {},
    asset_class_return: {},
    realized_vs_unrealized: { realized: 0.0, unrealized: 0.0 },
    benchmark_relative_alpha: null,
    data_quality: { benchmark_data: "missing" },
    methodology: "Unavailable"
  });
}

export async function getOptionsStrategy(symbol: string): Promise<OptionsStrategyReport> {
  return getJson<OptionsStrategyReport>(`/stocks/${symbol}/options-strategy`, {
    symbol,
    stock_price: 0,
    implied_volatility: 0,
    iv_percentile: 0,
    implied_move_percent: 0,
    strategies: [],
    market_sentiment: "IBKR not connected or option parameters unavailable.",
    human_review_required: true,
    disclaimer: "This is fallback data. Please configure your API client.",
    provider: "deterministic_fallback",
    asOf: new Date().toISOString(),
    dataSource: "Mock",
    isMock: true,
    warnings: ["Fallback data: failed to connect to portfolio API."]
  });
}


