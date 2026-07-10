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
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  jensens_alpha: number | null;
  tracking_error: number | null;
  information_ratio: number | null;
  correlation_matrix: Record<string, Record<string, number>>;
  factor_exposures: Record<string, number>;
  stress_tests: StressScenario[];
  data_quality: Record<string, string>;
  methodology: Record<string, string>;
}

interface PerformanceAttribution {
  security_selection_pnl: Record<string, number>;
  sector_allocation_pnl: Record<string, number>;
  asset_class_pnl: Record<string, number>;
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
            P&amp;L Breakdown &amp; Factor Profile
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-md bg-panel p-3">
              <h4 className="text-xs font-semibold uppercase text-zinc-500 mb-2">Realized vs. Unrealized</h4>
              <dl className="text-sm space-y-1">
                <div className="flex justify-between"><dt>Unrealized P&amp;L</dt><dd className="font-semibold text-accent">+{currencySymbol}{attribution.realized_vs_unrealized.unrealized.toLocaleString()}</dd></div>
                <div className="flex justify-between"><dt>Realized Profits</dt><dd className="font-semibold text-zinc-700">{currencySymbol}{attribution.realized_vs_unrealized.realized.toLocaleString()}</dd></div>
              </dl>
            </div>
            <div className="rounded-md bg-panel p-3">
              <h4 className="text-xs font-semibold uppercase text-zinc-500 mb-2">Benchmark Analysis</h4>
              <dl className="text-sm space-y-1">
                <div className="flex justify-between"><dt>Alpha vs SPY</dt><dd className="font-semibold text-zinc-700">{formatPercent(attribution.benchmark_relative_alpha)}</dd></div>
                <div className="flex justify-between"><dt>Benchmark data</dt><dd className="text-zinc-600">{attribution.data_quality?.benchmark_data ?? "Unavailable"}</dd></div>
              </dl>
            </div>
          </div>

          <div className="mt-4">
            <h4 className="text-xs font-semibold uppercase text-zinc-500 mb-2">
              {advancedRisk.data_quality?.factor_model === "experimental"
                ? "Experimental Factor Exposures"
                : "Strategic Factor Exposures"}
            </h4>
            <div className="space-y-2">
              {Object.entries(advancedRisk.factor_exposures).map(([factor, value]) => {
                const isExperimental = advancedRisk.data_quality?.factor_model === "experimental";
                const label = isExperimental ? `${value.toFixed(2)}x` : `${value.toFixed(1)}%`;
                const width = isExperimental
                  ? `${Math.min(100, Math.abs(value) * 50)}%`
                  : `${value}%`;
                return (
                <div key={factor} className="space-y-1">
                  <div className="flex justify-between text-xs font-medium">
                    <span>{factor}</span>
                    <span>{label}</span>
                  </div>
                  <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                    <div className="h-full bg-accent rounded-full" style={{ width }} />
                  </div>
                </div>
              )})}
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

