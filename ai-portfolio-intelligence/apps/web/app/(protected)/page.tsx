"use client";

import { AppLink as Link } from "@/components/AppLink";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Activity, AlertTriangle, ArrowUpRight, Inbox, ListChecks } from "lucide-react";

import { Disclaimer } from "@/components/Disclaimer";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
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
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge, toneForStatus } from "@/components/ui/Badge";
import { formatCurrency, formatPercent, humanizeCode } from "@/lib/format";
import type { DecisionQueueItem } from "@/lib/types";

function DashboardContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;

  const { data, error, loading, refreshing, stale, reload } = useClientResource(
    () =>
      Promise.all([
        getPortfolioSummary(accountId),
        // P0.7 / §15.3: a failed request must surface as a degraded panel, never as an
        // empty-but-successful state. Tag the fallback so the UI can tell them apart.
        getDecisionQueue(accountId).catch(() => ({ account_id: "", queue: [], count: 0, __degraded: true })),
        getPnlHistory(accountId),
        getScheduleSettings(),
        getDataHealth().catch(() => ({ checks: [], overall_status: "unknown", __degraded: true })),
        getResearchChangeFeed(accountId).catch(() => ({ changes: [], count: 0, __degraded: true })),
      ]),
    [accountId],
  );

  if (loading) {
    return <PageLoading variant="dashboard" label="Loading dashboard" />;
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
        <PageErrorBanner message={loadError ?? "Portfolio data is unavailable."} onRetry={reload} />
      </div>
    );
  }

  const decisionQueueDegraded = Boolean((decisionQueue as { __degraded?: boolean }).__degraded);
  const dataHealthDegraded = Boolean((dataHealth as { __degraded?: boolean }).__degraded);
  const changeFeedDegraded = Boolean((changeFeed as { __degraded?: boolean }).__degraded);

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
  const dataHealthStatus = dataHealthDegraded
    ? "unavailable"
    : String((dataHealth as { overall_status?: string }).overall_status || "unknown");
  const dataHealthTone =
    toneForStatus(dataHealthStatus) === "negative"
      ? ("bad" as const)
      : toneForStatus(dataHealthStatus) === "warning"
        ? ("warn" as const)
        : toneForStatus(dataHealthStatus) === "positive"
          ? ("good" as const)
          : ("neutral" as const);

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Decision operating system"
        title="Attention required"
        description="What changed, what breaches policy, and what is waiting on your review."
        refreshing={refreshing}
        stale={stale}
        actions={
          <Link
            className="inline-flex items-center gap-2 rounded-md border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:bg-panel"
            href="/decisions"
          >
            Full decision queue <ArrowUpRight size={15} aria-hidden />
          </Link>
        }
      />

      <Disclaimer />
      {loadError ? <PageErrorBanner message={loadError} onRetry={reload} /> : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Urgent reviews"
          value={urgent.length}
          tone={urgent.length > 0 ? "warn" : "neutral"}
          detail={urgent.length === 0 ? "Nothing needs attention today" : "Priority: urgent or this week"}
        />
        <StatCard
          label="Changed today"
          value={changed.length}
          detail="Decisions whose outcome moved"
        />
        <StatCard
          label="Policy / risk alerts"
          value={summaryData.risk.alerts.length}
          tone={summaryData.risk.alerts.length > 0 ? "warn" : "neutral"}
          detail="Breaches of your IPS limits"
        />
        <StatCard
          label="Data health"
          value={humanizeCode(dataHealthStatus)}
          tone={dataHealthTone}
          detail="Coverage of the inputs behind these figures"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            icon={<ListChecks size={16} aria-hidden className="text-zinc-400" />}
            title="Decision queue"
            description="Positions whose review is open, highest priority first."
            actions={
              queue.length > 8 ? (
                <span className="text-xs text-zinc-500">Showing 8 of {queue.length}</span>
              ) : null
            }
          />
          <div className="grid gap-2">
            {decisionQueueDegraded ? (
              <DegradedStateBanner message="Decision queue unavailable — this panel is empty because the request failed, not because there are no reviews. Open Decision Center to retry." />
            ) : queue.length === 0 ? (
              <EmptyState
                title="No active reviews"
                description="Monitors continue to run in Decision Center; nothing currently needs a decision."
              />
            ) : (
              queue.slice(0, 8).map((item) => (
                <Link
                  key={item.decision_id}
                  className="rounded-md border border-hairline p-2.5 transition-colors hover:border-line hover:bg-panel"
                  href={`/decisions/${encodeURIComponent(item.decision_id)}`}
                >
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="font-semibold text-zinc-900">{item.symbol}</span>
                    <StatusBadge value={item.priority ?? "routine"} />
                  </div>
                  <p className="mt-1 text-xs leading-5 text-zinc-600">
                    {/* Only show the transition when the outcome actually moved;
                        "Review — trim → Review — trim" is noise. */}
                    {item.previous_outcome && item.previous_outcome !== item.outcome
                      ? `${humanizeCode(item.previous_outcome)} → ${humanizeCode(item.outcome)}`
                      : humanizeCode(item.outcome)}
                    {" · Top blocker: "}
                    {humanizeCode((item.blockers || [])[0], "none")}
                  </p>
                </Link>
              ))
            )}
          </div>
        </Card>
        <Card>
          <CardHeader
            icon={<Inbox size={16} aria-hidden className="text-zinc-400" />}
            title="What changed"
            description="Material moves detected since the last research packets."
          />
          <div className="grid gap-2 text-sm">
            {changeFeedDegraded ? (
              <DegradedStateBanner message="Research change feed unavailable — the request failed, so changes cannot be shown. This is not a confirmation that nothing changed." />
            ) : changes.length === 0 ? (
              <EmptyState
                title="No material changes"
                description="Nothing has moved enough to reopen a thesis since the last packets were generated."
              />
            ) : (
              changes.slice(0, 8).map((change, idx) => (
                <div
                  key={`${change.decision_id || change.symbol}-${idx}`}
                  className="flex items-center justify-between gap-3 rounded-md border border-hairline p-2.5"
                >
                  <div className="min-w-0">
                    <div className="font-medium text-zinc-900">{change.symbol || "—"}</div>
                    <p className="truncate text-xs text-zinc-600">{humanizeCode(change.change_code, "Change")}</p>
                  </div>
                  <StatusBadge value={change.severity || "info"} />
                </div>
              ))
            )}
          </div>
        </Card>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.3fr_1fr_1fr_1.1fr]">
        <StatCard
          label="Net liquidation"
          value={formatCurrency(summaryData.summary.net_liquidation, {
            currency: summaryData.summary.base_currency,
            decimals: 0,
          })}
          detail={summaryData.summary.base_currency}
          visual={<PerformanceSparkline values={sparklineValues} height={56} />}
        />
        <StatCard
          label="Cash reserve"
          value={formatCurrency(summaryData.summary.cash, {
            currency: summaryData.summary.base_currency,
            decimals: 0,
          })}
          detail={`${formatPercent(summaryData.risk.cash_percent)} of net liquidation`}
        />
        <StatCard
          label="Unrealized P&L"
          value={formatCurrency(summaryData.summary.total_unrealized_pnl, {
            currency: summaryData.summary.base_currency,
            decimals: 0,
            signed: true,
          })}
          tone={summaryData.summary.total_unrealized_pnl < 0 ? "bad" : "good"}
          detail="Across all open positions"
        />
        <RiskGauge score={summaryData.risk.risk_score} label="Risk budget used" />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            icon={<AlertTriangle size={16} aria-hidden className="text-zinc-400" />}
            title="Data health"
            description="Whether the inputs behind these numbers are complete."
            actions={
              <Link className="text-xs font-medium text-accent hover:underline" href="/data-health">
                Open
              </Link>
            }
          />
          <div className="grid gap-2">
            {dataHealthDegraded ? (
              <DegradedStateBanner message="Data health checks unavailable — the request failed. Absence of warnings here does not mean the data is healthy." />
            ) : null}
            {healthChecks.slice(0, 6).map((check) => (
              <div key={check.id} className="rounded-md border border-hairline bg-panel p-2.5 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-zinc-900">{humanizeCode(check.id)}</span>
                  <StatusBadge value={check.status} />
                </div>
                <p className="mt-0.5 text-xs leading-5 text-zinc-600">{check.detail}</p>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader
            icon={<Activity size={16} aria-hidden className="text-zinc-400" />}
            title="Sector exposure"
            description="Share of invested market value by GICS sector."
            actions={
              <Link className="text-xs font-medium text-accent hover:underline" href="/portfolio">
                Portfolio
              </Link>
            }
          />
          <DonutChart data={summaryData.risk.sector_exposure} title="Sectors" />
        </Card>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h3 className="text-[15px] font-semibold text-zinc-900">Holdings</h3>
            <p className="text-xs text-zinc-500">Sort any column; every row opens its full workspace.</p>
          </div>
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
    <Suspense fallback={<PageLoading variant="dashboard" />}>
      <DashboardContent />
    </Suspense>
  );
}
