"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowUpRight } from "lucide-react";

import { Disclaimer } from "@/components/Disclaimer";
import { HoldingsTable } from "@/components/HoldingsTable";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import {
  getPnlHistory,
  getPortfolioSummary,
  getRecommendations,
  getScheduleSettings,
} from "@/lib/api";
import { RiskGauge } from "@/components/RiskGauge";
import { DonutChart } from "@/components/DonutChart";
import { PerformanceSparkline } from "@/components/PerformanceSparkline";
import { AIPnlChart } from "@/components/AIPnlChart";
import { DailyActionsPanel } from "@/components/DailyActionsPanel";
import { useClientResource } from "@/lib/use-client-resource";

function DashboardContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;

  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getPortfolioSummary(accountId),
        getRecommendations(accountId),
        getPnlHistory(accountId),
        getScheduleSettings(),
      ]),
    [accountId],
  );

  if (loading) {
    return <PageLoading />;
  }

  let loadError = error;
  const [summaryData, recommendationResponse, pnlHistory, scheduleData] = data ?? [null, null, [], { runs: [] }];

  if (!summaryData && !loadError) {
    loadError = "Portfolio data is unavailable.";
  }

  if (!summaryData) {
    return (
      <div className="grid gap-6">
        <Disclaimer />
        <PageErrorBanner message={loadError ?? "Portfolio data is unavailable."} />
      </div>
    );
  }

  const topIdeas = (recommendationResponse?.recommendations ?? []).slice(0, 4);
  const sparklineValues =
    pnlHistory && pnlHistory.length >= 2
      ? pnlHistory.map((entry: { net_liquidation: number }) => entry.net_liquidation)
      : [summaryData.summary.net_liquidation, summaryData.summary.net_liquidation];

  return (
    <div className="grid gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">Portfolio analyst workspace</p>
          <h2 className="text-3xl font-semibold">Dashboard</h2>
        </div>
        <Link className="inline-flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm hover:bg-panel" href="/reports">
          View reports <ArrowUpRight size={16} aria-hidden />
        </Link>
      </div>

      <Disclaimer />
      {loadError ? <PageErrorBanner message={loadError} /> : null}
      {summaryData.positions.length === 0 ? (
        <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">
          IBKR read-only connector is not configured. Mock portfolio data is disabled, so no holdings are shown.
        </div>
      ) : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1fr_1.2fr]">
        <div className="rounded-md border border-line bg-white p-4 flex flex-col justify-between min-h-[145px]">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Portfolio Value</div>
            <div className="mt-1 text-2xl font-bold">${summaryData.summary.net_liquidation.toLocaleString()}</div>
            <div className="text-xs text-zinc-400 mt-0.5">{summaryData.summary.base_currency}</div>
          </div>
          <div className="mt-2">
            <PerformanceSparkline values={sparklineValues} />
          </div>
        </div>
        <StatCard label="Cash" value={`$${summaryData.summary.cash.toLocaleString()}`} detail={`${summaryData.risk.cash_percent.toFixed(2)}% cash`} />
        <StatCard label="Unrealized P&L" value={`$${summaryData.summary.total_unrealized_pnl.toLocaleString()}`} tone="good" />
        <RiskGauge score={summaryData.risk.risk_score} label="Portfolio Risk Score" />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <AIPnlChart history={pnlHistory} />
        <DailyActionsPanel initialRuns={scheduleData.runs ?? []} />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Largest Positions</h3>
            <Link className="text-sm text-accent hover:underline" href="/portfolio">Full portfolio</Link>
          </div>
          <HoldingsTable positions={summaryData.positions} />
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold">Sector Exposure</h3>
          <DonutChart data={summaryData.risk.sector_exposure} title="Sectors" />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold">
            <AlertTriangle size={18} aria-hidden /> Major Risk Alerts
          </h3>
          <div className="grid gap-2">
            {summaryData.risk.alerts.map((alert) => (
              <div key={alert.alert_type} className="rounded-md border border-line bg-panel p-3 text-sm">
                <div className="font-medium capitalize">{alert.severity} severity</div>
                <p className="text-zinc-700">{alert.message}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Decision-Support Suggestions</h3>
          <div className="grid gap-2">
            {topIdeas.map((item) => (
              <Link key={item.symbol} className="rounded-md border border-line p-3 hover:bg-panel" href={`/holdings/detail?symbol=${encodeURIComponent(item.symbol)}`}>
                <div className="flex justify-between text-sm">
                  <span className="font-semibold">{item.symbol}</span>
                  <span>{item.action}</span>
                </div>
                <p className="mt-1 text-xs text-zinc-600">{item.human_review_reminder}</p>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <DashboardContent />
    </Suspense>
  );
}
