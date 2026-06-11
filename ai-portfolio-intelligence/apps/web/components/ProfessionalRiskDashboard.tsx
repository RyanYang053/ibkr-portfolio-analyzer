"use client";

import { ShieldAlert, TrendingUp, Flame } from "lucide-react";

interface StressScenario {
  name: string;
  description: string;
  portfolio_change_pct: number;
  estimated_loss: number;
  risk_level: string;
}

interface AdvancedRiskMetrics {
  max_drawdown: number | null;
  volatility: number | null;
  portfolio_beta_spy: number | null;
  portfolio_beta_qqq: number | null;
  value_at_risk_95: number | null;
  conditional_var_95: number | null;
  correlation_matrix: Record<string, Record<string, number>>;
  factor_exposures: Record<string, number>;
  stress_tests: StressScenario[];
  data_quality: Record<string, string>;
  methodology: Record<string, string>;
}

interface PerformanceAttribution {
  security_selection_return: Record<string, number>;
  sector_allocation_return: Record<string, number>;
  asset_class_return: Record<string, number>;
  realized_vs_unrealized: { realized: number; unrealized: number };
  benchmark_relative_alpha: number | null;
  data_quality: Record<string, string>;
  methodology: string;
}

interface ProfessionalRiskDashboardProps {
  suitabilityWarnings: string[];
  advancedRisk: AdvancedRiskMetrics;
  attribution: PerformanceAttribution;
  baseCurrency?: string;
}

export function ProfessionalRiskDashboard({
  suitabilityWarnings,
  advancedRisk,
  attribution,
  baseCurrency = "USD"
}: ProfessionalRiskDashboardProps) {
  const currencySymbol = baseCurrency === "CAD" ? "C$" : "$";

  return (
    <div className="grid gap-6">
      {suitabilityWarnings && suitabilityWarnings.length > 0 && (
        <div className="rounded-md border border-warning bg-amber-50 p-4">
          <div className="flex gap-3">
            <ShieldAlert className="text-warning flex-shrink-0" size={24} aria-hidden />
            <div>
              <h4 className="text-sm font-semibold text-amber-900">Suitability & Compliance Warnings</h4>
              <ul className="mt-2 text-xs text-amber-800 list-disc pl-4 space-y-1">
                {suitabilityWarnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold inline-flex items-center gap-2">
            <TrendingUp size={18} className="text-accent" />
            P&amp;L Breakdown &amp; Heuristic Factor Profile
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-md bg-panel p-3">
              <h4 className="text-xs font-semibold uppercase text-zinc-500 mb-2">Realized vs. Unrealized</h4>
              <dl className="text-sm space-y-1">
                <div className="flex justify-between"><dt>Unrealized Return</dt><dd className="font-semibold text-accent">+{currencySymbol}{attribution.realized_vs_unrealized.unrealized.toLocaleString()}</dd></div>
                <div className="flex justify-between"><dt>Realized Profits</dt><dd className="font-semibold text-zinc-700">{currencySymbol}{attribution.realized_vs_unrealized.realized.toLocaleString()}</dd></div>
              </dl>
            </div>
            <div className="rounded-md bg-panel p-3">
              <h4 className="text-xs font-semibold uppercase text-zinc-500 mb-2">Benchmark Analysis</h4>
              <dl className="text-sm space-y-1">
                <div className="flex justify-between"><dt>Alpha vs SPY</dt><dd className="font-semibold text-zinc-700">{formatPercent(attribution.benchmark_relative_alpha)}</dd></div>
                <div className="flex justify-between"><dt>Benchmark data</dt><dd className="text-zinc-600">Unavailable</dd></div>
              </dl>
            </div>
          </div>

          <div className="mt-4">
            <h4 className="text-xs font-semibold uppercase text-zinc-500 mb-2">Strategic Factor Exposures</h4>
            <div className="space-y-2">
              {Object.entries(advancedRisk.factor_exposures).map(([factor, value]) => (
                <div key={factor} className="space-y-1">
                  <div className="flex justify-between text-xs font-medium">
                    <span>{factor}</span>
                    <span>{value.toFixed(1)}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                    <div className="h-full bg-accent rounded-full" style={{ width: `${value}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold inline-flex items-center gap-2">
            <Flame size={18} className="text-danger" />
            Illustrative Stress Scenarios
          </h3>
          <div className="space-y-3">
            {advancedRisk.stress_tests.map((scenario, idx) => (
              <div key={idx} className="p-3 rounded-md bg-panel hover:bg-zinc-50 transition-colors border border-line/40">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-sm">{scenario.name}</h4>
                    <p className="text-xs text-zinc-500 mt-1">{scenario.description}</p>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                      scenario.risk_level === "High" ? "bg-red-50 text-danger" : "bg-amber-50 text-warning"
                    }`}>
                      {scenario.risk_level} Risk
                    </span>
                    <div className="mt-1 font-semibold text-sm text-danger font-mono">
                      {scenario.portfolio_change_pct.toFixed(2)}%
                    </div>
                    <div className="text-xs text-zinc-600 font-mono mt-0.5">
                      -{currencySymbol}{scenario.estimated_loss.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase text-zinc-500">Historical Drawdown</div>
          <div className="mt-2 text-2xl font-bold text-danger">{formatPercent(advancedRisk.max_drawdown, true)}</div>
          <div className="mt-1 text-xs text-zinc-500">Account-value series; not cash-flow adjusted</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase text-zinc-500">Annualized Volatility</div>
          <div className="mt-2 text-2xl font-bold text-zinc-700">{formatPercent(advancedRisk.volatility)}</div>
          <div className="mt-1 text-xs text-zinc-500">Requires at least 20 daily observations</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase text-zinc-500">Portfolio Beta</div>
          <div className="mt-2 text-2xl font-bold text-zinc-700">{formatNumber(advancedRisk.portfolio_beta_spy)} <span className="text-xs font-normal text-zinc-500">(SPY)</span></div>
          <div className="mt-1 text-xs text-zinc-500">{formatNumber(advancedRisk.portfolio_beta_qqq)} vs QQQ</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase text-zinc-500">Value at Risk (95% Daily)</div>
          <div className="mt-2 text-2xl font-bold text-zinc-700">{formatCurrency(advancedRisk.value_at_risk_95, currencySymbol)}</div>
          <div className="mt-1 text-xs text-zinc-500">CVaR: {formatCurrency(advancedRisk.conditional_var_95, currencySymbol)}</div>
        </div>
      </section>
    </div>
  );
}

function formatPercent(value: number | null, negative = false) {
  if (value === null) return "Unavailable";
  return `${negative ? "-" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value: number | null) {
  return value === null ? "Unavailable" : value.toFixed(2);
}

function formatCurrency(value: number | null, symbol: string) {
  return value === null
    ? "Unavailable"
    : `${symbol}${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
