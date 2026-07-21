import type {
  AIStatus,
  AIStockReport,
  Alert,
  BrokerStatus,
  DecisionPacket,
  DecisionQueueResponse,
  PortfolioOptimizationProposal,
  PortfolioRisk,
  PortfolioSummary,
  Position,
  RebalanceProposal,
  Recommendation,
  RecommendationResponse,
  OptionsStrategyReport,
} from "./types";

const BACKEND_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CLIENT_API_BASE = "/api/backend";
const DESKTOP_MODE = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

async function resolveApiBase(): Promise<string> {
  if (typeof window !== "undefined") {
    const { isDesktopRuntimeAvailable, getDesktopRuntime } = await import("./desktop-api");
    if (isDesktopRuntimeAvailable()) {
      return getDesktopRuntime().apiBaseUrl;
    }
    if (DESKTOP_MODE) {
      // Static desktop build before runtime injection should fail closed.
      return "";
    }
    return CLIENT_API_BASE;
  }
  return BACKEND_URL;
}

async function buildRequestHeaders(initHeaders?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initHeaders);
  // Desktop static export is client-only; never pull next/headers into that graph.
  if (typeof window === "undefined" && !DESKTOP_MODE) {
    const { cookies } = await import("next/headers");
    const cookieStore = await cookies();
    const token = cookieStore.get("access_token")?.value;
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const csrfToken = cookieStore.get("csrf_token")?.value;
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  } else if (typeof window !== "undefined") {
    const { isDesktopRuntimeAvailable, getDesktopRuntime } = await import("./desktop-api");
    if (isDesktopRuntimeAvailable()) {
      headers.set("X-Local-Session", getDesktopRuntime().sessionToken);
    }
    const csrfToken = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
      ?.split("=")[1];
    if (csrfToken) {
      headers.set("X-CSRF-Token", decodeURIComponent(csrfToken));
    }
  }
  return headers;
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  if (typeof window !== "undefined") {
    const { isDesktopRuntimeAvailable, desktopFetch } = await import("./desktop-api");
    if (isDesktopRuntimeAvailable()) {
      return desktopFetch(path, { ...init, cache: "no-store" });
    }
  }
  const base = await resolveApiBase();
  if (!base) {
    throw new ApiError(503, { detail: "Desktop API runtime is not ready" });
  }
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

export async function requireJson<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const useCache = method === "GET" && typeof window !== "undefined" && !init?.cache;
  if (useCache) {
    const cached = readGetCache<T>(path);
    if (cached !== undefined) {
      return cached;
    }
  }

  const response = await apiFetch(path, init);
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new ApiError(response.status, detail);
  }
  const data = (await response.json()) as T;
  if (useCache) {
    writeGetCache(path, data);
  }
  return data;
}

type CacheEntry = { expiresAt: number; data: unknown };
const GET_CACHE = new Map<string, CacheEntry>();
const GET_CACHE_TTL_MS = 45_000;

function readGetCache<T>(path: string): T | undefined {
  const entry = GET_CACHE.get(path);
  if (!entry) {
    return undefined;
  }
  if (Date.now() > entry.expiresAt) {
    GET_CACHE.delete(path);
    return undefined;
  }
  return entry.data as T;
}

function writeGetCache(path: string, data: unknown): void {
  GET_CACHE.set(path, { expiresAt: Date.now() + GET_CACHE_TTL_MS, data });
}

/** Drop short-lived GET cache (e.g. after account switch or broker reconnect). */
export function invalidateApiGetCache(prefix?: string): void {
  if (!prefix) {
    GET_CACHE.clear();
    return;
  }
  for (const key of GET_CACHE.keys()) {
    if (key.startsWith(prefix)) {
      GET_CACHE.delete(key);
    }
  }
}

export function extractApiMessage(detail: unknown): string | null {
  if (!detail || typeof detail !== "object") {
    return null;
  }

  const root = detail as Record<string, unknown>;
  const nested = root.detail;

  if (typeof root.message === "string") {
    return root.message;
  }
  if (typeof nested === "string") {
    return nested;
  }

  if (nested && typeof nested === "object") {
    const object = nested as Record<string, unknown>;
    if (typeof object.message === "string") {
      return object.message;
    }
    if (typeof object.code === "string") {
      return object.code;
    }
  }

  return null;
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const message = extractApiMessage(error.detail);
    if (message) {
      if (
        message.includes("account_id is required") ||
        (typeof error.detail === "object" &&
          error.detail !== null &&
          (error.detail as { detail?: { code?: string } }).detail?.code ===
            "ACCOUNT_SELECTION_REQUIRED")
      ) {
        return "Multiple IBKR accounts found. Use Active Account in the sidebar (or Consolidated View), then refresh.";
      }
      return message;
    }
    if (error.status === 503) return "Broker or data provider is not configured.";
    if (error.status === 401) return "Authentication is required.";
    if (error.status === 422) {
      const code =
        typeof error.detail === "object" &&
        error.detail !== null &&
        (error.detail as { detail?: { code?: string }; code?: string }).detail?.code;
      if (code === "ACCOUNT_CONTEXT_UNAVAILABLE") {
        return "Broker account context unavailable. Confirm IBKR Gateway is connected, then retry.";
      }
      return "Multiple IBKR accounts found. Use Active Account in the sidebar (or Consolidated View), then refresh.";
    }
    return `Request failed (${error.status}).`;
  }
  return "Request failed.";
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

