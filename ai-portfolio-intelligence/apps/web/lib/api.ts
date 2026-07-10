import type {
  AIStatus,
  AIStockReport,
  Alert,
  BrokerStatus,
  PortfolioOptimizationProposal,
  PortfolioRisk,
  PortfolioSummary,
  Position,
  RebalanceProposal,
  Recommendation,
  OptionsStrategyReport,
} from "./types";

const BACKEND_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CLIENT_API_BASE = "/api/backend";

const AUTH_FAILURE_STATUSES = new Set([401, 422, 503]);

async function resolveApiBase(): Promise<string> {
  return typeof window === "undefined" ? BACKEND_URL : CLIENT_API_BASE;
}

async function buildRequestHeaders(initHeaders?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initHeaders);
  if (typeof window === "undefined") {
    const { cookies } = await import("next/headers");
    const cookieStore = await cookies();
    const token = cookieStore.get("access_token")?.value;
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  return headers;
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = await resolveApiBase();
  const headers = await buildRequestHeaders(init?.headers);
  return fetch(`${base}${path}`, { ...init, headers, cache: "no-store" });
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`API request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function requireJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "object" && error.detail && "message" in (error.detail as object)) {
      return String((error.detail as { message?: string }).message);
    }
    if (error.status === 503) return "Broker or data provider is not configured.";
    if (error.status === 401) return "Authentication is required.";
    if (error.status === 422) return "Account selection is required for this view.";
    return `Request failed (${error.status}).`;
  }
  return "Request failed.";
}

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await apiFetch(path);
    if (!response.ok) {
      if (AUTH_FAILURE_STATUSES.has(response.status)) {
        const detail = await response.json().catch(() => null);
        throw new ApiError(response.status, detail);
      }
      return fallback;
    }
    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    return fallback;
  }
}

const fallbackPositions: Position[] = [];

export async function getPortfolioSummary(accountId?: string): Promise<PortfolioSummary> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson<PortfolioSummary>(`/portfolio/summary${query}`);
}

export async function getPositions(accountId?: string): Promise<Position[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson<Position[]>(`/portfolio/positions${query}`);
}

export async function getRisk(accountId?: string): Promise<PortfolioRisk> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson<PortfolioRisk>(`/portfolio/risk${query}`);
}

export async function getAlerts(accountId?: string): Promise<Alert[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson<Alert[]>(`/alerts${query}`);
}

export async function getRecommendations(accountId?: string): Promise<Recommendation[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson<Recommendation[]>(`/recommendations${query}`);
}

export async function getAccounts(): Promise<any[]> {
  return getJson("/broker/accounts", []);
}

function buildHoldingQuery(accountId?: string, conId?: number | null): string {
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  if (conId != null) params.set("con_id", String(conId));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function getHoldingAnalysis(
  symbol: string,
  accountId?: string,
  conId?: number | null,
): Promise<{ position: Position; recommendation: Recommendation; score: { final_score: number | null; interpretation: string; sub_scores: Record<string, number> }; last_ai_report?: AIStockReport | null }> {
  const query = buildHoldingQuery(accountId, conId);
  return requireJson(`/stocks/${symbol}/analysis${query}`);
}

export async function getReports(accountId?: string) {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/reports${query}`);
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
  return requireJson<AIStockReport>(`/ai/analyze-stock/${symbol}`, { method: "POST" });
}

export async function configureAI(apiKey: string, model: string): Promise<AIStatus & { api_key: string }> {
  return requireJson<AIStatus & { api_key: string }>("/ai/configure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, model }),
  });
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