      <section className="rounded-md border border-line bg-white p-6">
        <h3 className="mb-4 text-lg font-semibold inline-flex items-center gap-2">
          <ShieldAlert size={18} className="text-accent" />
          Risk-Adjusted Performance Indicators (Institutional Metrics)
        </h3>
        {advancedRisk.data_quality?.historical_metrics !== "sufficient" && (
          <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            Historical portfolio metrics are withheld until actual account snapshots and a complete
            external-cash-flow activity ledger cover the measurement period (
            {advancedRisk.data_quality?.cash_flow_ledger ?? "ledger unavailable"}).
            Security correlations below, when present, come from an ex-ante current-holdings model (
            {advancedRisk.data_quality?.security_return_series ?? "unavailable"}), not realized account history.
          </div>
        )}
        <p className="text-xs text-zinc-500 mb-6 -mt-3">
          Metrics use cash-flow-adjusted account returns when the activity ledger is complete. Risk-free rate
          comes from server configuration. Correlation diagnostics use today&apos;s holdings backcast separately.
        </p>
        
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {/* Sharpe Card */}
          <div className="rounded-md bg-panel p-4 border border-line/30 hover:border-accent/30 transition-all duration-300 relative group">
            <div className="text-xs font-semibold uppercase text-zinc-500 flex justify-between items-center">
              <span>Sharpe Ratio</span>
              <span className="text-zinc-400 cursor-help group-hover:text-accent font-normal text-[10px]">ℹ️
                <span className="invisible group-hover:visible absolute left-0 bottom-full mb-2 z-10 w-64 bg-zinc-800 text-white text-[11px] p-2 rounded shadow-lg normal-case font-normal leading-relaxed">
                  {advancedRisk.methodology?.sharpe_ratio || "Excess return per unit of total risk (volatility). High Sharpe indicates high return efficiency."}
                </span>
              </span>
            </div>
            <div className={`mt-2 text-2xl font-bold font-mono ${
              advancedRisk.sharpe_ratio !== null && advancedRisk.sharpe_ratio >= 1.5 
                ? "text-accent" 
                : advancedRisk.sharpe_ratio !== null && advancedRisk.sharpe_ratio >= 1.0 
                ? "text-teal-600" 
                : advancedRisk.sharpe_ratio !== null && advancedRisk.sharpe_ratio < 0 
                ? "text-danger" 
                : "text-zinc-700"
            }`}>
              {formatNumber(advancedRisk.sharpe_ratio)}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              {advancedRisk.sharpe_ratio !== null && advancedRisk.sharpe_ratio >= 1.0 ? "Efficient Excess Return" : "Risk-to-volatility ratio"}
            </div>
          </div>

          {/* Sortino Card */}
          <div className="rounded-md bg-panel p-4 border border-line/30 hover:border-accent/30 transition-all duration-300 relative group">
            <div className="text-xs font-semibold uppercase text-zinc-500 flex justify-between items-center">
              <span>Sortino Ratio</span>
              <span className="text-zinc-400 cursor-help group-hover:text-accent font-normal text-[10px]">ℹ️
                <span className="invisible group-hover:visible absolute left-0 bottom-full mb-2 z-10 w-64 bg-zinc-800 text-white text-[11px] p-2 rounded shadow-lg normal-case font-normal leading-relaxed">
                  {advancedRisk.methodology?.sortino_ratio || "Excess return per unit of downside deviation. Ignores upside volatility, penalizing only negative returns."}
                </span>
              </span>
            </div>
            <div className={`mt-2 text-2xl font-bold font-mono ${
              advancedRisk.sortino_ratio !== null && advancedRisk.sortino_ratio >= 1.5 
                ? "text-accent" 
                : advancedRisk.sortino_ratio !== null && advancedRisk.sortino_ratio < 0 
                ? "text-danger" 
                : "text-zinc-700"
            }`}>
              {formatNumber(advancedRisk.sortino_ratio)}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              Downside risk-adjusted ratio
            </div>
          </div>

          {/* Jensen's Alpha Card */}
          <div className="rounded-md bg-panel p-4 border border-line/30 hover:border-accent/30 transition-all duration-300 relative group">
            <div className="text-xs font-semibold uppercase text-zinc-500 flex justify-between items-center">
              <span>Jensen&apos;s Alpha</span>
              <span className="text-zinc-400 cursor-help group-hover:text-accent font-normal text-[10px]">ℹ️
                <span className="invisible group-hover:visible absolute left-0 bottom-full mb-2 z-10 w-64 bg-zinc-800 text-white text-[11px] p-2 rounded shadow-lg normal-case font-normal leading-relaxed">
                  {advancedRisk.methodology?.jensens_alpha || "The portfolio's excess return relative to the market CAPM prediction. Positive means outperforming the beta-adjusted benchmark."}
                </span>
              </span>
            </div>
            <div className={`mt-2 text-2xl font-bold font-mono ${
              advancedRisk.jensens_alpha !== null && advancedRisk.jensens_alpha > 0 
                ? "text-accent" 
                : advancedRisk.jensens_alpha !== null && advancedRisk.jensens_alpha < 0 
                ? "text-danger" 
                : "text-zinc-700"
            }`}>
              {advancedRisk.jensens_alpha !== null && advancedRisk.jensens_alpha > 0 ? "+" : ""}
              {formatPercent(advancedRisk.jensens_alpha)}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              Annualized excess return vs SPY
            </div>
          </div>

