import { Disclaimer } from "@/components/Disclaimer";
import { StatCard } from "@/components/StatCard";
import { AIRefreshPanel } from "@/components/AIRefreshPanel";
import { getAIStatus, getHoldingAnalysis, getTechnicals, getNews, getFundamentals, getWatchlist, getOptionsStrategy } from "@/lib/api";
import { PerformanceSparkline } from "@/components/PerformanceSparkline";
import { HoldingInteractiveChart } from "@/components/HoldingInteractiveChart";
import { WatchlistToggle } from "@/components/WatchlistToggle";
import { TagChatButton } from "@/components/TagChatButton";
import { OptionsStrategyDashboard } from "@/components/OptionsStrategyDashboard";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function HoldingDetailPage({ 
  params,
  searchParams,
}: { 
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { symbol } = await params;
  const { tab = "research" } = await searchParams;
  
  const [data, aiStatus, technicals, news, fundamentals, watchlist] = await Promise.all([
    getHoldingAnalysis(symbol.toUpperCase()),
    getAIStatus(),
    getTechnicals(symbol.toUpperCase()),
    getNews(symbol.toUpperCase()),
    getFundamentals(symbol.toUpperCase()),
    getWatchlist(),
  ]);
  const position = data.position;
  const recommendation = data.recommendation;

  const watchItem = (watchlist as any[]).find(
    (item) => item.symbol.toUpperCase() === symbol.toUpperCase()
  );
  const initialWatchlistItem = watchItem ? { id: watchItem.id, reason: watchItem.reason } : null;

  return (
    <div className="grid gap-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">Holding research</p>
          <h2 className="text-3xl font-semibold">{position.symbol} · {position.company_name}</h2>
        </div>
        <div className="mt-1 sm:mt-0 flex items-center gap-2">
          <TagChatButton symbol={position.symbol} />
          <WatchlistToggle symbol={position.symbol} initialWatchlistItem={initialWatchlistItem} />
        </div>
      </div>

      {/* Tabs navigation */}
      <div className="border-b border-line flex items-center gap-6 text-sm">
        <Link
          href={`?tab=research`}
          className={`pb-2.5 border-b-2 font-semibold transition-all -mb-px ${
            tab === "research"
              ? "border-accent text-accent"
              : "border-transparent text-zinc-500 hover:text-zinc-800"
          }`}
        >
          Research Overview
        </Link>
        <Link
          href={`?tab=options`}
          className={`pb-2.5 border-b-2 font-semibold transition-all -mb-px ${
            tab === "options"
              ? "border-accent text-accent"
              : "border-transparent text-zinc-500 hover:text-zinc-800"
          }`}
        >
          Options Strategy
        </Link>
      </div>

      {tab === "options" ? (
        <OptionsStrategyDashboard symbol={position.symbol} />
      ) : (
        <>
          <Disclaimer />
          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Current Price" value={`$${position.market_price.toLocaleString()}`} />
            <StatCard label="Market Value" value={`$${position.market_value.toLocaleString()}`} />
            <StatCard label="Portfolio Weight" value={`${position.portfolio_weight.toFixed(2)}%`} />
            <StatCard label="Final Score" value={data.score.final_score === null ? "Unavailable" : data.score.final_score.toFixed(1)} detail={data.score.interpretation} />
          </section>
          <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
            <div className="grid gap-4">
              {/* Decision-Support View */}
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="text-lg font-semibold">Decision-Support View</h3>
                <div className="mt-3 rounded-md bg-panel p-3">
                  <div className="text-sm uppercase tracking-wide text-zinc-500">Action category</div>
                  <div className="text-2xl font-bold text-accent">{recommendation.action}</div>
                </div>
                <div className="mt-4 grid gap-3 text-sm text-zinc-700">
                  <p>{recommendation.explanation}</p>
                  <p><strong>Add zone:</strong> {recommendation.add_zone ?? "Unavailable until research inputs are verified."}</p>
                  <p><strong>Hold zone:</strong> {recommendation.hold_zone ?? "Unavailable until research inputs are verified."}</p>
                  <p><strong>Trim review zone:</strong> {recommendation.trim_review_zone ?? "Unavailable until research inputs are verified."}</p>
                  <p><strong>Exit review trigger:</strong> {recommendation.exit_review_trigger ?? "Unavailable until research inputs are verified."}</p>
                </div>
              </div>

              {/* Technical Trend Card */}
              <div className="rounded-md border border-line bg-white p-4">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="text-lg font-semibold">Technical Trend</h3>
                    <p className="text-xs text-zinc-500 font-medium capitalize mt-0.5">Classification: {technicals.trend_classification ?? "Unavailable"}</p>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold text-zinc-800">RSI (14): {technicals.rsi_14 === null || technicals.rsi_14 === undefined ? "Unavailable" : technicals.rsi_14.toFixed(1)}</span>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wide mt-0.5">
                      52W Drawdown: {technicals.drawdown_from_52w_high === null || technicals.drawdown_from_52w_high === undefined ? "Unavailable" : `${technicals.drawdown_from_52w_high.toFixed(1)}%`}
                    </p>
                  </div>
                </div>
                <HoldingInteractiveChart symbol={position.symbol} />
              </div>

              {/* Recent News & Catalysts */}
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="text-lg font-semibold mb-3">Recent News & Catalysts</h3>
                {news && news.length > 0 ? (
                  <div className="grid gap-3 max-h-[350px] overflow-y-auto pr-1">
                    {news.map((item, idx) => (
                      <div key={idx} className="border-b border-line last:border-0 pb-3 last:pb-0">
                        <a
                          href={item.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-semibold text-sm text-zinc-900 hover:text-accent hover:underline block leading-tight"
                        >
                          {item.title}
                        </a>
                        <div className="flex justify-between items-center mt-1 text-[11px] text-zinc-500">
                          <span>Source: {item.source}</span>
                          {item.providerPublishTime > 0 ? (
                            <span>{new Date(item.providerPublishTime * 1000).toLocaleDateString()}</span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500">No recent news available.</p>
                )}
              </div>
            </div>

            <div className="grid gap-4 self-start">
              {/* Sub-Scores */}
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="text-lg font-semibold">Sub-Scores</h3>
                <div className="mt-4 grid gap-3">
                  {Object.entries(data.score.sub_scores).map(([label, value]) => (
                    <div key={label}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span className="capitalize">{label.replaceAll("_", " ")}</span>
                        <span className="font-semibold">{value.toFixed(1)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-panel">
                        <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.min(value, 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Key Fundamentals & Valuation */}
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="text-lg font-semibold mb-3">Key Fundamentals & Valuation</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-zinc-500 block">Revenue Growth (YoY)</span>
                    <span className="font-semibold text-base">{formatPercent(fundamentals.revenue_growth_yoy)}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Gross Margin</span>
                    <span className="font-semibold text-base">{formatPercent(fundamentals.gross_margin)}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Operating Margin</span>
                    <span className="font-semibold text-base">{formatPercent(fundamentals.operating_margin)}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Free Cash Flow</span>
                    <span className="font-semibold text-base">
                      {formatLargeCurrency(fundamentals.free_cash_flow)}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Cash & Equivalents</span>
                    <span className="font-semibold text-base">
                      {formatLargeCurrency(fundamentals.cash)}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Total Debt</span>
                    <span className="font-semibold text-base">
                      {formatLargeCurrency(fundamentals.total_debt)}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Forward P/E</span>
                    <span className="font-semibold text-base">
                      {fundamentals.pe_forward !== null ? fundamentals.pe_forward.toFixed(1) : "N/A"}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">EV / Sales</span>
                    <span className="font-semibold text-base">
                      {fundamentals.ev_sales !== null ? fundamentals.ev_sales.toFixed(1) : "N/A"}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-zinc-500 block">FCF Yield</span>
                    <span className="font-semibold text-base">
                      {fundamentals.fcf_yield !== null ? `${(fundamentals.fcf_yield * 100).toFixed(2)}%` : "N/A"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Evidence and Data Freshness */}
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="text-lg font-semibold">Evidence and Data Freshness</h3>
                <ul className="mt-3 list-disc pl-5 grid gap-1.5 text-sm text-zinc-700">
                  {recommendation.evidence.map((item) => <li key={item}>{item}</li>)}
                </ul>
                <p className="mt-4 text-xs font-medium text-warning bg-amber-50 border border-amber-200 rounded-md p-3">
                  {recommendation.human_review_reminder}
                </p>
              </div>
            </div>
          </section>

          <AIRefreshPanel key={position.symbol} symbol={position.symbol} initialProvider={aiStatus.mode === "live_gemini" ? `gemini:${aiStatus.model}` : "deterministic_fallback"} initialReport={data.last_ai_report} />
        </>
      )}
    </div>
  );
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

function formatLargeCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return "Unavailable";
  return value >= 1e9
    ? `$${(value / 1e9).toFixed(1)}B`
    : `$${(value / 1e6).toFixed(1)}M`;
}