export async function getRecommendations(accountId?: string): Promise<RecommendationResponse> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson<RecommendationResponse>(`/recommendations${query}`);
}

export async function getAccounts(): Promise<any[]> {
  return requireJson("/broker/accounts");
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
): Promise<{
  position: Position;
  recommendation?: Recommendation;
  score_interpretation?: Recommendation;
  authoritative_outcome?: string;
  outcome?: string;
  score: { final_score: number | null; interpretation: string; sub_scores: Record<string, number> };
  last_ai_report?: AIStockReport | null;
}> {
  const query = buildHoldingQuery(accountId, conId);
  return requireJson(`/stocks/${symbol}/analysis${query}`);
}

export async function getReports(accountId?: string) {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/reports${query}`);
}

export async function getWatchlist() {
  return requireJson("/watchlist");
}

export async function getAuditLogs() {
  if (DESKTOP_MODE) {
    return requireJson("/desktop/audit-logs");
  }
  return requireJson("/admin/audit-logs");
}

export async function getAIStatus(): Promise<AIStatus> {
  return requireJson<AIStatus>("/ai/status");
}

export async function refreshAIStockReport(symbol: string): Promise<AIStockReport> {
  return requireJson<AIStockReport>(`/ai/analyze-stock/${symbol}`, { method: "POST" });
}

export async function configureAI(apiKey: string, model: string): Promise<AIStatus> {
  return requireJson<AIStatus>("/ai/configure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, model }),
  });
}

export async function getBrokerStatus(): Promise<BrokerStatus> {
  return requireJson<BrokerStatus>("/broker/status");
}

export async function getFlexTokenStatus(): Promise<{ configured: boolean }> {
  return requireJson<{ configured: boolean }>("/desktop/secrets/flex-token");
}

export async function saveFlexToken(token: string): Promise<{ configured: boolean }> {
  return requireJson<{ configured: boolean }>("/desktop/secrets/flex-token", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ token }),
  });
}

export async function deleteFlexToken(): Promise<{ configured: boolean }> {
  return requireJson<{ configured: boolean }>("/desktop/secrets/flex-token", {
    method: "DELETE",
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
  return requireJson(`/stocks/${symbol}/news`);
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
  return requireJson("/ai/schedule");
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
  return requireJson(`/portfolio/profile${query}`);
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
  return requireJson(`/portfolio/policy${query}`);
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

export async function getDecisionCenter(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/decision-center${query}`);
}

export async function getDecisionQueue(accountId?: string): Promise<DecisionQueueResponse> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/decisions/queue${query}`);
}

export async function getDecisionPacket(decisionId: string): Promise<DecisionPacket> {
  return requireJson(`/decisions/${encodeURIComponent(decisionId)}`);
}

export async function respondToDecision(
  decisionId: string,
  response: string,
  extras?: { intended_weight?: number; reasoning?: string },
): Promise<Record<string, unknown>> {
  return requireJson(`/decisions/${encodeURIComponent(decisionId)}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision_id: decisionId,
      response,
      ...(extras || {}),
    }),
  });
}

export async function getFinancialPlan(planId = "default"): Promise<Record<string, unknown>> {
  return requireJson(`/planning/plan?plan_id=${encodeURIComponent(planId)}`);
}

export async function getResearchQueue(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/research/queue${query}`);
}

export async function getResearchChangeFeed(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/research/change-feed${query}`);
}

export async function getMonitoringEvents(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/monitoring/events${query}`);
}

export async function acknowledgeMonitoringEvent(
  eventId: string,
  note?: string,
): Promise<Record<string, unknown>> {
  return requireJson(`/monitoring/events/${encodeURIComponent(eventId)}/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
}

export async function resolveMonitoringEvent(
  eventId: string,
  note?: string,
): Promise<Record<string, unknown>> {
  return requireJson(`/monitoring/events/${encodeURIComponent(eventId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
}

export async function snoozeMonitoringEvent(
  eventId: string,
  snoozeUntil: string,
  note?: string,
): Promise<Record<string, unknown>> {
  return requireJson(`/monitoring/events/${encodeURIComponent(eventId)}/snooze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snooze_until: snoozeUntil, note }),
  });
}

export async function getMonitoringNotifications(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/monitoring/notifications${query}`);
}

export async function flushMonitoringNotifications(): Promise<Record<string, unknown>> {
  return requireJson(`/monitoring/notifications/flush`, { method: "POST" });
}

export async function getOptionsExpiryCalendar(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/monitoring/options-expiry${query}`);
}

