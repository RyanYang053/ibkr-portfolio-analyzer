"use client";

import { useState } from "react";
import { Brain, RefreshCw, AlertTriangle, ListChecks, ShieldAlert } from "lucide-react";
import { refreshAIPortfolioReport } from "@/lib/api";

export function AIPortfolioRefreshPanel({ initialReport }: { initialReport?: any | null }) {
  const [report, setReport] = useState<any | null>(initialReport ?? null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setIsLoading(true);
    setError(null);
    try {
      const result = await refreshAIPortfolioReport();
      setReport(result);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "AI analysis refresh failed");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="rounded-md border border-line bg-white p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-zinc-900">
            <Brain size={18} className="text-accent" aria-hidden /> AI Portfolio Intelligence Memo
          </h3>
          <p className="text-sm text-zinc-500">
            {report
              ? `Generated via ${report.provider ?? "Gemini"}`
              : "No active AI portfolio intelligence report exists."}
          </p>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-accent/90 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 disabled:opacity-60 transition-colors"
          onClick={refresh}
          disabled={isLoading}
        >
          <RefreshCw size={16} aria-hidden className={isLoading ? "animate-spin" : ""} />
          {isLoading ? "Analyzing Portfolio..." : report ? "Refresh Portfolio Analysis" : "Analyze Full Portfolio"}
        </button>
      </div>

      {error ? (
        <p className="mt-3 rounded-md border border-danger bg-red-50 p-3 text-sm text-danger">{error}</p>
      ) : null}

      {report ? (
        <div className="mt-6 grid gap-6 border-t border-line pt-6">
          {/* Top Row Overview */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-md bg-panel p-4 border border-line">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500 block mb-1">Executive Summary</span>
              <p className="text-sm text-zinc-800 leading-relaxed">{report.portfolio_summary}</p>
            </div>
            
            <div className="rounded-md bg-zinc-50 p-4 border border-line flex flex-col justify-between">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500 block mb-2">Metrics Summary</span>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {report.overall_portfolio_risk && (
                    <div>
                      <span className="text-zinc-500 block text-xs">Risk Profile</span>
                      <span className="font-semibold text-zinc-800">{report.overall_portfolio_risk}</span>
                    </div>
                  )}
                  {report.cash_deployment_view && (
                    <div>
                      <span className="text-zinc-500 block text-xs">Cash Position</span>
                      <span className="font-semibold text-zinc-800">{report.cash_deployment_view}</span>
                    </div>
                  )}
                  {report.confidence && (
                    <div>
                      <span className="text-zinc-500 block text-xs">Analysis Confidence</span>
                      <span className="font-semibold text-zinc-800">{report.confidence}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Macro & Sector Outlook */}
          <div className="grid gap-4 md:grid-cols-2">
            {report.macro_outlook && (
              <div className="rounded-md border border-line p-4 bg-zinc-50/50">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500 block mb-1.5">Macroeconomic Outlook</span>
                <p className="text-sm text-zinc-800 leading-relaxed">{report.macro_outlook}</p>
              </div>
            )}
            {report.sector_dynamics && (
              <div className="rounded-md border border-line p-4 bg-zinc-50/50">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500 block mb-1.5">Sector Dynamics & Market Trends</span>
                <p className="text-sm text-zinc-800 leading-relaxed">{report.sector_dynamics}</p>
              </div>
            )}
          </div>

          {/* Core Insights Grid */}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {/* Watchlist & Catalysts */}
            <div className="rounded-md border border-line p-4">
              <h4 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-950 mb-3">
                <ShieldAlert size={16} className="text-amber-500" /> Holdings to Watch
              </h4>
              {report.holdings_to_watch && report.holdings_to_watch.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {report.holdings_to_watch.map((symbol: string) => (
                    <span key={symbol} className="px-2 py-1 rounded bg-amber-50 border border-amber-200 text-xs font-semibold text-amber-700">
                      {symbol}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No high-risk holdings flagged.</p>
              )}

              {/* Contributors / Detractors */}
              <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-zinc-500 block font-medium mb-1">Top Contributors</span>
                  <ul className="list-disc pl-4 text-zinc-700">
                    {report.largest_contributors?.map((sym: string) => <li key={sym}>{sym}</li>) || "None"}
                  </ul>
                </div>
                <div>
                  <span className="text-zinc-500 block font-medium mb-1">Top Detractors</span>
                  <ul className="list-disc pl-4 text-zinc-700">
                    {report.largest_detractors?.map((sym: string) => <li key={sym}>{sym}</li>) || "None"}
                  </ul>
                </div>
              </div>
            </div>

            {/* Possible Add Zones */}
            <div className="rounded-md border border-line p-4">
              <h4 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-950 mb-3">
                <ListChecks size={16} className="text-accent" /> Suggested Add Zones
              </h4>
              {report.possible_add_zones && report.possible_add_zones.length > 0 ? (
                <ul className="grid gap-1.5 pl-4 list-disc text-xs text-zinc-700">
                  {report.possible_add_zones.map((zone: string, index: number) => (
                    <li key={index}>{zone}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-zinc-500">No add zones suggestions.</p>
              )}
            </div>

            {/* Risk Alerts */}
            <div className="rounded-md border border-line p-4 col-span-1 md:col-span-2 xl:col-span-1">
              <h4 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-950 mb-3">
                <AlertTriangle size={16} className="text-red-500" /> Active Risk Alerts
              </h4>
              {report.risk_alerts && report.risk_alerts.length > 0 ? (
                <div className="grid gap-2 max-h-[150px] overflow-y-auto pr-1">
                  {report.risk_alerts.map((alert: any, index: number) => {
                    const alertType = typeof alert === "string" ? alert : alert.alert_type;
                    const message = typeof alert === "string" ? "" : alert.message;
                    return (
                      <div key={index} className="p-2 bg-red-50 border border-red-100 rounded text-xs">
                        <span className="font-semibold uppercase text-red-700 text-[10px] block mb-0.5">
                          {alertType?.replace("_", " ")}
                        </span>
                        {message && <p className="text-red-600 leading-tight">{message}</p>}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No active risk alerts.</p>
              )}
            </div>
          </div>

          {report.provenance ? (
            <div className="rounded-md border border-line p-4 bg-white text-sm">
              <h4 className="font-semibold text-zinc-950 mb-2.5">Data Provenance (Audit Trail)</h4>
              <div className="flex flex-wrap gap-2">
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                  report.provenance.live_portfolio_data 
                    ? "bg-emerald-50 border-emerald-200 text-emerald-700" 
                    : "bg-zinc-50 border-zinc-200 text-zinc-600"
                }`}>
                  Portfolio: {report.provenance.live_portfolio_data ? "Live" : "Mock"}
                </span>
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                  report.provenance.live_market_data 
                    ? "bg-emerald-50 border-emerald-200 text-emerald-700" 
                    : "bg-zinc-50 border-zinc-200 text-zinc-600"
                }`}>
                  Market: {report.provenance.live_market_data ? "Live" : "Mock"}
                </span>
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                  report.provenance.cached_data 
                    ? "bg-sky-50 border-sky-200 text-sky-700" 
                    : "bg-zinc-50 border-zinc-200 text-zinc-600"
                }`}>
                  Cached: {report.provenance.cached_data ? "Yes" : "No"}
                </span>
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                  report.provenance.mock_fallback_data 
                    ? "bg-amber-50 border-amber-200 text-amber-700" 
                    : "bg-emerald-50 border-emerald-200 text-emerald-700"
                }`}>
                  Fallback: {report.provenance.mock_fallback_data ? "Active" : "None"}
                </span>
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                  report.provenance.web_grounded_context 
                    ? "bg-emerald-50 border-emerald-200 text-emerald-700" 
                    : "bg-zinc-50 border-zinc-200 text-zinc-600"
                }`}>
                  Web-Grounded: {report.provenance.web_grounded_context ? "Grounded" : "No Search"}
                </span>
              </div>
            </div>
          ) : null}

          {/* Missing & Warnings Footer */}
          <div className="rounded-md border border-line p-4 bg-zinc-50 text-xs text-zinc-600 leading-relaxed grid gap-2 md:grid-cols-2">
            <div>
              <span className="font-semibold text-zinc-700 block mb-1">Missing / Stale Data Categories</span>
              <p>{report.missing_data?.join(", ") || "None flagged."}</p>
            </div>
            <div>
              <span className="font-semibold text-zinc-700 block mb-1">Decision Support Context</span>
              <ul className="list-disc pl-4 grid gap-0.5">
                {report.do_not_act_warnings?.map((warn: string, idx: number) => (
                  <li key={idx}>{warn}</li>
                )) || <li>For support only. Requires human review.</li>}
              </ul>
            </div>
          </div>

          {report.provider_error && (
            <p className="rounded-md border border-warning bg-amber-50 p-3 text-xs text-warning">
              Gemini analysis failed, utilizing deterministic fallback rules: {report.provider_error}
            </p>
          )}

          <p className="text-[10px] text-zinc-400 text-center leading-normal mt-2">
            {report.disclaimer}
          </p>
        </div>
      ) : null}
    </section>
  );
}