          {/* Tracking Error Card */}
          <div className="rounded-md bg-panel p-4 border border-line/30 hover:border-accent/30 transition-all duration-300 relative group">
            <div className="text-xs font-semibold uppercase text-zinc-500 flex justify-between items-center">
              <span>Tracking Error</span>
              <span className="text-zinc-400 cursor-help group-hover:text-accent font-normal text-[10px]">ℹ️
                <span className="invisible group-hover:visible absolute left-0 bottom-full mb-2 z-10 w-64 bg-zinc-800 text-white text-[11px] p-2 rounded shadow-lg normal-case font-normal leading-relaxed">
                  {advancedRisk.methodology?.tracking_error || "Standard deviation of the differences between the portfolio and market returns. Measures active benchmark deviation risk."}
                </span>
              </span>
            </div>
            <div className="mt-2 text-2xl font-bold text-zinc-700 font-mono">
              {formatPercent(advancedRisk.tracking_error)}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              Annualized active deviation
            </div>
          </div>

          {/* Information Ratio Card */}
          <div className="rounded-md bg-panel p-4 border border-line/30 hover:border-accent/30 transition-all duration-300 relative group">
            <div className="text-xs font-semibold uppercase text-zinc-500 flex justify-between items-center">
              <span>Information Ratio</span>
              <span className="text-zinc-400 cursor-help group-hover:text-accent font-normal text-[10px]">ℹ️
                <span className="invisible group-hover:visible absolute left-0 bottom-full mb-2 z-10 w-64 bg-zinc-800 text-white text-[11px] p-2 rounded shadow-lg normal-case font-normal leading-relaxed">
                  {advancedRisk.methodology?.information_ratio || "Active return vs benchmark divided by the active tracking error. Measures manager's ability to consistently generate alpha relative to active risk."}
                </span>
              </span>
            </div>
            <div className={`mt-2 text-2xl font-bold font-mono ${
              advancedRisk.information_ratio !== null && advancedRisk.information_ratio >= 0.5 
                ? "text-accent" 
                : advancedRisk.information_ratio !== null && advancedRisk.information_ratio < 0 
                ? "text-danger" 
                : "text-zinc-700"
            }`}>
              {formatNumber(advancedRisk.information_ratio)}
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">
              Excess return active efficiency
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase text-zinc-500">Historical Drawdown</div>
          <div className="mt-2 text-2xl font-bold text-danger">{formatPercent(advancedRisk.max_drawdown, true)}</div>
          <div className="mt-1 text-xs text-zinc-500">Cash-flow-adjusted account series when ledger is complete</div>
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
          <div className="text-xs font-semibold uppercase text-zinc-500">Parametric VaR (95% Daily)</div>
          <div className="mt-2 text-2xl font-bold text-zinc-700">{formatCurrency(advancedRisk.value_at_risk_95, currencySymbol)}</div>
          <div className="mt-1 text-xs text-zinc-500">CVaR: {formatCurrency(advancedRisk.conditional_var_95, currencySymbol)}</div>
        </div>
      </section>
    </div>
  );
}

function formatPercent(value: number | null | undefined, negative = false) {
  if (value === null || value === undefined) return "Unavailable";
  return `${negative ? "-" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "Unavailable" : value.toFixed(2);
}

function formatCurrency(value: number | null | undefined, symbol: string) {
  return value === null || value === undefined
    ? "Unavailable"
    : `${symbol}${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
