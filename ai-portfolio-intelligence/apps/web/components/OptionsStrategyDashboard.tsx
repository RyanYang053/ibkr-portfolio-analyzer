"use client";

import React from "react";
import type { OptionsStrategyReport, OptionsStrategyDetails } from "../lib/types";
import { TrendingUp, Activity, DollarSign, Calendar, Shield, Percent, Sparkles, AlertTriangle, ArrowRight } from "lucide-react";

type OptionsStrategyDashboardProps = {
  initialData?: OptionsStrategyReport | null;
  symbol: string;
};

export function OptionsStrategyDashboard({ initialData, symbol }: OptionsStrategyDashboardProps) {
  const [data, setData] = React.useState<OptionsStrategyReport | null>(initialData || null);
  const [loading, setLoading] = React.useState(!initialData);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (initialData) return;
    
    let active = true;
    setLoading(true);
    setError(null);
    
    const fetchOptions = async () => {
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const res = await fetch(`${API_URL}/stocks/${symbol}/options-strategy`);
        if (!res.ok) {
          throw new Error("Failed to fetch options strategy data");
        }
        const json = await res.json();
        if (active) {
          setData(json);
          setLoading(false);
        }
      } catch (err: any) {
        if (active) {
          setError(err.message || "An error occurred");
          setLoading(false);
        }
      }
    };
    
    fetchOptions();
    
    return () => {
      active = false;
    };
  }, [symbol, initialData]);

  const formatIV = (iv: number | null | undefined) => {
    if (iv == null) return "Unavailable";
    return `${(iv * 100).toFixed(1)}%`;
  };

  const getStrategyTypeBadgeStyle = (type: string) => {
    switch (type.toLowerCase()) {
      case "income":
      case "defensive":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "bullish":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "bearish":
        return "bg-rose-50 text-rose-700 border-rose-200";
      default:
        return "bg-zinc-50 text-zinc-700 border-zinc-200";
    }
  };

  if (loading) {
    return (
      <div className="grid gap-6 animate-pulse">
        <div className="rounded-md border border-line bg-white p-5 h-48 flex flex-col justify-between">
          <div className="h-6 bg-zinc-200 rounded w-1/4"></div>
          <div className="h-4 bg-zinc-200 rounded w-3/4"></div>
          <div className="grid grid-cols-4 gap-4 mt-4">
            <div className="h-16 bg-zinc-200 rounded"></div>
            <div className="h-16 bg-zinc-200 rounded"></div>
            <div className="h-16 bg-zinc-200 rounded"></div>
            <div className="h-16 bg-zinc-200 rounded"></div>
          </div>
        </div>
        <div className="h-6 bg-zinc-200 rounded w-1/3 mt-2"></div>
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-md border border-line bg-white p-5 h-64"></div>
          <div className="rounded-md border border-line bg-white p-5 h-64"></div>
        </div>
      </div>
    );
  }

  if (error || !data || !data.strategies || data.strategies.length === 0) {
    return (
      <div className="rounded-md border border-line bg-white p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-zinc-400 mx-auto mb-2" />
        <p className="text-sm font-semibold text-zinc-800">No option strategies generated</p>
        <p className="text-xs text-zinc-500 mt-1">
          {error || "Please ensure Gemini is configured and active to generate options strategies."}
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      {/* Hard Mock Warning Banner */}
      {data.isMock && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 flex gap-3 items-start">
          <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-bold text-rose-800 uppercase tracking-wide">
              Simulated Data — Not Suitable for Trading Decisions
            </h4>
            <p className="text-xs text-rose-700 mt-1 leading-relaxed">
              Options strategy data is simulated because live AI/market data is unavailable. The options strategies, Greeks, and contract prices displayed below are mathematically generated models for testing and educational analysis only.
            </p>
          </div>
        </div>
      )}

      {/* Options Market Overview Header */}
      <div className="rounded-md border border-line bg-white p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-accent mb-1">
              <Sparkles className="h-3 w-3 text-accent" />
              Educational Options Strategy Candidate Analyzer
            </span>
            <h3 className="text-xl font-semibold text-zinc-900">
              Options Market Context for {symbol}
            </h3>
            <p className="text-sm text-zinc-500 mt-1">
              Scenario-based options structures and AI-generated options analysis for educational review. This does not constitute trading recommendations or order execution.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full border border-line bg-zinc-50 px-2.5 py-0.5 text-xs font-medium text-zinc-600">
              Provider: {data.provider}
            </span>
            {!data.isMock && data.provenance?.web_grounded_context && (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                ⚡ Search Grounded (Real-Time)
              </span>
            )}
          </div>
        </div>

        {/* Metadata & Source Info */}
        <div className="mt-4 pt-4 border-t border-line flex flex-wrap items-center gap-y-2 gap-x-6 text-xs text-zinc-500">
          <div>
            <span className="font-semibold text-zinc-700">Data as of:</span>{" "}
            {data.asOf ? new Date(data.asOf).toLocaleString(undefined, { timeZoneName: "short" }) : "N/A"}
          </div>
          <div>
            <span className="font-semibold text-zinc-700">Source:</span>{" "}
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${data.isMock ? "bg-zinc-100 text-zinc-700 border border-zinc-300" : "bg-emerald-100 text-emerald-800 border border-emerald-300"}`}>
              {data.dataSource}
            </span>
          </div>
          {data.quoteDelaySeconds !== undefined && data.quoteDelaySeconds > 0 && (
            <div>
              <span className="font-semibold text-zinc-700">Quote Delay:</span>{" "}
              {data.quoteDelaySeconds}s
            </div>
          )}
          <div className="text-zinc-400">
            • Educational analysis only • No orders are placed
          </div>
        </div>

        {/* Options Market Context Stats */}
        <div className="grid gap-4 mt-6 grid-cols-2 lg:grid-cols-4">
          <div className="rounded-md bg-panel p-4 border border-zinc-100">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-zinc-500">
              <span>Underlying Price</span>
              <DollarSign className="h-4 w-4 text-zinc-400" />
            </div>
            <div className="mt-2 text-2xl font-bold text-zinc-900">
              ${data.stock_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">Anchor stock price</div>
          </div>

          <div className="rounded-md bg-panel p-4 border border-zinc-100">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-zinc-500">
              <span>Implied Volatility</span>
              <Activity className="h-4 w-4 text-zinc-400" />
            </div>
            <div className="mt-2 text-2xl font-bold text-zinc-900">
              {formatIV(data.implied_volatility)}
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">Annualized IV</div>
          </div>

          <div className="rounded-md bg-panel p-4 border border-zinc-100">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-zinc-500">
              <span>IV Percentile (IVR)</span>
              <Percent className="h-4 w-4 text-zinc-400" />
            </div>
            <div className="mt-2 text-2xl font-bold text-zinc-900">
              {data.iv_percentile != null ? `${data.iv_percentile}%` : "Unavailable"}
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">Relative to 52W range</div>
          </div>

          <div className="rounded-md bg-panel p-4 border border-zinc-100">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-zinc-500">
              <span>Expected Expiry Move</span>
              <TrendingUp className="h-4 w-4 text-zinc-400" />
            </div>
            <div className="mt-2 text-2xl font-bold text-accent">
              ±{data.implied_move_percent != null ? `${data.implied_move_percent.toFixed(1)}%` : "Unavailable"}
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">Estimated monthly price range</div>
          </div>
        </div>

        {/* Options Market Sentiment Summary */}
        <div className="mt-5 rounded-md border border-amber-100 bg-amber-50/50 p-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-amber-800">
            Market Sentiment & Volatility View
          </h4>
          <p className="text-sm text-zinc-700 mt-1 leading-relaxed">
            {data.market_sentiment}
          </p>
        </div>
      </div>

      {/* Strategies Title */}
      <div>
        <h4 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Educational Options Strategy Candidates
        </h4>
      </div>

      {/* Options Strategies Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {data.strategies.length > 0 ? (
          data.strategies.map((strat: OptionsStrategyDetails, idx: number) => (
            <div key={idx} className="rounded-md border border-line bg-white p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold capitalize ${getStrategyTypeBadgeStyle(strat.type)}`}>
                    {strat.type}
                  </span>
                  <span className="text-xs text-zinc-400 inline-flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Exp: {new Date(strat.expiration).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                </div>

                <h3 className="text-lg font-bold text-zinc-900 mt-3">{strat.name}</h3>

                {/* Strike details table */}
                <div className="grid grid-cols-2 gap-y-3 gap-x-4 mt-4 text-sm border-b border-line pb-4 mb-4">
                  <div>
                    <span className="text-zinc-500 block text-xs">Strikes & Action</span>
                    <span className="font-semibold text-zinc-800">{strat.strikes}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-xs">Net Debit/Credit</span>
                    <span className={`font-semibold ${strat.net_credit_debit >= 0 ? "text-emerald-600" : "text-zinc-800"}`}>
                      {strat.net_credit_debit >= 0 ? "+" : ""}${Math.abs(strat.net_credit_debit).toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-xs">Probability of Profit</span>
                    <span className="font-semibold text-zinc-800">
                      {strat.probability_of_profit != null ? `${strat.probability_of_profit}%` : "Unavailable"}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-xs">Breakeven Stock Price</span>
                    <span className="font-semibold text-zinc-800">${strat.breakeven.toFixed(2)}</span>
                  </div>
                </div>

                {/* Risk Parameters */}
                <div className="grid grid-cols-2 gap-4 text-xs bg-panel p-3 rounded-md border border-zinc-100">
                  <div>
                    <span className="text-zinc-500 font-medium">Max Profit</span>
                    <p className="font-semibold text-emerald-700 mt-0.5">{strat.max_profit}</p>
                  </div>
                  <div>
                    <span className="text-zinc-500 font-medium">Max Loss</span>
                    <p className="font-semibold text-rose-700 mt-0.5">{strat.max_loss}</p>
                  </div>
                </div>

                {/* Account Eligibility Check */}
                <div className={`mt-4 p-3 rounded-md border text-xs flex items-start gap-2 ${strat.eligible ? "bg-zinc-50 border-zinc-200" : "bg-amber-50/50 border-amber-200"}`}>
                  <Shield className={`h-4 w-4 shrink-0 mt-0.5 ${strat.eligible ? "text-emerald-600" : "text-amber-600"}`} />
                  <div>
                    <span className="font-bold block uppercase tracking-wider text-[10px] text-zinc-500 mb-0.5">
                      Account Eligibility Check
                    </span>
                    <p className={`leading-relaxed ${strat.eligible ? "text-zinc-700" : "text-amber-800 font-semibold"}`}>
                      {strat.eligibility_reason}
                    </p>
                  </div>
                </div>

                {/* Rationale */}
                <div className="mt-4">
                  <span className="text-zinc-500 block text-xs font-semibold uppercase tracking-wider mb-1">Analysis & Rationale</span>
                  <p className="text-sm text-zinc-600 leading-relaxed">{strat.rationale}</p>
                </div>
              </div>

              {/* Disclaimer reminder at card bottom */}
              <div className="mt-6 pt-4 border-t border-line flex items-center justify-between text-[11px] text-zinc-400">
                <span className="inline-flex items-center gap-1">
                  <Shield className="h-3.5 w-3.5" /> Option Derivative Policy Check
                </span>
                <span className="hover:underline cursor-pointer inline-flex items-center gap-0.5">
                  Review parameters <ArrowRight className="h-3 w-3" />
                </span>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-md border border-line bg-white p-8 text-center col-span-2">
            <AlertTriangle className="h-8 w-8 text-zinc-400 mx-auto mb-2" />
            <p className="text-sm font-semibold text-zinc-800">No option strategies generated</p>
            <p className="text-xs text-zinc-500 mt-1">Please ensure Gemini is configured and active to generate options strategies.</p>
          </div>
        )}
      </div>

      {/* Compliance / Risk Disclaimer */}
      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
        <div className="flex gap-2">
          <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <h5 className="text-xs font-bold text-zinc-800 uppercase tracking-wide">Options Risk Disclosure & Disclaimer</h5>
            <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
              {data.disclaimer} Options trading involves significant risk of total premium loss and is not suitable for all investors. Assignment risk applies to all short options positions. The probability of profit (POP), max profit, max loss, and breakeven levels are mathematically calculated or estimated and do not represent guaranteed outcomes. This portfolio intelligence module is strictly for decision-support and educational analysis. No trading accounts are accessed for order placement, and no orders can be placed or executed.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
