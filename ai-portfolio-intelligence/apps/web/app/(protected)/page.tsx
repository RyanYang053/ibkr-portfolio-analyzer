"use client";

import { AppLink as Link } from "@/components/AppLink";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowUpRight } from "lucide-react";

import { Disclaimer } from "@/components/Disclaimer";
import { HoldingsTable } from "@/components/HoldingsTable";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import {
  getDataHealth,
  getDecisionQueue,
  getPnlHistory,
  getPortfolioSummary,
  getResearchChangeFeed,
  getScheduleSettings,
} from "@/lib/api";
import { RiskGauge } from "@/components/RiskGauge";
import { DonutChart } from "@/components/DonutChart";
import { PerformanceSparkline } from "@/components/PerformanceSparkline";
import { useClientResource } from "@/lib/use-client-resource";
import type { DecisionQueueItem } from "@/lib/types";

function DashboardContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;

  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getPortfolioSummary(accountId),
        getDecisionQueue(accountId).catch(() => ({ account_id: "", queue: [], count: 0 })),
        getPnlHistory(accountId),
        getScheduleSettings(),
        getDataHealth().catch(() => ({ checks: [], overall_status: "unknown" })),
        getResearchChangeFeed(accountId).catch(() => ({ changes: [], count: 0 })),
      ]),
    [accountId],
  );

  if (loading) {
    return <PageLoading />;
  }

  let loadError = error;
  const [summaryData, decisionQueue, pnlHistory, scheduleData, dataHealth, changeFeed] = data ?? [
    null,
    { account_id: "", queue: [] as DecisionQueueItem[], count: 0 },
    [],
    { runs: [] },
    { checks: [], overall_status: "unknown" },
    { changes: [], count: 0 },
  ];

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

  const queue = decisionQueue?.queue ?? [];
  const urgent = queue.filter((item) =>
    ["urgent", "this_week", "critical", "high"].includes(String(item.priority || "")),
  );
  const changed = queue.filter((item) => item.previous_outcome && item.previous_outcome !== item.outcome);
  const sparklineValues =
    pnlHistory && pnlHistory.length >= 2
      ? pnlHistory.map((entry: { net_liquidation: number }) => entry.net_liquidation)
      : [summaryData.summary.net_liquidation, summaryData.summary.net_liquidation];
  const healthChecks = Array.isArray((dataHealth as { checks?: unknown }).checks)
    ? ((dataHealth as { checks: Array<Record<string, string>> }).checks)
    : [];
  const changes = Array.isArray((changeFeed as { changes?: unknown }).changes)
    ? ((changeFeed as { changes: Array<Record<string, string>> }).changes)
    : [];

  return (
    <div className="grid gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">Decision operating system</p>
          <h2 className="text-3xl font-semibold">Attention required</h2>
        </div>
        <Link className="inline-flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm hover:bg-panel" href="/decisions">
          Full decision queue <ArrowUpRight size={16} aria-hidden />
        </Link>
      </div>

      <Disclaimer />
      {loadError ? <PageErrorBanner message={loadError} /> : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Urgent reviews</div>
          <div className="mt-1 text-2xl font-bold">{urgent.length}</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Changed today</div>
          <div className="mt-1 text-2xl font-bold">{changed.length}</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Policy / risk alerts</div>
          <div className="mt-1 text-2xl font-bold">{summaryData.risk.alerts.length}</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Data health</div>
          <div className="mt-1 text-2xl font-bold capitalize">
            {String((dataHealth as { overall_status?: string }).overall_status || "unknown")}
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Decision queue</h3>
          <div className="grid gap-2">
            {queue.slice(0, 8).length === 0 ? (
              <p className="text-sm text-zinc-600">No active reviews. Monitors stay in Decision Center.</p>
            ) : (
              queue.slice(0, 8).map((item) => (
                <Link
                  key={item.decision_id}
                  className="rounded-md border border-line p-3 hover:bg-panel"
                  href={`/decisions/${encodeURIComponent(item.decision_id)}`}
                >
                  <div className="flex justify-between text-sm">
                    <span className="font-semibold">{item.symbol}</span>
                    <span>{item.outcome}</span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-600">
                    {item.previous_outcome ? `${item.previous_outcome} → ${item.outcome} · ` : ""}
                    Priority {item.priority ?? "routine"} · Top blocker {(item.blockers || [])[0] || "none"}
                  </p>
                </Link>
              ))
            )}
          </div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">What changed</h3>
          <div className="grid gap-2 text-sm">
            {changes.slice(0, 8).length === 0 ? (
              <p className="text-zinc-600">No material changes detected since last packets.</p>
            ) : (
              changes.slice(0, 8).map((change, idx) => (
                <div key={`${change.decision_id || change.symbol}-${idx}`} className="rounded-md border border-line p-3">
                  <div className="font-medium">
                    {change.symbol || "—"} · {change.change_code || "change"}
                  </div>
                  <p className="text-xs text-zinc-600">Severity {change.severity || "info"}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1fr_1.2fr]">
        <div className="rounded-md border border-line bg-white p-4 flex flex-col justify-between min-h-[145px]">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Net liquidation</div>
            <div className="mt-1 text-2xl font-bold">${summaryData.summary.net_liquidation.toLocaleString()}</div>
            <div className="text-xs text-zinc-400 mt-0.5">{summaryData.summary.base_currency}</div>
          </div>
          <div className="mt-2">
            <PerformanceSparkline values={sparklineValues} />
          </div>
        </div>
        <StatCard label="Cash reserve" value={`$${summaryData.summary.cash.toLocaleString()}`} detail={`${summaryData.risk.cash_percent.toFixed(2)}% cash`} />
        <StatCard label="Unrealized P&L" value={`$${summaryData.summary.total_unrealized_pnl.toLocaleString()}`} tone="good" />
        <RiskGauge score={summaryData.risk.risk_score} label="Risk budget used" />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold">
            <AlertTriangle size={18} aria-hidden /> Data health
          </h3>
          <div className="grid gap-2">
            {healthChecks.slice(0, 6).map((check) => (
              <div key={check.id} className="rounded-md border border-line bg-panel p-3 text-sm">
                <div className="font-medium capitalize">
                  {check.id.replaceAll("_", " ")} · {check.status}
                </div>
                <p className="text-zinc-700">{check.detail}</p>
              </div>
            ))}
          </div>
          <Link className="mt-3 inline-block text-sm text-accent hover:underline" href="/data-health">
            Open data health
          </Link>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Sector exposure</h3>
            <Link className="text-sm text-accent hover:underline" href="/portfolio">
              Portfolio
            </Link>
          </div>
          <DonutChart data={summaryData.risk.sector_exposure} title="Sectors" />
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Largest positions</h3>
          <span className="text-xs text-zinc-500">
            Scheduler runs: {(scheduleData.runs ?? []).length}
          </span>
        </div>
        <HoldingsTable positions={summaryData.positions} />
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