export async function createDesktopBackup(passphrase?: string): Promise<Record<string, unknown>> {
  return requireJson(`/desktop/backup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: "manual", passphrase }),
  });
}

export async function verifyDesktopBackupRestore(
  encryptedPath: string,
  passphrase: string,
): Promise<Record<string, unknown>> {
  return requireJson(`/desktop/backup/verify-restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ encrypted_path: encryptedPath, passphrase }),
  });
}

export async function exportDesktopArchive(): Promise<Record<string, unknown>> {
  return requireJson(`/desktop/export`, { method: "POST" });
}

export async function getDataHealth(): Promise<Record<string, unknown>> {
  return requireJson(`/data-health`);
}

export async function getMethodologies(): Promise<Record<string, unknown>> {
  return requireJson(`/methodologies`);
}

export async function approveMethodology(body: {
  methodology_id: string;
  version: string;
  approver?: string;
  notes?: string;
}): Promise<Record<string, unknown>> {
  return requireJson(`/methodologies/approvals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getConstructionScenarios(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/construction/scenarios${query}`);
}

export async function getHoldingDecision(
  instrumentKey: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/holdings/${encodeURIComponent(instrumentKey)}/decision${query}`);
}

export async function getHoldingLenses(
  instrumentKey: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/holdings/${encodeURIComponent(instrumentKey)}/lenses${query}`);
}

export async function putHoldingThesis(
  instrumentKey: string,
  text: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/holdings/${encodeURIComponent(instrumentKey)}/thesis${query}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function getStockValuation(
  symbol: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/stocks/${encodeURIComponent(symbol)}/valuation${query}`);
}

export async function getTaxLots(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/portfolio/tax-lots${query}`);
}

export async function searchInstruments(
  q: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ q });
  if (accountId) params.set("account_id", accountId);
  return requireJson(`/instruments/search?${params.toString()}`);
}

export async function getInstrumentOverview(
  instrumentId: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/instruments/${encodeURIComponent(instrumentId)}/overview${query}`);
}

// --- Trade Plans (§9) -------------------------------------------------------

export async function listTradePlans(
  accountId: string,
  status?: string,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ account_id: accountId });
  if (status) params.set("status", status);
  return requireJson(`/trade-plans?${params.toString()}`);
}

export async function createTradePlan(
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return requireJson(`/trade-plans`, { method: "POST", body: JSON.stringify(body) });
}

export async function getTradePlan(planId: string): Promise<Record<string, unknown>> {
  return requireJson(`/trade-plans/${encodeURIComponent(planId)}`);
}

export async function updateTradePlan(
  planId: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return requireJson(`/trade-plans/${encodeURIComponent(planId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function evaluateTradePlan(
  planId: string,
  accountId?: string,
): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/trade-plans/${encodeURIComponent(planId)}/evaluate${query}`, {
    method: "POST",
  });
}

export async function transitionTradePlan(
  planId: string,
  action: "approve" | "reject" | "defer",
): Promise<Record<string, unknown>> {
  return requireJson(`/trade-plans/${encodeURIComponent(planId)}/${action}`, { method: "POST" });
}

// --- Trade Journal (§10) ----------------------------------------------------

export async function listJournal(accountId: string): Promise<Record<string, unknown>> {
  return requireJson(`/journal?account_id=${encodeURIComponent(accountId)}`);
}

export async function createJournalEntry(body: Record<string, unknown>): Promise<Record<string, unknown>> {
  return requireJson(`/journal`, { method: "POST", body: JSON.stringify(body) });
}

export async function updateJournalEntry(
  entryId: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return requireJson(`/journal/${encodeURIComponent(entryId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function addJournalReview(
  entryId: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return requireJson(`/journal/${encodeURIComponent(entryId)}/review`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getJournalAnalytics(accountId: string): Promise<Record<string, unknown>> {
  return requireJson(`/journal/analytics?account_id=${encodeURIComponent(accountId)}`);
}

// --- Markets (§7) -----------------------------------------------------------

export async function getMarketOverview(): Promise<Record<string, unknown>> {
  return requireJson(`/markets/overview`);
}

export async function getMarketRegime(): Promise<Record<string, unknown>> {
  return requireJson(`/markets/regime`);
}

export async function getMarketCalendar(): Promise<Record<string, unknown>> {
  return requireJson(`/markets/calendar`);
}

export async function runTaxReconciliation(
  accountId?: string,
  taxYear?: number,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams();
  if (accountId) params.set("account_id", accountId);
  if (taxYear != null) params.set("tax_year", String(taxYear));
  const query = params.toString() ? `?${params.toString()}` : "";
  return requireJson(`/portfolio/tax-reconciliation${query}`, { method: "POST" });
}

export async function getPlanFeasibility(planId = "default"): Promise<Record<string, unknown>> {
  return requireJson(`/planning/feasibility?plan_id=${encodeURIComponent(planId)}`);
}

export async function getReplacementUniverse(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/construction/replacement-universe${query}`);
}

export async function evaluateMonitoring(accountId?: string): Promise<Record<string, unknown>> {
  const query = accountId ? `?account_id=${accountId}` : "";
  return requireJson(`/monitoring/evaluate${query}`, { method: "POST" });
}


