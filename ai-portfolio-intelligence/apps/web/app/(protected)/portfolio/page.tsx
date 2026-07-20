"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Disclaimer } from "@/components/Disclaimer";
import { HoldingsTable } from "@/components/HoldingsTable";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import {
  ApiError,
  formatApiError,
  getAdvancedRiskMetrics,
  getOptimizationProposal,
  getPerformanceAttribution,
  getPortfolioSummary,
  getPositions,
  getRebalanceProposal,
} from "@/lib/api";
import type { PortfolioOptimizationProposal, PortfolioRisk, Position, RebalanceProposal } from "@/lib/types";
import { DonutChart } from "@/components/DonutChart";
import { ProfessionalRiskDashboard } from "@/components/ProfessionalRiskDashboard";
import { PortfolioConstructionPanel } from "@/components/PortfolioConstructionPanel";
import { DataQualityPanel } from "@/components/DataQualityBadge";
import { CalculationLineagePanel } from "@/components/CalculationLineagePanel";

function sumWeights(positions: Position[], predicate: (position: Position) => boolean) {
  return positions.reduce((total, position) => total + (predicate(position) ? position.portfolio_weight : 0), 0);
}

function groupExposure(positions: Position[], key: "sector" | "currency") {
  return positions.reduce<Record<string, number>>((exposure, position) => {
    const label = position[key]?.trim() || "Unknown";
    exposure[label] = (exposure[label] ?? 0) + position.portfolio_weight;
    return exposure;
  }, {});
}

function shouldUsePositionDerivedRisk(risk: PortfolioRisk, positions: Position[]) {
  const hasLivePositionValue = positions.some((position) => position.market_value > 0);
  const hasPositionWeights = sumWeights(positions, (position) => position.market_value > 0) > 0;
  const hasInvestedRiskExposure =
    (risk?.etf_percent ?? 0) > 0 ||
    (risk?.single_stock_percent ?? 0) > 0 ||
    (risk?.speculative_percent ?? 0) > 0 ||
    Object.values(risk?.sector_exposure ?? {}).some((value) => value > 0);

  return hasLivePositionValue && hasPositionWeights && ((risk?.total_value ?? 0) <= 0 || !hasInvestedRiskExposure);
}

function deriveRiskFromPositions(risk: PortfolioRisk, positions: Position[]) {
  const safeRisk: PortfolioRisk = {
    total_value: risk?.total_value ?? 0,
    risk_score: risk?.risk_score ?? 0,
    cash_percent: risk?.cash_percent ?? 0,
    etf_percent: risk?.etf_percent ?? 0,
    single_stock_percent: risk?.single_stock_percent ?? 0,
    speculative_percent: risk?.speculative_percent ?? 0,
    sector_exposure: risk?.sector_exposure ?? {},
    currency_exposure: risk?.currency_exposure ?? {},
    top_5_concentration: risk?.top_5_concentration ?? 0,
    herfindahl_concentration_score: risk?.herfindahl_concentration_score ?? 0,
    herfindahl_concentration_label: risk?.herfindahl_concentration_label ?? "Unknown",
    margin_usage_percent: risk?.margin_usage_percent ?? 0,
    alerts: risk?.alerts ?? [],
  };

  if (!shouldUsePositionDerivedRisk(safeRisk, positions)) {
    return { risk: safeRisk, derivedFromPositions: false };
  }

  const totalValue = positions.reduce((total, position) => total + Math.max(position.market_value, 0), 0);

  return {
    derivedFromPositions: true,
    risk: {
      ...safeRisk,
      total_value: totalValue,
      etf_percent: sumWeights(positions, (position) => position.is_etf),
      single_stock_percent: sumWeights(positions, (position) => !position.is_etf),
      speculative_percent: sumWeights(positions, (position) => position.is_speculative),
      sector_exposure: groupExposure(positions, "sector"),
      currency_exposure: groupExposure(positions, "currency"),
    },
  };
}

function topExposure(exposure: Record<string, number>) {
  return Object.entries(exposure).sort(([, first], [, second]) => second - first)[0] ?? ["None", 0];
}

const emptyRebalanceProposal: RebalanceProposal = {
  proposed_trades: [],
  cash_impact: 0,
  tax_impact_warning: "Rebalance proposal unavailable for consolidated view.",
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
  methodology: "Optimization proposal unavailable for consolidated view.",
  compliance_disclaimer: "Review only. This application does not execute trades.",
  unavailable: true,
};

type PortfolioState = {
  loading: boolean;
  loadError: string | null;
  summary: Awaited<ReturnType<typeof getPortfolioSummary>> | null;
  positions: Position[];
  advancedRisk: Record<string, unknown> | null;
  attribution: Record<string, unknown> | null;
  rebalance: RebalanceProposal;
  optimization: PortfolioOptimizationProposal;
  analyticsError: string | null;
};

function PortfolioContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const professionalAnalyticsAvailable = Boolean(accountId && accountId !== "all");

  const [state, setState] = useState<PortfolioState>({
    loading: true,
    loadError: null,
    summary: null,
    positions: [],
    advancedRisk: null,
    attribution: null,
    rebalance: emptyRebalanceProposal,
    optimization: emptyOptimizationProposal,
    analyticsError: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setState((current) => ({ ...current, loading: true, loadError: null, analyticsError: null }));

      try {
        const [summary, positions] = await Promise.all([
          getPortfolioSummary(accountId),
          getPositions(accountId),
        ]);

        let advancedRisk: Record<string, unknown> | null = null;
        let attribution: Record<string, unknown> | null = null;
        let rebalance: RebalanceProposal = emptyRebalanceProposal;
        let optimization: PortfolioOptimizationProposal = emptyOptimizationProposal;
        let analyticsError: string | null = null;

        if (professionalAnalyticsAvailable) {
          try {
            [advancedRisk, attribution, rebalance, optimization] = await Promise.all([
              getAdvancedRiskMetrics(accountId),
              getPerformanceAttribution(accountId),
              getRebalanceProposal(accountId),
              getOptimizationProposal(accountId),
            ]);
          } catch (error) {
            if (error instanceof ApiError) {
              analyticsError =
                typeof error.detail === "object" && error.detail && "message" in (error.detail as object)
                  ? String((error.detail as { message?: string }).message)
                  : `Professional analytics unavailable (${error.status}).`;
            } else {
              analyticsError = "Professional analytics unavailable.";
            }
          }
        }

        if (!cancelled) {
          setState({
            loading: false,
            loadError: null,
            summary,
            positions,
            advancedRisk,
            attribution,
            rebalance,
            optimization,
            analyticsError,
          });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            loading: false,
            loadError: formatApiError(error),
            summary: null,
            positions: [],
            advancedRisk: null,
            attribution: null,
            rebalance: emptyRebalanceProposal,
            optimization: emptyOptimizationProposal,
            analyticsError: null,
          });
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [accountId, professionalAnalyticsAvailable]);

  if (state.loading) {
    return <PageLoading />;
  }

  if (!state.summary) {
    return (
      <div className="grid gap-6">
        <Disclaimer />
        <PageErrorBanner message={state.loadError ?? "Portfolio data is unavailable."} />
      </div>
    );
  }

  const { risk, derivedFromPositions } = deriveRiskFromPositions(state.summary.risk, state.positions);
  const [topCurrency, topCurrencyWeight] = topExposure(risk.currency_exposure);
  const suitabilityWarnings = state.summary.suitability_warnings ?? [];
  const advancedRisk = state.advancedRisk as any;
  const attribution = state.attribution as any;

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Holdings and allocation</p>
        <h2 className="text-3xl font-semibold">Portfolio</h2>
      </div>
      <Disclaimer />
      {!professionalAnalyticsAvailable ? (
        <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">
          Select a specific account to view performance, historical risk, attribution, tax lots, and construction proposals.
        </div>
      ) : null}
      {state.analyticsError ? (
        <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">
          {state.analyticsError}
        </div>
      ) : null}
      {state.positions.length === 0 ? (
        <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">
          No live IBKR read-only portfolio is connected. Mock holdings are disabled.
        </div>
      ) : null}
      {derivedFromPositions ? (
        <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">
          Risk summary is unavailable, so exposure is derived from the live holdings shown below.
        </div>
      ) : null}
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="ETF Exposure" value={`${risk.etf_percent.toFixed(2)}%`} />
        <StatCard label="Single-Stock Exposure" value={`${risk.single_stock_percent.toFixed(2)}%`} />
        <StatCard label="Speculative Exposure" value={`${risk.speculative_percent.toFixed(2)}%`} tone="warn" />
        <StatCard label="Currency Exposure" value={topCurrency} detail={`${topCurrencyWeight.toFixed(2)}%`} />
      </section>

      <HoldingsTable positions={state.positions} />

      <PortfolioConstructionPanel
        rebalance={state.rebalance}
        optimization={state.optimization}
        baseCurrency={state.summary.summary.base_currency}
      />

      {advancedRisk && attribution ? (
        <ProfessionalRiskDashboard
          suitabilityWarnings={suitabilityWarnings}
          advancedRisk={advancedRisk}
          attribution={attribution}
          baseCurrency={state.summary.summary.base_currency}
        />
      ) : null}

      {advancedRisk ? (
        <section className="grid gap-4 xl:grid-cols-2">
          <DataQualityPanel dataQuality={advancedRisk.data_quality ?? {}} />
          <CalculationLineagePanel
            calculationRunId={advancedRisk.calculation_run_id}
            methodology={advancedRisk.methodology}
            exclusions={Object.entries(advancedRisk.data_quality ?? {})
              .filter(([, value]) => value === "missing" || value === "insufficient")
              .map(([key]) => key)}
            factorModelStatus={advancedRisk.factor_model_status}
          />
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold">Sector Allocation</h3>
          <DonutChart data={risk.sector_exposure} title="Sectors" />
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold">Currency Allocation</h3>
          <DonutChart data={risk.currency_exposure} title="Currencies" />
        </div>
      </section>
    </div>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <PortfolioContent />
    </Suspense>
  );
}