export async function configureBrokerReadonly(payload: { mode: string; host: string; port: number; client_id: number; account_id?: string }): Promise<BrokerStatus> {
  return requireJson<BrokerStatus>("/broker/configure-readonly", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getTechnicals(symbol: string): Promise<{
  symbol: string;
  historical_prices: number[];
  rsi_14: number | null;
  drawdown_from_52w_high: number | null;
  trend_classification: string | null;
  atr_14: number | null;
  data_quality: string;
  methodology: string;
}> {
  return requireJson(`/stocks/${symbol}/technicals`);
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
  return requireJson(`/stocks/${symbol}/fundamentals`);
}

export async function refreshAIPortfolioReport(): Promise<any> {
  return requireJson("/ai/analyze-portfolio", { method: "POST" });
}

export async function getChartData(symbol: string, range: string): Promise<Array<{
  date: string;
  close: number;
  open: number;
  high: number;
  low: number;
}>> {
  return requireJson(`/stocks/${symbol}/chart?range=${range}`);
}

export async function addWatchlistItem(payload: {
  symbol: string;
  reason: string;
  target_add_price?: number;
  target_trim_review_price?: number;
}): Promise<Record<string, any>> {
  return requireJson("/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteWatchlistItem(id: number): Promise<Record<string, any>> {
  return requireJson(`/watchlist/${id}`, { method: "DELETE" });
}

export async function sendChatMessage(
  message: string,
  taggedSymbols: string[],
  history: Array<{ role: string; content: string }>
): Promise<{ response: string }> {
  return requireJson("/ai/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, tagged_symbols: taggedSymbols, history }),
  });
}

export async function getPnlHistory(accountId?: string): Promise<any[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  try {
    return await requireJson(`/portfolio/pnl-history${query}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return [];
    }
    throw error;
  }
}

export async function recordSnapshot(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/pnl-history/record${query}`, { method: "POST" });
}

export async function getScheduleSettings(): Promise<{ settings: any; runs: any[] }> {
  return getJson("/ai/schedule", {
    settings: { enabled: false, morning_time: "09:30", midday_time: "12:30", night_time: "20:00" },
    runs: []
  });
}

export async function updateScheduleSettings(payload: { enabled: boolean; morning_time: string; midday_time: string; night_time: string }): Promise<any> {
  return requireJson("/ai/schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function triggerScheduledAnalyze(period: string): Promise<any> {
  return requireJson("/ai/scheduled-analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period }),
  });
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
  return requireJson(`/portfolio/profile${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
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
  return requireJson(`/portfolio/policy${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policy),
  });
}

export async function getAdvancedRiskMetrics(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/advanced-risk${query}`);
}

export async function getPerformanceAttribution(accountId?: string): Promise<any> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/attribution${query}`);
}

const emptyRebalanceProposal: RebalanceProposal = {
  proposed_trades: [],
  cash_impact: 0,
  tax_impact_warning: "Rebalance proposal unavailable. Connect IBKR and configure your investment policy.",
  compliance_disclaimer: "Review only. This application does not execute trades.",
  unavailable: true,
};

const emptyOptimizationProposal: PortfolioOptimizationProposal = {
  objective: "min_variance",
  proposed_trades: [],
  expected_volatility: null,
  expected_return: null,
  sharpe_ratio: null,
  constraints_applied: [],
  methodology: "Optimization proposal unavailable.",
  compliance_disclaimer: "Review only. This application does not execute trades.",
  unavailable: true,
};

export async function getRebalanceProposal(accountId?: string): Promise<RebalanceProposal> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const proposal = await requireJson<RebalanceProposal>(`/portfolio/rebalance-proposal${query}`);
  return { ...proposal, unavailable: false };
}

export async function getOptimizationProposal(accountId?: string): Promise<PortfolioOptimizationProposal> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const proposal = await requireJson<PortfolioOptimizationProposal>(`/portfolio/optimization-proposal${query}`);
  return { ...proposal, unavailable: false };
}

export async function getOptionsStrategy(
  symbol: string,
  accountId?: string,
  conId?: number | null,
): Promise<OptionsStrategyReport> {
  const query = buildHoldingQuery(accountId, conId);
  return requireJson<OptionsStrategyReport>(`/stocks/${symbol}/options-strategy${query}`);
}


