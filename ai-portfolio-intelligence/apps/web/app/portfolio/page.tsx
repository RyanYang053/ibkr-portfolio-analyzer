import { AllocationBars } from "@/components/AllocationBars";
import { Disclaimer } from "@/components/Disclaimer";
import { HoldingsTable } from "@/components/HoldingsTable";
import { StatCard } from "@/components/StatCard";
import {
  getPortfolioSummary,
  getPositions,
  getAdvancedRiskMetrics,
  getPerformanceAttribution,
  getRebalanceProposal,
  getOptimizationProposal,
} from "@/lib/api";
import type { PortfolioRisk, Position } from "@/lib/types";
import { DonutChart } from "@/components/DonutChart";
import { ProfessionalRiskDashboard } from "@/components/ProfessionalRiskDashboard";
import { PortfolioConstructionPanel } from "@/components/PortfolioConstructionPanel";

export const dynamic = "force-dynamic";

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
  // Ensure risk is fully initialized to avoid undefined property access elsewhere on the page
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

interface PageProps {
  searchParams: Promise<{ account_id?: string }>;
}

export default async function PortfolioPage(props: PageProps) {
  const searchParams = await props.searchParams;
  const accountId = searchParams.account_id || undefined;

  const [summary, positions, advancedRisk, attribution, rebalance, optimization] = await Promise.all([
    getPortfolioSummary(accountId),
    getPositions(accountId),
    getAdvancedRiskMetrics(accountId),
    getPerformanceAttribution(accountId),
    getRebalanceProposal(accountId),
    getOptimizationProposal(accountId),
  ]);
  const { risk, derivedFromPositions } = deriveRiskFromPositions(summary.risk, positions);
  const [topCurrency, topCurrencyWeight] = topExposure(risk.currency_exposure);

  const suitabilityWarnings = summary.suitability_warnings ?? [];

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Holdings and allocation</p>
        <h2 className="text-3xl font-semibold">Portfolio</h2>
      </div>
      <Disclaimer />
      {positions.length === 0 ? (
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
      
      <HoldingsTable positions={positions} />

      <PortfolioConstructionPanel
        rebalance={rebalance}
        optimization={optimization}
        baseCurrency={summary.summary.base_currency}
      />
      
      <ProfessionalRiskDashboard
        suitabilityWarnings={suitabilityWarnings}
        advancedRisk={advancedRisk}
        attribution={attribution}
        baseCurrency={summary.summary.base_currency}
      />

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
