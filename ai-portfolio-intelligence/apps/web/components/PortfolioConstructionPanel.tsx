"use client";

import { useState } from "react";
import { Scale, Sparkles } from "lucide-react";
import type { PortfolioOptimizationProposal, RebalanceProposal } from "@/lib/types";

type PortfolioConstructionPanelProps = {
  rebalance: RebalanceProposal;
  optimization: PortfolioOptimizationProposal;
  baseCurrency?: string;
};

type TradeRow = {
  symbol: string;
  action: string;
  current_weight: number;
  proposed_weight: number;
  proposed_trade_value: number;
  reason: string;
};

export function PortfolioConstructionPanel({
  rebalance,
  optimization,
  baseCurrency = "USD",
}: PortfolioConstructionPanelProps) {
  const [activeTab, setActiveTab] = useState<"rebalance" | "optimize">("rebalance");
  const currencySymbol = baseCurrency === "CAD" ? "C$" : "$";

  const rebalanceRows: TradeRow[] = rebalance.proposed_trades.map((trade) => ({
    symbol: trade.symbol,
    action: trade.action,
    current_weight: trade.current_weight,
    proposed_weight: trade.target_weight,
    proposed_trade_value: trade.proposed_trade_value,
    reason: trade.reason,
  }));

  const optimizationRows: TradeRow[] = optimization.proposed_trades.map((trade) => ({
    symbol: trade.symbol,
    action: trade.action,
    current_weight: trade.current_weight,
    proposed_weight: trade.optimal_weight,
    proposed_trade_value: trade.proposed_trade_value,
    reason: trade.reason,
  }));

  const activeRows = activeTab === "rebalance" ? rebalanceRows : optimizationRows;
  const activeTrades = activeRows.filter((trade) => trade.action !== "Hold");

  return (
    <section className="rounded-md border border-line bg-white p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold">Portfolio Construction Review</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Read-only proposals for policy rebalancing and mean-variance optimization. No orders are submitted.
          </p>
        </div>
        <div className="inline-flex rounded-md border border-line bg-panel p-1 text-sm">
          <button
            type="button"
            onClick={() => setActiveTab("rebalance")}
            className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 transition-colors ${
              activeTab === "rebalance" ? "bg-white text-ink shadow-sm" : "text-zinc-600 hover:text-ink"
            }`}
          >
            <Scale size={15} aria-hidden />
            Rebalance
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("optimize")}
            className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 transition-colors ${
              activeTab === "optimize" ? "bg-white text-ink shadow-sm" : "text-zinc-600 hover:text-ink"
            }`}
          >
            <Sparkles size={15} aria-hidden />
            Optimize
          </button>
        </div>
      </div>

      {activeTab === "rebalance" ? (
        <ProposalSummary
          unavailable={rebalance.unavailable}
          emptyMessage="No policy-driven rebalance trades are required, or the proposal is unavailable."
          metrics={[
            { label: "Estimated cash impact", value: formatCurrency(rebalance.cash_impact, currencySymbol) },
            { label: "Proposed trades", value: String(activeTrades.length) },
          ]}
          warning={rebalance.tax_impact_warning}
          methodology="Bounded rebalance review based on your IPS drift, concentration limits, and cash floor."
        />
      ) : (
        <ProposalSummary
          unavailable={optimization.unavailable}
          emptyMessage="Optimization requires at least two long equity positions with sufficient return history."
          metrics={[
            { label: "Expected volatility", value: formatPercent(optimization.expected_volatility) },
            { label: "Expected return", value: formatPercent(optimization.expected_return) },
            { label: "Sharpe (modeled)", value: formatNumber(optimization.sharpe_ratio) },
            { label: "Proposed trades", value: String(activeTrades.length) },
          ]}
          warning={optimization.methodology}
          constraints={optimization.constraints_applied}
        />
      )}

      {activeTrades.length === 0 ? (
        <div className="mt-4 rounded-md border border-line bg-panel p-4 text-sm text-zinc-600">
          {activeTab === "rebalance" && rebalance.unavailable
            ? rebalance.tax_impact_warning
            : activeTab === "optimize" && optimization.unavailable
              ? optimization.methodology
              : "No actionable trades in this proposal."}
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-md border border-line">
          <table className="min-w-full text-sm">
            <thead className="bg-panel text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-3">Symbol</th>
                <th className="px-3 py-3">Action</th>
                <th className="px-3 py-3 text-right">Current wt.</th>
                <th className="px-3 py-3 text-right">{activeTab === "rebalance" ? "Target wt." : "Optimal wt."}</th>
                <th className="px-3 py-3 text-right">Trade value</th>
                <th className="px-3 py-3">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {activeTrades.map((trade) => (
                <tr key={`${trade.symbol}-${trade.action}`} className="border-t border-line">
                  <td className="px-3 py-3 font-semibold">{trade.symbol}</td>
                  <td className="px-3 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        trade.action === "Buy"
                          ? "bg-teal-50 text-accent"
                          : trade.action === "Sell"
                            ? "bg-red-50 text-danger"
                            : "bg-zinc-100 text-zinc-600"
                      }`}
                    >
                      {trade.action}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right">{trade.current_weight.toFixed(2)}%</td>
                  <td className="px-3 py-3 text-right">{trade.proposed_weight.toFixed(2)}%</td>
                  <td
                    className={`px-3 py-3 text-right font-mono ${
                      trade.proposed_trade_value >= 0 ? "text-accent" : "text-danger"
                    }`}
                  >
                    {formatCurrency(trade.proposed_trade_value, currencySymbol)}
                  </td>
                  <td className="px-3 py-3 text-xs text-zinc-600">{trade.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-zinc-500">
        {activeTab === "rebalance" ? rebalance.compliance_disclaimer : optimization.compliance_disclaimer}
      </p>
    </section>
  );
}

function ProposalSummary({
  unavailable,
  emptyMessage,
  metrics,
  warning,
  methodology,
  constraints,
}: {
  unavailable?: boolean;
  emptyMessage: string;
  metrics: Array<{ label: string; value: string }>;
  warning?: string;
  methodology?: string;
  constraints?: string[];
}) {
  return (
    <div className="grid gap-3">
      {unavailable ? (
        <div className="rounded-md border border-warning bg-amber-50 p-3 text-sm text-amber-900">{emptyMessage}</div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="rounded-md bg-panel p-3">
            <div className="text-xs font-semibold uppercase text-zinc-500">{metric.label}</div>
            <div className="mt-1 text-lg font-semibold text-zinc-800">{metric.value}</div>
          </div>
        ))}
      </div>
      {methodology ? <p className="text-xs text-zinc-600">{methodology}</p> : null}
      {warning ? <p className="rounded-md border border-line bg-zinc-50 p-3 text-xs text-zinc-700">{warning}</p> : null}
      {constraints && constraints.length > 0 ? (
        <ul className="list-disc pl-5 text-xs text-zinc-600">
          {constraints.map((constraint) => (
            <li key={constraint}>{constraint}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return "Unavailable";
  return `${value.toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return "Unavailable";
  return value.toFixed(2);
}

function formatCurrency(value: number, symbol: string) {
  const sign = value >= 0 ? "+" : "-";
  return `${sign}${symbol}${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
